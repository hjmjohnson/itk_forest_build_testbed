#!/usr/bin/env python3
"""Comment/string-aware regex substitution for C/C++ sources.

Applies (pattern, replacement) regex substitutions ONLY to code regions —
never inside // line comments, /* */ block comments, raw strings, or
string/char literals. Prints each file it actually changed (one per line).
With --dry-run, prints a unified diff per file and writes nothing.

This is the safety guard the plain-sed path lacks: identifier renames such
as atoi -> std::stoi must not rewrite documentation or string contents.
"""

import argparse
import difflib
import re
import sys


def _segment(src):
    """Split src into (is_code, text) runs, isolating comments and literals."""
    i, n = 0, len(src)
    runs = []  # [is_code, [chunks]]

    def push(is_code, s):
        if runs and runs[-1][0] == is_code:
            runs[-1][1].append(s)
        else:
            runs.append([is_code, [s]])

    while i < n:
        two = src[i : i + 2]
        c = src[i]
        if two == "//":
            j = src.find("\n", i)
            j = n if j == -1 else j
            push(False, src[i:j])
            i = j
        elif two == "/*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            push(False, src[i:j])
            i = j
        elif c == '"' or c == "'":
            # Raw string: R"delim( ... )delim"
            if c == '"' and i > 0 and src[i - 1] == "R":
                m = re.match(r'"([^(\s\\]{0,16})\(', src[i:])
                if m:
                    close = ')' + m.group(1) + '"'
                    j = src.find(close, i + m.end())
                    j = n if j == -1 else j + len(close)
                    push(False, src[i:j])
                    i = j
                    continue
            q = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == q:
                    j += 1
                    break
                if src[j] == "\n":  # unterminated; stop at line end
                    break
                j += 1
            push(False, src[i:j])
            i = j
        else:
            push(True, c)
            i += 1
    return [(is_code, "".join(chunks)) for is_code, chunks in runs]


def transform(src, subs):
    """Return src with subs applied to code regions only."""
    out = []
    for is_code, text in _segment(src):
        if is_code:
            for pat, repl in subs:
                text = pat.sub(repl, text)
        out.append(text)
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sub", nargs=2, action="append", metavar=("PATTERN", "REPL"),
                    default=[], help="regex pattern and replacement (repeatable)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    subs = [(re.compile(p), r) for p, r in a.sub]
    if not subs:
        return 0
    for path in a.files:
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"mc_code_subst: skip {path}: {e}", file=sys.stderr)
            continue
        new = transform(src, subs)
        if new == src:
            continue
        if a.dry_run:
            diff = difflib.unified_diff(
                src.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=path, tofile=path + " (proposed)")
            sys.stdout.writelines(diff)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
