"""Find the append or subscript-assignment run that follows a default-constructed
container local, decide whether brace initialization is safe, and render it.

Pure functions over source text and the container's canonical type.
"""

import re
from dataclasses import dataclass, field

from ioa.skip import Reason
from ioa.source import mask

PUSH, INDEX = "push_back_run", "index_assign_run"
COLUMNS = 120
CONTAINERS = ("std::vector", "std::array", "itk::Array", "vnl_vector")
INT_LITERAL = re.compile(r"^(-?)\s*(?:0[xX][\da-fA-F']+|\d[\d']*)([uUlLzZ]*)$")
FLOAT_LITERAL = re.compile(r"^-?\s*(?:\d[\d']*\.[\d']*|\.\d[\d']*|\d[\d']*(?=[eE]))(?:[eE][+-]?\d+)?([fFlL]?)$")
IDENT = re.compile(r"^[A-Za-z_]\w*$")
INT_RANK = {"char": 1, "short": 2, "int": 3, "long": 4, "long long": 5}
FLOAT_RANK = {"float": 1, "double": 2, "long double": 3}
UNSIGNED_ALIASES = {"size_t": 4, "SizeValueType": 4, "IdentifierType": 4}
SIGNED_ALIASES = {"ptrdiff_t": 4, "OffsetValueType": 4, "IndexValueType": 4}
STORAGE = re.compile(r"(?<![\w:])(?:static|thread_local)\b")


@dataclass
class Run:
    cls: str
    begin: int
    end: int
    first: int
    last: int
    indent: str
    head: str
    args: list[list[str]]
    comments: list[str] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)
    size: int | None = None
    skipped: Reason | None = None
    note: str = ""


def _close(code: str, i: int) -> int:
    """Index of the bracket closing the one at i, or -1."""
    depth = 0
    for k in range(i, len(code)):
        if code[k] in "([{":
            depth += 1
        elif code[k] in ")]}":
            depth -= 1
            if depth == 0:
                return k
    return -1


def _semicolon(code: str, i: int) -> int:
    depth = 0
    for k in range(i, len(code)):
        ch = code[k]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return -1
        elif ch == ";" and depth == 0:
            return k
    return -1


def split_top(code: str) -> list[tuple[int, int]]:
    """Spans of the top-level comma-separated parts of code (template angles respected)."""
    spans, depth, angle, start = [], 0, 0, 0
    for i, ch in enumerate(code):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "<" and i and (code[i - 1].isalnum() or code[i - 1] in "_:") and depth == 0:
            angle += 1
        elif ch == ">" and angle and code[i - 1] != "-":
            angle -= 1
        elif ch == "," and depth == 0 and angle == 0:
            spans.append((start, i))
            start = i + 1
    spans.append((start, len(code)))
    return spans


def _squash(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", s.strip())


def template_args(type_text: str) -> tuple[str, list[str]] | None:
    m = re.search(r"<", type_text)
    if not m:
        return None
    close = type_text.rfind(">")
    if close < m.start():
        return None
    inner = type_text[m.start() + 1:close]
    return type_text[:m.start()].strip(), [inner[a:b].strip() for a, b in split_top(inner)]


def container_of(canonical: str) -> tuple[str, list[str]] | None:
    """(container, template arguments) of a canonical container type, inline namespaces dropped."""
    found = template_args(re.sub(r"^(?:const\s+)?", "", canonical.strip()))
    if found is None:
        return None
    base = re.sub(r"::__\w+::", "::", found[0])
    return (base, found[1]) if base in CONTAINERS else None


def element_type(head: str) -> str | None:
    """The first template argument as spelled in the declaration head `Type name`."""
    m = re.match(r"^(.*?[\w>])\s+[A-Za-z_]\w*$", head.strip(), re.S)
    found = template_args(m[1]) if m else None
    return found[1][0] if found and found[1] and found[1][0] else None


def _line_of(text: str, i: int) -> int:
    return text.count("\n", 0, i) + 1


def _line_end(text: str, i: int) -> int:
    j = text.find("\n", i)
    return len(text) if j < 0 else j


def _trailing(text: str, code: str, a: int, b: int) -> str | None:
    """The comment in text[a:b] when only whitespace and a comment follow code; else None."""
    if code[a:b].strip():
        return None
    return text[a:b].strip()


def _statement(text: str, code: str, at: int, name: str):
    """(cls, args, index, semicolon, line end, comment) of one run statement starting at offset at, or None."""
    semi = _semicolon(code, at)
    if semi < 0:
        return None
    stmt = code[at:semi]
    eol = _line_end(text, semi)
    comment = _trailing(text, code, semi + 1, eol)
    if comment is None:
        return None
    word = re.compile(rf"(?<![\w.>:]){re.escape(name)}(?!\w)")
    push = re.match(rf"{re.escape(name)}\s*\.\s*(push_back|emplace_back)\s*\(", stmt)
    if push:
        open_ = at + push.end() - 1
        close = _close(code, open_)
        if close < 0 or code[close + 1:semi].strip():
            return None
        inner = code[open_ + 1:close]
        if not inner.strip() or word.search(inner):
            return None
        spans = split_top(inner) if push[1] == "emplace_back" else [(0, len(inner))]
        args = [text[open_ + 1 + a:open_ + 1 + b] for a, b in spans]
        return PUSH, args, None, semi, eol, comment
    idx = re.match(rf"{re.escape(name)}\s*\[", stmt)
    if idx:
        open_ = at + idx.end() - 1
        close = _close(code, open_)
        lit = INT_LITERAL.match(code[open_ + 1:close].strip()) if close > 0 else None
        if lit is None or lit[1]:
            return None
        assign = re.match(r"\s*=(?!=)", code[close + 1:semi])
        if not assign:
            return None
        start = close + 1 + assign.end()
        rhs = code[start:semi]
        if not rhs.strip() or word.search(rhs):
            return None
        index = int(re.sub(r"[uUlLzZ']", "", code[open_ + 1:close].strip()), 0)
        return INDEX, [text[start:semi]], index, semi, eol, comment
    return None


def find_run(text: str, line: int, col: int, name: str) -> Run | None:
    """The run after the declaration of name at 1-based line and byte column col, or None."""
    code = mask(text, literals=True)
    commentless = mask(text)
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        return None
    line_start = sum(len(s) + 1 for s in lines[:line - 1])
    raw = lines[line - 1]
    prefix = raw.encode("utf-8", "surrogateescape")[:col - 1].decode("utf-8", "surrogateescape")
    if prefix.strip():
        return None
    begin = line_start + len(prefix)
    semi = _semicolon(code, begin)
    if semi < 0:
        return None
    decl = code[begin:semi]
    head = re.match(rf"^(.*[\w>*&])\s+{re.escape(name)}\s*(?:\(\s*(\d+)[uUlLzZ]*\s*\))?\s*$", decl, re.S)
    if head is None or len(split_top(head[1])) > 1 or code[begin:semi] != text[begin:semi]:
        return None
    first_comment = _trailing(text, code, semi + 1, _line_end(text, semi))
    if first_comment is None:
        return None
    named = _squash(f"{text[begin:begin + len(head[1])]} {name}")
    run = Run("", begin, _line_end(text, semi), line, line, prefix, named, [])
    if head[2] is not None:
        run.size = int(head[2])
    if first_comment:
        run.comments.append(first_comment)
    pos = run.end + 1
    while pos < len(text):
        eol = _line_end(text, pos)
        here = text[pos:eol]
        if here.lstrip().startswith("#"):
            k = eol + 1
            while k < len(text) and (text[k:_line_end(text, k)].lstrip().startswith("#")
                                     or not text[k:_line_end(text, k)].strip()):
                k = _line_end(text, k) + 1
            nxt = text[k:_line_end(text, k)]
            if k < len(text) and nxt.startswith(prefix) and not nxt[len(prefix)].isspace() and (
                    _statement(text, code, k + len(prefix), name)):
                run.skipped = Reason.PREPROCESSOR
            break
        if not here.startswith(prefix) or not here[len(prefix):len(prefix) + 1].strip():
            break
        if not code[pos:eol].strip():
            break
        found = _statement(text, code, pos + len(prefix), name)
        if found is None:
            break
        cls, args, index, semi, end, comment = found
        if (run.cls and cls != run.cls) or (run.size is not None and cls == PUSH):
            break
        if commentless[pos:semi] != text[pos:semi]:
            run.skipped, run.note = Reason.COMMENT_STRANDED, "comment-in-element"
        run.cls = cls
        run.args.append([_squash(a) for a in args])
        if index is not None:
            run.indices.append(index)
        if comment:
            run.comments.append(comment)
        run.end = end
        run.last = _line_of(text, end)
        pos = end + 1
    if not run.args:
        if run.skipped is None:
            return None
        run.cls = run.cls or PUSH
    return run


def declared_type(before: str, ident: str) -> str | None:
    """The type of the last visible declaration of ident in before (masked), or None."""
    pat = re.compile(
        rf"(?:^|[;{{}}(,])\s*((?:(?:const|constexpr|static)\s+)*[A-Za-z_][\w:<>]*(?:\s+[A-Za-z_][\w:<>]*)*)"
        rf"\s*[&*]*\s*(?<![\w]){re.escape(ident)}\s*(?=[=;,)\[{{(])"
    )
    found = None
    for m in pat.finditer(before):
        if m[1].split()[-1] not in ("return", "else", "case", "goto", "delete", "new", "throw"):
            found = m[1]
    return found


def classify(type_text: str) -> tuple[str, bool, int] | None:
    """('int', unsigned, rank) or ('float', False, rank) for an arithmetic type, else None."""
    t = re.sub(r"\b(?:const|constexpr|static|volatile)\b", "", type_text)
    t = re.sub(r"^(?:\w+::)*", "", t.strip()) if "<" not in t else t.strip()
    t = " ".join(t.split())
    if t in FLOAT_RANK:
        return "float", False, FLOAT_RANK[t]
    if t in UNSIGNED_ALIASES:
        return "int", True, UNSIGNED_ALIASES[t]
    if t in SIGNED_ALIASES:
        return "int", False, SIGNED_ALIASES[t]
    if m := re.fullmatch(r"(u?)int(\d+)_t", t):
        return "int", bool(m[1]), {8: 1, 16: 2, 32: 3, 64: 5}.get(int(m[2]), 3)
    if t == "bool":
        return "int", True, 0
    words = t.split()
    unsigned = "unsigned" in words
    rest = " ".join(w for w in words if w not in ("signed", "unsigned", "int")) or "int"
    if t in ("unsigned", "signed") or (words and all(w in ("signed", "unsigned", "char", "short", "int", "long")
                                                     for w in words)):
        return "int", unsigned, INT_RANK.get(rest, 3)
    return None


def element_kind(expr: str, before: str) -> tuple[str, bool, int, str] | None:
    """(kind, unsigned, rank, how) of an element: how is literal or identifier."""
    e = expr.strip()
    if m := INT_LITERAL.match(e):
        suffix = m[2].lower()
        return "int", "u" in suffix, 3 + suffix.count("l"), "negative" if m[1] else "literal"
    if m := FLOAT_LITERAL.match(e):
        return "float", False, {"f": 1, "l": 3}.get(m[1].lower(), 2), "literal"
    if IDENT.match(e):
        declared = declared_type(before, e)
        kind = classify(declared) if declared else None
        return (*kind, "identifier") if kind else None
    return None


def narrows(target: tuple[str, bool, int], elem: tuple[str, bool, int, str]) -> bool:
    tkind, tunsigned, trank = target
    ekind, eunsigned, erank, how = elem
    if tkind == "int":
        if ekind == "float":
            return True
        if not tunsigned and eunsigned:
            return True
        if tunsigned and (how == "negative" or (how == "identifier" and not eunsigned)):
            return True
        return how == "identifier" and erank > trank
    if ekind == "int":
        return how == "identifier"
    return how == "identifier" and erank > trank


def brace_list(run: Run) -> list[str]:
    """The brace-list elements in order: by index for subscript runs."""
    if run.cls == INDEX:
        return [a[0] for _, a in sorted(zip(run.indices, run.args))]
    elem = element_type(run.head)
    return [a[0] if len(a) == 1 else f"{elem}({', '.join(a)})" for a in run.args]


def judge(run: Run, canonicals: list[str], before: str) -> None:
    """Set run.skipped and run.note for the first guard that fails for any instantiation."""
    if run.skipped is not None:
        return
    code = mask(before, literals=True)
    for canonical in canonicals or [""]:
        found = container_of(canonical)
        container, targs = found if found else ("", [])
        verdict = _verdict(run, container, targs, code)
        if verdict:
            run.skipped, run.note = verdict
            return


def _verdict(run: Run, container: str, targs: list[str], before: str) -> tuple[Reason, str] | None:
    if STORAGE.search(run.head):
        return Reason.STATIC_LOCAL, ""
    if container == "vnl_vector":
        return Reason.INIT_LIST_CTOR, "no-init-list"
    if any(len(a) > 1 for a in run.args) and element_type(run.head) is None:
        return Reason.INIT_LIST_CTOR, "element-type-unknown"
    if run.size is not None and container != "std::vector":
        return Reason.INIT_LIST_CTOR, "sized-non-vector"
    if run.cls == INDEX:
        n = len(run.indices)
        size = targs[1] if container == "std::array" and len(targs) > 1 else None
        if run.size is not None:
            size = str(run.size)
        if sorted(run.indices) != list(range(n)) or (size is not None and size.isdigit() and int(size) != n):
            return Reason.NARROWING, "partial-coverage"
        if run.indices != sorted(run.indices) and not all(_inert(a[0]) for a in run.args):
            return Reason.ORDER_VIOLATION, "index-order"
    target = classify(targs[0]) if targs else None
    if target is None:
        return None
    kinds = [element_kind(a[0], before) if len(a) == 1 else None for a in run.args]
    if any(k is not None and narrows(target, k) for k in kinds):
        return Reason.NARROWING, ""
    if container == "std::vector" and len(run.args) <= 2 and (
            not all(k and k[0] == "float" for k in kinds) if target[0] == "int"
            else any(k and k[0] == "int" for k in kinds)):
        return Reason.INIT_LIST_CTOR, ""
    return None


def _inert(expr: str) -> bool:
    """A literal: evaluating it in another order changes nothing."""
    e = expr.strip()
    return bool(INT_LITERAL.match(e) or FLOAT_LITERAL.match(e)
                or re.fullmatch(r"(?:u8|u|U|L)?(?:'(?:\\.|[^'\\])+'|\"(?:\\.|[^\"\\])*\")", e))


def render(run: Run) -> str:
    """The replacement declaration, starting at the declaration's first column."""
    elems = brace_list(run)
    comment = f" {run.comments[0]}" if run.comments else ""
    one = f"{run.head}{{{', '.join(elems)}}};"
    if len(run.indent) + len(one) + len(comment) <= COLUMNS:
        return one + comment
    inner = ",\n".join(f"{run.indent}  {e}" for e in elems)
    return f"{run.head}{{\n{inner}\n{run.indent}}};{comment}"


def count_elements(text: str, begin: int, name: str) -> tuple[int, int, int] | None:
    """(element count, offset of name, offset of the closing `;`) of the brace declaration of name at or after begin."""
    code = mask(text, literals=True)
    m = re.compile(rf"(?<![\w.]){re.escape(name)}\s*\{{").search(code, begin)
    if m is None:
        return None
    close = _close(code, m.end() - 1)
    semi = code.find(";", close)
    if close < 0 or semi < 0 or code[close + 1:semi].strip():
        return None
    inner = code[m.end():close]
    parts = [inner[a:b] for a, b in split_top(inner)]
    return sum(1 for p in parts if p.strip()), m.start(), semi
