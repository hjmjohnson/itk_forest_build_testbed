#!/usr/bin/env python3
"""Find code that will not build against both ITK release-5.4 and ITK main
with ITK_FUTURE_LEGACY_REMOVE=ON.

Usage:
  python3 scan.py --itk-src <ITK main checkout> <consumer-dir> [<consumer-dir> ...]
  python3 scan.py --itk-src ~/src/ITK --json out.json ~/src/ANTs

The deprecated-header table is read from the ITK checkout, not hardcoded:
every ITK header carrying "is deprecated; migrate to <replacement>" is a shim
that warns under ITK_LEGACY_REMOVE and fails under ITK_FUTURE_LEGACY_REMOVE.

Findings, one line each (file:line  KIND  detail):
  DEPRECATED_INCLUDE  includes a shimmed header; use the named replacement
  DEPRECATED_SYMBOL   uses a shimmed class/function (often reached through a
                      transitive include that ITK 6 no longer provides)
  MSVC_PORTABILITY    M_PI and friends, undefined on MSVC
Exit status: 0 with no findings, 1 otherwise.
"""
import argparse
import json
import os
import re
import sys

SOURCE_EXT = (".h", ".hxx", ".hpp", ".txx", ".cxx", ".cpp", ".cc", ".c", ".inl")
SKIP_DIRS = {".git", "build", "ThirdParty", "third_party", "_deps"}
SHIM = re.compile(r'is deprecated; migrate to ([^"]+?)\.?"')
MSVC_MACROS = re.compile(r"\bM_(PI|PI_2|PI_4|E|SQRT2|LN2|LN10|LOG2E|LOG10E|1_PI|2_PI|2_SQRTPI|SQRT1_2)\b")
LINE_COMMENT = re.compile(r"^\s*//")


def itk_shims(itk_src):
    """{header basename: replacement} for every deprecation shim in ITK."""
    shims = {}
    for root, dirs, files in os.walk(os.path.join(itk_src, "Modules")):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            if not f.endswith((".h", ".hxx")):
                continue
            p = os.path.join(root, f)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    m = SHIM.search(fh.read())
            except OSError:
                continue
            if m:
                shims[f] = " ".join(m.group(1).split())
    return shims


def sources(paths):
    for top in paths:
        if os.path.isfile(top):
            yield top
            continue
        for root, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith("-build")]
            for f in files:
                if f.endswith(SOURCE_EXT):
                    yield os.path.join(root, f)


def scan(paths, shims):
    include_re = re.compile(r'#\s*include\s*[<"](?:[\w./]*/)?(' + "|".join(map(re.escape, shims)) + r')[>"]')
    symbols = {os.path.splitext(h)[0]: h for h in shims}
    symbol_re = re.compile(r"\b(" + "|".join(map(re.escape, sorted(symbols, key=len, reverse=True))) + r")\b(?!\.h)")
    findings = []
    for path in sources(paths):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().split("\n")
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if LINE_COMMENT.match(line):
                continue
            m = include_re.search(line)
            if m:
                findings.append((path, n, "DEPRECATED_INCLUDE", m.group(1), shims[m.group(1)]))
                continue
            for m in symbol_re.finditer(line):
                h = symbols[m.group(1)]
                findings.append((path, n, "DEPRECATED_SYMBOL", m.group(1), shims[h]))
            for m in MSVC_MACROS.finditer(line):
                findings.append((path, n, "MSVC_PORTABILITY", m.group(0), "itk::Math constants (itkMath.h)"))
    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--itk-src", required=True, help="ITK main source checkout")
    ap.add_argument("--json", help="also write findings as JSON")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    shims = itk_shims(os.path.expanduser(a.itk_src))
    if not shims:
        sys.exit(f"no deprecation shims found under {a.itk_src}/Modules; is it an ITK main checkout?")
    findings = scan(a.paths, shims)
    for path, n, kind, what, repl in findings:
        print(f"{path}:{n}  {kind:<18} {what}  ->  {repl}")
    by_kind = {}
    for f in findings:
        by_kind[f[2]] = by_kind.get(f[2], 0) + 1
    print(f"\n{len(shims)} ITK shims; {len(findings)} findings " + str(by_kind), file=sys.stderr)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump([dict(zip(("file", "line", "kind", "what", "replacement"), f)) for f in findings], fh, indent=1)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
