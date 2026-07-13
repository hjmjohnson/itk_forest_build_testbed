#!/usr/bin/env python3
"""Find no-argument ITK CTests that are candidates for GoogleTest conversion.

A candidate is an ``itk_add_test(NAME <n> COMMAND <driver> <fn>)`` whose test
function name equals the test NAME, takes no trailing arguments after the
driver function, has an on-disk ``<fn>.cxx``, and has no existing
``<fn-with-Test->GTest>.cxx``.

Usage:
    find_gtest_candidates.py [ROOT] [--module Modules/Group/Name] [--json]

ROOT defaults to the current working directory (an ITK source tree). With
``--module`` the scan is restricted to a single module's test directory; this
is the form the skill uses when converting one module at a time. Without it the
whole tree is scanned (used to build the by-module candidate inventory).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# itk_add_test(NAME <name> COMMAND <driver> <fn>) with nothing after <fn>.
# \s matches newlines, so multi-line blocks are handled.
_BLOCK_RE = re.compile(r"itk_add_test\s*\(\s*NAME\s+(\w+)\s+COMMAND\s+(\w+)\s+(\w+)\s*\)")


def _scan_cmakelists(cml: Path) -> list[str]:
    testdir = cml.parent
    text = cml.read_text(errors="replace")
    found: list[str] = []
    for match in _BLOCK_RE.finditer(text):
        name, _driver, fn = match.group(1), match.group(2), match.group(3)
        if name != fn:
            continue
        cxx = testdir / f"{fn}.cxx"
        gtest = testdir / (fn.replace("Test", "GTest") + ".cxx")
        if cxx.exists() and not gtest.exists():
            found.append(fn)
    return sorted(found)


def _module_of(cml: Path) -> str:
    parts = cml.parent.parts
    try:
        idx = parts.index("Modules")
    except ValueError:
        return str(cml.parent)
    return "/".join(parts[idx : idx + 3])


def scan(root: Path, module: str | None) -> dict[str, list[str]]:
    if module:
        cmls = [root / module / "test" / "CMakeLists.txt"]
        cmls = [c for c in cmls if c.exists()]
    else:
        cmls = sorted(root.glob("Modules/*/*/test/CMakeLists.txt"))
    out: dict[str, list[str]] = {}
    for cml in cmls:
        candidates = _scan_cmakelists(cml)
        if candidates:
            out[_module_of(cml)] = candidates
    return dict(sorted(out.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--module", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    by_module = scan(Path(args.root), args.module)
    total = sum(len(v) for v in by_module.values())

    if args.json:
        print(
            json.dumps(
                {"total": total, "modules": len(by_module), "by_module": by_module},
                indent=1,
            )
        )
    else:
        for module, names in by_module.items():
            print(f"# {module}  ({len(names)})")
            for fn in names:
                print(f"  {fn}")
        print(f"\nTotal: {total} candidate(s) across {len(by_module)} module(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
