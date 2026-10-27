"""When a local that clang-tidy proved const can be constexpr instead.

Pure functions over declaration text and the variable's canonical type.
"""

import re

NUMBER = r"[+-]?(?:0[xX][\da-fA-F']+|0[bB][01']+|(?:\d[\d']*\.?[\d']*|\.\d[\d']*)(?:[eE][+-]?\d+)?)[uUlLfFzZ]*"
CHAR = r"(?:u8|u|U|L)?'(?:\\.|[^'\\])+'"
SCALAR = rf"(?:{NUMBER}|true|false|{CHAR})"
STRING = r'"(?:\\.|[^"\\])*"'
TEMPLATE_ARGS = r"<[^();]+>"

SCALAR_RE = re.compile(rf"^{SCALAR}$")
STRING_RE = re.compile(rf"^{STRING}$")
FILLED_RE = re.compile(rf"^[\w:<>, ]*::Filled\(\s*{SCALAR}\s*\)$")
MAKE_FILLED_RE = re.compile(rf"^(?:itk::)?MakeFilled\s*{TEMPLATE_ARGS}\(\s*{SCALAR}\s*\)$")
TRAITS_RE = re.compile(rf"^(?:(?:std::)?numeric_limits|(?:itk::)?NumericTraits)\s*{TEMPLATE_ARGS}::\w+\(\s*\)$")
AGGREGATE_RE = re.compile(r"^(?:std::(?:__\w+::)?array|itk::(?:Size|Index|Offset))<")
ARRAY_RE = re.compile(r"^(.*?)\s*\[\d*\]$")

BUILTINS = {
    "bool", "char", "signed char", "unsigned char", "wchar_t", "char8_t", "char16_t", "char32_t",
    "short", "unsigned short", "int", "unsigned int", "long", "unsigned long", "long long",
    "unsigned long long", "float", "double", "long double",
}


def mask(text: str, literals: bool = False) -> str:
    """Blank comments (and literal contents when asked), keeping offsets and newlines."""
    out = list(text)
    i, n = 0, len(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif text[i] == '"' or (text[i] == "'" and not (i and text[i - 1].isdigit())):
            q, j = text[i], i + 1
            while j < n and text[j] != q and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            if literals:
                blank(i + 1, j - 1)
            i = j
        else:
            i += 1
    return "".join(out)


def _name(code: str, name: str) -> re.Match | None:
    return re.search(rf"(?<![\w:]){re.escape(name)}(?!\w)", code)


def initializer(decl: str, name: str) -> str | None:
    """The initializer of name in decl: `= x` gives x, braces and parens are kept."""
    code = mask(decl).strip()
    m = _name(code, name)
    if m is None:
        return None
    rest = code[m.end():].rstrip().removesuffix(";").strip()
    while rest.startswith("["):
        rest = rest[rest.find("]") + 1:].lstrip()
    if rest.startswith("=") and not rest.startswith("=="):
        rest = rest[1:].strip()
    elif not rest.startswith(("{", "(")):
        return None
    return rest or None


def _declared_type(decl: str, name: str) -> str:
    code = mask(decl)
    m = _name(code, name)
    return code[: m.start()].strip() if m else code


def _scalar_type(ctype: str) -> str:
    t = re.sub(r"\b(?:const|volatile)\b", " ", ctype)
    return " ".join(t.split())


def _builtin(ctype: str) -> bool:
    return _scalar_type(ctype) in BUILTINS


def _split_top(inner: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _brace_literals(init: str) -> list[str] | None:
    """Leaf elements of a (nested) brace list, or None if any is not a scalar literal."""
    if not (init.startswith("{") and init.endswith("}")):
        return [init] if SCALAR_RE.match(init) else None
    leaves: list[str] = []
    for part in _split_top(init[1:-1]):
        sub = _brace_literals(part)
        if sub is None:
            return None
        leaves += sub
    return leaves


def promotable(decl: str, name: str, ctype: str) -> bool:
    """True when the const local `name` declared by `decl` may be constexpr.

    ctype is the variable's canonical type (clang-tidy's `aka` type when given).
    """
    init = initializer(decl, name)
    if init is None:
        return False
    written = _declared_type(decl, name)
    if any("Pointer" in t or "&" in t for t in (written, ctype)):
        return False
    if init.startswith("(") and init.endswith(")"):
        init = init[1:-1].strip()
    if init.startswith("{"):
        leaves = _brace_literals(init)
        if leaves is None:
            return False
        array = ARRAY_RE.match(_scalar_type(ctype))
        if array:
            return _builtin(array[1])
        if AGGREGATE_RE.match(_scalar_type(ctype)):
            return True
        return len(leaves) == 1 and _builtin(ctype)
    if init == "nullptr":
        return _builtin(ctype) or ctype.rstrip().endswith("*")
    if SCALAR_RE.match(init):
        return _builtin(ctype)
    if STRING_RE.match(init):
        return _scalar_type(ctype).replace(" *", "*") == "char*" and "const" in ctype
    if FILLED_RE.match(init) or MAKE_FILLED_RE.match(init):
        return True
    if TRAITS_RE.match(init):
        return _builtin(ctype)
    return False
