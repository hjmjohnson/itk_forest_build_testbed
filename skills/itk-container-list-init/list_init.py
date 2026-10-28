#!/usr/bin/env python3
"""Rewrite a default-constructed std::vector, std::array, itk::Array, or vnl_vector local
followed only by appends or constant-index assignments into brace initialization.

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
from runs import Run, count_elements, find_run, judge, render  # noqa: E402

KIND = "container-list-init"
MATCHERS = [Path(__file__).resolve().parent / "matchers" / n for n in ("push_back_run.cq", "index_assign_run.cq")]


@dataclass
class Candidate:
    file: Path
    line: int
    col: int
    name: str
    canonicals: list[str] = field(default_factory=list)


def candidates(graph: Path, root: Path) -> tuple[list[Candidate], list[str]]:
    """Declarations the matchers report, one per location, with every instantiation's type."""
    matches, dropped = run_query(graph, MATCHERS, root=root)
    found: dict[tuple[Path, int, int], Candidate] = {}
    for m in matches:
        n = m.node
        path = n.file.resolve()
        if n.kind != "VarDecl" or not n.name or not path.is_file() or not in_scope(path, root):
            continue
        c = found.setdefault((path, n.line, n.col), Candidate(path, n.line, n.col, n.name))
        if n.canonical not in c.canonicals:
            c.canonicals.append(n.canonical)
    return sorted(found.values(), key=lambda c: (c.file, c.line, c.col)), dropped


def plan(cands: list[Candidate], docs: dict[Path, Doc]) -> list[tuple[Path, Run]]:
    out: list[tuple[Path, Run]] = []
    for c in cands:
        doc = docs.setdefault(c.file, Doc(c.file))
        run = find_run(doc.text, c.line, c.col, c.name)
        if run is None:
            continue
        if any(p == c.file and r.begin <= run.end and run.begin <= r.end for p, r in out):
            continue
        judge(run, c.canonicals, doc.text[:run.begin])
        out.append((c.file, run))
    return out


def _site(root: Path, path: Path, a: int, b: int, cls: str, text: str, **kw) -> Site:
    n = max(1, text.count("\n"))
    start = min(max(1, a), n)
    return Site(path.relative_to(root), start, min(max(start, b), n), KIND, cls, **kw)


def run(graph: Path, root: Path, manifest: Path | None, apply: bool) -> int:
    cands, dropped = candidates(graph, root)
    if dropped:
        print(f"list-init: dropped {len(dropped)} TU(s) that failed to parse: {', '.join(dropped)}")
    docs: dict[Path, Doc] = {}
    plans = plan(cands, docs)

    if not apply:
        counts: dict[tuple[str, Path], int] = defaultdict(int)
        for path, r in plans:
            label = r.cls if r.skipped is None else f"skipped:{r.skipped}"
            counts[(label, path.relative_to(root))] += 1
        for (label, rel), n in sorted(counts.items()):
            print(f"{label} {rel} {n}")
        return 0

    edits: dict[Path, list[tuple[int, int, str]]] = defaultdict(list)
    for path, r in plans:
        if r.skipped is None:
            edits[path].append((r.begin, r.end, render(r)))
    if edits:
        apply_edits(edits, docs, name=KIND)
        for path in edits:
            format_changed(path, docs[path].text)

    sites: list[Site] = []
    bad: dict[Path, str] = {}
    after = {p: p.read_text(errors="surrogateescape") for p in edits}
    for path, r in plans:
        old = docs[path].text
        new = after.get(path, old)
        ops = opcodes(old, new) if path in after else []
        a, b = map_line(ops, r.first - 1, False) + 1, map_line(ops, r.last, True)
        if r.skipped is not None:
            sites.append(_site(root, path, a, b, r.cls, new, skipped=r.skipped, note=r.note))
            continue
        start = sum(len(s) + 1 for s in new.split("\n")[:a - 1])
        counted = count_elements(new, start, name_of(r))
        if counted is None or counted[0] != len(r.args):
            bad.setdefault(path, f"element-count:{counted[0] if counted else 'unparsed'}")
            sites.append(_site(root, path, a, b, r.cls, new))
            continue
        first, last = (new.count("\n", 0, k) + 1 for k in counted[1:])
        sites.append(_site(root, path, first, last, r.cls, new, note=f"elements:{counted[0]}"))

    stranded = check_hunks("".join(
        unified_diff(path.relative_to(root).as_posix(), docs[path].text, after[path])
        for path in sorted(edits)
    ))
    for s in stranded:
        bad.setdefault((root / s.file).resolve(), "")
    for path in bad:
        path.write_bytes(docs[path].data)
    if bad:
        notes = {(root / s.file).resolve(): s.text for s in reversed(stranded)}
        for i, ((path, r), s) in enumerate(zip(plans, sites)):
            if path in bad and s.skipped is None:
                reason = Reason.COMMENT_STRANDED if path in notes else Reason.GATE_FAILED
                sites[i] = _site(root, path, r.first, r.last, r.cls, docs[path].text,
                                 skipped=reason, note=notes.get(path) or bad[path])
            elif path in bad:
                sites[i] = _site(root, path, r.first, r.last, r.cls, docs[path].text,
                                 skipped=s.skipped, note=s.note)

    if manifest is not None:
        Manifest(KIND, sites).write(manifest)
    applied = sum(1 for s in sites if s.skipped is None)
    print(f"list-init: {applied} applied, {len(sites) - applied} skipped, {len(dropped)} TU(s) dropped")
    return 0


def name_of(r: Run) -> str:
    return r.head.split()[-1]


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
