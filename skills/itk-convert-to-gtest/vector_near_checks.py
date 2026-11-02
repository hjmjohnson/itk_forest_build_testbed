"""Collapse element-by-element EXPECT_NEAR checks into ITK_EXPECT_VECTOR_NEAR.

ITK_EXPECT_VECTOR_NEAR(a, b, tol) (itkGTestPredicate.h) compares two ITK
array-like objects (Point, Vector, CovariantVector, FixedArray, Array,
VariableLengthVector, ...) by RMS difference and prints both on failure.
See ITK PR #7090. Two shapes are rewritten:

    for (unsigned int i = 0; i < N; ++i)          ITK_EXPECT_VECTOR_NEAR(a, b, tol);
    {
      EXPECT_NEAR(a[i], b[i], tol);
    }

    EXPECT_NEAR(a[0], b[0], tol) << "msg";        ITK_EXPECT_VECTOR_NEAR(a, b, tol) << "msg";
    EXPECT_NEAR(a[1], b[1], tol) << "msg";

A streamed message is kept when it is the same on every element and does not
use the loop variable; otherwise it is dropped (the macro prints both
objects). The RMS test lets one component differ by up to sqrt(n) * tol.

The rewrite compares every element, so a loop bound or a run that covers
only part of the object changes what is checked: compare the reported count
with the object's length. A run followed by a check of element k in another
form (a negated expected value, say) is skipped. Types without itk::NumericTraits<T>::GetLength
(std::vector, C arrays, matrix rows) fail to compile; revert those sites.

Usage: vector_near_checks.py [--fix] FILE...
  without --fix: list sites, exit 1 if any exist
  with --fix:    rewrite the files in place
"""

import argparse
import re
import sys
from pathlib import Path

FOR = re.compile(
    r"^(?P<indent>\s*)for\s*\(\s*(?:const\s+)?(?:unsigned\s+int|unsigned|int|size_t|std::size_t|"
    r"itk::SizeValueType|itk::IndexValueType|auto|[\w:]+Type)\s+(?P<v>\w+)\s*=\s*0[uU]?\s*;\s*(?P=v)\s*<\s*"
    r"(?P<n>[^;]+?)\s*;\s*(?:\+\+(?P=v)|(?P=v)\+\+)\s*\)\s*(?P<brace>\{)?\s*$"
)
INDEXED = re.compile(r"^(?P<obj>[\w:]+(?:(?:\.|->)\w+(?:\(\))?|\(\))*)\[\s*(?P<i>\w+)\s*\]$")


def split_args(text):
    """Split 'a, b, c' at top-level commas."""
    args, depth, cur, quote = [], 0, "", None
    for ch in text:
        if quote:
            cur += ch
            if ch == quote and not cur.endswith("\\" + quote):
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{<":
            depth += ch != "<"
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
            continue
        cur += ch
    args.append(cur.strip())
    return args


def statement(lines, i):
    """Parse an EXPECT_NEAR statement starting at line i.

    Returns (last_line, indent, a, idx_a, b, idx_b, tol, msg) or None.
    """
    m = re.match(r"^(\s*)EXPECT_NEAR\s*\(", lines[i])
    if not m:
        return None
    text, j = lines[i].strip(), i
    while not text.rstrip().endswith(";"):
        j += 1
        if j >= len(lines) or j - i > 6:
            return None
        text += " " + lines[j].strip()
    body = text[text.index("(") + 1 :]
    depth = 1
    for k, ch in enumerate(body):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0:
            break
    else:
        return None
    args, rest = split_args(body[:k]), body[k + 1 :].rstrip()[:-1].strip()
    if len(args) != 3 or (rest and not rest.startswith("<<")):
        return None
    ma, mb = INDEXED.match(args[0]), INDEXED.match(args[1])
    if not ma or not mb:
        return None
    return j, m.group(1), ma["obj"], ma["i"], mb["obj"], mb["i"], args[2], rest


def uses(expr, var):
    return re.search(rf"\b{re.escape(var)}\b", expr) is not None


def loop_site(lines, i):
    m = FOR.match(lines[i])
    if not m:
        return None
    v, j, braced = m["v"], i + 1, bool(m["brace"])
    if not braced and j < len(lines) and lines[j].strip() == "{":
        j, braced = j + 1, True
    if j >= len(lines):
        return None
    s = statement(lines, j)
    if not s:
        return None
    last, _, a, ia, b, ib, tol, msg = s
    if ia != v or ib != v or any(uses(x, v) for x in (a, b, tol)):
        return None
    if uses(msg, v):
        msg = ""
    end = last
    if braced:
        end = last + 1
        if end >= len(lines) or lines[end].strip() != "}":
            return None
    return end, m["indent"], a, b, tol, msg, m["n"]


def run_site(lines, i):
    s = statement(lines, i)
    if not s or s[3] != "0" or s[5] != "0":
        return None
    last, indent, a, _, b, _, tol, msg = s
    msgs, k, end = [msg], 1, last
    while end + 1 < len(lines):
        n = statement(lines, end + 1)
        if not n or (n[2], n[4], n[6]) != (a, b, tol) or n[3] != str(k) or n[5] != str(k):
            break
        msgs.append(n[7])
        end, k = n[0], k + 1
    if k < 2:
        return None
    following = " ".join(lines[end + 1 : end + 3])
    if re.search(rf"(?:{re.escape(a)}|{re.escape(b)})\[\s*{k}\s*\]", following):
        return None
    return end, indent, a, b, tol, msg if len(set(msgs)) == 1 else "", str(k)


def process(path, fix):
    lines = path.read_text().split("\n")
    out, hits, i = [], 0, 0
    while i < len(lines):
        site = loop_site(lines, i) or run_site(lines, i)
        if not site:
            out.append(lines[i])
            i += 1
            continue
        end, indent, a, b, tol, msg, count = site
        hits += 1
        print(f"{path}:{i + 1}: {a} vs {b}, {count} elements, tol {tol}{', message kept' if msg else ''}")
        out.append(f"{indent}ITK_EXPECT_VECTOR_NEAR({a}, {b}, {tol}){' ' + msg if msg else ''};")
        i = end + 1
    if fix and hits:
        path.write_text("\n".join(out))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()
    total = sum(process(f, args.fix) for f in args.files)
    return 1 if total and not args.fix else 0


if __name__ == "__main__":
    sys.exit(main())
