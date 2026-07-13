#!/usr/bin/env python3
"""
patch_destructors.py — Mechanically fix inline = default destructor ABI issue.

For each candidate header/cxx pair:
  1. Removes `= default` from the inline destructor declaration in the .h
  2. Injects `ClassName::~ClassName() = default;` after the namespace opening
     brace in the .cxx

Usage:
    python patch_destructors.py --scan-dir Modules/ [--dry-run] [--verbose]
    python patch_destructors.py --file include/itkFoo.h [--dry-run]

The script CANNOT detect template false-positives at this stage — build
immediately after running and revert any files that fail to compile.

See: https://github.com/InsightSoftwareConsortium/ITK/issues/6000
"""

import argparse
import re
import sys
from pathlib import Path

# Matches:  ~ClassName() override = default;
# Also:     ~ClassName() = default;   (no override, less common)
INLINE_DTOR_RE = re.compile(r"~(\w+)\(\)\s*(?:override\s*)?=\s*default\s*;")

# Matches the namespace opening — both styles ITK uses:
#   namespace itk {
#   namespace itk\n{
#   namespace itk::fem\n{
NAMESPACE_OPEN_RE = re.compile(
    r"(namespace\s+\S+(?:\s*::\s*\S+)*\s*\n\{|\bnamespace\s+\S+(?:\s*::\s*\S+)*\s*\{)"
)


def find_candidates(scan_dir: Path, verbose: bool) -> list[tuple[Path, Path, str]]:
    """Return list of (header, cxx, class_name) triples that are candidates."""
    candidates = []
    excluded = {"ThirdParty"}

    for header in sorted(scan_dir.rglob("*.h")):
        # Skip ThirdParty
        if any(ex in header.parts for ex in excluded):
            continue

        text = header.read_text(errors="replace")
        matches = list(INLINE_DTOR_RE.finditer(text))
        if not matches:
            continue

        # Skip template classes
        if re.search(r"ITK_TEMPLATE_EXPORT|^\s*template\s*<", text, re.MULTILINE):
            if verbose:
                print(f"  SKIP (template): {header}")
            continue

        # Skip non-exported classes
        if not re.search(r"\w+_EXPORT", text):
            if verbose:
                print(f"  SKIP (no export macro): {header}")
            continue

        # Skip abstract classes
        if re.search(r"=\s*0\s*;", text):
            if verbose:
                print(f"  SKIP (abstract): {header}")
            continue

        # Find corresponding .cxx
        cxx = header.parent.parent / "src" / (header.stem + ".cxx")
        if not cxx.exists():
            # Try same directory
            cxx_alt = header.with_suffix(".cxx")
            if cxx_alt.exists():
                cxx = cxx_alt
            else:
                if verbose:
                    print(f"  SKIP (no .cxx found): {header}")
                continue

        # Check .cxx doesn't already have an out-of-line dtor
        cxx_text = cxx.read_text(errors="replace")
        class_name = matches[0].group(1)
        if re.search(rf"{re.escape(class_name)}::~{re.escape(class_name)}", cxx_text):
            if verbose:
                print(f"  SKIP (already has out-of-line dtor): {header}")
            continue

        candidates.append((header, cxx, class_name))
        if verbose:
            print(f"  CANDIDATE: {header.name} / {class_name}")

    return candidates


def patch_header(header: Path, class_name: str, dry_run: bool) -> bool:
    """Remove = default from the inline destructor. Returns True if changed."""
    text = header.read_text()
    new_text, count = INLINE_DTOR_RE.subn(
        lambda m: m.group(0).replace(" = default", "").replace("= default", "").rstrip().rstrip(";")
        + ";",
        text,
    )
    # Simpler: targeted replacement
    new_text = re.sub(
        rf"(~{re.escape(class_name)}\(\)\s*(?:override\s*)?)=\s*default\s*;",
        r"\1;",
        text,
    )
    if new_text == text:
        return False
    if not dry_run:
        header.write_text(new_text)
    return True


def patch_cxx(cxx: Path, class_name: str, dry_run: bool) -> bool:
    """Inject ClassName::~ClassName() = default; after namespace opening."""
    text = cxx.read_text()
    dtor_line = f"{class_name}::~{class_name}() = default;\n"

    # Find the first namespace opening brace
    m = NAMESPACE_OPEN_RE.search(text)
    if not m:
        print(f"  WARNING: could not find namespace opening in {cxx}", file=sys.stderr)
        return False

    insert_pos = m.end()
    # Insert after the opening brace (and any immediately following newline)
    if insert_pos < len(text) and text[insert_pos] == "\n":
        insert_pos += 1

    new_text = text[:insert_pos] + dtor_line + text[insert_pos:]
    if not dry_run:
        cxx.write_text(new_text)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan-dir", type=Path, help="Root directory to scan recursively")
    group.add_argument("--file", type=Path, help="Single header file to process")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without writing"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.file:
        # Single-file mode: find cxx next to include/ → src/
        header = args.file
        text = header.read_text(errors="replace")
        m = INLINE_DTOR_RE.search(text)
        if not m:
            print(f"No inline = default destructor found in {header}")
            return
        class_name = m.group(1)
        cxx = header.parent.parent / "src" / (header.stem + ".cxx")
        if not cxx.exists():
            print(f"No .cxx found at {cxx}", file=sys.stderr)
            sys.exit(1)
        candidates = [(header, cxx, class_name)]
    else:
        print(f"Scanning {args.scan_dir} ...")
        candidates = find_candidates(args.scan_dir, args.verbose)

    if not candidates:
        print("No candidates found.")
        return

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Processing {len(candidates)} candidate(s):\n")
    fixed = 0
    for header, cxx, class_name in candidates:
        h_changed = patch_header(header, class_name, args.dry_run)
        c_changed = patch_cxx(cxx, class_name, args.dry_run)
        status = "would fix" if args.dry_run else "fixed"
        if h_changed or c_changed:
            print(f"  {status}: {header.name} / {cxx.name}  ({class_name})")
            fixed += 1
        else:
            print(f"  NO CHANGE: {header.name} (already correct?)")

    print(f"\nDone: {fixed}/{len(candidates)}")
    if not args.dry_run and fixed:
        print("\nNext step: build the affected modules and revert any files that")
        print("fail to compile (they are likely template class false-positives).")


if __name__ == "__main__":
    main()
