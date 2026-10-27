import re

from find_declare_then_init import (
    Finding,
    check_indent_match,
    declined_finding,
    strip_comment,
)


def _mask(text: str) -> str:
    text = re.sub(r'"(?:[^"\\]|\\.)*"', lambda m: '"' * len(m.group()), text)
    return re.sub(r"'(?:[^'\\]|\\.)*'", lambda m: "'" * len(m.group()), text)


def _match_paren(masked: str, start: int) -> int:
    depth = 0
    for k in range(start, len(masked)):
        if masked[k] == "(":
            depth += 1
        elif masked[k] == ")":
            depth -= 1
            if depth == 0:
                return k
    return -1


def _writes(varname: str) -> re.Pattern:
    v = re.escape(varname)
    return re.compile(
        rf"(?<![\w.>:]){v}\s*(?:[-+*/%&|^]|<<|>>)?=(?!=)"
        rf"|(?:\+\+|--)\s*{v}\b|(?<![\w.>:]){v}\s*(?:\+\+|--)|(?<![&\w])&{v}\b"
    )


CONTROL_KEYWORDS = {"if", "while", "for", "switch", "return", "sizeof", "decltype"}


def _bare_call_arg(varname: str) -> re.Pattern:
    return re.compile(rf"(?:([\w:.>-]*)\s*\(|,)\s*{re.escape(varname)}\s*(?=[,)])")


def _later_use_hazard(lines: list[str], start: int, varname: str) -> str | None:
    writes = _writes(varname)
    arg = _bare_call_arg(varname)
    depth = 0
    for line in lines[start:]:
        code = _mask(strip_comment(line))
        if writes.search(code):
            return "later-write"
        if any(m.group(1) not in CONTROL_KEYWORDS and (m.group(1) or m.group().startswith(","))
               for m in arg.finditer(code)):
            return "by-ref-arg"
        depth += code.count("{") - code.count("}")
        if depth < 0:
            return None
    return None


def _body(lines: list[str], j: int, rest: str, varname: str):
    """Return (assigned_value, last_line_idx), "else" when an else follows, or None for the branch, or None."""
    stmt = rf"{re.escape(varname)}\s*=\s*(true|false)\s*;"
    if re.search(r"\belse\b", rest):
        return "else"
    m = re.fullmatch(rf"(\{{\s*)?{stmt}(\s*\}})?", rest)
    if m:
        return (m.group(2), j) if bool(m.group(1)) == bool(m.group(3)) else None
    if rest not in ("", "{") or j + 1 >= len(lines):
        return None
    k = j + 1
    braced = rest == "{"
    if not braced and lines[k].strip() == "{":
        braced, k = True, k + 1
    if k >= len(lines):
        return None
    sm = re.fullmatch(rf"\s*{stmt}\s*", strip_comment(lines[k]))
    if not sm:
        return None
    if not braced:
        return sm.group(1), k
    if k + 1 >= len(lines):
        return None
    close = lines[k + 1].strip()
    if close == "}":
        return sm.group(1), k + 1
    return "else" if re.match(r"\}\s*else\b", close) else None


def analyze(
    lines: list[str], i: int, indent: str, vartype: str, varname: str, filepath: str, max_gap: int
) -> Finding | None:
    if vartype != "bool":
        return None
    init = re.search(r"=\s*(true|false)\s*;\s*$", lines[i])
    if not init:
        return None
    j = i + 1
    while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith(("//", "/*"))):
        j += 1
    if j >= len(lines) or j - i > max_gap:
        return None
    text = strip_comment(lines[j]).rstrip()
    if not re.match(r"^\s*if\s*\(", text):
        return None
    masked = _mask(text)
    open_idx = masked.index("(")
    close_idx = _match_paren(masked, open_idx)
    if close_idx < 0:
        return None
    cond = text[open_idx + 1 : close_idx].strip()
    if not cond or re.search(rf"\b{re.escape(varname)}\b", cond):
        return None
    body = _body(lines, j, text[close_idx + 1 :].strip(), varname)
    if body is None:
        return None

    def decline(note: str) -> Finding:
        return declined_finding(filepath, i, j, vartype, varname, "bool_branch", note)

    if body == "else":
        return decline("else-branch")
    value, end = body
    if value == init.group(1):
        return None
    after = next((l.strip() for l in lines[end + 1 :] if l.strip()), "")
    if re.match(r"else\b", after):
        return decline("else-branch")
    if any(strip_comment(l) != l or "/*" in l for l in lines[j : end + 1]):
        return decline("comment-stranded")
    if not check_indent_match(indent, lines[j]):
        return decline("indent-mismatch")
    hazard = _later_use_hazard(lines, end + 1, varname)
    if hazard:
        return decline(hazard)
    bare = re.fullmatch(r"[A-Za-z_][\w:]*(?:(?:\.|->)\w+)*", cond) and cond not in ("true", "false")
    if value == "true":
        expr = f"static_cast<bool>({cond})" if bare else cond
    else:
        expr = f"!{cond}" if bare else f"!({cond})"
    return Finding(
        file=filepath,
        decl_line=i + 1,
        init_line=j + 1,
        varname=varname,
        vartype=vartype,
        pattern="bool_branch",
        init_expr=expr,
        gap_lines=j - i - 1,
        suggestion=f"{indent}const bool {varname} = {expr};",
        init_end=end + 1,
    )

