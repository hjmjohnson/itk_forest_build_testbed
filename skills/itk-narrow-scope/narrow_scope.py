#!/usr/bin/env python3
"""Move a local declaration into the narrowest nested scope that holds every use of it.

Edits the working tree and writes a manifest; never commits.
"""

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "itk-init-over-assign" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ioa.comments import check_hunks, unified_diff  # noqa: E402
from ioa.compile_commands import find_graph  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.query import run_query  # noqa: E402
from ioa.skip import Reason  # noqa: E402
from ioa.tidy import Doc, apply_edits, format_changed, in_scope, map_line, opcodes  # noqa: E402
from scopes import Decl, Move, Source, accept, edits, plan, replacements, signature  # noqa: E402

KIND = "narrow-scope"
CLS = "narrow-scope"
MATCHERS = [Path(__file__).resolve().parent / "matchers" / "var_uses.cq"]


@dataclass
class Candidate:
    file: Path
    line: int
    col: int
    name: str
    types: set[str] = field(default_factory=set)
    trivial: set[str] = field(default_factory=set)
    static: bool = False
    ctor: bool = False


def candidates(graph: Path, root: Path) -> tuple[list[Candidate], list[str]]:
    """Local declarations, one per location, with type facts merged across instantiations."""
    matches, dropped = run_query(graph, MATCHERS, root=root)
    found: dict[tuple[Path, int, int], Candidate] = {}
    for m in matches:
        n = m.node
        path = n.file.resolve()
        if n.kind != "VarDecl" or not n.name or not path.is_file() or not in_scope(path, root):
            continue
        c = found.setdefault((path, n.line, n.col), Candidate(path, n.line, n.col, n.name))
        if m.binding == "local":
            c.types.add(n.canonical)
        elif m.binding == "trivial":
            c.trivial.add(n.canonical)
        elif m.binding == "static":
            c.static = True
        elif m.binding == "ctor":
            c.ctor = True
    return sorted((c for c in found.values() if c.types), key=lambda c: (c.file, c.line, c.col)), dropped


def _offset(doc: Doc, line: int, col: int) -> int:
    lines = doc.data.split(b"\n")
    return doc.c(sum(len(x) + 1 for x in lines[:line - 1]) + col - 1)


def plan_all(cands: list[Candidate], docs: dict[Path, Doc],
             sources: dict[Path, Source]) -> list[tuple[Path, Move]]:
    out: list[tuple[Path, Move]] = []
    for c in cands:
        doc = docs.setdefault(c.file, Doc(c.file))
        src = sources.setdefault(c.file, Source(doc.text))
        mv = plan(src, Decl(_offset(doc, c.line, c.col), c.name, c.types <= c.trivial, c.static, c.ctor))
        if mv is not None:
            out.append((c.file, mv))
    return out


def _site(root: Path, path: Path, a: int, b: int, text: str, **kw) -> Site:
    n = max(1, text.count("\n"))
    start = min(max(1, a), n)
    return Site(path.relative_to(root), start, min(max(start, b), n), KIND, CLS, **kw)


def locate(text: str, sig: str, near: int) -> tuple[int, int] | None:
    """1-based first and last line of the whitespace-free signature nearest line `near`."""
    chars: list[str] = []
    line_of: list[int] = []
    for i, ln in enumerate(text.split("\n"), 1):
        for ch in ln:
            if not ch.isspace():
                chars.append(ch)
                line_of.append(i)
    flat = "".join(chars)
    best = None
    k = flat.find(sig)
    while k >= 0:
        span = (line_of[k], line_of[k + len(sig) - 1])
        if best is None or abs(span[0] - near) < abs(best[0] - near):
            best = span
        k = flat.find(sig, k + 1)
    return best


def _original(root: Path, path: Path, mv: Move, text: str, ops: list[tuple], **kw) -> Site:
    first, last = mv.lines
    a = map_line(ops, first, False) + 1 if ops else first + 1
    b = map_line(ops, last + 1, True) if ops else last + 1
    return _site(root, path, a, b, text, **kw)


def run(graph: Path, root: Path, manifest: Path | None, apply: bool) -> int:
    cands, dropped = candidates(graph, root)
    if dropped:
        print(f"narrow-scope: dropped {len(dropped)} TU(s) that failed to parse: {', '.join(dropped)}")
    docs: dict[Path, Doc] = {}
    sources: dict[Path, Source] = {}
    plans = plan_all(cands, docs, sources)
    moving: dict[Path, list[Move]] = defaultdict(list)
    for path, mv in plans:
        if mv.skipped is None:
            moving[path].append(mv)
    kept = {id(mv) for path, mvs in moving.items() for mv in accept(sources[path], mvs)}
    deferred = sum(1 for _, mv in plans if mv.skipped is None and id(mv) not in kept)
    plans = [(p, mv) for p, mv in plans if mv.skipped is not None or id(mv) in kept]

    if not apply:
        counts: dict[tuple[str, Path], int] = defaultdict(int)
        for path, mv in plans:
            label = CLS if mv.skipped is None else f"skipped:{mv.skipped}"
            counts[(label, path.relative_to(root))] += 1
        for (label, rel), n in sorted(counts.items()):
            print(f"{label} {rel} {n}")
        return 0

    changes = {
        path: replacements(sources[path], [mv for mv in mvs if id(mv) in kept], edits)
        for path, mvs in moving.items()
    }
    changes = {p: es for p, es in changes.items() if es}
    if changes:
        apply_edits(changes, docs, name=KIND)
        for path in changes:
            format_changed(path, docs[path].text)

    after = {p: p.read_text(errors="surrogateescape") for p in changes}
    bad: dict[Path, tuple[Reason, str]] = {}
    for path in changes:
        rel = str(path.relative_to(root))
        stranded = check_hunks(unified_diff(rel, docs[path].text, after[path]))
        if stranded:
            bad[path] = (Reason.COMMENT_STRANDED, stranded[0].text)

    placed: list[tuple[Path, Move, Site | None]] = []
    for path, mv in plans:
        old = docs[path].text
        new = after.get(path, old)
        ops = opcodes(old, new) if path in after else []
        if mv.skipped is not None or path in bad:
            placed.append((path, mv, _original(root, path, mv, new, ops, skipped=mv.skipped, note=mv.note)))
            continue
        start = map_line(ops, mv.lines[0], False) + 1
        found = locate(new, signature(sources[path], mv), start)
        if found is None:
            bad[path] = (Reason.GATE_FAILED, "moved-declaration-not-found")
            placed.append((path, mv, None))
            continue
        placed.append((path, mv, _site(root, path, start, found[1], new, note=mv.target.form)))

    for path in bad:
        path.write_bytes(docs[path].data)
    out: list[Site] = []
    for path, mv, s in placed:
        if path in bad and mv.skipped is None:
            reason, note = bad[path]
            s = _original(root, path, mv, docs[path].text, [], skipped=reason, note=note)
        elif path in bad:
            s = _original(root, path, mv, docs[path].text, [], skipped=mv.skipped, note=mv.note)
        out.append(s)

    if manifest is not None:
        Manifest(KIND, out).write(manifest)
    applied = sum(1 for s in out if s.skipped is None)
    print(f"narrow-scope: {applied} applied, {len(out) - applied} skipped, {deferred} deferred to a "
          f"later run, {len(dropped)} TU(s) dropped")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True, type=Path,
                    help="build dir holding compile_commands.json, or a parent of it")
    ap.add_argument("--repo", required=True, type=Path, help="repository root")
    ap.add_argument("--manifest", type=Path, help="manifest path (written only with --apply)")
    ap.add_argument("--apply", action="store_true", help="edit the working tree")
    args = ap.parse_args(argv)
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
