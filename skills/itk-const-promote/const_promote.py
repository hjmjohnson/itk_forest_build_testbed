#!/usr/bin/env python3
"""Promote the locals a prior init-over-assign stage initialized to const, and to
constexpr when the initializer is a compile-time literal, using clang-tidy
misc-const-correctness.

Edits the working tree and writes a manifest; never commits.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "itk-init-over-assign" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from constexpr_rule import mask, promotable  # noqa: E402
from ioa.compile_commands import NinjaNotFoundError, find_graph, including_tus  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.skip import Reason  # noqa: E402
from ioa.tidy import (  # noqa: E402
    Diag, Doc, apply_edits, format_changed, in_scope, map_line, opcodes, run_tidy,
)

CHECK = "misc-const-correctness"
OPTIONS = {
    "AnalyzeValues": True,
    "AnalyzeReferences": True,
    "WarnPointersAsValues": False,
    "TransformValues": True,
    "TransformReferences": True,
    "TransformPointersAsValues": False,
}
KINDS = ("local-const", "container-const", "itk-helpers-constexpr")
CONST, CONSTEXPR = "const", "constexpr"
MESSAGE = re.compile(r"^variable '([^']+)' of type '([^']*)'(?: \(aka '([^']*)'\))? can be declared 'const'")
SOURCE_SUFFIXES = {".cxx", ".cpp", ".cc", ".c++", ".C"}
CONDITIONAL = re.compile(r"(?m)^[ \t]*#[ \t]*(?:if|ifdef|ifndef|elif|else|endif)\b")
AUTO = re.compile(r"(?<![\w:])auto\b(?=\s*[&*]*\s*[A-Za-z_]\w*\s*[={(])")


@dataclass(frozen=True)
class Hit:
    file: Path
    begin: int
    name: str
    ctype: str


@dataclass
class Plan:
    file: Path
    begin: int
    end: int
    cls: str
    skipped: Reason | None = None
    note: str = ""


def statement_end(code: str, begin: int) -> int:
    """Offset of the `;` (or unmatched `)`) ending the declaration at begin; code is masked."""
    depth = 0
    for i in range(begin, len(code)):
        ch = code[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif ch == ";" and depth == 0:
            return i
    return len(code)


def guarded(code: str, begin: int) -> bool:
    """A conditional directive between the declaration and the end of its scope."""
    depth = 0
    for i in range(begin, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            if depth == 0:
                return bool(CONDITIONAL.search(code, begin, i))
            depth -= 1
    return bool(CONDITIONAL.search(code, begin))


def has_second_declarator(code: str, name_end: int, end: int) -> bool:
    depth = angle = 0
    for i in range(name_end, end):
        ch = code[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "<" and i and (code[i - 1].isalnum() or code[i - 1] == "_"):
            angle += 1
        elif ch == ">" and angle and code[i - 1] != "-":
            angle -= 1
        elif ch == "," and depth == 0 and angle == 0:
            return True
    return False


def ranges_of(prior: Manifest, root: Path) -> dict[Path, list[tuple[int, int]]]:
    out: dict[Path, list[tuple[int, int]]] = defaultdict(list)
    for s in prior.applied():
        out[(root / s.file).resolve()].append((s.start, s.end))
    return out


def near(ranges: list[tuple[int, int]], first: int, last: int) -> bool:
    return any(first <= b + 1 and last >= a - 1 for a, b in ranges)


def translation_units(files: list[Path], graph: Path, root: Path) -> list[Path]:
    data = json.loads((graph / "compile_commands.json").read_text())
    known = {(Path(e["directory"]) / e["file"]).resolve() for e in data}
    tus: list[Path] = []
    for f in files:
        if f in known:
            tus.append(f)
            continue
        try:
            found = [(root / t).resolve() for t in including_tus(f, graph, root, cap=1)]
        except NinjaNotFoundError:
            found = []
        if not found:
            print(f"const-promote: no translation unit includes {f.relative_to(root)}; not analyzed")
        tus += [t for t in found if t not in tus]
    return tus


def auto_count(doc: Doc, code: str, ranges: list[tuple[int, int]]) -> int:
    """Plain `auto` locals near a prior site; misc-const-correctness never reports them."""
    n = 0
    for m in AUTO.finditer(code):
        prev = code[: m.start()].rstrip()
        if prev and prev[-1] not in ";{}":
            continue
        end = statement_end(code, m.start())
        n += near(ranges, doc.line(m.start()) + 1, doc.line(end) + 1)
    return n


def locate(diags: list[Diag], docs: dict[Path, Doc]) -> list[Hit]:
    """Diagnostics on the analyzed files, at character offsets."""
    out = []
    for d in diags:
        msg = MESSAGE.match(d.message)
        if d.file is None or d.offset is None or msg is None or d.file.resolve() not in docs:
            continue
        path = d.file.resolve()
        out.append(Hit(path, docs[path].c(d.offset), msg[1], msg[3] or msg[2]))
    return out


def plan_hits(hits: list[Hit], docs: dict[Path, Doc], ranges: dict[Path, list[tuple[int, int]]]) -> list[tuple]:
    """(Plan, first line, last line) per declaration, 1-based lines of the original text."""
    found: dict[tuple[Path, int], list[tuple[str, str]]] = defaultdict(list)
    for h in dict.fromkeys(hits):
        found[(h.file, h.begin)].append((h.name, h.ctype))
    out = []
    masked: dict[Path, str] = {}
    for (path, begin), names in sorted(found.items()):
        doc = docs[path]
        code = masked.setdefault(path, mask(doc.text, literals=True))
        end = statement_end(code, begin)
        first, last = doc.line(begin) + 1, doc.line(end) + 1
        if not near(ranges[path], first, last):
            continue
        decl = doc.text[begin:end + 1]
        name, ctype = names[0]
        plan = Plan(path, begin, end, CONST)
        head = re.search(rf"(?<![\w:]){re.escape(name)}(?!\w)", code[begin:end])
        if re.match(r"(?:static|thread_local)\b", code[begin:end]) or (
            head and re.search(r"\b(?:static|thread_local)\b", code[begin:begin + head.start()])
        ):
            plan.skipped = Reason.STATIC_LOCAL
        elif guarded(code, begin):
            plan.skipped = Reason.PREPROCESSOR
        elif head is None:
            plan.skipped, plan.note = Reason.GATE_FAILED, "declaration-not-found"
        elif len(names) > 1 or has_second_declarator(code, begin + head.end(), end):
            plan.skipped, plan.note = Reason.GATE_FAILED, "multiple-declarators"
        elif re.match(r"(?:\[\[|alignas\b|extern\b|register\b)", code[begin:end]):
            plan.skipped, plan.note = Reason.GATE_FAILED, "unsupported-specifier"
        elif promotable(decl, name, ctype):
            plan.cls = CONSTEXPR
        out.append((plan, first, last))
    return sorted(out, key=lambda t: (t[0].file, t[0].begin))


def follow(ops: list[tuple], x: int, end: bool) -> int:
    """map_line, but line by line through a same-size replace (realigned declarations)."""
    for tag, i1, i2, j1, j2 in ops:
        if tag == "replace" and i2 - i1 == j2 - j1 and ((i1 < x <= i2) if end else (i1 <= x < i2)):
            return j1 + (x - i1)
    return map_line(ops, x, end)


def site(root: Path, path: Path, first: int, last: int, kind: str, cls: str, text: str, **kw) -> Site:
    n = max(1, text.count("\n"))
    start = min(max(1, first), n)
    return Site(path.relative_to(root), start, min(max(start, last), n), kind, cls, **kw)


def run(graph: Path, root: Path, manifest: Path | None, only_from: Path, kind: str, apply: bool) -> int:
    ranges = {p: r for p, r in ranges_of(Manifest.read(only_from), root).items()
              if p.is_file() and in_scope(p, root)}
    files = sorted(ranges)
    tus = translation_units(files, graph, root)
    diags, dropped = run_tidy(graph, root, CHECK, OPTIONS, tus)
    docs = {p: Doc(p) for p in files}
    hits = locate(diags, docs)
    if dropped:
        print(f"const-promote: dropped {len(dropped)} TU(s) that failed to compile: {', '.join(dropped)}")
    plans = plan_hits(hits, docs, ranges)

    if not apply:
        counts: dict[tuple[str, Path], int] = defaultdict(int)
        for plan, _, _ in plans:
            label = plan.cls if plan.skipped is None else f"skipped:{plan.skipped}"
            counts[(label, plan.file.relative_to(root))] += 1
        for (label, rel), n in sorted(counts.items()):
            print(f"{label} {rel} {n}")
        for path in files:
            n = auto_count(docs[path], mask(docs[path].text, literals=True), ranges[path])
            if n:
                print(f"auto-unanalyzed {path.relative_to(root)} {n}")
        return 0

    edits: dict[Path, list[tuple[int, int, str]]] = defaultdict(list)
    for plan, _, _ in plans:
        if plan.skipped is None:
            edits[plan.file].append((plan.begin, plan.begin, f"{plan.cls} "))
    if edits:
        apply_edits(edits, docs, name="const-promote")
        for path in edits:
            format_changed(path, docs[path].text)
    sites: list[Site] = []
    after = {p: p.read_text(errors="surrogateescape") for p in edits}
    ops = {p: opcodes(docs[p].text, t) for p, t in after.items()}
    for plan, first, last in plans:
        new = after.get(plan.file, docs[plan.file].text)
        moved = ops.get(plan.file, [])
        a, b = follow(moved, first - 1, False) + 1, follow(moved, last, True)
        sites.append(site(root, plan.file, a, b, kind, plan.cls, new, skipped=plan.skipped, note=plan.note))

    autos = sum(auto_count(docs[p], mask(docs[p].text, literals=True), ranges[p]) for p in files)
    notes = [f"{autos} plain auto local(s) near a prior site left unanalyzed"] if autos else []
    if manifest is not None:
        Manifest(kind, sites, notes=notes).write(manifest)
    applied = sum(1 for s in sites if s.skipped is None)
    print(f"const-promote: {applied} applied, {len(sites) - applied} skipped, {len(dropped)} TU(s) dropped")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True, type=Path,
                    help="build dir holding compile_commands.json, or a parent of it")
    ap.add_argument("--repo", required=True, type=Path, help="repository root")
    ap.add_argument("--manifest", type=Path, help="manifest path (written only with --apply)")
    ap.add_argument("--only-from", required=True, type=Path,
                    help="manifest of the stage whose applied sites this run may promote")
    ap.add_argument("--kind", required=True, choices=KINDS, help="manifest kind for this run")
    ap.add_argument("--apply", action="store_true", help="edit the working tree")
    args = ap.parse_args(argv)
    root = args.repo.resolve()
    if not root.is_dir():
        ap.error(f"--repo {args.repo} is not a directory")
    if not args.only_from.is_file():
        ap.error(f"--only-from {args.only_from} is not a file")
    graph = args.graph.resolve()
    if not (graph / "compile_commands.json").exists():
        graph = find_graph(graph, root.name)
    return run(graph, root, args.manifest, args.only_from, args.kind, args.apply)


if __name__ == "__main__":
    sys.exit(main())
