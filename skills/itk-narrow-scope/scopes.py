"""Scope analysis for moving a local declaration into the narrowest scope that uses it.

Works on source text with comments and literal contents masked; clang-query supplies
the declaration's position, name, storage, and whether its type is trivially
default-constructible.
"""

import re
from dataclasses import dataclass, field

from ioa.skip import Reason
from ioa.source import mask

WORD = re.compile(r"[A-Za-z_]\w*")
OPEN, CLOSE = "([{", ")]}"
PREPRO = re.compile(r"(?m)^[ \t]*#")
LABEL = re.compile(
    r"(?m)(?:^|[;{}])\s*(?:case\b|default\s*:(?!:)|(?!(?:public|private|protected)\b)[A-Za-z_]\w*\s*:(?!:))"
)
CALL = re.compile(r"[\w>\])]\s*\(|\bnew\b|[A-Za-z_]\w*\s*\{")
MUTATES = re.compile(r"\+\+|--|<<=|>>=|[^=!<>]=(?!=)")
ASSIGNED = re.compile(r"(?<![\w$])([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)?(?:[-+*/%&|^]|<<|>>)?=(?!=)")
IDENT = re.compile(r"(?<![\w.])[A-Za-z_]\w*")
LITERAL_WORDS = {"nullptr", "true", "false"}
NOT_TYPES = {"return", "case", "throw", "delete", "else", "do", "co_return", "co_yield", "sizeof", "goto"}
LAMBDA = re.compile(r"\[([^\[\]]*)\]\s*(?:\([^()]*\))?\s*(?:mutable\s*)?(?:noexcept\s*)?(?:->[^{};]*)?$")
ENTRIES = {"block": {"{"}, "init-statement": {"if(", "ifconstexpr(", "switch(", "for("}}


@dataclass
class Stmt:
    kind: str
    start: int
    end: int
    head: tuple[int, int] | None = None
    subs: list["Stmt"] = field(default_factory=list)
    body: list["Stmt"] = field(default_factory=list)
    open: int = -1

    def has(self, p: int) -> bool:
        return self.start <= p < self.end


@dataclass(frozen=True)
class Decl:
    """A local declaration: char offset of its first token, name, and clang's type facts."""

    start: int
    name: str
    trivial: bool
    static: bool
    ctor: bool = False
    trivial_dtor: bool = True


@dataclass
class Target:
    form: str
    at: int
    in_loop: bool
    body: list[Stmt] = field(default_factory=list)
    stmt: Stmt | None = None
    in_try: bool = False


@dataclass
class Move:
    """A planned move, or the reason it is skipped."""

    decl: Decl
    stmt: tuple[int, int]
    lines: tuple[int, int]
    skipped: Reason | None = None
    note: str = ""
    target: Target | None = None
    removal: tuple[int, int] = (0, 0)
    comments: list[str] = field(default_factory=list)


class Source:
    def __init__(self, text: str):
        self.text = text
        self.masked = mask(text, literals=True)
        self._blocks: dict[int, list[Stmt]] = {}

    def block(self, open_: int) -> list[Stmt]:
        if open_ not in self._blocks:
            self._blocks[open_] = parse_block(self.masked, open_)
        return self._blocks[open_]


def closing(m: str, i: int) -> int:
    depth = 0
    for k in range(i, len(m)):
        c = m[k]
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
            if depth == 0:
                return k
    return len(m)


def _ws(m: str, i: int, end: int) -> int:
    while i < end and m[i].isspace():
        i += 1
    return i


def _word(m: str, i: int) -> str:
    w = WORD.match(m, i)
    return w[0] if w else ""


def _line_start(t: str, p: int) -> int:
    return t.rfind("\n", 0, p) + 1


def _line_end(t: str, p: int) -> int:
    j = t.find("\n", p)
    return len(t) if j < 0 else j


def _top(m: str, a: int, b: int, ch: str) -> bool:
    k = a
    while k < b:
        c = m[k]
        if c in OPEN:
            k = closing(m, k) + 1
            continue
        if c == ch and not (ch == ":" and (m[k + 1:k + 2] == ":" or m[k - 1:k] == ":")):
            return True
        k += 1
    return False


def _paren(m: str, i: int, end: int) -> tuple[int, int] | None:
    i = _ws(m, i, end)
    if i >= end or m[i] != "(":
        return None
    return i, min(closing(m, i), end)


def _simple(m: str, i: int, end: int) -> Stmt:
    k = i
    while k < end:
        c = m[k]
        if c in OPEN:
            k = closing(m, k) + 1
            continue
        if c in CLOSE:
            break
        if c == ";":
            return Stmt("simple", i, k + 1)
        if c == "#" and k > i and not m[_line_start(m, k):k].strip():
            break
        k += 1
    return Stmt("simple", i, max(min(k, end), i + 1))


def parse_stmt(m: str, i: int, end: int) -> Stmt:
    c = m[i]
    if c == "#":
        k = i
        while True:
            j = _line_end(m, k)
            if j >= end or m[j - 1] != "\\":
                return Stmt("directive", i, min(j, end))
            k = j + 1
    if c == "{":
        j = min(closing(m, i), end)
        return Stmt("block", i, j + 1, open=i)
    if c == ";":
        return Stmt("empty", i, i + 1)
    w = _word(m, i)
    after = i + len(w)
    if w in ("if", "switch", "while", "for"):
        k = after
        if w == "if" and _word(m, _ws(m, k, end)) == "constexpr":
            k = _ws(m, k, end) + len("constexpr")
        p = _paren(m, k, end)
        if p is None or p[1] >= end:
            return _simple(m, i, end)
        body = parse_stmt(m, _ws(m, p[1] + 1, end), end)
        subs, last, kind = [body], body.end, w
        if w == "if":
            k = _ws(m, last, end)
            if _word(m, k) == "else":
                e = parse_stmt(m, _ws(m, k + 4, end), end)
                subs.append(e)
                last = e.end
        if w == "for" and _top(m, p[0] + 1, p[1], ":") and not _top(m, p[0] + 1, p[1], ";"):
            kind = "range_for"
        return Stmt(kind, i, last, head=(p[0] + 1, p[1]), subs=subs)
    if w == "do":
        body = parse_stmt(m, _ws(m, after, end), end)
        k = _ws(m, body.end, end)
        p = _paren(m, k + 5, end) if _word(m, k) == "while" else None
        if p is None:
            return Stmt("do", i, body.end, subs=[body])
        semi = m.find(";", p[1], end)
        return Stmt("do", i, end if semi < 0 else semi + 1, head=(p[0] + 1, p[1]), subs=[body])
    if w == "try":
        k = _ws(m, after, end)
        if k >= end or m[k] != "{":
            return _simple(m, i, end)
        blocks = [parse_stmt(m, k, end)]
        while True:
            k = _ws(m, blocks[-1].end, end)
            p = _paren(m, k + 5, end) if _word(m, k) == "catch" else None
            h = _ws(m, p[1] + 1, end) if p else end
            if h >= end or m[h] != "{":
                break
            blocks.append(parse_stmt(m, h, end))
        return Stmt("try", i, blocks[-1].end, subs=blocks)
    if w == "case" or w == "default" and m[_ws(m, after, end):][:1] == ":":
        k = after
        while k < end and not (m[k] == ":" and m[k + 1:k + 2] != ":" and m[k - 1] != ":"):
            k = closing(m, k) + 1 if m[k] in OPEN else k + 1
        return Stmt("label", i, min(k + 1, end))
    if w:
        k = _ws(m, after, end)
        if k < end and m[k] == ":" and m[k + 1:k + 2] != ":":
            return Stmt("label", i, k + 1)
    return _simple(m, i, end)


def parse_block(m: str, open_: int) -> list[Stmt]:
    """Top-level statements of the block whose '{' is at open_; nested blocks parse lazily."""
    end = min(closing(m, open_), len(m))
    out: list[Stmt] = []
    i = open_ + 1
    while (i := _ws(m, i, end)) < end:
        s = parse_stmt(m, i, end)
        out.append(s)
        i = max(s.end, i + 1)
    return out


def _fill(src: Source, s: Stmt) -> Stmt:
    if s.kind == "block" and not s.body:
        s.body = src.block(s.open)
    return s


def enclosing_open(m: str, pos: int) -> int | None:
    depth = 0
    for k in range(pos - 1, -1, -1):
        c = m[k]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                return k
            depth -= 1
    return None


def _back(m: str, p: int) -> int:
    p -= 1
    while p >= 0 and m[p].isspace():
        p -= 1
    return p


def mentions(m: str, name: str, a: int, b: int) -> list[int]:
    """Offsets of name in m[a:b] that can refer to a local: not a member, qualified name,
    or scope qualifier."""
    out = []
    for x in re.finditer(rf"(?<![\w$]){re.escape(name)}(?![\w$])", m[a:b]):
        p = a + x.start()
        j = _back(m, p)
        if j >= 0 and (m[j] == "." or m[j - 1:j + 1] in ("->", "::")):
            continue
        k = _ws(m, a + x.end(), len(m))
        if m[k:k + 2] == "::":
            continue
        out.append(p)
    return out


def _declares(m: str, p: int, name: str) -> bool:
    k = _ws(m, p + len(name), len(m))
    if m[k:k + 1] not in ("=", ";", "(", "{", "[", ",") or m[k:k + 2] == "==":
        return False
    j = _back(m, p)
    if j < 0:
        return False
    if m[j] in ">*&":
        return True
    w = re.search(r"[A-Za-z_]\w*$", m[max(0, j - 63):j + 1])
    return bool(w) and w[0] not in NOT_TYPES


def _in_ref_lambda(m: str, p: int, floor: int) -> bool:
    o = enclosing_open(m, p)
    while o is not None and o > floor:
        lam = LAMBDA.search(m[max(0, o - 400):o])
        if lam and "&" in lam[1]:
            return True
        o = enclosing_open(m, o)
    return False


def address_taken(m: str, ps: list[int], floor: int) -> bool:
    for p in ps:
        j = _back(m, p)
        if j >= 0 and m[j] == "&" and m[j - 1:j] != "&":
            k = _back(m, j)
            if k < 0 or not (m[k].isalnum() or m[k] in "_)]"):
                return True
        if re.search(r"&\s*[A-Za-z_]\w*\s*[=({]\s*$", m[max(0, p - 120):p]):
            return True
        if _in_ref_lambda(m, p, floor):
            return True
    return False


def assigned_first(m: str, body: list[Stmt], name: str) -> bool:
    """True when the first statement of body that mentions name assigns all of it."""
    for s in body:
        ps = mentions(m, name, s.start, s.end)
        if not ps:
            continue
        x = re.match(rf"\s*{re.escape(name)}\s*=(?!=)", m[s.start:s.end])
        return s.kind == "simple" and bool(x) and len(ps) == 1
    return False


def _initializer(m: str, a: int, b: int, name: str) -> str:
    for x in re.finditer(rf"(?<![\w$]){re.escape(name)}(?![\w$])", m[a:b]):
        k = _ws(m, a + x.end(), b)
        if m[k:k + 1] in ("=", "(", "{", "[", ";"):
            return m[a + x.end():b].rstrip().removesuffix(";")
    return m[a:b]


def _try_entry(s: Stmt, ms: list[int]) -> tuple[Stmt | None, bool, bool]:
    """For a try statement: the one block holding every mention, whether that block is the
    try block, and whether mentions span the try block and a handler."""
    holding = [b for b in s.subs if any(b.has(p) for p in ms)]
    if len(holding) != 1:
        return None, False, any(s.subs[0].has(p) for p in ms)
    return holding[0], holding[0] is s.subs[0], False


def _candidates(src: Source, level: list[Stmt], ms: list[int]) -> tuple[list[Target], bool]:
    """Nested scopes holding every mention, outermost first, and whether a try blocked one."""
    m = src.masked
    out: list[Target] = []
    in_loop = in_try = False
    while True:
        hit = [s for s in level if any(s.has(p) for p in ms)]
        if len(hit) != 1:
            first = hit[0] if hit else None
            blocked = bool(first and first.kind == "try" and any(first.subs[0].has(p) for p in ms))
            return out, blocked
        s = hit[0]
        inside = [b for b in s.subs if all(b.has(p) for p in ms)]
        head = s.head and s.head[0] <= min(ms) < s.head[1]
        if s.kind == "block":
            level = _fill(src, s).body
            out.append(Target("block", s.open + 1, in_loop, level, in_try=in_try))
            continue
        if s.kind in ("if", "switch", "for") and head:
            init_free = (m[s.head[0]:s.head[1]].lstrip().startswith(";") if s.kind == "for"
                         else not _top(m, s.head[0], s.head[1], ";"))
            if init_free:
                out.append(Target("init-statement", s.head[0], in_loop, stmt=s, in_try=in_try))
            return out, False
        if s.kind == "try":
            block, entered, blocked = _try_entry(s, ms)
            if block is None:
                return out, blocked
            in_try = in_try or entered
        if head or not inside or inside[0].kind != "block":
            return out, False
        b = _fill(src, inside[0])
        level = b.body
        if s.kind in ("for", "range_for", "while", "do"):
            in_loop = True
        if s.kind != "switch":
            out.append(Target("loop-body" if in_loop and s.kind != "if" and s.kind != "try" else "block",
                              b.open + 1, in_loop, level, in_try=in_try))


def _yields_address(text: str, p: int, name: str, whole: bool, array: bool) -> bool:
    if whole:
        return True
    after = text[_ws(text, p + len(name), len(text)):]
    if re.match(r"(?:\.|->)\s*~?[A-Za-z_]\w*\s*(?:<[^;]*?>\s*)?\(", after):
        return True
    return array and not after.startswith("[")


def escapes(m: str, name: str, a: int, b: int, whole: bool = True, array: bool = False) -> bool:
    """True when a statement in m[a:b] assigns a name declared outside m[a:b] and mentions
    name in a way that can yield its address: any mention when whole, a member call, or a
    bare array name that decays to a pointer."""
    for piece in re.finditer(r"[^;{}]+", m[a:b]):
        text = piece[0]
        if not any(_yields_address(text, p, name, whole, array) for p in mentions(text, name, 0, len(text))):
            continue
        for x in ASSIGNED.finditer(text):
            lhs = x[1]
            if lhs == name:
                continue
            j = _back(text, x.start(1))
            if j >= 0 and (text[j] == "." or text[j - 1:j + 1] == "->"):
                return True
            if not any(_declares(m, p, lhs) for p in mentions(m, lhs, a, b)):
                return True
    return False


NOT_CALLS = {
    "if", "while", "for", "switch", "return", "catch", "sizeof", "alignof", "decltype",
    "noexcept", "static_cast", "const_cast", "reinterpret_cast", "dynamic_cast",
}


def _args(m: str, open_: int) -> list[str]:
    close = closing(m, open_)
    out, depth, start = [], 0, open_ + 1
    for k in range(open_ + 1, close):
        c = m[k]
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        elif c == "," and depth == 0:
            out.append(m[start:k])
            start = k + 1
    return [*out, m[start:close]]


def _template_head(m: str, gt: int) -> int:
    """Offset of the identifier's last char before the `<` matching m[gt], else -1."""
    depth = 0
    for i in range(gt, -1, -1):
        if m[i] == ">":
            depth += 1
        elif m[i] == "<":
            depth -= 1
            if depth == 0:
                j = _back(m, i)
                return j if j >= 0 and (m[j].isalnum() or m[j] == "_") else -1
        elif m[i] in ";{}()":
            return -1
    return -1


def call_argument(m: str, name: str, a: int, b: int, whole: bool = True, array: bool = False) -> bool:
    """True when a call in m[a:b] takes a member-call result on name, or name itself when
    whole (a non-trivial type) or array (it decays to a pointer)."""
    member = rf"\s*(?:\.|->)\s*~?[A-Za-z_]\w*\s*(?:<[^;]*?>\s*)?\(.*\)"
    tail = rf"(?:{member})?" if whole or array else member
    arg = re.compile(rf"\s*{re.escape(name)}{tail}\s*", re.S)
    for k in range(a, b):
        if m[k] != "(":
            continue
        j = _back(m, k)
        if j >= 0 and m[j] == ">":
            j = _template_head(m, j)
        if j < 0 or not (m[j].isalnum() or m[j] in "_)]"):
            continue
        callee = re.search(r"([A-Za-z_]\w*)$", m[:j + 1])
        if callee and callee[1] in NOT_CALLS:
            continue
        if any(arg.fullmatch(x) for x in _args(m, k)):
            return True
    return False


def _end(src: Source, t: Target) -> int:
    return t.stmt.end if t.form == "init-statement" else min(closing(src.masked, t.at - 1), len(src.masked))


def _check(src: Source, mv: Move, t: Target, ms: list[int], init: str) -> tuple[Reason, str] | None:
    m = src.masked
    crossed = m[mv.stmt[1]:t.at]
    if PREPRO.search(crossed):
        return Reason.PREPROCESSOR, ""
    if LABEL.search(crossed):
        return Reason.GOTO_OR_CASE, ""
    if address_taken(m, ms, mv.stmt[1]):
        return Reason.LOOP_CARRIED, "address-taken"
    if escapes(m, mv.decl.name, t.at, _end(src, t), whole=not mv.decl.trivial,
               array=init.lstrip().startswith("[")):
        return Reason.LOOP_CARRIED, "escapes"
    expr = re.sub(r"^\s*(?:\[[^\]]*\]\s*)*=", "", init)
    call = (bool(CALL.search(init)) or mv.decl.ctor
            or not mv.decl.trivial and init.lstrip().startswith(("(", "{")))
    mutates = bool(MUTATES.search(expr))
    dead = t.form != "init-statement" and assigned_first(m, t.body, mv.decl.name)
    if t.in_loop:
        if call:
            return Reason.COSTLY_CONSTRUCT, "call"
        if mutates:
            return Reason.COSTLY_CONSTRUCT, "side-effect"
        if not mv.decl.trivial:
            return Reason.COSTLY_CONSTRUCT, "non-trivial"
        if not dead:
            return Reason.LOOP_CARRIED, ""
    else:
        if not mv.decl.trivial_dtor:
            return Reason.COSTLY_CONSTRUCT, "nontrivial-dtor"
        reads = any(w not in LITERAL_WORDS for w in IDENT.findall(init))
        if (call or mutates or reads and not dead) and "".join(crossed.split()) not in ENTRIES.get(t.form, set()):
            return Reason.COSTLY_CONSTRUCT, "side-effect"
    if call_argument(m, mv.decl.name, t.at, _end(src, t), whole=not mv.decl.trivial,
                     array=init.lstrip().startswith("[")):
        return Reason.LOOP_CARRIED, "escapes"
    return None


def plan(src: Source, decl: Decl) -> Move | None:
    """The move for decl, a skip with its reason, or None when no nested scope holds
    every use."""
    t, m = src.text, src.masked
    open_ = enclosing_open(m, decl.start)
    if open_ is None:
        return None
    stmts = src.block(open_)
    k = next((i for i, s in enumerate(stmts) if s.has(decl.start)), None)
    if k is None or stmts[k].kind != "simple":
        return None
    s = stmts[k]
    close = min(closing(m, open_), len(m))
    ms = mentions(m, decl.name, s.end, close)
    if not ms or any(_declares(m, p, decl.name) for p in ms):
        return None
    if t[_line_start(t, s.start):s.start].strip() or m[s.end:_line_end(m, s.end)].strip():
        return None
    first = t.count("\n", 0, s.start)
    mv = Move(decl, (s.start, s.end), (first, first + t.count("\n", s.start, s.end)))
    targets, blocked = _candidates(src, stmts[k + 1:], ms)
    if not targets:
        if blocked:
            mv.skipped = Reason.TRY_READ_AFTER
            return mv
        return None
    if decl.static:
        mv.skipped = Reason.STATIC_LOCAL
        return mv
    init = _initializer(m, s.start, s.end, decl.name)
    failure = None
    for target in reversed(targets):
        if target.in_try:
            bad = (Reason.TRY_READ_AFTER, "")
        elif target.form == "init-statement" and target.in_loop:
            bad = (Reason.LOOP_CARRIED, "")
        elif target.form == "init-statement" and mask(t[s.start:s.end]) != t[s.start:s.end]:
            bad = (Reason.COMMENT_STRANDED, "comment-in-declaration")
        else:
            bad = _check(src, mv, target, ms, init)
        if bad is None:
            mv.target = target
            break
        failure = failure or bad
    else:
        mv.skipped, mv.note = failure
        return mv
    if not _comments(src, mv):
        return None
    return mv


def _comments(src: Source, mv: Move) -> bool:
    """Collect the comment block above the declaration and set the removal range."""
    t, m = src.text, src.masked
    lines = t.split("\n")
    mlines = m.split("\n")
    first, last = mv.lines
    top = first
    while top > 0 and not mlines[top - 1].strip() and lines[top - 1].strip():
        top -= 1
    if top < first and not lines[top].lstrip().startswith(("//", "/*")):
        return False
    mv.comments = lines[top:first]
    a = sum(len(x) + 1 for x in lines[:top])
    b = sum(len(x) + 1 for x in lines[:last + 1])
    mv.removal = (a, min(b, len(t)))
    return True


def _indent(t: str, p: int) -> str:
    return re.match(r"[ \t]*", t[_line_start(t, p):])[0]


def _shift(lines: list[str], old: str, new: str) -> list[str]:
    return [new + x[len(old):] if x.startswith(old) else new + x.lstrip() for x in lines]


def one_line(text: str) -> str:
    parts = text.split("\n")
    return " ".join([parts[0].rstrip()] + [x.strip() for x in parts[1:]])


def edits(src: Source, mv: Move) -> list[tuple[int, int, str]]:
    """Character-offset replacements that perform mv."""
    t, m = src.text, src.masked
    tg = mv.target
    a, b = mv.stmt
    old = _indent(t, a)
    out = [(mv.removal[0], mv.removal[1], "")]
    if tg.form == "init-statement":
        s = tg.stmt
        single = one_line(t[a:b])
        trailing = t[b:_line_end(t, b)].strip()
        ind = _indent(t, s.start)
        notes = _shift(mv.comments, old, ind) + ([ind + trailing] if trailing else [])
        if notes:
            ls = _line_start(t, s.start)
            out.append((ls, ls, "\n".join(notes) + "\n"))
        if s.kind == "for":
            semi = m.index(";", tg.at)
            out.append((tg.at, semi + 1, single))
        else:
            out.append((tg.at, tg.at, single + " "))
        return out
    nxt = _ws(m, tg.at, len(m))
    ind = _indent(t, nxt) if m[nxt:nxt + 1] != "}" and t.count("\n", tg.at, nxt) else _indent(t, tg.at) + "  "
    body = _shift(mv.comments + t[_line_start(t, a):_line_end(t, b)].split("\n"), old, ind)
    tail = "" if not m[tg.at:_line_end(m, tg.at)].strip() else "\n"
    out.append((tg.at, tg.at, "\n" + "\n".join(body) + tail))
    return out


def signature(src: Source, mv: Move) -> str:
    """Whitespace-free text that locates the moved declaration after formatting."""
    t = src.text
    decl = t[mv.stmt[0]:mv.stmt[1]]
    if mv.target.form == "init-statement":
        s = mv.target.stmt
        decl = t[s.start:mv.target.at] + one_line(decl)
    return "".join(decl.split())


def _overlaps(e: tuple[int, int, str], f: tuple[int, int, str]) -> bool:
    (a, b, _), (c, d, _) = e, f
    if a < b and c < d:
        return a < d and c < b
    if a == b:
        return c < a < d
    return a < c < b


def accept(src: Source, moves: list[Move]) -> list[Move]:
    """Moves in order whose edits do not overlap an earlier accepted move's edits."""
    taken: list[tuple[int, int, str]] = []
    heads: set[int] = set()
    out = []
    for mv in moves:
        es = edits(src, mv)
        if any(_overlaps(e, f) for e in es for f in taken) or mv.target.at in heads:
            continue
        taken += es
        if mv.target.form == "init-statement":
            heads.add(mv.target.at)
        out.append(mv)
    return out


def merge(es: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Join touching replacements, keeping insertion order, so no two share an offset."""
    out: list[list] = []
    for a, b, text in sorted(es, key=lambda e: (e[0], e[1] > e[0])):
        if out and a == out[-1][1]:
            out[-1][1] = b
            out[-1][2] += text
        else:
            out.append([a, b, text])
    return [tuple(e) for e in out]


def close_gaps(src: Source, es: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Widen whole-line deletions so they leave no doubled blank line and no blank line
    just inside a brace."""
    t, m = src.text, src.masked
    out = []
    for a, b, text in es:
        if not text and a == _line_start(t, a) and b > a and t[b - 1] == "\n":
            above = m[_line_start(m, a - 1):a].strip() if a else "{"
            nxt = _line_end(t, b)
            if nxt < len(t) and not t[b:nxt].strip() and (not above or above.endswith("{")):
                b = nxt + 1
            elif not above and a and m[b:_line_end(m, b)].strip().startswith("}"):
                a = _line_start(t, a - 1)
        out.append((a, b, text))
    return out


def replacements(src: Source, moves: list[Move], make=None) -> list[tuple[int, int, str]]:
    """The merged replacements for moves, built by make (default: edits)."""
    make = make or edits
    return close_gaps(src, merge([e for mv in moves for e in make(src, mv)]))


def apply_text(src: Source, moves: list[Move]) -> str:
    t = src.text
    for a, b, text in reversed(replacements(src, accept(src, moves))):
        t = t[:a] + text + t[b:]
    return t
