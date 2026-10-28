#!/usr/bin/env python3
"""Rewrite `->Allocate(true)` and `.Allocate(true)` calls to `AllocateInitialized()`.

Edits the working tree and writes a manifest of kind itk-helpers; never commits.
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "itk-init-over-assign" / "lib"))

from ioa.comments import check_hunks, unified_diff  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.skip import Reason  # noqa: E402
from ioa.source import mask  # noqa: E402
from ioa.tidy import format_changed, in_scope, map_line, opcodes  # noqa: E402

KIND = "itk-helpers"
CLS = "allocate_true"
MINIMUM = (5, 3)
SOURCES = ("*.h", "*.hxx", "*.hpp", "*.txx", "*.cxx", "*.cpp", "*.cc")
CALL = re.compile(r"(->|\.)(\s*)Allocate\s*\(\s*true\s*\)")
REPLACEMENT = "AllocateInitialized()"
DEFINITION = re.compile(r"\bAllocateInitialized\s*\(\s*\)[^;{}]*\{")


@dataclass
class Call:
    begin: int
    end: int
    line: int


def itk_version(graph: Path) -> tuple[int, int] | None:
    """ITK_VERSION_MAJOR/MINOR of the ITK the graph builds against, from ITK_DIR in its CMakeCache.txt."""
    dirs = [graph]
    try:
        cache = (graph / "CMakeCache.txt").read_text(errors="replace")
    except OSError:
        cache = ""
    if m := re.search(r"^ITK_DIR:\w+=(.+)$", cache, re.M):
        dirs.insert(0, Path(m[1].strip()))
    for d in dirs:
        try:
            config = (d / "ITKConfig.cmake").read_text(errors="replace")
        except OSError:
            continue
        found = [re.search(rf'set\(ITK_VERSION_{part}\s+"?(\d+)', config) for part in ("MAJOR", "MINOR")]
        if all(found):
            return int(found[0][1]), int(found[1][1])
    return None


def sources(root: Path) -> list[Path]:
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *SOURCES],
                            capture_output=True, text=True, check=True).stdout
    return [p for p in (root / f for f in listed.split("\0") if f) if p.is_file() and in_scope(p, root)]


def _inside_definition(masked: str, at: int) -> bool:
    heads = list(DEFINITION.finditer(masked, 0, at))
    if not heads:
        return False
    body = masked[heads[-1].end():at]
    return body.count("{") >= body.count("}")


def calls(text: str) -> list[Call]:
    masked = mask(text, literals=True)
    return [Call(m.start(), m.end(), text.count("\n", 0, m.start()) + 1)
            for m in CALL.finditer(masked) if not _inside_definition(masked, m.start())]


def rewrite(text: str, found: list[Call]) -> str:
    out, last = [], 0
    for c in found:
        head = CALL.match(text, c.begin)
        out += [text[last:c.begin], head[1], head[2], REPLACEMENT]
        last = c.end
    return "".join(out) + text[last:]


def run(graph: Path, root: Path, manifest: Path | None, apply: bool) -> int:
    version = itk_version(graph)
    if version is None:
        print(f"allocate-initialized: ITK version unreadable from {graph}; assuming >= 5.3")
    plans = {p: (data, found) for p in sources(root)
             if (found := calls((data := p.read_bytes()).decode("utf-8", "surrogateescape")))}

    if not apply:
        for p, (_, found) in sorted(plans.items()):
            print(f"{CLS} {p.relative_to(root)} {len(found)}")
        return 0

    note = "itk-version:unknown" if version is None else ""
    sites: list[Site] = []
    if version is not None and version < MINIMUM:
        for p, (_, found) in sorted(plans.items()):
            sites += [Site(p.relative_to(root), c.line, c.line, KIND, CLS, Reason.ITK_VERSION,
                           f"itk:{version[0]}.{version[1]}") for c in found]
    else:
        for p, (data, found) in sorted(plans.items()):
            rel = p.relative_to(root)
            old = data.decode("utf-8", "surrogateescape")
            renamed = rewrite(old, found)
            p.write_bytes(renamed.encode("utf-8", "surrogateescape"))
            format_changed(p, old)
            new = p.read_text(errors="surrogateescape")
            stranded = check_hunks(unified_diff(str(rel), old, new))
            if stranded:
                p.write_bytes(data)
                sites += [Site(rel, c.line, c.line, KIND, CLS, Reason.COMMENT_STRANDED, stranded[0].text)
                          for c in found]
                continue
            # The rename keeps every line in place, so only the formatter moves lines.
            ops = opcodes(renamed, new)
            sites += [Site(rel, map_line(ops, c.line - 1, False) + 1, map_line(ops, c.line, True), KIND, CLS,
                           note=note) for c in found]

    if manifest is not None:
        Manifest(KIND, sites).write(manifest)
    applied = sum(1 for s in sites if s.skipped is None)
    print(f"allocate-initialized: {applied} applied, {len(sites) - applied} skipped")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True, type=Path,
                    help="build dir whose CMakeCache.txt names the ITK_DIR the repo builds against")
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
    return run(args.graph.resolve(), root, args.manifest, args.apply)


if __name__ == "__main__":
    sys.exit(main())
