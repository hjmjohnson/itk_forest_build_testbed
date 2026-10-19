#!/usr/bin/env python3
"""Compare two lcov exports line by line.

Library sources are identical before and after the GoogleTest conversion, so
a covered line is identified by (path relative to the source root, line). The
check passes only if every line covered before is still covered after.

Usage: compare_coverage.py BEFORE BEFORE_SRC AFTER AFTER_SRC [REPORT.md]
BEFORE and AFTER are comma-separated lcov files or per-driver lcov directories,
one per run; covered means covered in any run, so lines that vary between
runs count as covered on both sides. TestKernel (test infrastructure) is
excluded.
"""

import sys
from collections import defaultdict
from pathlib import Path


TEST_INFRASTRUCTURE = "Modules/Core/TestKernel/"


def lcov_files(paths):
    """lcov files from a comma-separated list of files or directories (one per run)."""
    files = []
    for path in map(Path, paths.split(",")):
        files += sorted(path.glob("*.lcov")) if path.is_dir() else [path]
    return files


def covered_lines(lcov_path, src_root):
    """Union of covered lines over one lcov file or a directory of them."""
    root = str(Path(src_root).resolve()) + "/"
    covered = defaultdict(set)
    instrumented = defaultdict(set)
    for f in lcov_files(lcov_path):
        current = None
        with f.open() as stream:
            for line in stream:
                if line.startswith("SF:"):
                    path = line[3:].rstrip("\n")
                    current = path[len(root) :] if path.startswith(root) else path
                    if current.startswith(TEST_INFRASTRUCTURE):
                        current = None
                elif line.startswith("DA:") and current:
                    number, count = line[3:].split(",")[:2]
                    instrumented[current].add(int(number))
                    if int(count) > 0:
                        covered[current].add(int(number))
    return covered, instrumented


def main():
    before_lcov, before_src, after_lcov, after_src = sys.argv[1:5]
    report = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    before, before_instr = covered_lines(before_lcov, before_src)
    after, after_instr = covered_lines(after_lcov, after_src)

    lost = {f: sorted(lines - after.get(f, set())) for f, lines in before.items()}
    lost = {f: lines for f, lines in lost.items() if lines}
    gained = {f: sorted(after[f] - before.get(f, set())) for f in after}
    gained = {f: lines for f, lines in gained.items() if lines}

    total_before = sum(len(v) for v in before.values())
    total_after = sum(len(v) for v in after.values())
    instr_before = sum(len(v) for v in before_instr.values())
    instr_after = sum(len(v) for v in after_instr.values())

    out = [
        "# Line coverage before and after the GoogleTest conversion",
        "",
        f"- Files with coverage before: {len(before)}; after: {len(after)}",
        f"- Covered lines before: {total_before} of {instr_before} instrumented",
        f"- Covered lines after: {total_after} of {instr_after} instrumented",
        f"- Files that lost any covered line: {len(lost)}"
        f" ({sum(len(v) for v in lost.values())} lines)",
        f"- Files that gained covered lines: {len(gained)}"
        f" ({sum(len(v) for v in gained.values())} lines)",
        "",
    ]
    if lost:
        out += ["## Lines covered before but not after", ""]
        for f in sorted(lost):
            shown = ", ".join(map(str, lost[f][:40]))
            more = f" (+{len(lost[f]) - 40} more)" if len(lost[f]) > 40 else ""
            out.append(f"- `{f}`: {shown}{more}")
        out.append("")
    if gained:
        out += ["## Lines covered after but not before", ""]
        for f in sorted(gained):
            out.append(f"- `{f}`: {len(gained[f])} lines")
        out.append("")
    text = "\n".join(out)
    print(text)
    if report:
        report.write_text(text + "\n")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
