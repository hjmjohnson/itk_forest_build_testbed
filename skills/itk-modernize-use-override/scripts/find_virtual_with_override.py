#!/usr/bin/env python3
"""Find (and optionally remove) `virtual` on declarations that also carry `override` or `final`.

Text-only heuristic, no build required. Complements clang-tidy modernize-use-override
by covering macro bodies and modules that are not compiled locally.

Known false positives: comment text without a leading `*`, string literals, `#if 0`
blocks, and `override`/`final` used as identifiers. Review every hit before --fix.

Known misses: `inline virtual`, `[[attr]] virtual`, a `//` comment before `override`,
and `= {}` default arguments.

Usage:
  find_virtual_with_override.py [REPO ...] [--ref REV] [--exclude REGEX] [--fix]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERN = re.compile(
    r"^[ \t]*virtual\b(?:(?!\*/|/\*|//|\n[ \t]*\n|\n[ \t]*#)[^;{}])*?\b(?:override|final)\b",
    re.MULTILINE,
)
LEADING_VIRTUAL = re.compile(r"^([ \t]*)virtual[ \t]+")
SUFFIXES = ("*.h", "*.hxx", "*.hpp", "*.cxx", "*.cpp", "*.cc", "*.txx", "*.in")
DEFAULT_EXCLUDE = r"(^|/)ThirdParty/"


def git(repo: Path, *args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, check=True).stdout


def candidate_files(repo: Path, ref: str | None, exclude: re.Pattern) -> list[str]:
    tree = [ref] if ref else []
    out = subprocess.run(
        ["git", "-C", str(repo), "grep", "-l", "-w", "virtual", *tree, "--", *SUFFIXES],
        capture_output=True,
        text=True,
    ).stdout.split()
    paths = [p.split(":", 1)[1] if ref else p for p in out]
    return [p for p in paths if not exclude.search(p)]


def read_contents(repo: Path, ref: str | None, paths: list[str]) -> dict[str, str]:
    if not ref:
        return {p: (repo / p).read_text(encoding="utf-8", errors="replace") for p in paths}
    blob = git(repo, "cat-file", "--batch", stdin=("\n".join(f"{ref}:{p}" for p in paths) + "\n").encode())
    contents, pos = {}, 0
    for p in paths:
        eol = blob.index(b"\n", pos)
        size = int(blob[pos:eol].split()[2])
        contents[p] = blob[eol + 1 : eol + 1 + size].decode("utf-8", errors="replace")
        pos = eol + 1 + size + 1
    return contents


def scan(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), text.count("\n", 0, m.start()) + 1, m.group(0)) for m in PATTERN.finditer(text)]


def remove_virtual(text: str, starts: list[int]) -> str:
    for start in sorted(starts, reverse=True):
        line_end = text.find("\n", start)
        line_end = len(text) if line_end == -1 else line_end
        text = text[:start] + LEADING_VIRTUAL.sub(r"\1", text[start:line_end], count=1) + text[line_end:]
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repos", nargs="*", type=Path, default=[Path.cwd()])
    parser.add_argument("--ref", help="scan a git revision instead of the working tree")
    parser.add_argument("--exclude", default=DEFAULT_EXCLUDE, help=f"path regex to skip (default: {DEFAULT_EXCLUDE})")
    parser.add_argument("--fix", action="store_true", help="remove the leading `virtual` in the working tree")
    args = parser.parse_args()
    if args.fix and args.ref:
        parser.error("--fix applies to the working tree; omit --ref")

    exclude = re.compile(args.exclude)
    total = 0
    for repo in args.repos:
        repo = repo.expanduser().resolve()
        if not (repo / ".git").exists():
            print(f"{repo}: not a git repository", file=sys.stderr)
            continue
        paths = candidate_files(repo, args.ref, exclude)
        for path, text in read_contents(repo, args.ref, paths).items():
            hits = scan(text)
            for _, line, match in hits:
                print(f"{repo / path}:{line}: {' '.join(match.split())}")
            if hits and args.fix:
                (repo / path).write_text(remove_virtual(text, [s for s, _, _ in hits]), encoding="utf-8")
            total += len(hits)
    print(f"{total} hit(s)", file=sys.stderr)
    return 1 if total and not args.fix else 0


if __name__ == "__main__":
    sys.exit(main())
