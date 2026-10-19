#!/usr/bin/env python3
"""Find no-argument ITK CTests that are candidates for GoogleTest conversion.

A candidate is an ``itk_add_test(NAME <n> COMMAND <driver> <fn>)`` whose test
function name equals the test NAME, takes no trailing arguments after the
driver function, has an on-disk ``<fn>.cxx``, and has no existing
``<fn-with-Test->GTest>.cxx``.

A matching test registered inside if(0) / if(FALSE) / if(OFF) / if(NO) is
still a candidate, listed under "disabled": convert it and keep it disabled in
an if(0) block with its comments, because such blocks often mark unfinished
work. A matching test is excluded, with a reason, when a mechanical conversion
would change what it does:
  test-properties     named in set_tests_properties (environment, WILL_FAIL, ...)
  function-reused     the same test function is also registered by another itk_add_test
  factory-dependent   enumerates, unregisters, or registers object factories,
                      which the legacy driver sets up and GoogleTest drivers do not

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
_ANY_ADD_TEST_RE = re.compile(r"itk_add_test\s*\((.*?)\)", re.S)
_DISABLED_IF_RE = re.compile(r"^\s*if\s*\(\s*(?:0|FALSE|OFF|NO)\s*\)", re.I | re.M)
_FACTORY_RE = re.compile(
    r"ObjectFactoryBase::(?:GetRegisteredFactories|UnRegisterAllFactories|UnRegisterFactory|"
    r"RegisterFactory|ReHash|CreateAllInstance)|RegisterOneFactory\s*\("
)


def _disabled_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of if(0)-style blocks, matched to their endif()."""
    spans = []
    for start in _DISABLED_IF_RE.finditer(text):
        depth = 0
        for tok in re.finditer(r"^\s*(if|endif)\s*\(", text[start.start() :], re.I | re.M):
            depth += 1 if tok.group(1).lower() == "if" else -1
            if depth == 0:
                spans.append((start.start(), start.start() + tok.end()))
                break
    return spans


def _exclusion(text: str, pos: int, fn: str, cxx: Path) -> str | None:
    for props in re.finditer(r"set_tests_properties\s*\((.*?)PROPERTIES", text, re.S):
        if re.search(rf"\b{fn}\b", props.group(1)):
            return "test-properties"
    for block in _ANY_ADD_TEST_RE.finditer(text):
        if block.start() == pos:
            continue
        words = block.group(1).split()
        if fn in words:
            return "function-reused"
    if _FACTORY_RE.search(cxx.read_text(errors="replace")):
        return "factory-dependent"
    return None


def _scan_cmakelists(
    cml: Path, excluded: dict[str, str] | None = None, disabled: list[str] | None = None
) -> list[str]:
    testdir = cml.parent
    text = cml.read_text(errors="replace")
    spans = _disabled_spans(text)
    found: list[str] = []
    for match in _BLOCK_RE.finditer(text):
        name, _driver, fn = match.group(1), match.group(2), match.group(3)
        if name != fn:
            continue
        cxx = testdir / f"{fn}.cxx"
        gtest = testdir / (fn.replace("Test", "GTest") + ".cxx")
        if not cxx.exists() or gtest.exists():
            continue
        reason = _exclusion(text, match.start(), fn, cxx)
        if reason:
            if excluded is not None:
                excluded[fn] = reason
            continue
        if disabled is not None and any(a <= match.start() < b for a, b in spans):
            disabled.append(fn)
        found.append(fn)
    return sorted(found)


def _module_of(cml: Path) -> str:
    parts = cml.parent.parts
    try:
        idx = parts.index("Modules")
    except ValueError:
        return str(cml.parent)
    return "/".join(parts[idx : idx + 3])


def scan(
    root: Path,
    module: str | None,
    excluded: dict[str, dict[str, str]] | None = None,
    disabled: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    if module:
        cmls = [root / module / "test" / "CMakeLists.txt"]
        cmls = [c for c in cmls if c.exists()]
    else:
        cmls = sorted(root.glob("Modules/*/*/test/CMakeLists.txt"))
    out: dict[str, list[str]] = {}
    for cml in cmls:
        skipped: dict[str, str] = {}
        off: list[str] = []
        candidates = _scan_cmakelists(cml, skipped, off)
        if candidates:
            out[_module_of(cml)] = candidates
        if skipped and excluded is not None:
            excluded[_module_of(cml)] = skipped
        if off and disabled is not None:
            disabled[_module_of(cml)] = sorted(off)
    return dict(sorted(out.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--module", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    excluded: dict[str, dict[str, str]] = {}
    disabled: dict[str, list[str]] = {}
    by_module = scan(Path(args.root), args.module, excluded, disabled)
    total = sum(len(v) for v in by_module.values())
    n_excluded = sum(len(v) for v in excluded.values())

    if args.json:
        print(
            json.dumps(
                {
                    "total": total,
                    "modules": len(by_module),
                    "by_module": by_module,
                    "excluded": dict(sorted(excluded.items())),
                    "disabled": dict(sorted(disabled.items())),
                },
                indent=1,
            )
        )
    else:
        for module, names in by_module.items():
            print(f"# {module}  ({len(names)})")
            for fn in names:
                print(f"  {fn}")
        if disabled:
            print("\n# Disabled in if(0): convert, and keep disabled in an if(0) block with its comments")
            for module, names in sorted(disabled.items()):
                for fn in names:
                    print(f"  {module}: {fn}")
        if excluded:
            print("\n# Excluded (a mechanical conversion would change the test)")
            for module, skipped in sorted(excluded.items()):
                for fn, reason in sorted(skipped.items()):
                    print(f"  {module}: {fn}  [{reason}]")
        print(f"\nTotal: {total} candidate(s) across {len(by_module)} module(s); {n_excluded} excluded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
