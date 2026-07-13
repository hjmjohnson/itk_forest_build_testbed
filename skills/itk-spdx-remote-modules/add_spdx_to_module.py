#!/usr/bin/env python3
"""Add SPDX license identifiers to an ITK remote module's source files.

Follows VTK's convention: two // (or #) comment lines before the existing
license block. Handles both "Copyright NumFOCUS" and legacy "Copyright
Insight Software Consortium" headers.

Usage:
    python3 add_spdx_to_module.py /path/to/module [--dry-run]
"""

import argparse
import sys
from pathlib import Path

SPDX_COPYRIGHT = "Copyright NumFOCUS"
SPDX_LICENSE = "Apache-2.0"

C_HEADER = (
    f"// SPDX-FileCopyrightText: {SPDX_COPYRIGHT}\n" f"// SPDX-License-Identifier: {SPDX_LICENSE}\n"
)

HASH_HEADER = (
    f"# SPDX-FileCopyrightText: {SPDX_COPYRIGHT}\n" f"# SPDX-License-Identifier: {SPDX_LICENSE}\n"
)

C_EXTENSIONS = {".h", ".hxx", ".cxx", ".txx"}
HASH_EXTENSIONS = {".py"}

# Copyright patterns that indicate an ITK-family file
ITK_COPYRIGHT_PATTERNS = [
    "Copyright NumFOCUS",
    "Copyright Insight Software Consortium",
]

SKIP_PATTERNS = [
    "/ThirdParty/",
    "/.pixi/",
    "/cmake-build",
    "/build/",
    "/dist/",
    "/.git/",
    "/CMakeFiles/",
]


def should_skip(path: Path) -> bool:
    s = str(path)
    return any(pat in s for pat in SKIP_PATTERNS)


def has_itk_copyright(content: str) -> bool:
    return any(pat in content for pat in ITK_COPYRIGHT_PATTERNS)


def needs_spdx(content: str) -> bool:
    return has_itk_copyright(content) and "SPDX-License-Identifier" not in content


def add_spdx_header(content: str, header: str) -> str:
    """Prepend the SPDX header before the file content."""
    if content.startswith("#!"):
        first_newline = content.index("\n") + 1
        return content[:first_newline] + header + content[first_newline:]
    return header + content


def process_file(path: Path, dry_run: bool) -> bool:
    """Add SPDX header to a single file. Returns True if modified."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return False

    if not needs_spdx(content):
        return False

    suffix = path.suffix
    name = path.name

    if suffix in C_EXTENSIONS:
        header = C_HEADER
    elif suffix in HASH_EXTENSIONS or name == "CMakeLists.txt":
        header = HASH_HEADER
    else:
        return False

    new_content = add_spdx_header(content, header)

    if dry_run:
        print(f"  would modify: {path}")
    else:
        path.write_text(new_content, encoding="utf-8")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module_dir", help="Path to the remote module directory")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    root = Path(args.module_dir).resolve()

    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 1

    # Verify it looks like an ITK module
    if not (root / "itk-module.cmake").exists() and not (root / "CMakeLists.txt").exists():
        print(f"WARNING: {root} may not be an ITK module (no itk-module.cmake)", file=sys.stderr)

    globs = ["**/*.h", "**/*.hxx", "**/*.cxx", "**/*.txx", "**/*.py"]

    modified = 0
    scanned = 0

    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if should_skip(path):
                continue
            scanned += 1
            if process_file(path, args.dry_run):
                modified += 1

    action = "Would modify" if args.dry_run else "Modified"
    print(f"Scanned {scanned} files, {action} {modified}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
