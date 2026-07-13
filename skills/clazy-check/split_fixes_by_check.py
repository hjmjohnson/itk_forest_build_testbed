#!/usr/bin/env python3
"""Split clazy YAML fix files by DiagnosticName into per-check subdirectories.

Given a directory of YAML fix files (produced by clazy-standalone --export-fixes),
this script:
  1. Reads each YAML file
  2. Groups diagnostics by DiagnosticName (e.g. clazy-old-style-connect)
  3. Writes filtered YAML files into per-check subdirectories
  4. Skips diagnostics with empty Replacements (no auto-fix available)

Usage:
    split_fixes_by_check.py <fixes-dir> [--list]

With --list, only prints the available check names and file counts, then exits.

Output structure:
    <fixes-dir>/
        by-check/
            clazy-old-style-connect/
                file1.yaml
                file2.yaml
            clazy-copyable-polymorphic/
                file1.yaml
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path


def parse_yaml_diagnostics(content: str) -> tuple[str, list[dict]]:
    """Parse a clazy fix YAML file without requiring PyYAML.

    Returns (main_source_file, list_of_diagnostic_dicts).
    Each diagnostic dict has keys: name, raw_text (the YAML block).
    """
    # Extract MainSourceFile
    m = re.search(r"MainSourceFile:\s*'([^']*)'", content)
    main_source = m.group(1) if m else ""

    # Split into individual diagnostic blocks.
    # Each starts with "  - DiagnosticName:" and runs until the next
    # "  - DiagnosticName:" or end of the Diagnostics list.
    diag_pattern = re.compile(r"^  - DiagnosticName:\s*(\S+)\s*$", re.MULTILINE)
    matches = list(diag_pattern.finditer(content))

    diagnostics = []
    for i, match in enumerate(matches):
        name = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end].rstrip("\n")

        # Check if this diagnostic has non-empty Replacements.
        # Skip if Replacements is empty ([] or no entries).
        has_replacements = False
        repl_match = re.search(r"Replacements:\s*(\[?\]?)", block)
        if repl_match:
            if repl_match.group(1) != "[]":
                # Has replacement entries (multi-line YAML list)
                has_replacements = True
        # Also check for "- FilePath:" under Replacements
        if re.search(r"- FilePath:", block):
            has_replacements = True

        if has_replacements:
            diagnostics.append({"name": name, "raw_text": block})

    return main_source, diagnostics


def split_fixes(fixes_dir: Path, list_only: bool = False) -> dict[str, int]:
    """Split YAML files by check name.

    Returns dict mapping check_name -> file_count.
    """
    by_check_dir = fixes_dir / "by-check"

    # Collect all diagnostics grouped by check name
    # check_name -> list of (yaml_filename, main_source, diagnostic_block)
    checks: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    yaml_files = sorted(fixes_dir.glob("*.yaml"))
    if not yaml_files:
        print(f"No YAML files found in {fixes_dir}", file=sys.stderr)
        return {}

    for yaml_path in yaml_files:
        content = yaml_path.read_text()
        main_source, diagnostics = parse_yaml_diagnostics(content)
        for diag in diagnostics:
            checks[diag["name"]].append((yaml_path.name, main_source, diag["raw_text"]))

    if list_only:
        return {name: len(entries) for name, entries in sorted(checks.items())}

    # Clean and recreate by-check directory
    if by_check_dir.exists():
        shutil.rmtree(by_check_dir)
    by_check_dir.mkdir(parents=True)

    counts = {}
    for check_name, entries in sorted(checks.items()):
        check_dir = by_check_dir / check_name
        check_dir.mkdir(parents=True, exist_ok=True)

        # Group entries by YAML filename (one output YAML per source file per check)
        by_file: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for yaml_name, main_source, block in entries:
            by_file[yaml_name].append((main_source, block))

        for yaml_name, file_entries in by_file.items():
            main_source = file_entries[0][0]
            blocks = [entry[1] for entry in file_entries]
            # Reconstruct a valid YAML file with only this check's diagnostics
            out_lines = [
                "---",
                f"MainSourceFile:  '{main_source}'",
                "Diagnostics:",
            ]
            for block in blocks:
                out_lines.append(block)
            out_content = "\n".join(out_lines) + "\n...\n"
            (check_dir / yaml_name).write_text(out_content)

        counts[check_name] = len(by_file)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Split clazy fix YAMLs by check name")
    parser.add_argument(
        "fixes_dir",
        type=Path,
        help="Directory containing clazy fix YAML files",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Only list available check names and counts, then exit",
    )
    args = parser.parse_args()

    if not args.fixes_dir.is_dir():
        print(f"Error: {args.fixes_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    counts = split_fixes(args.fixes_dir, list_only=args.list)

    if not counts:
        print("No fixable diagnostics found.")
        sys.exit(0)

    print(f"{'Check Name':<45} {'Files':>6}")
    print("─" * 52)
    total = 0
    for name, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"{name:<45} {count:>6}")
        total += count
    print("─" * 52)
    print(f"{'Total':<45} {total:>6}")

    if not args.list:
        print(f"\nPer-check directories in: {args.fixes_dir / 'by-check'}")


if __name__ == "__main__":
    main()
