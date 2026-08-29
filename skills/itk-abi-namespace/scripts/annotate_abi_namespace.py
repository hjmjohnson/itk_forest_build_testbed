#!/usr/bin/env python3
"""Wrap every `namespace itk { ... }` block in ITK_ABI_NAMESPACE_BEGIN/END.

Every such block in a file is annotated, not just the first: a file that
opens `namespace itk` twice (itkPrintHelper.h, for one) is half-migrated
otherwise, and the halves disagree only under a non-default namespace.

Namespaces nested inside an annotated block (itk::Statistics, itk::Function)
ride along inside the inline namespace. Blocks written in the C++17 nested
form `namespace itk::Sub` are expanded to the two-level form, because the
inline namespace has to sit between `itk` and the nested name.

Usage:  annotate_abi_namespace.py [--apply] <path>...
Without --apply the script reports what it would change and touches nothing.
"""
import argparse
import re
import sys
from pathlib import Path

EXTS = {".h", ".hxx", ".cxx", ".txx", ".hpp", ".in"}
SKIP_PARTS = {".git", "ThirdParty", "build", ".devlocal", ".pixi"}

# `namespace itk` followed by `{` (not `namespace itk::sub` and not an alias).
NS_OPEN = re.compile(r"^([ \t]*)namespace\s+itk\s*$\n^[ \t]*\{[ \t]*$", re.M)
NS_OPEN_INLINE = re.compile(r"^([ \t]*)namespace\s+itk\s*\{[ \t]*$", re.M)
# C++17 nested form: `namespace itk::Math` ... `} // namespace itk::Math`
NS_NESTED = re.compile(r"^[ \t]*namespace\s+itk::(\w[\w:]*)\s*$\n^[ \t]*\{[ \t]*$", re.M)
ALREADY = "ITK_ABI_NAMESPACE_BEGIN"


def mask_noise(text):
    """Same-length copy with comment and literal bodies blanked.

    Brace matching and pattern search run against this so that a `{` inside a
    string (itkConstNeighborhoodIteratorWithOnlyIndex.hxx prints one) cannot
    unbalance the scan. Offsets are preserved, so every index found in the mask
    addresses the same character in the original.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if text[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            for k in range(i, min(j + 1, n)):
                if text[k] != "\n":
                    out[k] = " "
            i = j + 1
        else:
            i += 1
    return "".join(out)


def first_unannotated(text, mask, pattern):
    """First match of pattern whose block does not already open with BEGIN."""
    for match in pattern.finditer(mask):
        brace_pos = mask.index("{", match.start())
        end_pos = find_block_end(mask, brace_pos)
        if end_pos < 0:
            continue
        if ALREADY not in mask[brace_pos:end_pos]:
            return match
    return None


def find_block_end(text, brace_pos):
    """Index of the `}` matching the `{` at brace_pos, ignoring nothing else."""
    depth = 0
    for i in range(brace_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def annotate(text):
    """Return (new_text, n_blocks) with every `namespace itk` block wrapped."""
    total = 0
    while True:
        text, n = annotate_one(text)
        if not n:
            return text, total
        total += n


def annotate_one(text):
    """Wrap the first not-yet-annotated `namespace itk` block."""
    mask = mask_noise(text)
    match = first_unannotated(text, mask, NS_OPEN) or first_unannotated(text, mask, NS_OPEN_INLINE)
    if match:
        brace_pos = mask.index("{", match.start())
        end_pos = find_block_end(mask, brace_pos)
        if end_pos < 0:
            return text, 0
        # Insert END first so the earlier index stays valid.
        out = text[:end_pos] + ALREADY.replace("BEGIN", "END") + "\n" + text[end_pos:]
        out = out[: brace_pos + 1] + "\n" + ALREADY + out[brace_pos + 1 :]
        return out, 1

    # C++17 nested form must be expanded, because the inline namespace has to
    # sit between `itk` and the nested name.
    nested = first_unannotated(text, mask, NS_NESTED)
    if not nested:
        return text, 0
    sub = nested.group(1)
    brace_pos = mask.index("{", nested.start())
    end_pos = find_block_end(mask, brace_pos)
    if end_pos < 0:
        return text, 0

    close_line_end = text.find("\n", end_pos)
    close_line_end = len(text) if close_line_end < 0 else close_line_end
    new_close = f"}} // namespace {sub}\nITK_ABI_NAMESPACE_END\n}} // namespace itk"
    out = text[:end_pos] + new_close + text[close_line_end:]
    new_open = f"namespace itk\n{{\n{ALREADY}\nnamespace {sub}\n{{"
    return out[: nested.start()] + new_open + out[brace_pos + 1 :], 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    changed = skipped = 0
    for root in args.paths:
        files = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in files:
            if path.suffix not in EXTS or not path.is_file():
                continue
            if SKIP_PARTS & set(path.parts):
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            new, n = annotate(text)
            if not n:
                if "namespace itk" in text and ALREADY not in text:
                    skipped += 1
                    print(f"  SKIP (unmatched shape) {path}", file=sys.stderr)
                continue
            changed += 1
            if args.apply:
                path.write_text(new)

    verb = "annotated" if args.apply else "would annotate"
    print(f"{verb} {changed} files; {skipped} skipped for manual review")


main()
