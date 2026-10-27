import re

from find_declare_then_init import (
    ASSIGN_PATTERN,
    Finding,
    check_gap_forward_refs,
    check_indent_match,
    declined_finding,
    find_next_use,
    gap_is_blank_or_comment,
    strip_comment,
)


def analyze(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    if re.search(r"\bconst\b", vartype) and not re.search(r"\bauto\b", vartype):
        return None
    j = find_next_use(lines, i + 1, varname, indent, max_gap)
    if j is None or not gap_is_blank_or_comment(lines, i, j):
        return None
    m = ASSIGN_PATTERN.match(strip_comment(lines[j]))
    if not m or m.group(1) != varname:
        return None
    expr = m.group(2)
    if expr.startswith("=") or re.search(rf"\b{re.escape(varname)}\b", expr):
        return None
    if re.search(r"\bauto\b", vartype):
        return declined_finding(filepath, i, j, vartype, varname, "placeholder", "auto-type")
    if "&" in vartype:
        return None
    if not check_indent_match(indent, lines[j]):
        return declined_finding(filepath, i, j, vartype, varname, "placeholder", "indent-mismatch")
    head = lines[i][: lines[i].index("=")].rstrip()
    return Finding(
        file=filepath,
        decl_line=i + 1,
        init_line=j + 1,
        varname=varname,
        vartype=vartype,
        pattern="placeholder",
        init_expr=expr,
        gap_lines=j - i - 1,
        suggestion=f"{head} = {expr};",
        forward_refs=check_gap_forward_refs(lines, i, j, expr),
    )
