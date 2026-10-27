import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ioa.manifest import Manifest, Site
from ioa.patch import Hunk, diff, git, parse_diff


@dataclass
class StageRecord:
    kind: str
    manifest: Manifest
    tree_before: str
    tree_after: str


def snapshot(repo: Path) -> str:
    """Write the working tree's tracked files as a tree without touching the index."""
    index = Path(git(repo, "rev-parse", "--git-path", "index").strip())
    index = index if index.is_absolute() else repo / index
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "index"
        shutil.copyfile(index, tmp)
        env = {**os.environ, "GIT_INDEX_FILE": str(tmp)}
        git(repo, "add", "-u", "--", ".", env=env)
        return git(repo, "write-tree", env=env).strip()


def _texts(lines: list[str]) -> set[str]:
    return {t for t in (ln.strip() for ln in lines) if t}


@dataclass
class _Stage:
    record: StageRecord
    added: dict[Path, set[str]] = field(default_factory=dict)
    removed: dict[Path, set[str]] = field(default_factory=dict)
    site_texts: list[tuple[Site, set[str], set[str]]] = field(default_factory=list)

    def owns(self, h: Hunk) -> bool:
        if h.added:
            return bool(self.added.get(h.file, set()) & _texts(h.added))
        return bool(self.removed.get(h.file, set()) & _texts(h.removed))

    def sites(self, h: Hunk) -> list[Site]:
        key = _texts(h.added) if h.added else _texts(h.removed)
        return [
            s for s, add, rem in self.site_texts
            if s.file == h.file and key & (add if h.added else rem)
        ]


def load(repo: Path, rec: StageRecord) -> _Stage:
    st = _Stage(rec)
    hunks, _ = parse_diff(diff(repo, "-U0", rec.tree_before, rec.tree_after))
    for h in hunks:
        st.added.setdefault(h.file, set()).update(_texts(h.added))
        st.removed.setdefault(h.file, set()).update(_texts(h.removed))
    for s in rec.manifest.applied():
        add: set[str] = set()
        rem: set[str] = set()
        for h in hunks:
            lo = h.lines().start
            hi = max(lo, h.lines().stop - 1)
            if h.file == s.file and lo <= s.end and s.start <= hi:
                add |= _texts(h.added)
                rem |= _texts(h.removed)
        st.site_texts.append((s, add, rem))
    return st
