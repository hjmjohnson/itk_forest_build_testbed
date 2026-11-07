#!/usr/bin/env python3
"""List ITK image iterators declared writable that the file never writes through.

Read-only scanner: it never edits a file. Output is a candidate list for a
person to convert by hand; precision is about 80 percent, so check each one.

  const_iterators.py scan <root> [<root> ...] [--json] [--summary]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ITER = r"(?:itk::)?(Image\w*?Iterator\w*)"
DECL = re.compile(ITER + r"\s*<\s*([^<>;]*(?:<[^<>;]*>[^<>;]*)*)>\s*(?:::\w+\s*)?\s*(\w+)\s*[\(\{=;]")
ALIAS = re.compile(
    r"(?:using\s+(\w+)\s*=\s*(?:typename\s+)?" + ITER + r"\s*<([^;]*)>\s*;"
    r"|typedef\s+(?:typename\s+)?" + ITER + r"\s*<([^;]*)>\s+(\w+)\s*;)"
)
SKIP_DIRS = {".git", "ThirdParty", "Utilities", "ExternalData", "Testing"}
EXTENSIONS = {".cxx", ".cpp", ".cc", ".h", ".hxx", ".txx", ".hpp"}
NOT_IMAGE_ITERATOR = re.compile(
    r"Neighborhood|SliceIterator$|Container|Path|Line|FloodFilled|Conditional|Shaped|Mesh|Point|Cell|List|Sample|Histogram|Measurement"
)


def skipped(path, root):
    parts = path.relative_to(root).parts[:-1]
    return any(
        p in SKIP_DIRS or p.endswith("-build") or p.startswith((".", "build", "cmake-build")) for p in parts
    )


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def written(text, var):
    name = re.escape(var)
    return bool(
        re.search(rf"\b{name}\s*(?:\.|->)\s*(?:Set|Value)\s*\(", text)
        or re.search(rf"\*\s*{name}\s*=", text)
        or re.search(rf"\bstd::(?:fill|copy|transform)\w*\([^;]*\b{name}\b", text)
    )


def escapes(text, var):
    """True when the iterator is passed to a function, which may write through it."""
    name = re.escape(var)
    return bool(re.search(rf"[\(,]\s*&?{name}\s*[,\)]", text))


def declarations(text):
    aliases = {}
    for m in ALIAS.finditer(text):
        if m.group(1):
            aliases[m.group(1)] = (m.group(2), m.group(3))
        else:
            aliases[m.group(6)] = (m.group(4), m.group(5))
    found = []
    for m in DECL.finditer(text):
        start = text.rfind("\n", 0, m.start()) + 1
        if re.search(r"\b(typedef|using)\b", text[start:m.start()]):
            continue
        found.append((m.start(), m.group(1), m.group(2), m.group(3), None))
    for alias, (kind, arg) in aliases.items():
        for m in re.finditer(rf"(?<![:\w]){re.escape(alias)}\s+(\w+)\s*[\(\{{=;]", text):
            found.append((m.start(), kind, arg, m.group(1), alias))
    return found


def scan_file(path, root):
    text = path.read_text(errors="ignore")
    if "Iterator" not in text:
        return [], Counter()
    counts = Counter()
    decls = declarations(text)
    writable_aliases = {
        a for _, kind, _, var, a in decls if a and "Const" not in kind and written(text, var)
    }
    candidates = []
    for offset, kind, arg, var, alias in decls:
        if NOT_IMAGE_ITERATOR.search(kind):
            continue
        if "Const" in kind:
            counts["const"] += 1
            continue
        counts["writable"] += 1
        if re.match(r"\s*const\b", arg):
            counts["writable_over_const_image"] += 1
        if written(text, var):
            continue
        counts["never_written"] += 1
        notes = []
        if escapes(text, var):
            notes.append("passed to a function")
        if alias and alias in writable_aliases:
            notes.append(f"alias {alias} is shared with a written iterator: split it")
        candidates.append(
            {
                "file": str(path.relative_to(root)),
                "line": line_of(text, offset),
                "type": f"{kind}<{arg.strip()[:40]}>",
                "variable": var,
                "notes": notes,
            }
        )
    return candidates, counts


def scan(root):
    root = Path(root).resolve()
    candidates, counts = [], Counter()
    for path in sorted(root.rglob("*")):
        if path.suffix not in EXTENSIONS or not path.is_file() or skipped(path, root):
            continue
        found, c = scan_file(path, root)
        candidates.extend(found)
        counts.update(c)
    return candidates, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="list read-only writable iterators")
    p.add_argument("roots", nargs="+")
    p.add_argument("--json", action="store_true")
    p.add_argument("--summary", action="store_true", help="print counts only")
    args = parser.parse_args()

    for root in args.roots:
        candidates, counts = scan(root)
        if args.json:
            print(json.dumps({"root": root, "counts": counts, "candidates": candidates}, indent=2))
            continue
        print(f"# {root}: {dict(counts)}")
        if args.summary:
            continue
        for c in candidates:
            note = f"  [{'; '.join(c['notes'])}]" if c["notes"] else ""
            print(f"{c['file']}:{c['line']}: {c['type']} {c['variable']}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
