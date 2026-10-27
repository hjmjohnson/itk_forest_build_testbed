import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@")
IDENT = re.compile(r"[A-Za-z_]\w*")


@dataclass(frozen=True)
class Stranded:
    file: Path
    line: int
    text: str


@dataclass
class _Comment:
    start: int
    text: str


@dataclass
class _Hunk:
    file: Path
    first_old: int
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    deleted_file: bool = False


def _skip_literal(line: str, i: int) -> int:
    quote = line[i]
    i += 1
    while i < len(line) and line[i] != quote:
        i += 2 if line[i] == "\\" else 1
    return i + 1


def _scan(lines: list[str]) -> tuple[list[str], list[_Comment]]:
    """Split lines into per-line code and the comments found in them."""
    codes: list[str] = []
    comments: list[_Comment] = []
    block: _Comment | None = None
    for n, line in enumerate(lines):
        code = ""
        i = 0
        while i < len(line):
            if block is None and line.startswith("/*", i):
                block = _Comment(n, "")
                part_start, search_from = i, i + 2
            elif block is not None:
                part_start, search_from = i, i
            elif line[i] in "\"'":
                j = _skip_literal(line, i)
                code += line[i:j]
                i = j
                continue
            elif line.startswith("//", i):
                comments.append(_Comment(n, line[i:].strip()))
                break
            else:
                code += line[i]
                i += 1
                continue
            j = line.find("*/", search_from)
            end = len(line) if j < 0 else j + 2
            block.text += ("\n" if block.text else "") + line[part_start:end].strip()
            i = end
            if j >= 0:
                comments.append(block)
                block = None
        codes.append(code)
    if block is not None:
        comments.append(block)
    return codes, comments


def _identifier(code: str) -> str:
    head = re.split(r"[=({;]", code, maxsplit=1)[0]
    ids = IDENT.findall(head)
    if not ids:
        return ""
    return ids[0] if re.search(r"\.|->", head) else ids[-1]


def _neighbor_code(codes: list[str], start: int) -> str:
    if codes[start].strip():
        return codes[start]
    for dist in range(1, len(codes)):
        for j in (start + dist, start - dist):
            if 0 <= j < len(codes) and codes[j].strip():
                return codes[j]
    return ""


def _parse(diff_text: str) -> list[_Hunk]:
    hunks: list[_Hunk] = []
    path = Path()
    deleted = False
    cur: _Hunk | None = None
    old_left = new_left = 0
    for raw in diff_text.splitlines():
        if cur is not None and (old_left > 0 or new_left > 0):
            if raw.startswith("-") and old_left > 0:
                cur.removed.append(raw[1:])
                old_left -= 1
            elif raw.startswith("+") and new_left > 0:
                cur.added.append(raw[1:])
                new_left -= 1
            elif old_left > 0 and new_left > 0 and raw.startswith(" "):
                old_left -= 1
                new_left -= 1
            continue
        if raw.startswith("+++ "):
            name = raw[4:].split("\t")[0]
            deleted = name == "/dev/null"
            path = Path(name[2:] if name.startswith("b/") else name)
        elif m := HUNK.match(raw):
            old_left = int(m[2]) if m[2] is not None else 1
            new_left = int(m[3]) if m[3] is not None else 1
            cur = _Hunk(path, int(m[1]), deleted_file=deleted)
            hunks.append(cur)
    return hunks


def check_hunks(diff_text: str) -> list[Stranded]:
    hunks = _parse(diff_text)
    pools = []
    for h in hunks:
        codes, found = _scan(h.added)
        pools.append(([c.text for c in found], "\n".join(codes)))
    stranded: list[Stranded] = []
    for hunk, (pool, _) in zip(hunks, pools):
        if hunk.deleted_file:
            continue
        codes, found = _scan(hunk.removed)
        for c in found:
            if c.text in pool:
                pool.remove(c.text)
                continue
            ident = _identifier(_neighbor_code(codes, c.start))
            word = re.compile(rf"\b{re.escape(ident)}\b") if ident else None
            other = next(
                (
                    p
                    for h, p in zip(hunks, pools)
                    if h is not hunk and c.text in p[0] and word and word.search(p[1])
                ),
                None,
            )
            if other is not None:
                other[0].remove(c.text)
                continue
            stranded.append(Stranded(hunk.file, hunk.first_old + c.start, c.text))
    return stranded


def unified_diff(rel: str, old: str, new: str) -> str:
    """A -U0 diff of one file's text, for check_hunks without consulting the git index."""
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}", n=0))
