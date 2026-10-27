"""Constructor initializer-list parsing, order guard, and comment carrying."""

import re
from dataclasses import dataclass, field

IDENT = re.compile(r"[A-Za-z_]\w*")
POINTERISH = re.compile(r"Pointer|unique_ptr|shared_ptr|SmartPointer")
SKIP_STMT = {
    "using", "typedef", "friend", "static", "enum", "class", "struct", "union",
    "template", "static_assert", "operator",
}
NOT_NAMES = {
    "const", "override", "final", "noexcept", "volatile", "mutable", "public",
    "private", "protected", "virtual", "inline", "constexpr", "explicit",
}
CLOSE = {")": "(", "}": "{", "]": "["}
OPEN = {v: k for k, v in CLOSE.items()}


def _blank(out: list[str], i: int, j: int) -> None:
    for k in range(i, j):
        if out[k] != "\n":
            out[k] = " "


def mask(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Blank comments, literals, and preprocessor lines; keep offsets and newlines."""
    out = list(text)
    comments: list[tuple[int, int]] = []
    i, n, bol = 0, len(text), True
    while i < n:
        c = text[i]
        if c == "\n":
            bol, i = True, i + 1
            continue
        if bol and c in " \t":
            i += 1
            continue
        if bol and c == "#":
            j = i
            while j < n and text[j] != "\n":
                j += 2 if text.startswith("\\\n", j) else 1
            _blank(out, i, j)
            i = j
            continue
        bol = False
        if text.startswith("//", i) or text.startswith("/*", i):
            if text[i + 1] == "/":
                j = text.find("\n", i)
                j = n if j < 0 else j
            else:
                j = text.find("*/", i + 2)
                j = n if j < 0 else j + 2
            comments.append((i, j))
            _blank(out, i, j)
            i = j
            continue
        if c in "\"'":
            j = i + 1
            while j < n and text[j] not in (c, "\n"):
                j += 2 if text[j] == "\\" else 1
            _blank(out, i + 1, min(j, n))
            i = j + 1
            continue
        i += 1
    return "".join(out), comments


def prev_code(m: str, i: int) -> int:
    j = i - 1
    while j >= 0 and m[j].isspace():
        j -= 1
    return j


def match_back(m: str, i: int) -> int:
    close, depth = m[i], 0
    for j in range(i, -1, -1):
        if m[j] == close:
            depth += 1
        elif m[j] == CLOSE[close]:
            depth -= 1
            if depth == 0:
                return j
    return -1


def match_fwd(m: str, i: int) -> int:
    opener, depth = m[i], 0
    for j in range(i, len(m)):
        if m[j] == opener:
            depth += 1
        elif m[j] == OPEN[opener]:
            depth -= 1
            if depth == 0:
                return j
    return len(m) - 1


def name_back(m: str, k: int) -> int:
    """Start of a possibly qualified, possibly templated name ending at k."""
    while k >= 0:
        if m[k] == ">":
            depth = 0
            while k >= 0:
                depth += {">": 1, "<": -1}.get(m[k], 0)
                k -= 1
                if depth == 0:
                    break
        elif m[k].isalnum() or m[k] == "_":
            k -= 1
        elif m[k] == ":" and k > 0 and m[k - 1] == ":":
            k -= 2
        else:
            break
    return k + 1


def body_after(m: str, i: int) -> int | None:
    """Offset of the constructor body brace at or after i (inside a signature or list)."""
    while i < len(m):
        c = m[i]
        if c in "([":
            i = match_fwd(m, i) + 1
            continue
        if c == "{":
            if m[prev_code(m, i)] in ")}":
                return i
            i = match_fwd(m, i) + 1
            continue
        if c == ";":
            return None
        i += 1
    return None


def body_before(m: str, i: int) -> int | None:
    """Offset of the unmatched brace opening the block that contains i."""
    depth = 0
    for j in range(i - 1, -1, -1):
        if m[j] == "}":
            depth += 1
        elif m[j] == "{":
            if depth == 0:
                return j
            depth -= 1
    return None


@dataclass
class Entry:
    name: str
    text: str
    start: int = -1
    end: int = -1
    lead: list[str] = field(default_factory=list)
    trail: str = ""

    @property
    def expr(self) -> str:
        code = mask(self.text)[0]
        cut = min((code.find(c) for c in "({" if c in code), default=len(code))
        return code[cut:]


@dataclass
class Ctor:
    sig_end: int
    body_open: int
    cls: str
    in_class: bool
    indent: str
    entries: list[Entry]
    head: list[str] = field(default_factory=list)
    tail: list[str] = field(default_factory=list)


def _split_entries(m: str, start: int, end: int) -> list[tuple[int, int]]:
    spans, cur, i, angle, in_name = [], start, start, 0, True
    while i < end:
        c = m[i]
        if c in "({[":
            i, in_name = match_fwd(m, i) + 1, False
            continue
        if in_name and c in "<>":
            angle += 1 if c == "<" else -1
        elif c == "," and angle == 0:
            spans.append((cur, i))
            cur, in_name = i + 1, True
        i += 1
    spans.append((cur, end))
    out = []
    for a, b in spans:
        while a < b and m[a].isspace():
            a += 1
        while b > a and m[b - 1].isspace():
            b -= 1
        out.append((a, b))
    return out


def parse_ctor(text: str, m: str, comments: list[tuple[int, int]], body_open: int) -> Ctor | None:
    pos = prev_code(m, body_open)
    if pos < 0 or m[pos] not in ")}":
        return None
    colon, p = None, pos
    while True:
        j = match_back(m, p)
        k = prev_code(m, j)
        s = name_back(m, k)
        if s > k:
            return None
        q = prev_code(m, s)
        if q >= 0 and m[q] == ",":
            p = prev_code(m, q)
            if p < 0 or m[p] not in ")}":
                return None
            continue
        access = re.search(r"\b(?:public|private|protected)\s*$", m[max(0, q - 16):q])
        if q >= 1 and m[q] == ":" and m[q - 1] != ":" and not access:
            colon = q
        break
    params = prev_code(m, colon) if colon is not None else pos
    if m[params] != ")":
        return None
    k = prev_code(m, match_back(m, params))
    name = re.sub(r"\s+", "", m[name_back(m, k):k + 1])
    if "::" in name:
        qual = re.sub(r"<[^<>]*>", "", name.rsplit("::", 1)[0])
        cls, in_class = IDENT.findall(qual)[-1], False
    else:
        cls, in_class = name, True
    sig_end = params + 1
    line = text[text.rfind("\n", 0, sig_end) + 1:sig_end]
    indent = line[: len(line) - len(line.lstrip())]
    entries = []
    if colon is not None:
        for a, b in _split_entries(m, colon + 1, body_open):
            if a == b:
                return None
            head = m[a:b]
            cut = min((head.find(c) for c in "({" if c in head), default=len(head))
            entries.append(Entry(head[:cut].strip(), text[a:b], a, b))
    ctor = Ctor(sig_end, body_open, cls, in_class, indent, entries)
    for c0, c1 in comments:
        if not sig_end <= c0 < body_open:
            continue
        ctext = text[c0:c1]
        if colon is None or c0 < colon:
            ctor.head.append(ctext)
            continue
        prev = [e for e in entries if e.end <= c0]
        if prev and "\n" not in text[prev[-1].end:c0]:
            prev[-1].trail = (prev[-1].trail + " " + ctext).strip()
            continue
        nxt = [e for e in entries if e.start > c0]
        (nxt[0].lead if nxt else ctor.tail).append(ctext)
    return ctor


def render(ctor: Ctor, entries: list[Entry]) -> str:
    pad = ctor.indent + "  "
    out = "".join(" " + h for h in ctor.head)
    for i, e in enumerate(entries):
        out += "".join(f"\n{pad}{c}" for c in e.lead)
        out += f"\n{pad}{': ' if i == 0 else ', '}{e.text}" + (f" {e.trail}" if e.trail else "")
    out += "".join(f"\n{pad}{c}" for c in ctor.tail)
    return out + "\n" + ctor.indent


def find_class(m: str, cls: str) -> tuple[int, int] | None:
    pat = re.compile(
        rf"\b(?:class|struct)\s+(?:[A-Za-z_]\w*\s+)*?{re.escape(cls)}\s*(?:final\s*)?(?::(?!:)[^;{{}}]*)?\{{"
    )
    for hit in pat.finditer(m):
        start = hit.end() - 1
        return start + 1, match_fwd(m, start)
    return None


def _split_top(head: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for c in head:
        depth += {"<": 1, ">": -1}.get(c, 0)
        if c == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    return parts + [cur]


def _statement_members(stmt: str) -> list[str]:
    s = stmt.strip()
    while (flat := re.sub(r"\([^()]*\)", "@", s)) != s:
        s = flat
    s = s.replace("@", "()")
    while macro := re.match(r"\s*[A-Za-z_]\w*\s*\(\)\s*(?=[A-Za-z_])", s):
        s = s[macro.end():]
    first = IDENT.match(s)
    if not s or (first and first.group() in SKIP_STMT) or re.search(r"\boperator\b", s):
        return []
    head = re.split(r"=|\{|\[|(?<!:):(?!:)", s, maxsplit=1)[0].rstrip()
    trimmed = re.sub(r"(\s*\b(?:const|override|final|noexcept|volatile)\b|\s*&&?)+$", "", head)
    if trimmed.endswith(")"):
        return []
    names = []
    for part in _split_top(head):
        ids = IDENT.findall(part)
        if ids and ids[-1] not in NOT_NAMES:
            names.append(ids[-1])
    return names


def data_members(m: str, start: int, end: int) -> list[str]:
    names: list[str] = []
    stmt, i = start, start
    while i < end:
        c = m[i]
        if c in "([":
            i = match_fwd(m, i) + 1
            continue
        if c == "{":
            is_body = "(" in m[stmt:i]
            i = match_fwd(m, i) + 1
            if is_body:
                stmt = i
            continue
        if c == ";":
            names += _statement_members(m[stmt:i])
            stmt = i + 1
        elif c == ":" and m[stmt:i].strip() in ("public", "private", "protected"):
            stmt = i + 1
        i += 1
    return names


def _later_refs(e: Entry, order: dict[str, int]) -> bool:
    expr = e.expr
    for hit in IDENT.finditer(expr):
        before = expr[: hit.start()].rstrip()
        if before.endswith(".") or (before.endswith("->") and not before[:-2].rstrip().endswith("this")):
            continue
        if order.get(hit.group(), -1) > order[e.name]:
            return True
    return False


def plan_order(entries: list[Entry], members: list[str]) -> tuple[list[Entry] | None, str]:
    """Entries in declaration order, or None with a note when moving would read a later member."""
    order = {n: i for i, n in enumerate(members)}
    for e in entries:
        if e.name in order and _later_refs(e, order):
            return None, f"{e.name} reads a later-declared member"
    unknown = [e for e in entries if e.name not in order]
    known = [e for e in entries if e.name in order]
    ranked = sorted(known, key=lambda e: order[e.name])
    if ranked == known:
        return entries, ""
    if entries[: len(unknown)] != unknown:
        return None, UNKNOWN_INITIALIZER
    return unknown + ranked, ""


UNKNOWN_INITIALIZER = "unknown-initializer"


def has_directive(text: str, a: int, b: int) -> bool:
    return re.search(r"^[ \t]*#", text[text.rfind("\n", 0, a) + 1:b], re.M) is not None


def ctor_bodies(m: str, cls: str) -> list[int]:
    """Body braces of every constructor of cls defined in m."""
    out = []
    for hit in re.finditer(rf"(?<![\w~.>]){re.escape(cls)}\s*(?:<[^;{{}}()]*>\s*)?\(", m):
        body = body_after(m, hit.end() - 1)
        if body is not None and body not in out:
            out.append(body)
    return out


def decl_head(m: str, offset: int) -> str:
    i = offset - 1
    while i >= 0 and m[i] not in ";{}" and not (m[i] == ":" and m[i - 1] != ":" and m[i + 1] != ":"):
        i -= 1
    return m[i + 1:offset]


def line_bounds(text: str, a: int, b: int) -> tuple[int, int]:
    end = text.find("\n", b)
    return text.rfind("\n", 0, a) + 1, len(text) if end < 0 else end


def statement_removal(text: str, comments: list[tuple[int, int]], a: int, b: int):
    """Widen a removed body statement to its whole line; return (start, end, carried, stranded)."""
    ls, le = line_bounds(text, a, b)
    if text[ls:a].strip():
        return a, b, "", False
    rest = text[b:le].strip()
    trailing = [text[c0:c1] for c0, c1 in comments if b <= c0 < le]
    if rest and rest != " ".join(trailing):
        return a, b, "", False
    ple = max(ls - 1, 0)
    pls = text.rfind("\n", 0, ple) + 1
    code = [k for k in range(pls, ple) if not text[k].isspace()]
    stranded = bool(code) and all(any(c0 <= k < c1 for c0, c1 in comments) for k in code)
    return ls, min(le + 1, len(text)), rest, stranded
