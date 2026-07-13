#!/usr/bin/env python3
"""Find C++ declare-then-initialize patterns that can be combined.

Scans C++ source files for ONE class of pattern at a time (following
N-Dekker's incremental approach where each commit addresses exactly
one pattern class with a specific regex).

Pattern classes (--pattern):
  fill_zero     Type var; var.Fill(0);        -> Type var{};
  fill_nonzero  Type var; var.Fill(N);        -> auto var = Type::Filled(N);
  elem_same     Type var; var[0]=x;..var[N]=x -> auto var = Type::Filled(x);
  elem_diff     Type var; var[0]=x;..var[N]=z -> Type var{ x, .., z };
  elem_zero     Type var; var[0]=0;..var[N]=0 -> Type var{};
  assign        Type var; var = EXPR;         -> Type var = EXPR;
  setsize_fill  Type var; var.SetSize(N); var.Fill(V); -> Type var(N, V);

Constraints (matching N-Dekker's methodology):
  - Declaration and first init line MUST have the same indentation
  - For element_assign: all [i]= lines must be consecutive with same indent
  - No block boundaries ({) between declaration and init
  - The init must be the NEXT USE of that variable

Filters:
  --varname NAME    Only match variables with this exact name (e.g., size, start)
  --vartype REGEX   Only match type names matching this regex (e.g., SizeType)
  --tests-only      Only scan *Test*.cxx files

Usage:
    python3 find_declare_then_init.py --pattern fill_zero [OPTIONS] <path> [<path>...]

Examples:
    # Exactly what N-Dekker did in 9962e2f9 (size[i]=x -> Filled, tests only):
    python3 find_declare_then_init.py --pattern elem_same --varname size \\
        --vartype SizeType --tests-only --fix -r Modules/

    # What N-Dekker did in 6cb6bf98 (T var; var.Fill(x) -> MakeFilled):
    python3 find_declare_then_init.py --pattern fill_nonzero --fix -r Modules/

    # Find all zero-Fill patterns:
    python3 find_declare_then_init.py --pattern fill_zero --fix -r Modules/
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Regex patterns for C++ declarations
DECL_PATTERN = re.compile(
    r"^(\s*)"  # leading whitespace (group 1 = indent)
    r"((?:const\s+|constexpr\s+|auto\s+)?"  # optional qualifiers
    r"(?:[\w:]+(?:<[^>]*>)?(?:::[\w]+(?:<[^>]*>)?)*)"  # type (with templates, namespaces)
    r"(?:\s*\*)*)"  # optional pointer
    r"\s+"
    r"(\w+)"  # variable name (group 3)
    r"\s*;\s*$"  # semicolon, end of line
)

FILL_PATTERN = re.compile(r"^\s*(\w+)\.Fill\(\s*(.+?)\s*\)\s*;\s*$")
ASSIGN_PATTERN = re.compile(r"^\s*(\w+)\s*=\s*(.+?)\s*;\s*$")
SETSIZE_PATTERN = re.compile(r"^\s*(\w+)\.SetSize\(\s*(.+?)\s*\)\s*;\s*$")
ELEMENT_ASSIGN_PATTERN = re.compile(r"^\s*(\w+)\[(\d+)\]\s*=\s*(.+?)\s*;\s*$")


def strip_comment(line: str) -> str:
    """Strip trailing // comments (naive, ignores string literals)."""
    sanitized = re.sub(r'"[^"]*"', '""', line)
    sanitized = re.sub(r"'[^']*'", "''", sanitized)
    idx = sanitized.find("//")
    return line[:idx] if idx >= 0 else line


def get_indent(line: str) -> str:
    """Return the leading whitespace of a line."""
    return line[: len(line) - len(line.lstrip())]


def line_uses_var(line: str, varname: str) -> bool:
    """Check if a line references the variable (not just in comments)."""
    stripped = re.sub(r"//.*$", "", line)
    stripped = re.sub(r"/\*.*?\*/", "", stripped)
    return bool(re.search(rf"\b{re.escape(varname)}\b", stripped))


def is_zero_value(value: str) -> bool:
    """Check if a value is zero (0, 0.0, 0.0f, etc.)."""
    return bool(re.match(r"^0(\.0+)?[fFlL]?$", value.strip()))


def enters_new_block(line: str) -> bool:
    """Check if a line opens a new block scope."""
    stripped = re.sub(r'"[^"]*"', "", re.sub(r"'[^']*'", "", line))
    stripped = re.sub(r"//.*$", "", stripped)
    return stripped.count("{") > stripped.count("}")


def leaves_block(line: str) -> bool:
    """Check if a line closes a block scope."""
    stripped = re.sub(r'"[^"]*"', "", re.sub(r"'[^']*'", "", line))
    stripped = re.sub(r"//.*$", "", stripped)
    return stripped.count("}") > stripped.count("{")


@dataclass
class Finding:
    file: str
    decl_line: int
    init_line: int
    varname: str
    vartype: str
    pattern: str
    init_expr: str
    gap_lines: int
    suggestion: str
    forward_refs: list[str] | None = None  # identifiers that would be forward-referenced


def find_next_use(
    lines: list[str], start: int, varname: str, decl_indent: str, max_gap: int
) -> int | None:
    """Find the next line that uses varname, respecting scope and indent.

    Returns line index or None if not found within constraints.
    """
    gap = 0
    j = start
    while j < len(lines) and gap <= max_gap:
        stripped = lines[j].strip()

        # Skip blank lines and pure comment lines
        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            j += 1
            gap += 1
            continue

        # Stop if we enter a new block or leave current scope
        if enters_new_block(lines[j]) or leaves_block(lines[j]):
            return None

        if line_uses_var(lines[j], varname):
            return j

        gap += 1
        j += 1

    return None


def check_gap_forward_refs(
    lines: list[str], decl_idx: int, init_idx: int, init_expr: str
) -> list[str]:
    """Check if the Fill/init expression references identifiers defined in gap lines.

    Returns list of identifiers that would be forward-referenced if the init
    were moved to the declaration line.  An empty list means safe to move.
    """
    # Extract identifiers used in the init expression
    # Strip string literals and numeric literals first
    expr_clean = re.sub(r'"[^"]*"', "", init_expr)
    expr_clean = re.sub(r"'[^']*'", "", expr_clean)
    expr_clean = re.sub(r"\b\d+(\.\d+)?[fFlLuU]*\b", "", expr_clean)
    used_ids = set(re.findall(r"\b([a-zA-Z_]\w*)\b", expr_clean))
    # Remove common keywords / type names that aren't variables
    used_ids -= {
        "auto",
        "const",
        "constexpr",
        "static",
        "typename",
        "using",
        "int",
        "unsigned",
        "float",
        "double",
        "long",
        "short",
        "char",
        "bool",
        "void",
        "size_t",
        "true",
        "false",
        "nullptr",
        "static_cast",
        "dynamic_cast",
        "reinterpret_cast",
        "const_cast",
        "Fill",
        "MakeFilled",
        "Filled",
        "SetSize",
    }
    if not used_ids:
        return []

    forward_refs = []
    for gap_idx in range(decl_idx + 1, init_idx):
        gap_line = lines[gap_idx].strip()
        if not gap_line or gap_line.startswith("//"):
            continue
        # Check for variable/type declarations in gap that define identifiers used in init
        for ident in used_ids:
            # Look for patterns like: Type ident; / Type ident{ / constexpr Type ident / using ident =
            if re.search(rf"\b{re.escape(ident)}\s*[;={{]", gap_line) or re.search(
                rf"\busing\s+{re.escape(ident)}\s*=", gap_line
            ):
                forward_refs.append(ident)
    return forward_refs


def file_is_in_itk_namespace(filepath: str) -> bool:
    """Heuristic: .hxx/.txx files are template implementations inside namespace itk.
    .h files with class method implementations are also inside namespace itk.
    Test files (.cxx in test/ dirs) are typically NOT in namespace itk.
    """
    ext = Path(filepath).suffix
    if ext in (".hxx", ".txx"):
        return True
    # .h files in include/ dirs are inside namespace itk
    return ext == ".h" and "/include/" in filepath


def check_indent_match(decl_indent: str, init_line: str) -> bool:
    """Verify the init line has the same indentation as the declaration."""
    return get_indent(init_line) == decl_indent


def analyze_fill_zero(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None:
        return None
    clean = strip_comment(lines[j])
    m = FILL_PATTERN.match(clean)
    if (
        m
        and m.group(1) == varname
        and is_zero_value(m.group(2))
        and check_indent_match(indent, lines[j])
    ):
        return Finding(
            file=filepath,
            decl_line=i + 1,
            init_line=j + 1,
            varname=varname,
            vartype=vartype,
            pattern="fill_zero",
            init_expr=f"Fill({m.group(2)})",
            gap_lines=j - i - 1,
            suggestion=f"{indent}{vartype} {varname}{{}};",
        )
    return None


def analyze_fill_nonzero(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None:
        return None
    clean = strip_comment(lines[j])
    m = FILL_PATTERN.match(clean)
    if (
        m
        and m.group(1) == varname
        and not is_zero_value(m.group(2))
        and check_indent_match(indent, lines[j])
    ):
        val = m.group(2)
        # Determine namespace prefix: .hxx/.txx are inside namespace itk, test files are not
        ns = "" if file_is_in_itk_namespace(filepath) else "itk::"
        # Check for forward-reference hazards
        fwd_refs = check_gap_forward_refs(lines, i, j, val)
        return Finding(
            file=filepath,
            decl_line=i + 1,
            init_line=j + 1,
            varname=varname,
            vartype=vartype,
            pattern="fill_nonzero",
            init_expr=f"Fill({val})",
            gap_lines=j - i - 1,
            suggestion=f"{indent}auto {varname} = {ns}MakeFilled<{vartype}>({val});",
            forward_refs=fwd_refs,
        )
    return None


def analyze_elem_assign(
    lines: list[str],
    i: int,
    indent: str,
    vartype: str,
    varname: str,
    filepath: str,
    max_gap: int,
    want: str,  # "same", "diff", "zero"
) -> Finding | None:
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None:
        return None
    clean = strip_comment(lines[j])
    m = ELEMENT_ASSIGN_PATTERN.match(clean)
    if not m or m.group(1) != varname or m.group(2) != "0":
        return None
    if not check_indent_match(indent, lines[j]):
        return None

    # Collect consecutive element assignments [0], [1], [2], ...
    values = [m.group(3)]
    k = j + 1
    expected_idx = 1
    while k < len(lines):
        k_stripped = lines[k].strip()
        if not k_stripped:
            k += 1
            continue
        k_clean = strip_comment(lines[k])
        k_m = ELEMENT_ASSIGN_PATTERN.match(k_clean)
        if (
            k_m
            and k_m.group(1) == varname
            and int(k_m.group(2)) == expected_idx
            and check_indent_match(indent, lines[k])
        ):
            values.append(k_m.group(3))
            expected_idx += 1
            k += 1
        else:
            break

    if len(values) < 2:
        return None

    all_same = all(v == values[0] for v in values)
    all_zero = all(is_zero_value(v) for v in values)

    if want == "zero" and not all_zero:
        return None
    if want == "same" and (not all_same or all_zero):
        return None
    if want == "diff" and (all_same or all_zero):
        return None

    if all_zero:
        suggestion = f"{indent}{vartype} {varname}{{}};"
    elif all_same:
        suggestion = f"{indent}auto {varname} = {vartype}::Filled({values[0]});"
    else:
        vals_str = ", ".join(values)
        suggestion = f"{indent}{vartype} {varname}{{ {vals_str} }};"

    return Finding(
        file=filepath,
        decl_line=i + 1,
        init_line=j + 1,
        varname=varname,
        vartype=vartype,
        pattern=f"elem_{want}",
        init_expr=f"[0..{len(values) - 1}] = {', '.join(values)}",
        gap_lines=j - i - 1,
        suggestion=suggestion,
    )


def analyze_assign(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None:
        return None
    clean = strip_comment(lines[j])
    m = ASSIGN_PATTERN.match(clean)
    if m and m.group(1) == varname and check_indent_match(indent, lines[j]):
        expr = m.group(2)
        return Finding(
            file=filepath,
            decl_line=i + 1,
            init_line=j + 1,
            varname=varname,
            vartype=vartype,
            pattern="assign",
            init_expr=expr,
            gap_lines=j - i - 1,
            suggestion=f"{indent}{vartype} {varname} = {expr};",
        )
    return None


def analyze_setsize_fill(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None:
        return None
    clean = strip_comment(lines[j])
    sm = SETSIZE_PATTERN.match(clean)
    if not sm or sm.group(1) != varname or not check_indent_match(indent, lines[j]):
        return None
    size_val = sm.group(2)
    # Look for Fill on the next non-blank line
    k = j + 1
    while k < len(lines) and not lines[k].strip():
        k += 1
    if k < len(lines):
        k_clean = strip_comment(lines[k])
        fm = FILL_PATTERN.match(k_clean)
        if fm and fm.group(1) == varname:
            fill_val = fm.group(2)
            return Finding(
                file=filepath,
                decl_line=i + 1,
                init_line=j + 1,
                varname=varname,
                vartype=vartype,
                pattern="setsize_fill",
                init_expr=f"SetSize({size_val}), Fill({fill_val})",
                gap_lines=j - i - 1,
                suggestion=f"{indent}{vartype} {varname}({size_val}, {fill_val});",
            )
    return None


# Map pattern names to analyzer functions
PATTERN_ANALYZERS = {
    "fill_zero": lambda *a, **kw: analyze_fill_zero(*a, **kw),
    "fill_nonzero": lambda *a, **kw: analyze_fill_nonzero(*a, **kw),
    "elem_same": lambda lines, i, indent, vtype, vname, fp, mg: analyze_elem_assign(
        lines, i, indent, vtype, vname, fp, mg, want="same"
    ),
    "elem_diff": lambda lines, i, indent, vtype, vname, fp, mg: analyze_elem_assign(
        lines, i, indent, vtype, vname, fp, mg, want="diff"
    ),
    "elem_zero": lambda lines, i, indent, vtype, vname, fp, mg: analyze_elem_assign(
        lines, i, indent, vtype, vname, fp, mg, want="zero"
    ),
    "assign": lambda *a, **kw: analyze_assign(*a, **kw),
    "setsize_fill": lambda *a, **kw: analyze_setsize_fill(*a, **kw),
}


def analyze_file(
    filepath: str,
    pattern: str,
    varname_filter: str | None = None,
    vartype_filter: re.Pattern | None = None,
    max_gap: int = 9999,
) -> list[Finding]:
    """Analyze a single file for ONE pattern class."""
    findings: list[Finding] = []
    analyzer = PATTERN_ANALYZERS[pattern]

    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return findings

    for i, line in enumerate(lines):
        decl_match = DECL_PATTERN.match(line)
        if not decl_match:
            continue

        indent = decl_match.group(1)
        vartype = decl_match.group(2).strip()
        varname = decl_match.group(3)

        # Apply filters
        if varname_filter and varname != varname_filter:
            continue
        if vartype_filter and not vartype_filter.search(vartype):
            continue

        result = analyzer(lines, i, indent, vartype, varname, filepath, max_gap)
        if result:
            findings.append(result)

    return findings


def scan_paths(
    paths: list[str],
    recursive: bool = False,
    exclude_patterns: list[str] | None = None,
    tests_only: bool = False,
    **kwargs,
) -> list[Finding]:
    """Scan files/directories for findings."""
    findings: list[Finding] = []
    exclude_res = [re.compile(p) for p in (exclude_patterns or [])]
    extensions = {".cxx", ".hxx", ".txx", ".cpp", ".hpp", ".h", ".cc"}

    def should_exclude(path: str) -> bool:
        return any(r.search(path) for r in exclude_res)

    def matches_file_filter(fname: str) -> bool:
        if tests_only:
            return bool(re.search(r"Test.*\.cxx$", fname))
        return True

    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            if not should_exclude(str(path)) and matches_file_filter(path.name):
                findings.extend(analyze_file(str(path), **kwargs))
        elif path.is_dir() and recursive:
            for root, _dirs, files in os.walk(path):
                if should_exclude(root):
                    continue
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if (
                        Path(fname).suffix in extensions
                        and not should_exclude(fpath)
                        and matches_file_filter(fname)
                    ):
                        findings.extend(analyze_file(fpath, **kwargs))

    return findings


def apply_findings(findings: list[Finding]) -> dict[str, int]:
    """Apply fixes to files in-place.  Returns {filepath: count_applied}.

    Handles multi-match files correctly by processing init_line in
    descending order so that line deletions don't shift earlier indices.

    Findings with forward_refs are skipped (require manual intervention).
    """
    from collections import defaultdict

    by_file: dict[str, list[Finding]] = defaultdict(list)
    skipped = []
    for f in findings:
        if f.forward_refs:
            skipped.append(f)
        else:
            by_file[f.file].append(f)

    if skipped:
        print(
            f"\nSkipped {len(skipped)} finding(s) with forward-reference hazards:", file=sys.stderr
        )
        for s in skipped:
            print(
                f"  {s.file}:{s.decl_line}: {s.varname} — "
                f"Fill arg references {s.forward_refs} defined between decl and init",
                file=sys.stderr,
            )
        print(file=sys.stderr)

    applied: dict[str, int] = {}
    for filepath, file_findings in sorted(by_file.items()):
        with open(filepath) as fh:
            lines = fh.readlines()

        # Sort by init_line DESCENDING so deletions don't shift earlier indices
        file_findings.sort(key=lambda f: f.init_line, reverse=True)

        for f in file_findings:
            decl_idx = f.decl_line - 1
            init_idx = f.init_line - 1
            # Remove the init line
            del lines[init_idx]
            # Replace the declaration line with the suggestion
            lines[decl_idx] = f.suggestion + "\n"

        with open(filepath, "w") as fh:
            fh.writelines(lines)

        applied[filepath] = len(file_findings)
        print(f"  Applied: {filepath} ({len(file_findings)} fix(es))", file=sys.stderr)

    total = sum(applied.values())
    print(f"\nApplied {total} fix(es) in {len(applied)} file(s)", file=sys.stderr)
    if skipped:
        print(f"Skipped {len(skipped)} finding(s) requiring manual review", file=sys.stderr)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find C++ declare-then-initialize patterns (one class at a time).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument(
        "--pattern",
        required=True,
        choices=list(PATTERN_ANALYZERS.keys()),
        help="Pattern class to find (exactly one)",
    )
    parser.add_argument("--varname", default=None, help="Only match this variable name")
    parser.add_argument("--vartype", default=None, help="Only match types matching this regex")
    parser.add_argument(
        "--max-gap", type=int, default=9999, help="Max unrelated lines between declare and init"
    )
    parser.add_argument("--tests-only", action="store_true", help="Only scan *Test*.cxx files")
    parser.add_argument("--fix", action="store_true", help="Print suggested replacement")
    parser.add_argument(
        "--apply", action="store_true", help="Apply fixes in-place (skips forward-ref hazards)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "-r", "--recursive", action="store_true", help="Recursively search directories"
    )
    parser.add_argument(
        "--exclude", action="append", default=[], help="Exclude paths matching regex"
    )

    args = parser.parse_args()
    args.exclude.append(r"/ThirdParty/")

    vartype_re = re.compile(args.vartype) if args.vartype else None

    findings = scan_paths(
        args.paths,
        recursive=args.recursive,
        exclude_patterns=args.exclude,
        tests_only=args.tests_only,
        pattern=args.pattern,
        varname_filter=args.varname,
        vartype_filter=vartype_re,
        max_gap=args.max_gap,
    )

    if args.apply:
        apply_findings(findings)
    elif args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for f in findings:
            fwd = ""
            if f.forward_refs:
                fwd = f"  *** FORWARD-REF HAZARD: {f.forward_refs} ***"
            print(
                f"{f.file}:{f.decl_line}: [{f.pattern}] {f.vartype} {f.varname}; "
                f"-> {f.init_expr} (gap={f.gap_lines}){fwd}"
            )
            if args.fix:
                print(f"  suggestion: {f.suggestion}")
            print()

    if not args.json and not args.apply:
        print(f"Found {len(findings)} pattern(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
