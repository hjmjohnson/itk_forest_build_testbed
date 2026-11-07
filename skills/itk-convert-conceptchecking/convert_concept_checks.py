#!/usr/bin/env python3
"""Convert ITK concept checks in a code base the way ITK PR #7108 converted ITK.

ITK #7108 reimplemented itk::Concept as std::bool_constant traits checked by
static_assert. A code base built on ITK follows it in four phases, each meant
to be its own commit:

  audit          read-only report: removed APIs, dead guards, convertible checks
  enable         drop `#ifdef ITK_USE_CONCEPT_CHECKING` guards (ITK no longer
                 defines the macro, so the checks inside never compiled)
  static-assert  rewrite dimension, type, integer, signedness, and zero checks
                 as plain static_assert (the checks #7108 converted), and drop
                 the marker comments of a block left with nothing else
  comments       delete "Begin/End concept checking" comment lines

`all` runs enable, static-assert, and comments in that order. Every phase is a
dry run unless --apply is given. Nothing is committed. The script never
touches the removed custom-concept machinery (itkConceptConstraintsMacro,
Concept::Detail, ITK_CONCEPT_NO_CHECKING); `audit` lists it for a hand rewrite.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_SUFFIXES = {".h", ".hxx", ".txx", ".hpp", ".cxx", ".cpp", ".cc", ".inl"}
SKIP_DIRS = {".git", ".pixi", "node_modules", "__pycache__", ".devlocal"}

GUARD_OPEN = re.compile(
    r"^\s*#\s*(?:ifdef\s+ITK_USE_CONCEPT_CHECKING|if\s+defined\s*\(?\s*ITK_USE_CONCEPT_CHECKING\s*\)?)\s*(?://.*|/\*.*)?$"
)
PP_IF = re.compile(r"^\s*#\s*if(?:n?def)?\b")
PP_ELSE = re.compile(r"^\s*#\s*(?:else|elif)\b")
PP_ENDIF = re.compile(r"^\s*#\s*endif\b")
MARKER_COMMENT = re.compile(
    r"^\s*(?://+|/\*+)\s*(?:begin|start|end)\s+(?:of\s+)?concept\s+checking\.?\s*(?:\*+/)?\s*$",
    re.IGNORECASE,
)
TEMPLATE_PLACEHOLDER = re.compile(r"^\s*//\s*Add concept checking such as\s*$", re.IGNORECASE)
COMMENTED_CHECK = re.compile(r"^\s*//.*(?:itkConceptMacro|ITK_USE_CONCEPT_CHECKING)")
REMOVED_API = {
    "ITK_CONCEPT_NO_CHECKING": re.compile(r"\bITK_CONCEPT_NO_CHECKING\b"),
    "itkConceptConstraintsMacro": re.compile(r"\bitkConceptConstraintsMacro\b"),
    "Concept::Detail": re.compile(r"\bConcept::Detail\b"),
    "ITK_USE_STRICT_CONCEPT_CHECKING": re.compile(r"\bITK_USE_STRICT_CONCEPT_CHECKING\b"),
}
MACRO = re.compile(r"\bitkConceptMacro\s*\(")
CONCEPT_REF = re.compile(r"^\s*\(\s*((?:::)?(?:itk::)?)Concept::([A-Za-z]+)\s*<")

# Concept name -> number of template arguments; the conversions #7108 made.
CONVERTIBLE = {
    "SameDimension": 2,
    "SameDimensionOrMinusOne": 2,
    "SameDimensionOrMinusOneOrTwo": 2,
    "SameType": 2,
    "IsInteger": 1,
    "IsUnsignedInteger": 1,
    "Signed": 1,
    "HasZero": 1,
}
TRAIT_PREFIXES = ("std::is_same_v", "std::is_integral_v", "std::is_default_constructible_v")


@dataclass
class FileResult:
    path: Path
    original: str
    text: str
    changes: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.text != self.original


def source_files(roots: list[Path], excludes: list[str]) -> list[Path]:
    files = []
    for root in roots:
        candidates = [root] if root.is_file() else root.rglob("*")
        for p in candidates:
            if p.suffix not in SOURCE_SUFFIXES or not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if any(p.match(pattern) for pattern in excludes):
                continue
            if p.name == "itkConceptChecking.h":
                continue  # ITK's own definitions, e.g. in a vendored ITK
            files.append(p)
    return sorted(set(files))


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# ---------------------------------------------------------------- enable


def enable_guards(text: str) -> tuple[str, int, list[str]]:
    """Remove each `#ifdef ITK_USE_CONCEPT_CHECKING` line and its matching `#endif`."""
    lines = text.splitlines(keepends=True)
    drop: set[int] = set()
    notes = []
    i = 0
    while i < len(lines):
        if not GUARD_OPEN.match(lines[i]):
            i += 1
            continue
        depth, j, has_else = 0, i + 1, False
        while j < len(lines):
            if PP_IF.match(lines[j]):
                depth += 1
            elif PP_ELSE.match(lines[j]) and depth == 0:
                has_else = True
            elif PP_ENDIF.match(lines[j]):
                if depth == 0:
                    break
                depth -= 1
            j += 1
        if j == len(lines):
            notes.append(f"line {i + 1}: unterminated ITK_USE_CONCEPT_CHECKING guard; left as is")
        elif has_else:
            notes.append(f"line {i + 1}: guard has #else/#elif; convert by hand")
        else:
            drop.update((i, j))
        i = j + 1
    out = "".join(line for k, line in enumerate(lines) if k not in drop)
    return out, len(drop) // 2, notes


# ---------------------------------------------------------- static-assert


def matching_paren(text: str, open_at: int) -> int:
    """Index of the ')' that closes text[open_at] == '(', skipping strings and comments."""
    depth, k = 0, open_at
    while k < len(text):
        c = text[k]
        if c in "\"'":
            end = k + 1
            while end < len(text) and text[end] != c:
                end += 2 if text[end] == "\\" else 1
            k = end
        elif text.startswith("//", k):
            k = text.find("\n", k)
            if k < 0:
                return -1
        elif text.startswith("/*", k):
            k = text.find("*/", k)
            if k < 0:
                return -1
            k += 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return -1


def split_top_level(s: str, sep: str = ",") -> list[str]:
    parts, depth, start = [], 0, 0
    for k, c in enumerate(s):
        if c in "<([{":
            depth += 1
        elif c in ">)]}":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(s[start:k])
            start = k + 1
    parts.append(s[start:])
    return [" ".join(p.split()) for p in parts]


def template_args(concept_expr: str) -> list[str] | None:
    """The top-level template arguments of `( [itk::]Concept::Name< a, b > )`."""
    body = concept_expr.strip()
    if not (body.startswith("(") and body.endswith(")")):
        return None
    body = body[1:-1].strip()
    lt = body.find("<")
    if lt < 0 or not body.endswith(">"):
        return None
    return split_top_level(body[lt + 1 : -1])


INT_LITERAL = re.compile(r"^(\d+)[uUlL]*$")
SELF_TYPE = re.compile(r"\btypename\s+Self::(\w+)\b(?!\s*::)")


def unqualified(expr: str) -> str:
    """Drop `Self::`, which a class-scope static_assert does not need (N-Dekker on #7108)."""
    return re.sub(r"\bSelf::", "", SELF_TYPE.sub(r"\1", expr))


def literal(expr: str) -> int | None:
    m = INT_LITERAL.match(expr)
    return int(m.group(1)) if m else None


def convert(concept: str, args: list[str], prefix: str) -> str | None:
    """The static_assert condition for a convertible concept, as #7108 wrote it."""
    args = [unqualified(a) for a in args]
    if concept == "SameDimension":
        a, b = args
        return f"{a} == {b}"
    if concept in ("SameDimensionOrMinusOne", "SameDimensionOrMinusOneOrTwo"):
        a, b = args
        steps = 2 if concept == "SameDimensionOrMinusOne" else 3
        n = literal(a)
        if n is not None:
            low = n - steps + 1
            lower = f"{b} > 0" if low == 1 else f"{b} >= {low}"
            return f"{lower} && {b} <= {n}"
        return " || ".join(f"{b} == {v}" for v in [a] + [f"{a} - {k}" for k in range(1, steps)])
    if concept == "SameType":
        a, b = args
        return f"std::is_same_v<{a}, {b}>"
    (t,) = args
    if concept == "IsInteger":
        return f"std::is_integral_v<{t}>"
    if concept == "IsUnsignedInteger":
        return f"!{prefix}NumericTraits<{t}>::is_signed"
    if concept == "Signed":
        return f"{prefix}NumericTraits<{t}>::is_signed"
    if concept == "HasZero":
        return f"std::is_default_constructible_v<{t}>"
    return None


def to_static_assert(text: str, add_includes: bool = True) -> tuple[str, int, list[str]]:
    out, pos, count, notes = [], 0, 0, []
    for m in MACRO.finditer(text):
        if m.start() < pos:
            continue
        open_at = m.end() - 1
        close_at = matching_paren(text, open_at)
        if close_at < 0:
            notes.append(f"line {line_of(text, m.start())}: unbalanced itkConceptMacro; left as is")
            continue
        inner = text[open_at + 1 : close_at]
        name_and_concept = split_top_level(inner)
        if len(name_and_concept) != 2:
            continue
        concept_expr = inner[inner.find(",") + 1 :]
        ref = CONCEPT_REF.match(concept_expr)
        if not ref or ref.group(2) not in CONVERTIBLE:
            continue
        prefix = ref.group(1).removeprefix("::") if ref.group(1) else ""
        args = template_args(concept_expr)
        if args is None or len(args) != CONVERTIBLE[ref.group(2)]:
            notes.append(f"line {line_of(text, m.start())}: {ref.group(2)} not in the expected form; left as is")
            continue
        cond = convert(ref.group(2), args, prefix)
        if cond is None:
            continue
        out.append(text[pos : m.start()])
        out.append(f"static_assert({cond})")
        pos = close_at + 1
        count += 1
    out.append(text[pos:])
    result = "".join(out)
    if count:
        result = drop_markers_around_static_asserts(result)
    if add_includes and count and any(t in result for t in TRAIT_PREFIXES) and "<type_traits>" not in result:
        result = add_include(result, "<type_traits>")
    return result, count, notes


MARKER_KIND = re.compile(r"(begin|start|end)", re.IGNORECASE)


def drop_markers_around_static_asserts(text: str) -> str:
    """Delete the marker comments of a block that holds only static_assert statements."""
    lines = text.splitlines(keepends=True)
    kinds = {
        k: MARKER_KIND.search(line).group(1).lower() for k, line in enumerate(lines) if MARKER_COMMENT.match(line)
    }
    drop: set[int] = set()
    for k, kind in kinds.items():
        if kind == "end":
            continue
        j, statements, in_statement = k + 1, 0, False
        while j < len(lines):
            stripped = lines[j].strip()
            if not in_statement and not stripped.startswith("static_assert("):
                break
            statements += not in_statement
            in_statement = not stripped.endswith(";")
            j += 1
        if not statements or in_statement:
            continue
        if kinds.get(j) == "end":
            drop.update((k, j))
        elif next((kinds[m] for m in sorted(kinds) if m > k), "begin") != "end":
            drop.add(k)  # an opening marker that never had a closing one
    return "".join(line for k, line in enumerate(lines) if k not in drop)


INCLUDE_LINE = re.compile(r"^#\s*include\s*[<\"][^>\"]+[>\"]")


def add_include(text: str, header: str) -> str:
    """Insert after the first block of #include lines, never in a trailing .hxx include block."""
    lines = text.splitlines(keepends=True)
    first = next((k for k, line in enumerate(lines) if INCLUDE_LINE.match(line)), None)
    if first is None:
        return text
    last = first
    for k in range(first, len(lines)):
        stripped = lines[k].strip()
        if INCLUDE_LINE.match(lines[k]):
            last = k
        elif stripped and not stripped.startswith("//"):
            break
    indent = re.match(r"^#(\s*)include", lines[last]).group(1)
    lines.insert(last + 1, f"#{indent}include {header}\n")
    return "".join(lines)


# ----------------------------------------------------------------- comments


def remove_marker_comments(text: str) -> tuple[str, int]:
    """Delete marker lines; a deletion that leaves two blank lines in a row keeps only one."""
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    removed = 0
    k = 0
    while k < len(lines):
        if TEMPLATE_PLACEHOLDER.match(lines[k]):
            # ITKModuleTemplate's "Add concept checking such as" plus its commented example
            removed += 1
            k += 1
            if k < len(lines) and COMMENTED_CHECK.match(lines[k]):
                k += 1
            if kept and not kept[-1].strip() and k < len(lines) and not lines[k].strip():
                k += 1
            continue
        if MARKER_COMMENT.match(lines[k]):
            removed += 1
            k += 1
            if kept and not kept[-1].strip() and k < len(lines) and not lines[k].strip():
                k += 1
            continue
        kept.append(lines[k])
        k += 1
    return "".join(kept), removed


# -------------------------------------------------------------------- audit


def audit(files: list[Path], root: Path) -> int:
    guards, removed, commented, convertible, remaining, markers = [], [], [], {}, 0, 0
    for p in files:
        text = p.read_text(errors="replace")
        rel = p.relative_to(root) if p.is_relative_to(root) else p
        lines = text.splitlines()
        for k, line in enumerate(lines, 1):
            if GUARD_OPEN.match(line):
                guards.append(f"{rel}:{k}")
            if MARKER_COMMENT.match(line) or TEMPLATE_PLACEHOLDER.match(line):
                markers += 1
            elif COMMENTED_CHECK.match(line) and not (k > 1 and TEMPLATE_PLACEHOLDER.match(lines[k - 2])):
                commented.append(f"{rel}:{k}: {line.strip()[:100]}")
            for name, rx in REMOVED_API.items():
                if rx.search(line):
                    removed.append(f"{rel}:{k}: {name}")
        for m in MACRO.finditer(text):
            close_at = matching_paren(text, m.end() - 1)
            inner = text[m.end() : close_at] if close_at > 0 else ""
            ref = CONCEPT_REF.match(inner[inner.find(",") + 1 :]) if "," in inner else None
            if ref and ref.group(2) in CONVERTIBLE:
                convertible[ref.group(2)] = convertible.get(ref.group(2), 0) + 1
            else:
                remaining += 1
    cmake_hits = [
        f"{p.relative_to(root)}:{k}"
        for p in root.rglob("*")
        if p.is_file()
        and (p.name == "CMakeLists.txt" or p.suffix == ".cmake")
        and not any(part in SKIP_DIRS for part in p.parts)
        for k, line in enumerate(p.read_text(errors="replace").splitlines(), 1)
        if "ITK_USE_CONCEPT_CHECKING" in line or "ITK_USE_STRICT_CONCEPT_CHECKING" in line
    ]
    print(f"Scanned {len(files)} source files under {root}")
    print(f"\nRemoved API uses (rewrite by hand, see SKILL.md): {len(removed)}")
    for hit in removed:
        print(f"  {hit}")
    print(f"\nITK_USE_CONCEPT_CHECKING guards (phase enable): {len(guards)}")
    for hit in guards:
        print(f"  {hit}")
    print(f"\nCommented-out checks or guards (decide by hand: enable or delete): {len(commented)}")
    for hit in commented:
        print(f"  {hit}")
    print(f"\nCMake references to the removed options: {len(cmake_hits)}")
    for hit in cmake_hits:
        print(f"  {hit}")
    total = sum(convertible.values())
    print(f"\nConvertible itkConceptMacro checks (phase static-assert): {total}")
    for name, n in sorted(convertible.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5d} {name}")
    print(f"Other itkConceptMacro checks (kept): {remaining}")
    print(f"Marker and template placeholder comment lines (phase comments): {markers}")
    return 0


# --------------------------------------------------------------------- main


def run_phase(phase: str, text: str, add_includes: bool = True) -> tuple[str, int, list[str]]:
    if phase == "enable":
        return enable_guards(text)
    if phase == "static-assert":
        return to_static_assert(text, add_includes)
    if phase == "comments":
        new, n = remove_marker_comments(text)
        return new, n, []
    raise ValueError(phase)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=["audit", "enable", "static-assert", "comments", "all"])
    ap.add_argument("paths", nargs="*", type=Path, help="files or directories (default: --root)")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="code base root (default: cwd)")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="skip matching paths")
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    ap.add_argument("--diff", action="store_true", help="print a unified diff of every change")
    ap.add_argument(
        "--no-add-includes",
        dest="add_includes",
        action="store_false",
        help="do not add #include <type_traits> where std:: traits are introduced",
    )
    args = ap.parse_args(argv)

    root = args.root.resolve()
    files = source_files([p.resolve() for p in args.paths] or [root], args.exclude)
    if args.phase == "audit":
        return audit(files, root)

    phases = ["enable", "static-assert", "comments"] if args.phase == "all" else [args.phase]
    totals = {phase: 0 for phase in phases}
    changed_files = 0
    for p in files:
        original = p.read_text(errors="replace")
        result = FileResult(p, original, original)
        for phase in phases:
            result.text, n, notes = run_phase(phase, result.text, args.add_includes)
            totals[phase] += n
            result.changes += n
            result.notes.extend(f"{phase}: {note}" for note in notes)
        rel = p.relative_to(root) if p.is_relative_to(root) else p
        for note in result.notes:
            print(f"NOTE {rel}: {note}")
        if not result.changed:
            continue
        changed_files += 1
        print(f"{'APPLY' if args.apply else 'WOULD CHANGE'} {rel} ({result.changes})")
        if args.diff:
            sys.stdout.writelines(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    result.text.splitlines(keepends=True),
                    f"a/{rel}",
                    f"b/{rel}",
                )
            )
        if args.apply:
            p.write_text(result.text)
    summary = ", ".join(f"{phase}={n}" for phase, n in totals.items())
    print(f"\n{changed_files} files {'changed' if args.apply else 'would change'}; {summary}")
    if args.apply and changed_files:
        print("Next: run the project's clang-format, then build and run the tests (see SKILL.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
