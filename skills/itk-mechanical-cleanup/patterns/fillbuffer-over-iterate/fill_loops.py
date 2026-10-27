#!/usr/bin/env python3
"""Rewrite the one safe iterator fill loop shape into image->FillBuffer(value).

Reads SRC, writes the rewritten text to OUT, and appends a row per candidate loop it
leaves alone (pre-edit lines) to --skips. A candidate is a for/while loop on
`!it.IsAtEnd()` whose body calls `it.Set(`; it is rewritten only when the iterator is an
ImageRegionIterator over `img->GetBufferedRegion()` or `img->GetLargestPossibleRegion()`
and the body is exactly `it.Set(<loop-invariant expr>);` (plus `++it;` in a while loop).
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "itk-init-over-assign" / "lib"))

from ioa.skip import Reason  # noqa: E402
from ioa.source import mask  # noqa: E402

LOOP = re.compile(r"\b(for|while)\s*\(")
AT_END = re.compile(r"\s*!\s*(\w+)\s*\.\s*IsAtEnd\s*\(\s*\)\s*")
REGION = r"(?P<img>\w+)\s*,\s*(?P=img)\s*->\s*Get(?:Buffered|LargestPossible)Region\s*\(\s*\)"
CTOR = r"(?P<type>[\w:<>, ]+?)\s+{it}\s*[({{]\s*" + REGION + r"\s*[)}}]"
PURE_CALLS = {"static_cast", "ZeroValue", "OneValue", "max", "min", "lowest", "NonpositiveMin", "epsilon"}


def _close(masked: str, i: int) -> int:
    open_, close = masked[i], {"(": ")", "{": "}", "[": "]"}[masked[i]]
    depth = 0
    for k in range(i, len(masked)):
        depth += masked[k] == open_
        depth -= masked[k] == close
        if depth == 0:
            return k
    return -1


def _split_top(s: str, sep: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in s:
        depth += ch in "([{"
        depth -= ch in ")]}"
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    return parts + ["".join(cur)]


def is_region_iterator(type_: str, masked: str) -> bool:
    family = r"ImageRegionIterator(?:WithIndex)?\s*<"
    if re.search(r"\bImageRegionIterator(?:WithIndex)?\b", type_):
        return True
    alias = re.escape(type_.split("::")[-1].strip())
    return bool(re.search(rf"\busing\s+{alias}\s*=[^;]*\b{family}", masked)
                or re.search(rf"\btypedef\b[^;]*\b{family}[^;]*\b{alias}\s*;", masked))


def invariant(expr: str, it: str) -> bool:
    if not expr.strip() or re.search(rf"\b{re.escape(it)}\b", expr):
        return False
    if re.search(r"\+\+|--|(?<![=!<>])=(?!=)", expr):
        return False
    for call in re.finditer(r"(\w+)\s*(?:<[^()]*>)?\s*\(", expr):
        member = re.search(r"(?:\.|->)\s*$", expr[:call.start()])
        conversion = call[1][0].isupper() and call[1].endswith("Type") and not member
        if call[1] not in PURE_CALLS and not conversion:
            return False
    return True


def _set_call(stmt: str, it: str) -> str | None:
    m = re.fullmatch(rf"\s*{re.escape(it)}\s*\.\s*Set\s*\((?P<expr>.*)\)\s*", stmt, re.S)
    if not m or _close(stmt, stmt.index("(", m.start("expr") - 1)) != m.end("expr"):
        return None
    return m["expr"].strip()


def rewrite(text: str) -> tuple[str, list[tuple[int, int, Reason, str]]]:
    """The rewritten text and the (start, end, reason, note) lines of candidate loops left alone."""
    masked = mask(text, literals=True)
    uncommented = mask(text)
    edits: list[tuple[int, int, str]] = []
    skipped: list[tuple[int, int, Reason, str]] = []
    for m in LOOP.finditer(masked):
        open_ = m.end() - 1
        close = _close(masked, open_)
        if close < 0:
            continue
        header = masked[open_ + 1:close]
        parts = _split_top(header, ";") if m[1] == "for" else ["", header, ""]
        cond = AT_END.fullmatch(parts[1]) if len(parts) == 3 else None
        if not cond:
            continue
        it = cond[1]
        k = close + 1
        while k < len(masked) and masked[k].isspace():
            k += 1
        end = _close(masked, k) if masked[k:k + 1] == "{" else masked.find(";", k)
        if end < 0:
            continue
        body = masked[k + 1:end] if masked[k] == "{" else masked[k:end + 1]
        if not re.search(rf"\b{re.escape(it)}\s*\.\s*Set\s*\(", body):
            continue
        new = _safe(m, parts, it, body, masked, text, close)
        last = text.count("\n", 0, end) + 1
        if new is None:
            skipped.append((text.count("\n", 0, m.start()) + 1, last, Reason.LOOP_CARRIED, "not-fill-shape"))
        elif uncommented[new[0]:end + 1] != text[new[0]:end + 1]:
            skipped.append((text.count("\n", 0, new[0]) + 1, last, Reason.COMMENT_STRANDED, "comment-in-loop"))
        else:
            edits.append((new[0], end + 1, new[1]))
    out, last = [], 0
    for a, b, s in edits:
        out += [text[last:a], s]
        last = b
    return "".join(out) + text[last:], skipped


def _safe(m: re.Match, parts: list[str], it: str, body: str, masked: str, text: str,
          close: int) -> tuple[int, str] | None:
    stmts = [s for s in _split_top(body, ";")]
    if stmts[-1].strip():
        return None
    stmts = stmts[:-1]
    start = m.start()
    if m[1] == "for":
        decl = re.fullmatch(r"\s*" + CTOR.format(it=re.escape(it)) + r"\s*", parts[0])
        if not decl or not re.fullmatch(rf"\s*(?:\+\+\s*{re.escape(it)}|{re.escape(it)}\s*\+\+)\s*", parts[2]):
            return None
        if len(stmts) != 1:
            return None
    else:
        if len(stmts) != 2 or not re.fullmatch(rf"\s*(?:\+\+\s*{re.escape(it)}|{re.escape(it)}\s*\+\+)\s*",
                                               stmts[1]):
            return None
        stmts = stmts[:1]
        window = max(0, start - 2000)
        before = re.search(r"(?:^|[;{}])\s*(?P<decl>" + CTOR.format(it=re.escape(it)) + r"\s*;)"
                           rf"(?:\s*{re.escape(it)}\s*\.\s*GoToBegin\s*\(\s*\)\s*;)?\s*\Z",
                           masked[window:start])
        if not before or _used_after(masked, close, it):
            return None
        decl, start = before, window + before.start("decl")
    expr = _set_call(stmts[0], it)
    if expr is None or not is_region_iterator(decl["type"], masked) or not invariant(expr, it):
        return None
    return start, f"{decl['img']}->FillBuffer({text[_offset(text, masked, stmts[0], expr, m.start())]});"


def _offset(text: str, masked: str, stmt: str, expr: str, after: int) -> slice:
    i = masked.find(stmt, after) + stmt.index(expr)
    return slice(i, i + len(expr))


def _used_after(masked: str, close: int, it: str) -> bool:
    k = close + 1
    while masked[k].isspace():
        k += 1
    end = _close(masked, k) if masked[k] == "{" else masked.find(";", k)
    depth, stop = 0, len(masked)
    for i in range(end + 1, len(masked)):
        depth += masked[i] == "{"
        depth -= masked[i] == "}"
        if depth < 0:
            stop = i
            break
    return re.search(rf"\b{re.escape(it)}\b", masked[end + 1:stop]) is not None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--rel", help="path written in skip rows (default: src)")
    ap.add_argument("--skips", type=Path, help="append REL<TAB>START<TAB>END<TAB>REASON<TAB>NOTE rows here")
    args = ap.parse_args(argv)
    data = args.src.read_bytes().decode("utf-8", "surrogateescape")
    new, skipped = rewrite(data)
    args.out.write_bytes(new.encode("utf-8", "surrogateescape"))
    if args.skips is not None and skipped:
        rel = args.rel or str(args.src)
        with args.skips.open("a") as f:
            for a, b, reason, note in skipped:
                f.write(f"{rel}\t{a}\t{b}\t{reason}\t{note}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
