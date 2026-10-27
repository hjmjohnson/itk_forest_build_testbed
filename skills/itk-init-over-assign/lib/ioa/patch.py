import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ioa.manifest import Site

HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


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


def git(repo: Path, *args: str, input: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, input=input
    ).stdout


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


def index_sha(repo: Path, file: Path) -> str:
    return git(repo, "rev-parse", f":{file.as_posix()}").strip()


def write_index(repo: Path, file: Path, content: bytes) -> None:
    mode = git(repo, "ls-files", "-s", "--", file.as_posix()).split()[0]
    sha = git_bytes(repo, "hash-object", "-w", "--stdin", input=content).decode().strip()
    git(repo, "update-index", "--cacheinfo", f"{mode},{sha},{file.as_posix()}")


def blob_patch(repo: Path, file: Path, old_sha: str, new_sha: str) -> str:
    """A context patch for `file` that turns blob old_sha into blob new_sha."""
    text = git(repo, "diff", "-U3", old_sha, new_sha)
    name = file.as_posix()
    body = text.splitlines()
    start = next(i for i, ln in enumerate(body) if ln.startswith("@@"))
    head = [f"diff --git a/{name} b/{name}", f"--- a/{name}", f"+++ b/{name}"]
    return "\n".join(head + body[start:]) + "\n"


def apply_to_worktree(repo: Path, patch: str) -> bool:
    for extra in ([], ["-C1"]):
        p = subprocess.run(
            ["git", "apply", *extra, "-"], cwd=repo, capture_output=True, text=True, input=patch
        )
        if p.returncode == 0:
            return True
    return False
