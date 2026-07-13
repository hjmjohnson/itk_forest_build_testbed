#!/usr/bin/env python3
"""
scan.py — ITK Transform*Point migration classifier
Usage: python3 scan.py <source-dir> [--no-archive]

Scans C++ source files for ITK Transform*Point calls and classifies each
call site into one of four buckets:

  MIGRATE (ToPhysical)          — TransformIndex/ContinuousIndexToPhysicalPoint,
                                   two-arg void form, always safe to migrate.
  MIGRATE (FromPhysical,bool-)  — TransformPhysicalPoint*, two-arg form,
                                   bool return discarded — safe to migrate.
  KEEP    (bool-captured)       — TransformPhysicalPoint*, bool return used
                                   in if/assignment — leave unchanged.
  ALREADY_NEW                   — return-value form already in use.

Output is grouped by bucket, with file:line for each site.
"""

import re
import sys
from pathlib import Path

# ── Patterns ────────────────────────────────────────────────────────────────

# All four Transform method names
TO_PHYSICAL = re.compile(r"Transform(?:Index|ContinuousIndex)ToPhysicalPoint")
FROM_PHYSICAL = re.compile(r"TransformPhysicalPoint(?:ToIndex|ToContinuousIndex)")
ANY_TRANSFORM = re.compile(
    r"Transform(?:Index|ContinuousIndex)ToPhysicalPoint"
    r"|TransformPhysicalPoint(?:ToIndex|ToContinuousIndex)"
)

# Two-arg call: method(a, b) — comma inside the argument list
TWO_ARG = re.compile(r"Transform\w+\s*(<[^>]+>)?\s*\([^)]+,[^)]+\)")

# Return-value assigned: "= ...->Transform..." or "auto x = ..."
ASSIGNED = re.compile(r"(?:=\s*[a-zA-Z_][^=]*->|auto\s+\w+\s*=\s*)")

# Bool return captured: "bool x = ...", "const bool ... =", or inside if/while
BOOL_CAPTURED = re.compile(r"(?:(?:const\s+)?bool\s+\w+\s*=|if\s*\(|while\s*\()")

EXTENSIONS = {".cxx", ".hxx", ".h", ".txx", ".ixx"}

# ── Classifier ───────────────────────────────────────────────────────────────


def classify_line(line: str) -> str | None:
    """
    Returns one of: 'MIGRATE_TO', 'MIGRATE_FROM', 'KEEP_BOOL', 'ALREADY_NEW', None
    None means the line doesn't contain a relevant call (or is a comment/doc).
    """
    stripped = line.strip()

    # Skip pure comment lines and doc comment lines
    if stripped.startswith("//") or stripped.startswith("*"):
        return None

    has_to = bool(TO_PHYSICAL.search(line))
    has_from = bool(FROM_PHYSICAL.search(line))
    if not has_to and not has_from:
        return None

    has_two_arg = bool(TWO_ARG.search(line))
    is_assigned = bool(ASSIGNED.search(line))

    if not has_two_arg:
        # One-arg form — already new-style (whether assigned or not)
        return "ALREADY_NEW"

    if has_from:
        # Bool return: check if it's captured
        if BOOL_CAPTURED.search(line):
            return "KEEP_BOOL"
        return "MIGRATE_FROM"

    # has_to, has_two_arg
    return "MIGRATE_TO"


# ── Main ─────────────────────────────────────────────────────────────────────


def scan(root: Path, skip_archive: bool) -> dict[str, list[tuple[Path, int, str]]]:
    buckets: dict[str, list] = {
        "MIGRATE_TO": [],
        "MIGRATE_FROM": [],
        "KEEP_BOOL": [],
        "ALREADY_NEW": [],
    }

    for path in sorted(root.rglob("*")):
        if path.suffix not in EXTENSIONS:
            continue
        if "/build/" in str(path) or "/.git/" in str(path):
            continue
        if skip_archive and "/ARCHIVE/" in str(path):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            bucket = classify_line(line)
            if bucket:
                buckets[bucket].append((path, lineno, line.strip()))

    return buckets


def print_bucket(label: str, entries: list, root: Path) -> None:
    if not entries:
        print("  (none)")
        return
    for path, lineno, code in entries:
        rel = path.relative_to(root) if path.is_relative_to(root) else path
        print(f"  {rel}:{lineno}")
        print(f"    {code}")


def main() -> None:
    args = sys.argv[1:]
    skip_archive = "--no-archive" in args
    dirs = [a for a in args if not a.startswith("--")]

    if not dirs:
        print(__doc__)
        sys.exit(1)

    root = Path(dirs[0]).resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    buckets = scan(root, skip_archive)

    migrate_to = buckets["MIGRATE_TO"]
    migrate_from = buckets["MIGRATE_FROM"]
    keep = buckets["KEEP_BOOL"]
    already = buckets["ALREADY_NEW"]

    total_migrate = len(migrate_to) + len(migrate_from)

    print(f'\n{"="*70}')
    print(f"ITK Transform*Point Migration Scan: {root}")
    print(f'{"="*70}')
    print(
        f"  Migratable:    {total_migrate:3d}  "
        f"({len(migrate_to)} ToPhysical + {len(migrate_from)} FromPhysical/bool-ignored)"
    )
    print(f"  Keep (bool):   {len(keep):3d}")
    print(f"  Already new:   {len(already):3d}")
    print()

    print(f"── MIGRATE: ToPhysicalPoint (void→return, always safe) [{len(migrate_to)}] ──")
    print_bucket("MIGRATE_TO", migrate_to, root)

    print()
    print(f"── MIGRATE: FromPhysical, bool ignored [{len(migrate_from)}] ──")
    print_bucket("MIGRATE_FROM", migrate_from, root)

    print()
    print(f"── KEEP: FromPhysical, bool captured (leave two-arg) [{len(keep)}] ──")
    print_bucket("KEEP_BOOL", keep, root)

    print()
    print(f"── ALREADY new-style (no action needed) [{len(already)}] ──")
    if already:
        for path, lineno, code in already:
            rel = path.relative_to(root) if path.is_relative_to(root) else path
            print(f"  {rel}:{lineno}")


if __name__ == "__main__":
    main()
