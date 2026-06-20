#!/usr/bin/env python3
"""drop_blocks.py — resolve ITK C-preprocessor version guards and optionally rewrite files.

CLI: drop_blocks.py --floor-major N [--floor-minor M] [--apply] [--map TSV] FILE...

Resolution rules per region condition:
  ITK_VERSION_MAJOR <op> K [&& ITK_VERSION_MINOR <op> M]
      Evaluated arithmetically at (floor_major, floor_minor).
  defined(ITK_*) / __has_include(<header.h>)
      Header in map with first-version <= floor => TRUE (KEEP branch, DROP else).
      Unknown => AMBIGUOUS.
  Anything else => AMBIGUOUS.

Exit codes: 0 = applied/clean, 2 = ambiguous regions present, 1 = parse error.
"""

import argparse
import os
import re
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Header version map loader
# ---------------------------------------------------------------------------

def load_map(tsv_path: str) -> dict:
    """Load header->first_version from a tab-separated file."""
    hmap = {}
    with open(tsv_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                header, ver_str = parts
                hmap[header.strip()] = tuple(int(x) for x in ver_str.strip().split(".", 1))
            else:
                print(f"drop_blocks: ignoring malformed map line: {line}", file=sys.stderr)
    return hmap


# ---------------------------------------------------------------------------
# Condition resolver
# ---------------------------------------------------------------------------

# Matches: ITK_VERSION_MAJOR <op> K  [&& ITK_VERSION_MINOR <op> M]
_VER_RE = re.compile(
    r"^\s*ITK_VERSION_MAJOR\s*(>=|>|<=|<|==|!=)\s*(\d+)"
    r"(?:\s*&&\s*ITK_VERSION_MINOR\s*(>=|>|<=|<|==|!=)\s*(\d+))?\s*$"
)
_DEFINED_RE = re.compile(r"^\s*defined\s*\(\s*(ITK\w*)\s*\)\s*$")
_HAS_INCLUDE_RE = re.compile(r'^\s*__has_include\s*\(\s*(?:<([^>]+)>|"([^"]+)")\s*\)\s*$')


def _cmp(op: str, lhs: int, rhs: int) -> bool:
    return {">=": lhs >= rhs, ">": lhs > rhs, "<=": lhs <= rhs,
            "<": lhs < rhs, "==": lhs == rhs, "!=": lhs != rhs}[op]


def resolve_condition(cond: str, floor_major: int, floor_minor: int,
                      hmap: dict) -> Optional[bool]:
    """Return True/False if condition is deterministic at floor, else None."""
    cond = cond.strip()

    m = _VER_RE.match(cond)
    if m:
        op1, k1, op2, k2 = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        result = _cmp(op1, floor_major, k1)
        if op2 and k2 is not None:
            result = result and _cmp(op2, floor_minor, int(k2))
        return result

    m = _DEFINED_RE.match(cond)
    if m:
        # ITK_* defines — we don't have a map for defines; treat as ambiguous
        return None

    m = _HAS_INCLUDE_RE.match(cond)
    if m:
        header = m.group(1) or m.group(2)
        if header in hmap:
            first = hmap[header]
            floor = (floor_major, floor_minor)
            return first <= floor
        return None

    return None


# ---------------------------------------------------------------------------
# Preprocessor block parser
# ---------------------------------------------------------------------------

_DIRECTIVE_RE = re.compile(
    r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)?$"
)


class Branch:
    """One branch (condition + body lines) inside a region."""
    def __init__(self, cond: Optional[str], start_lineno: int):
        self.cond = cond          # None for #else
        self.start_lineno = start_lineno
        self.body: list = []      # (lineno, text) pairs


class Region:
    """A full #if...#endif region."""
    def __init__(self, start_lineno: int):
        self.start_lineno = start_lineno
        self.branches: list = []  # list of Branch


def parse_regions(lines):
    """Yield (line_index, Region) for each top-level #if...#endif block.

    Nested regions are tracked but not separately yielded — the nesting depth
    is used to avoid mis-associating #endif with an inner block.
    """
    stack = []   # stack of Region objects; stack[-1] is the current region
    i = 0
    while i < len(lines):
        m = _DIRECTIVE_RE.match(lines[i])
        if m:
            directive = m.group(1)
            rest = (m.group(2) or "").strip()

            if directive in ("if", "ifdef", "ifndef"):
                if directive == "if":
                    cond = rest
                elif directive == "ifdef":
                    cond = f"defined({rest})"
                else:  # ifndef
                    cond = f"!defined({rest})"
                region = Region(i)
                branch = Branch(cond, i)
                region.branches.append(branch)
                stack.append(region)

            elif directive == "elif" and stack:
                # Close current branch, open a new one
                stack[-1].branches.append(Branch(rest, i))

            elif directive == "else" and stack:
                stack[-1].branches.append(Branch(None, i))

            elif directive == "endif" and stack:
                region = stack.pop()
                region.end_lineno = i
                if not stack:
                    # Top-level region complete
                    yield region
        else:
            # Body line — attach to current branch
            if stack:
                stack[-1].branches[-1].body.append((i, lines[i]))

        i += 1


# ---------------------------------------------------------------------------
# File processor
# ---------------------------------------------------------------------------

def process_file(path: str, floor_major: int, floor_minor: int,
                 hmap: dict, apply: bool):
    """Process one file. Returns (report_lines, any_ambiguous, new_content_or_None)."""
    with open(path) as fh:
        original = fh.read()
    lines = original.splitlines(keepends=True)

    # Identify all top-level regions
    regions = list(parse_regions(lines))

    if not regions:
        return [], False, None

    report = []
    any_ambiguous = False
    file_ambiguous = False

    # For each region, determine resolution
    region_resolution = []  # (region, verdict, kept_branch_idx or None)
    for region in regions:
        # Resolve each branch condition in order
        verdict = "AMBIGUOUS"
        kept_idx = None
        all_resolved = True
        first_ambiguous_cond = None

        # For elif chains: resolve top-to-bottom
        true_found = False
        has_else = False
        for idx, branch in enumerate(region.branches):
            if branch.cond is None:
                has_else = True
                # #else — implicitly true if we get here and no prior was true
                if not true_found and all_resolved:
                    # All previous conditions were False
                    kept_idx = idx
                    verdict = "KEEP_ELSE"
                break
            result = resolve_condition(branch.cond, floor_major, floor_minor, hmap)
            if result is None:
                all_resolved = False
                if first_ambiguous_cond is None:
                    first_ambiguous_cond = branch.cond
                break
            if result and not true_found:
                true_found = True
                kept_idx = idx
                verdict = "KEEP"

        if not all_resolved:
            verdict = "AMBIGUOUS"
            kept_idx = None
        elif all_resolved and not true_found and not has_else:
            # All conditions resolved to False and there is no #else — dead region
            verdict = "DROP_ALL"

        if verdict == "AMBIGUOUS":
            any_ambiguous = True
            file_ambiguous = True

        region_resolution.append((region, verdict, kept_idx))

        # Build report lines
        cond_str = region.branches[0].cond or "(else)"
        lineno = region.start_lineno + 1  # 1-based
        if verdict == "AMBIGUOUS":
            ambiguous_cond = first_ambiguous_cond or cond_str
            report.append(f"{path}:{lineno}  AMBIGUOUS {ambiguous_cond}")
        elif verdict == "DROP_ALL":
            report.append(f"{path}:{lineno}  DROP_ALL {cond_str}")
        elif kept_idx is not None:
            kept_cond = region.branches[kept_idx].cond or "(else)"
            dropped = [b.cond or "(else)" for i, b in enumerate(region.branches)
                       if i != kept_idx]
            drop_str = " / ".join(dropped) if dropped else "(no-else)"
            report.append(f"{path}:{lineno}  KEEP {kept_cond} / DROP {drop_str}")
        else:
            # All conditions False, no else => whole region drops
            report.append(f"{path}:{lineno}  DROP (all-false, no else)")

    if not apply or file_ambiguous:
        return report, any_ambiguous, None

    # Build new content by processing lines in order
    # Build a set of line indices that belong to directives or dropped body
    keep_line_indices = set(range(len(lines)))

    for region, verdict, kept_idx in region_resolution:
        # Remove ALL directive lines (if/elif/else/endif boundaries)
        directive_lines = set()
        directive_lines.add(region.start_lineno)  # #if line
        directive_lines.add(region.end_lineno)     # #endif line
        for branch in region.branches[1:]:         # #elif / #else lines
            directive_lines.add(branch.start_lineno)
        keep_line_indices -= directive_lines

        if verdict == "DROP_ALL":
            # Remove ALL body lines — the entire region is dead code
            for branch in region.branches:
                for (li, _) in branch.body:
                    keep_line_indices.discard(li)
        else:
            # Remove body lines from all branches except kept_idx
            for idx, branch in enumerate(region.branches):
                if idx != kept_idx:
                    for (li, _) in branch.body:
                        keep_line_indices.discard(li)

    new_lines = [lines[i] for i in sorted(keep_line_indices)]
    return report, any_ambiguous, "".join(new_lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def default_map_path():
    return os.path.join(os.path.dirname(__file__), "header_version_map.tsv")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--floor-major", type=int, required=True)
    ap.add_argument("--floor-minor", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--map", default=None,
                    help="Path to header_version_map.tsv (default: sibling of this script)")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    map_path = args.map or default_map_path()
    hmap = {}
    if os.path.exists(map_path):
        hmap = load_map(map_path)

    global_ambiguous = False
    exit_code = 0

    for path in args.files:
        try:
            report, any_ambiguous, new_content = process_file(
                path, args.floor_major, args.floor_minor, hmap, args.apply
            )
        except Exception as exc:
            print(f"ERROR {path}: {exc}", file=sys.stderr)
            sys.exit(1)

        for line in report:
            print(line)

        if any_ambiguous:
            global_ambiguous = True

        if new_content is not None:
            with open(path, "w") as fh:
                fh.write(new_content)

    if global_ambiguous:
        exit_code = 2
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
