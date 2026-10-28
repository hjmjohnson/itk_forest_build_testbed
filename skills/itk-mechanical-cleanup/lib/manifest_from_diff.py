#!/usr/bin/env python3
"""Write a manifest (itk-helpers by default) for files a transform.sh rewrote in place.

Each argument pairs a saved pre-edit copy with the edited file, ORIG=REL (REL relative to
--repo). The edited lines are clang-formatted, every changed hunk becomes a site, and a file
whose edit strands a comment is restored from ORIG with its sites marked comment-stranded.
"""

import argparse
import sys
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "itk-init-over-assign" / "lib"))

from ioa.comments import check_hunks, unified_diff  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.skip import Reason  # noqa: E402
from ioa.tidy import format_changed, map_line, opcodes  # noqa: E402

KIND = "itk-helpers"


def _clamp(text: str, a: int, b: int) -> tuple[int, int]:
    n = max(1, text.count("\n"))
    start = min(max(1, a), n)
    return start, min(max(start, b), n)


def _skips(path: Path | None) -> dict[str, list[tuple[int, int, Reason, str]]]:
    out: dict[str, list[tuple[int, int, Reason, str]]] = {}
    if path is None or not path.exists():
        return out
    for row in path.read_text().splitlines():
        if row.strip():
            rel, a, b, reason, note = row.split("\t")
            out.setdefault(rel, []).append((int(a), int(b), Reason(reason), note))
    return out


def build(root: Path, cls: str, pairs: list[tuple[Path, str]], skips_file: Path | None,
          kind: str = KIND) -> Manifest:
    skips = _skips(skips_file)
    sites: list[Site] = []
    edited = {rel for _, rel in pairs}
    for orig, rel in pairs:
        path = root / rel
        old = orig.read_text(errors="surrogateescape")
        format_changed(path, old)
        new = path.read_text(errors="surrogateescape")
        ops = opcodes(old, new)
        stranded = check_hunks(unified_diff(rel, old, new))
        if stranded:
            path.write_bytes(orig.read_bytes())
            note = stranded[0].text
            for tag, i1, i2, _, _ in ops:
                if tag != "equal":
                    sites.append(Site(Path(rel), *_clamp(old, i1 + 1, i2), kind, cls,
                                      Reason.COMMENT_STRANDED, note))
            for a, b, reason, kept in skips.pop(rel, []):
                sites.append(Site(Path(rel), *_clamp(old, a, b), kind, cls, reason, kept))
            continue
        for tag, _, _, j1, j2 in ops:
            if tag != "equal":
                sites.append(Site(Path(rel), *_clamp(new, j1 + 1, j2), kind, cls))
        for a, b, reason, note in skips.pop(rel, []):
            sites.append(Site(Path(rel), *_clamp(new, map_line(ops, a - 1, False) + 1, map_line(ops, b, True)),
                              kind, cls, reason, note))
    for rel, rows in skips.items():
        text = (root / rel).read_text(errors="surrogateescape") if rel not in edited else ""
        sites += [Site(Path(rel), *_clamp(text, a, b), kind, cls, reason, note) for a, b, reason, note in rows]
    sites.sort(key=lambda s: (str(s.file), s.start, s.end))
    return Manifest(kind, sites)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--cls", required=True, help="site class, the pattern name")
    ap.add_argument("--kind", default=KIND, help="manifest kind")
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--skips", type=Path, help="rows of REL<TAB>START<TAB>END<TAB>REASON<TAB>NOTE, pre-edit lines")
    ap.add_argument("pairs", nargs="*", metavar="ORIG=REL")
    from ioa.tidy import add_llvm_bin_option, use_llvm_bin

    add_llvm_bin_option(ap)
    args = ap.parse_args(argv)
    use_llvm_bin(args)
    pairs = [(Path(o), r) for o, _, r in (p.partition("=") for p in args.pairs)]
    m = build(args.repo.resolve(), args.cls, pairs, args.skips, args.kind)
    m.write(args.manifest)
    applied = len(m.applied())
    print(f"manifest: {applied} applied, {len(m.sites) - applied} skipped -> {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
