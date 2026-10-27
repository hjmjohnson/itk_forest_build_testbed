import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ioa.manifest import Site

HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
DIFF_FLAGS = ("--no-color", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/")


@dataclass(eq=False)
class Hunk:
    file: Path
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    body: list[str] = field(default_factory=list)
    kind: str = ""
    sites: list[Site] = field(default_factory=list)
    group: int | None = None

    @property
    def removed(self) -> list[str]:
        return [ln[1:] for ln in self.body if ln.startswith("-")]

    @property
    def added(self) -> list[str]:
        return [ln[1:] for ln in self.body if ln.startswith("+")]

    def key(self) -> tuple:
        return (self.file, tuple(self.removed), tuple(self.added))

    def lines(self) -> range:
        if self.old_count:
            return range(self.old_start, self.old_start + self.old_count)
        return range(self.new_start, self.new_start + self.new_count)

    def old_lines(self) -> range:
        return range(self.old_start, self.old_start + self.old_count)


def git(repo: Path, *args: str, input: str | None = None, env: dict | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
        input=input, env=env,
    ).stdout


def diff(repo: Path, *args: str) -> str:
    return git(repo, "diff", *DIFF_FLAGS, *args)


def git_bytes(repo: Path, *args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, input=input
    ).stdout


def parse_diff(text: str) -> tuple[list[Hunk], list[Path]]:
    """Return the hunks of a -U0 diff and the added or deleted files it skips."""
    hunks: list[Hunk] = []
    skipped: list[Path] = []
    old = new = ""
    cur: Hunk | None = None
    for raw in text.splitlines():
        if raw.startswith("diff "):
            cur = None
        elif raw.startswith("--- ") and cur is None:
            old = raw[4:].split("\t")[0]
        elif raw.startswith("+++ ") and cur is None:
            new = raw[4:].split("\t")[0]
            if "/dev/null" in (old, new):
                name = old if new == "/dev/null" else new
                skipped.append(Path(name[2:]))
        elif m := HEADER.match(raw):
            if "/dev/null" in (old, new):
                cur = None
                continue
            cur = Hunk(
                Path(new[2:]),
                int(m[1]),
                1 if m[2] is None else int(m[2]),
                int(m[3]),
                1 if m[4] is None else int(m[4]),
            )
            hunks.append(cur)
        elif cur is not None and raw[:1] in ("-", "+", "\\"):
            cur.body.append(raw)
    return hunks, skipped


def _header(h: Hunk, new_start: int) -> str:
    return f"@@ -{h.old_start},{h.old_count} +{new_start},{h.new_count} @@"


def build_patch(hunks: list[Hunk], renumber: bool = True) -> str:
    """One -U0 patch per file; renumber when hunks are a subset of a diff."""
    out: list[str] = []
    by_file: dict[Path, list[Hunk]] = {}
    for h in hunks:
        by_file.setdefault(h.file, []).append(h)
    for file, fh in by_file.items():
        name = file.as_posix()
        out += [f"diff --git a/{name} b/{name}", f"--- a/{name}", f"+++ b/{name}"]
        delta = 0
        for h in sorted(fh, key=lambda h: h.old_start):
            start = h.new_start
            if renumber:
                start = h.old_start + delta + (h.old_count == 0) - (h.new_count == 0)
            out.append(_header(h, start))
            out += h.body
            delta += h.new_count - h.old_count
    return "\n".join(out) + "\n" if out else ""


def map_line(p: int, hunks: list[Hunk], end: bool = False, strict: bool = False) -> int:
    """Map old-side line p of a -U0 diff to its new side."""
    delta = 0
    for h in hunks:
        if h.old_count == 0:
            if h.old_start < p:
                delta += h.new_count
        elif h.old_start + h.old_count - 1 < p:
            delta += h.new_count - h.old_count
        elif h.old_start <= p:
            if strict:
                raise ValueError(f"line {p} was rewritten by another hunk")
            if h.new_count == 0:
                return h.new_start
            return h.new_start + (h.new_count - 1 if end else 0)
    return p + delta


def index_sha(repo: Path, file: Path) -> str:
    return git(repo, "rev-parse", f":{file.as_posix()}").strip()


def write_index(repo: Path, file: Path, content: bytes) -> None:
    mode = git(repo, "ls-files", "-s", "--", file.as_posix()).split()[0]
    sha = git_bytes(repo, "hash-object", "-w", "--stdin", input=content).decode().strip()
    git(repo, "update-index", "--cacheinfo", f"{mode},{sha},{file.as_posix()}")


def reverse_bytes(data: bytes, hunks: list[Hunk]) -> bytes:
    """Undo -U0 hunks whose new side is in data, bottom-up, checking every line.

    git apply -R places a zero-context pure deletion at its old-side line, which is wrong
    once an earlier hunk in the file changed the line count.
    """
    lines = data.split(b"\n")
    for h in sorted(hunks, key=lambda h: h.new_start, reverse=True):
        if any(ln.startswith("\\") for ln in h.body):
            raise ValueError(f"{h.file}:{h.new_start}: hunk touches a missing final newline")
        added = [ln.encode("utf-8", "surrogateescape") for ln in h.added]
        removed = [ln.encode("utf-8", "surrogateescape") for ln in h.removed]
        at = h.new_start - 1 if h.new_count else h.new_start
        if lines[at:at + len(added)] != added:
            raise ValueError(f"{h.file}:{h.new_start}: lines differ from the hunk's new side")
        lines[at:at + len(added)] = removed
    return b"\n".join(lines)


def reverse_in_worktree(repo: Path, hunks: list[Hunk]) -> None:
    """Undo hunks whose new side is in working-tree lines."""
    by_file: dict[Path, list[Hunk]] = {}
    for h in hunks:
        by_file.setdefault(h.file, []).append(h)
    for file, fh in by_file.items():
        path = repo / file
        path.write_bytes(reverse_bytes(path.read_bytes(), fh))


def mirror_format(
    repo: Path, file: Path, before: str, after: str,
    spans: list[tuple[int, int]] | None = None, clang_format: str = "clang-format",
) -> bool:
    """Replay the index formatting in working-tree lines, where other kinds' edits sit.

    When the formatting reaches a line another kind changed, format the working tree
    over the same spans instead, so it ends aligned; returns False in that case.
    """
    work = git(repo, "hash-object", "-w", "--", file.as_posix()).strip()
    to_work, _ = parse_diff(diff(repo, "-U0", before, work))
    fmt, _ = parse_diff(diff(repo, "-U0", before, after))
    moved = []
    try:
        for h in fmt:
            for ln in h.old_lines() or [h.old_start]:
                if ln:
                    map_line(ln, to_work, strict=True)
            start = map_line(h.old_start, to_work) if h.old_start else 0
            moved.append(Hunk(file, start, h.old_count, 0, h.new_count, h.body))
    except ValueError:
        if not spans:
            raise RuntimeError(f"{file}: clang-format touched another kind's lines") from None
        ranges = [f"--lines={map_line(a, to_work)}:{map_line(b, to_work, end=True)}" for a, b in spans]
        subprocess.run(
            [clang_format, "-i", "--style=file", "--fallback-style=none", *ranges, file.as_posix()],
            cwd=repo, check=True, capture_output=True,
        )
        return False
    git(repo, "apply", "--unidiff-zero", "-", input=build_patch(moved))
    return True
