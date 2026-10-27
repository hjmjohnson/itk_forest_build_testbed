import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ioa.manifest import Manifest, Site
from ioa.patch import Hunk, diff, git, map_line, parse_diff

WORD = re.compile(r"\w")


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
    """Stripped lines with an identifier character; bare braces prove nothing."""
    return {t for t in (ln.strip() for ln in lines) if WORD.search(t)}


@dataclass(frozen=True)
class Span:
    """A stage edit in final working-tree lines; `gap` is a deletion after `lo`."""

    lo: int
    hi: int
    gap: bool

    def meets(self, h: Hunk) -> bool:
        if h.new_count == 0:
            return self.gap and self.lo == h.new_start
        lo, hi = h.new_start, h.new_start + h.new_count - 1
        if self.gap:
            return lo - 1 <= self.lo <= hi
        return self.lo <= hi and lo <= self.hi


def _span(h: Hunk, fwd: list[Hunk]) -> Span:
    if h.new_count == 0:
        p = map_line(h.new_start, fwd, end=True)
        return Span(p, p, True)
    lo = map_line(h.new_start, fwd)
    hi = map_line(h.new_start + h.new_count - 1, fwd, end=True)
    return Span(lo, max(lo, hi), False)


@dataclass
class _Site:
    site: Site
    spans: list[Span]
    added: set[str]
    removed: set[str]
    group: int = 0


@dataclass
class Stage:
    record: StageRecord
    spans: dict[Path, list[Span]] = field(default_factory=dict)
    added: dict[Path, set[str]] = field(default_factory=dict)
    removed: dict[Path, set[str]] = field(default_factory=dict)
    sites_at: list[_Site] = field(default_factory=list)

    def at(self, h: Hunk) -> bool:
        return any(s.meets(h) for s in self.spans.get(h.file, []))

    def by_text(self, h: Hunk) -> bool:
        if h.added:
            return bool(self.added.get(h.file, set()) & _texts(h.added))
        return bool(self.removed.get(h.file, set()) & _texts(h.removed))

    def groups(self) -> list[list[tuple[Path, Span]]]:
        """Spans that must commit or revert together: one site, or a partner file set."""
        out: dict[int, list[tuple[Path, Span]]] = {}
        for s in self.sites_at:
            out.setdefault(s.group, []).extend((s.site.file, sp) for sp in s.spans)
        return [g for g in out.values() if g]

    def sites(self, h: Hunk) -> list[Site]:
        mine = [s for s in self.sites_at if s.site.file == h.file]
        placed = [s.site for s in mine if any(sp.meets(h) for sp in s.spans)]
        if placed or self.at(h):
            return placed
        key = _texts(h.added) if h.added else _texts(h.removed)
        return [s.site for s in mine if key & (s.added if h.added else s.removed)]


def _touches(h: Hunk, s: Site) -> bool:
    """Whether a stage hunk's post-edit side meets a site, which is in post-edit lines."""
    if h.new_count == 0:
        return s.start <= h.new_start <= s.end
    return h.new_start <= s.end and s.start <= h.new_start + h.new_count - 1


def load(repo: Path, rec: StageRecord) -> Stage:
    """Read a stage's edits and project them onto the current working tree."""
    st = Stage(rec)
    hunks, _ = parse_diff(diff(repo, "-U0", rec.tree_before, rec.tree_after))
    fwd: dict[Path, list[Hunk]] = {}
    for h in parse_diff(diff(repo, "-U0", rec.tree_after))[0]:
        fwd.setdefault(h.file, []).append(h)
    span_of = {id(h): _span(h, fwd.get(h.file, [])) for h in hunks}
    for h in hunks:
        st.spans.setdefault(h.file, []).append(span_of[id(h)])
        st.added.setdefault(h.file, set()).update(_texts(h.added))
        st.removed.setdefault(h.file, set()).update(_texts(h.removed))
    for s in rec.manifest.applied():
        hit = [h for h in hunks if h.file == s.file and _touches(h, s)]
        st.sites_at.append(
            _Site(
                s,
                [span_of[id(h)] for h in hit],
                set().union(*(_texts(h.added) for h in hit)),
                set().union(*(_texts(h.removed) for h in hit)),
                len(st.sites_at),
            )
        )
    comp = _partner_components(rec.manifest.partners)
    for s in st.sites_at:
        if s.site.file in comp:
            s.group = -1 - comp[s.site.file]
    return st


def _partner_components(pairs: list[tuple[Path, Path]]) -> dict[Path, int]:
    comp: dict[Path, int] = {}
    for n, (a, b) in enumerate(pairs):
        ca, cb = comp.get(a, n), comp.get(b, n)
        comp.update({f: ca for f, c in comp.items() if c == cb})
        comp[a] = comp[b] = ca
    return comp
