import re
from dataclasses import dataclass
from pathlib import Path

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
TRAILING = re.compile(r"^(?P<code>.*?\S)\s*(?P<comment>//.*)$")
IDENT = re.compile(r"[A-Za-z_]\w*")


@dataclass(frozen=True)
class Stranded:
    file: Path
    line: int
    text: str


@dataclass
class _Hunk:
    file: Path
    removed: list[tuple[int, str]]
    added: list[str]


def _split(line: str) -> tuple[str, str]:
    s = line.strip()
    if s.startswith(("//", "/*", "*")):
        return "", s
    m = TRAILING.match(s)
    if m:
        return m["code"], m["comment"].strip()
    return s, ""


def _identifier(code: str) -> str:
    head = re.split(r"[=({;]", code, maxsplit=1)[0]
    ids = IDENT.findall(head)
    if not ids:
        return ""
    return ids[0] if re.search(r"\.|->", head) else ids[-1]


def _parse(diff_text: str) -> list[_Hunk]:
    hunks: list[_Hunk] = []
    path = Path()
    cur: _Hunk | None = None
    old_no = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            name = raw[4:].split("\t")[0]
            path = Path(name[2:] if name.startswith("b/") else name)
            cur = None
        elif raw.startswith("--- "):
            cur = None
        elif m := HUNK.match(raw):
            cur = _Hunk(path, [], [])
            hunks.append(cur)
            old_no = int(m[1])
        elif cur is None:
            continue
        elif raw.startswith("-"):
            cur.removed.append((old_no, raw[1:]))
            old_no += 1
        elif raw.startswith("+"):
            cur.added.append(raw[1:])
    return hunks


def _neighbor_identifier(hunk: _Hunk, index: int) -> str:
    n = len(hunk.removed)
    for dist in range(1, n):
        for j in (index + dist, index - dist):
            if 0 <= j < n:
                code, _ = _split(hunk.removed[j][1])
                if code:
                    return _identifier(code)
    return ""


def _has_comment(lines: list[str], comment: str) -> bool:
    return any(_split(a)[1] == comment for a in lines)


def check_hunks(diff_text: str) -> list[Stranded]:
    hunks = _parse(diff_text)
    stranded: list[Stranded] = []
    for hunk in hunks:
        for i, (line_no, text) in enumerate(hunk.removed):
            code, comment = _split(text)
            if not comment or _has_comment(hunk.added, comment):
                continue
            ident = _identifier(code) if code else _neighbor_identifier(hunk, i)
            word = re.compile(rf"\b{re.escape(ident)}\b") if ident else None
            if word and any(
                h.file == hunk.file
                and _has_comment(h.added, comment)
                and any(word.search(_split(a)[0]) for a in h.added)
                for h in hunks
                if h is not hunk
            ):
                continue
            stranded.append(Stranded(hunk.file, line_no, comment))
    return stranded
