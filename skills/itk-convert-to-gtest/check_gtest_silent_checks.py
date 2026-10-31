"""Find checks in ITK tests that report a problem but cannot fail the test.

For each test source given (legacy or GoogleTest):
- try/catch where neither the try nor the catch records a failure:
  "expected-not-failed" when the try body or the five lines before it say
  an exception is expected (nothing fails if the call does not throw),
  otherwise "swallowed" (an unexpected exception is printed and the test
  carries on). The label is a hint; the fix depends on which one it is.
- if-block that prints an error but records no failure ("silent-if").

Recording a failure means FAIL/ADD_FAILURE/EXPECT_*/ASSERT_*, return, throw,
abort, setting a flag or status (x = false/true/EXIT_FAILURE), or bumping a
counter (++n, n++, n += 1). Comments are ignored, so a commented-out failure
counts as none. A hit is a candidate: a flag checked later, or a helper that falls
through to `return false`, is a false positive. Read each site before fixing.
Fix legacy defects first, then convert (SKILL.md, "Defects found in a legacy
test").

Usage: check_gtest_silent_checks.py FILE...   (exit 1 if any site is found)
"""

import argparse
import re
import sys
from pathlib import Path

RECORDS = re.compile(
    r"\b(FAIL|ADD_FAILURE|GTEST_FAIL|EXPECT_\w+|ASSERT_\w+|return|throw|abort)\b"
    r"|\w+\s*=\s*(false|true|EXIT_FAILURE)\b|\+\+\s*\w+|\w+\s*\+\+|\w+\s*\+=\s*1\b"
)
EXPECTS_THROW = re.compile(r"should|expected|exercise the exception|caus\w* an exception", re.I)
ERROR_PRINT = re.compile(
    r"std::c(err|out)\s*<<[^;]*\b(error|fail|wrong|incorrect|mismatch|differ|not |should)", re.I
)


def strip_comments(text):
    """Blank out comments, keeping offsets and line numbers."""

    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    return re.sub(r"//[^\n]*|/\*.*?\*/", blank, text, flags=re.S)


def block(text, open_brace):
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1 : i], i
    return "", len(text)


def without_nested_blocks(body):
    """Drop nested {...} so a print inside an inner block is judged by that block."""
    out, depth = [], 0
    for ch in body:
        depth += ch == "{"
        if depth == 0:
            out.append(ch)
        depth -= ch == "}"
    return "".join(out)


def scan(path):
    raw = Path(path).read_text()
    text = strip_comments(raw)
    line = lambda pos: text.count("\n", 0, pos) + 1
    hits = []
    for m in re.finditer(r"\btry\s*\{", text):
        tbody, tend = block(text, m.end() - 1)
        cm = re.match(r"\s*catch\s*\([^)]*\)\s*\{", text[tend + 1 :])
        if not cm:
            continue
        cbody, _ = block(text, tend + 1 + cm.end() - 1)
        if RECORDS.search(tbody) or RECORDS.search(cbody):
            continue
        before = "\n".join(raw[: m.start()].splitlines()[-5:])
        kind = "expected-not-failed" if EXPECTS_THROW.search(before + tbody) else "swallowed"
        hits.append((line(m.start()), kind))
    for m in re.finditer(r"\bif\s*\((?:[^{};]|\([^)]*\))*\)\s*\{", text):
        body, _ = block(text, m.end() - 1)
        if ERROR_PRINT.search(without_nested_blocks(body)) and not RECORDS.search(body):
            hits.append((line(m.start()), "silent-if"))
    return sorted(hits)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    found = 0
    for f in args.files:
        src = Path(f).read_text().splitlines()
        for n, kind in scan(f):
            print(f"{f}:{n}: {kind}: {src[n - 1].strip()}")
            found += 1
    print(f"# {found} site(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
