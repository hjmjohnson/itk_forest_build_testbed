import re

from find_declare_then_init import (
    Finding,
    check_gap_forward_refs,
    check_indent_match,
    declined_finding,
    find_next_use,
    gap_is_blank_or_comment,
    has_top_level_comma,
    strip_comment,
)

SIZING_METHOD = {
    r"std::vector<.*>": "resize",
    r"vnl_vector<.*>": "set_size",
    r"(?:itk::)?Array<.*>": "SetSize",
}


def analyze(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    method = next((m for rx, m in SIZING_METHOD.items() if re.fullmatch(rx, vartype)), None)
    if method is None:
        return None
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None or not gap_is_blank_or_comment(lines, i, j):
        return None
    m = re.match(
        rf"^\s*{re.escape(varname)}\.{method}\(\s*(.+?)\s*\)\s*;\s*$", strip_comment(lines[j])
    )
    if not m:
        return None
    arg = m.group(1)
    if has_top_level_comma(arg) or re.search(rf"\b{re.escape(varname)}\b", arg):
        return None
    if vartype.replace(" ", "") == "std::vector<bool>":
        return declined_finding(filepath, i, j, vartype, varname, "sized_ctor", "vector-bool")
    if not check_indent_match(indent, lines[j]):
        return declined_finding(filepath, i, j, vartype, varname, "sized_ctor", "indent-mismatch")
    return Finding(
        file=filepath,
        decl_line=i + 1,
        init_line=j + 1,
        varname=varname,
        vartype=vartype,
        pattern="sized_ctor",
        init_expr=f"{method}({arg})",
        gap_lines=j - i - 1,
        suggestion=f"{indent}{vartype} {varname}({arg});",
        forward_refs=check_gap_forward_refs(lines, i, j, arg),
    )
