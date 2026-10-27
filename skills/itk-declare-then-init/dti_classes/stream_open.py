import re

from find_declare_then_init import (
    Finding,
    check_gap_forward_refs,
    check_indent_match,
    declined_finding,
    find_next_use,
    gap_is_blank_or_comment,
    strip_comment,
)

STREAM_TYPES = {"std::ofstream", "std::ifstream", "std::fstream"}


def analyze(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    if vartype not in STREAM_TYPES:
        return None
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None or not gap_is_blank_or_comment(lines, i, j):
        return None
    m = re.match(rf"^\s*{re.escape(varname)}\.open\((.+)\)\s*;\s*$", strip_comment(lines[j]))
    if not m:
        return None
    args = m.group(1).strip()
    if re.search(rf"\b{re.escape(varname)}\b", args):
        return None
    if not check_indent_match(indent, lines[j]):
        return declined_finding(filepath, i, j, vartype, varname, "stream_open", "indent-mismatch")
    return Finding(
        file=filepath,
        decl_line=i + 1,
        init_line=j + 1,
        varname=varname,
        vartype=vartype,
        pattern="stream_open",
        init_expr=f"open({args})",
        gap_lines=j - i - 1,
        suggestion=f"{indent}{vartype} {varname}({args});",
        forward_refs=check_gap_forward_refs(lines, i, j, args),
    )
