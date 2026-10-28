#!/usr/bin/env python3
"""Rewrite a default-constructed local followed by `v.Fill(k);` into a single initialization:
`T v{};` for a zero fill, else `auto v = T::Filled(k);` or `auto v = itk::MakeFilled<T>(k);`.

Edits the working tree and writes a manifest of kind itk-helpers; never commits.
"""

import argparse
import functools
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "itk-init-over-assign" / "lib"))

from ioa.comments import check_hunks, unified_diff  # noqa: E402
from ioa.compile_commands import find_graph  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.preflight import itk_version as _itk_version_text  # noqa: E402
from ioa.query import run_query  # noqa: E402
from ioa.skip import Reason  # noqa: E402
from ioa.source import mask  # noqa: E402
from ioa.tidy import Doc, apply_edits, format_changed, in_scope, map_line, opcodes  # noqa: E402

KIND = "itk-helpers"
MAKE_FILLED_SINCE = (5, 3)
MATCHERS = [Path(__file__).resolve().parent / "matchers" / n
            for n in ("fill_candidate.cq", "own_filled.cq", "user_ctor.cq", "fixed_size.cq")]
CONSTEXPR_TYPES = re.compile(r"^(?:const )?itk::(?:Size|Index|Offset)<")
LITERAL = re.compile(r"[-+]?(?:0[xX][0-9a-fA-F']+|(?:\d[\d']*\.?[\d']*|\.\d+)(?:[eE][-+]?\d+)?)[uUlLfF]*")
ZERO_TRAIT = re.compile(r"(?:itk::)?NumericTraits<.+>::ZeroValue\(\)")
MUTATING_CALL = re.compile(r"^(?:Set|Fill)|^(?:begin|end|data)$")
ASSIGN_OPS = ("++", "--", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=")


@dataclass
class Candidate:
    file: Path
    line: int
    col: int
    name: str
    canonicals: set[str] = field(default_factory=set)
    own_filled: set[str] = field(default_factory=set)
    user_ctor: set[str] = field(default_factory=set)
    fixed_size: set[str] = field(default_factory=set)


@dataclass
class Pair:
    begin: int
    end: int
    first: int
    last: int
    type: str
    name: str
    arg: str
    comment: str
    own_filled: bool
    user_ctor: bool
    constexpr_ok: bool
    fixed_size: bool

    @property
    def cls(self) -> str:
        return "fill_zero" if is_zero(self.arg) else "fill_nonzero"

    @property
    def skipped(self) -> Reason | None:
        return None if self.fixed_size else Reason.GATE_FAILED


def is_literal(arg: str) -> bool:
    return LITERAL.fullmatch(arg) is not None


def is_zero(arg: str) -> bool:
    if ZERO_TRAIT.fullmatch(arg):
        return True
    if not is_literal(arg):
        return False
    s = arg.replace("'", "").lstrip("+-")
    if not s.lower().startswith("0x"):
        s = s.rstrip("uUlLfF")
    try:
        return (int(s, 0) if re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", s) else float(s)) == 0
    except ValueError:
        return False


def render(p: Pair) -> str:
    if p.cls == "fill_zero" and not p.user_ctor:
        decl = f"{p.type} {p.name}{{}};"
    else:
        call = (f"{p.type.removeprefix('typename ').strip()}::Filled({p.arg})" if p.own_filled
                else f"itk::MakeFilled<{p.type}>({p.arg})")
        head = "constexpr auto" if p.constexpr_ok and is_literal(p.arg) else "auto"
        decl = f"{head} {p.name} = {call};"
    return f"{decl} {p.comment}" if p.comment else decl


def candidates(graph: Path, root: Path) -> tuple[list[Candidate], list[str]]:
    matches, dropped = run_query(graph, MATCHERS, root=root)
    found: dict[tuple[Path, int, int], Candidate] = {}
    for m in matches:
        n = m.node
        path = n.file.resolve()
        if n.kind != "VarDecl" or not n.name or not path.is_file() or not in_scope(path, root):
            continue
        c = found.setdefault((path, n.line, n.col), Candidate(path, n.line, n.col, n.name))
        {"fill": c.canonicals, "own_filled": c.own_filled, "user_ctor": c.user_ctor,
         "fixed_size": c.fixed_size}[m.binding].add(n.canonical)
    return sorted((c for c in found.values() if c.canonicals), key=lambda c: (c.file, c.line, c.col)), dropped


def _close(masked: str, i: int, open_: str, close: str) -> int:
    depth = 0
    for k in range(i, len(masked)):
        if masked[k] == open_:
            depth += 1
        elif masked[k] == close:
            depth -= 1
            if depth == 0:
                return k
    return -1


def _top_level_comma(s: str) -> bool:
    depth = 0
    for ch in s:
        depth += ch in "(<[{"
        depth -= ch in ")>]}"
        if ch == "," and depth == 0:
            return True
    return False


def mutated_later(masked: str, start: int, name: str) -> bool:
    """Conservative text check for a write to name before its enclosing block closes."""
    depth, stop = 0, len(masked)
    for k in range(start, len(masked)):
        depth += masked[k] == "{"
        depth -= masked[k] == "}"
        if depth < 0:
            stop = k
            break
    for m in re.finditer(rf"(?<![\w.>:]){re.escape(name)}\b", masked[:stop]):
        if m.start() < start:
            continue
        before = masked[:m.start()].rstrip()
        if before.endswith(("++", "--")) or (before.endswith("&") and not before.endswith("&&")) \
                or (before.endswith(":") and not before.endswith("::")):
            return True
        i = m.end()
        while True:
            while i < stop and masked[i].isspace():
                i += 1
            member = re.match(r"(?:\.|->)\s*(\w+)\s*(\(?)", masked[i:stop])
            if member:
                if member[2] and MUTATING_CALL.search(member[1]):
                    return True
                i += member.end() - len(member[2])
            elif i < stop and masked[i] in "[(":
                j = _close(masked, i, masked[i], "]" if masked[i] == "[" else ")")
                if j < 0:
                    return True
                i = j + 1
            else:
                break
        after = masked[i:stop]
        if after.startswith(ASSIGN_OPS) or (after.startswith("=") and not after.startswith("==")):
            return True
    return False


@functools.lru_cache(maxsize=4)
def _masked(text: str) -> str:
    return mask(text)


def pair(doc: Doc, c: Candidate) -> Pair | None:
    """The `T v;` declaration at c and the `v.Fill(k);` statement on the next line, if that is the shape."""
    text, masked, name = doc.text, _masked(doc.text), c.name
    line_start = doc.c(sum(len(s) for s in doc.data.splitlines(True)[:c.line - 1]))
    begin = doc.c(doc.b(line_start) + c.col - 1)
    if text[line_start:begin].strip():
        return None
    semi = masked.find(";", begin)
    decl = re.fullmatch(rf"(?P<type>\S.*?)\s+{re.escape(name)}", masked[begin:semi], re.S)
    if semi < 0 or not decl or _top_level_comma(decl["type"]):
        return None
    type_ = text[begin:begin + len(decl["type"])]
    tail = re.compile(r"[ \t]*(//[^\n]*)?(?=\n|$)")
    decl_tail = tail.match(text, semi + 1)
    if not decl_tail or mask(decl_tail[0]).strip():
        return None
    fill = re.compile(rf"\n[ \t]*{re.escape(name)}\s*\.\s*Fill\s*\(").match(masked, decl_tail.end())
    if not fill:
        return None
    close = _close(masked, fill.end() - 1, "(", ")")
    end_stmt = re.compile(r"\s*;").match(masked, close + 1) if close > 0 else None
    fill_tail = tail.match(text, end_stmt.end()) if end_stmt else None
    if not fill_tail or mask(fill_tail[0]).strip():
        return None
    raw = text[fill.end():close]
    arg = raw.strip()
    if (not arg or mask(raw) != raw or _top_level_comma(arg) or "\n" in arg
            or re.search(rf"\b{re.escape(name)}\b", arg)):
        return None
    comments = [t[1] for t in (decl_tail, fill_tail) if t[1]]
    if len(comments) > 1:
        return None
    return Pair(
        begin, fill_tail.end(), c.line, c.line + 1, type_, name, arg, comments[0] if comments else "",
        own_filled=c.own_filled >= c.canonicals,
        user_ctor=bool(c.user_ctor),
        constexpr_ok=all(CONSTEXPR_TYPES.match(t) for t in c.canonicals)
        and not mutated_later(masked, fill_tail.end(), name),
        fixed_size=c.fixed_size >= c.canonicals,
    )


def itk_version(graph: Path) -> tuple[int, int] | None:
    m = re.match(r"(\d+)\.(\d+)", _itk_version_text(graph))
    return (int(m[1]), int(m[2])) if m else None


def _site(root: Path, path: Path, a: int, b: int, cls: str, text: str, **kw) -> Site:
    n = max(1, text.count("\n"))
    start = min(max(1, a), n)
    return Site(path.relative_to(root), start, min(max(start, b), n), KIND, cls, **kw)


def run(graph: Path, root: Path, manifest: Path | None, apply: bool) -> int:
    cands, dropped = candidates(graph, root)
    if dropped:
        print(f"sizetype-filled: dropped {len(dropped)} TU(s) that failed to parse: {', '.join(dropped)}")
    docs: dict[Path, Doc] = {}
    plans: list[tuple[Path, Pair]] = []
    for c in cands:
        p = pair(docs.setdefault(c.file, Doc(c.file)), c)
        if p is not None:
            plans.append((c.file, p))

    version = itk_version(graph)
    if version is None:
        print(f"sizetype-filled: ITK version unreadable from {graph}; assuming >= 5.3")
    too_old = version is not None and version < MAKE_FILLED_SINCE

    def blocked(p: Pair) -> bool:
        return too_old and p.skipped is None and "MakeFilled" in render(p)

    if not apply:
        counts: dict[tuple[str, Path], int] = defaultdict(int)
        for path, p in plans:
            reason = Reason.ITK_VERSION if blocked(p) else p.skipped
            counts[(p.cls if reason is None else f"skipped:{reason}", path.relative_to(root))] += 1
        for (cls, rel), n in sorted(counts.items()):
            print(f"{cls} {rel} {n}")
        return 0

    edits: dict[Path, list[tuple[int, int, str]]] = defaultdict(list)
    for path, p in plans:
        if p.skipped is None and not blocked(p):
            edits[path].append((p.begin, p.end, render(p)))
    if edits:
        apply_edits(edits, docs, name="sizetype-filled")
        for path in edits:
            format_changed(path, docs[path].text)

    after = {p: p.read_text(errors="surrogateescape") for p in edits}
    sites: list[Site] = []
    for path, p in plans:
        new = after.get(path, docs[path].text)
        ops = opcodes(docs[path].text, new)
        a, b = map_line(ops, p.first - 1, False) + 1, map_line(ops, p.last, True)
        if blocked(p):
            sites.append(_site(root, path, a, b, p.cls, new, skipped=Reason.ITK_VERSION,
                               note=f"itk:{version[0]}.{version[1]}"))
            continue
        note = "" if p.skipped is None else "not-fixed-size"
        sites.append(_site(root, path, a, b, p.cls, new, skipped=p.skipped, note=note))

    notes: dict[Path, str] = {}
    for path in edits:
        stranded = check_hunks(unified_diff(str(path.relative_to(root)), docs[path].text, after[path]))
        if stranded:
            notes[path] = stranded[0].text
            path.write_bytes(docs[path].data)
    for i, (path, p) in enumerate(plans):
        if path in notes:
            s = sites[i]
            reason, note = (Reason.COMMENT_STRANDED, notes[path]) if s.skipped is None else (s.skipped, s.note)
            sites[i] = _site(root, path, p.first, p.last, p.cls, docs[path].text, skipped=reason, note=note)

    if manifest is not None:
        Manifest(KIND, sites).write(manifest)
    applied = sum(1 for s in sites if s.skipped is None)
    print(f"sizetype-filled: {applied} applied, {len(sites) - applied} skipped, {len(dropped)} TU(s) dropped")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True, type=Path,
                    help="build dir holding compile_commands.json, or a parent of it")
    ap.add_argument("--repo", required=True, type=Path, help="repository root")
    ap.add_argument("--manifest", type=Path, help="manifest path (written only with --apply)")
    ap.add_argument("--apply", action="store_true", help="edit the working tree")
    from ioa.tidy import add_llvm_bin_option, use_llvm_bin

    add_llvm_bin_option(ap)
    args = ap.parse_args(argv)
    use_llvm_bin(args)
    if args.apply and args.manifest is None:
        ap.error("--apply needs --manifest")
    root = args.repo.resolve()
    if not root.is_dir():
        ap.error(f"--repo {args.repo} is not a directory")
    graph = args.graph.resolve()
    if not (graph / "compile_commands.json").exists():
        graph = find_graph(graph, root.name)
    return run(graph, root, args.manifest, args.apply)


if __name__ == "__main__":
    sys.exit(main())
