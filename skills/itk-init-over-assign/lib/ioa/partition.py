import dataclasses
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ioa import gate
from ioa.comments import check_hunks
from ioa.manifest import Manifest, Site
from ioa.patch import (
    Hunk,
    apply_to_worktree,
    blob_patch,
    build_patch,
    git,
    git_bytes,
    index_sha,
    parse_diff,
    write_index,
)
from ioa.skip import Reason

SUBJECTS = {
    "member-init": "STYLE: Initialize members in constructor initializer lists",
    "local-init": "STYLE: Initialize locals at declaration instead of assigning",
    "local-const": "STYLE: Make initialized locals const where never mutated",
    "container-list-init": "STYLE: Replace push_back and index sequences with list initialization",
    "container-const": "STYLE: Make list-initialized containers const where never mutated",
    "itk-helpers": "STYLE: Use Filled, MakeFilled, and AllocateInitialized helpers",
    "itk-helpers-constexpr": "STYLE: Make Filled values with literal arguments constexpr",
    "narrow-scope": "STYLE: Declare variables in the narrowest scope that uses them",
}


@dataclass
class CommitPlan:
    kind: str
    message: str
    hunks: list[Hunk]
    notes: list[str] = field(default_factory=list)


@dataclass
class CommitResult:
    sha: str | None
    reverted: list[Site]
    notes: list[str] = field(default_factory=list)


def _sites(manifests: list[Manifest], h: Hunk) -> list[Site]:
    lo, hi = h.lines().start, max(h.lines().start, h.lines().stop - 1)
    return [
        s
        for m in manifests
        for s in m.applied()
        if s.file == h.file and s.start <= hi and s.end >= lo
    ]


def plan(repo: Path, manifests: list[Manifest]) -> list[CommitPlan]:
    by_kind: dict[str, list[Manifest]] = {}
    for m in manifests:
        if m.kind not in SUBJECTS:
            raise ValueError(f"unknown transform kind: {m.kind}")
        by_kind.setdefault(m.kind, []).append(m)
    order = [k for k in SUBJECTS if k in by_kind]
    if not order:
        return []
    hunks, skipped = parse_diff(git(repo, "diff", "-U0", "HEAD"))
    notes: dict[str, list[str]] = {k: [] for k in order}
    notes[order[0]] += [f"{f}: added or deleted file left out" for f in skipped]
    for h in hunks:
        owners = [
            k for k in order
            if any(m.covers(h.file, ln) for m in by_kind[k] for ln in h.lines())
        ]
        if owners:
            h.kind = owners[-1]
            h.sites = _sites(by_kind[h.kind], h)
    for file in dict.fromkeys(h.file for h in hunks):
        in_file = [h for h in hunks if h.file == file]
        covered = [h for h in in_file if h.kind]
        if not covered:
            notes[order[0]].append(f"{file}: no covered hunk, attached to {order[0]}")
        for h in in_file:
            if h.kind:
                continue
            above = [c for c in covered if c.old_start < h.old_start]
            below = [c for c in covered if c.old_start >= h.old_start]
            near = above[-1] if above else (below[0] if below else None)
            h.kind = near.kind if near else order[0]
    return [
        CommitPlan(k, SUBJECTS[k], [h for h in hunks if h.kind == k], notes[k])
        for k in order
        if any(h.kind == k for h in hunks)
    ]


def _match(plan_hunks: list[Hunk], fresh: list[Hunk]) -> list[Hunk]:
    """Relocate plan hunks in a fresh diff, since earlier commits shift lines."""
    free = list(fresh)
    found = []
    for h in plan_hunks:
        cands = [f for f in free if f.key() == h.key()]
        if not cands:
            continue
        f = min(cands, key=lambda f: abs(f.old_start - h.old_start))
        free.remove(f)
        f.kind, f.sites = h.kind, h.sites
        found.append(f)
    return found


def _skip(h: Hunk, reason: Reason, note: str) -> list[Site]:
    if h.sites:
        return [dataclasses.replace(s, skipped=reason, note=note) for s in h.sites]
    lines = h.lines()
    end = max(lines.start, lines.stop - 1)
    return [Site(h.file, lines.start, end, h.kind, "uncovered", reason, note)]


def _revert_cached(repo: Path, file: Path, old_starts: set[int] | None) -> None:
    staged, _ = parse_diff(git(repo, "diff", "--cached", "-U0", "--", file.as_posix()))
    picked = [h for h in staged if old_starts is None or h.old_start in old_starts]
    if picked:
        patch = build_patch(picked, renumber=False)
        git(repo, "apply", "-R", "--cached", "--unidiff-zero", "-", input=patch)


def _format(repo: Path, file: Path) -> None:
    staged, _ = parse_diff(git(repo, "diff", "--cached", "-U0", "--", file.as_posix()))
    ranges = [
        f"--lines={h.new_start}:{h.new_start + h.new_count - 1}"
        for h in staged
        if h.new_count
    ]
    if not ranges:
        return
    before = git_bytes(repo, "show", f":{file.as_posix()}")
    p = subprocess.run(
        ["clang-format", f"--assume-filename={repo / file}", *ranges],
        cwd=repo, check=True, capture_output=True, input=before,
    )
    if p.stdout != before:
        write_index(repo, file, p.stdout)


def _failing_files(repo: Path, graph: Path, files: list[Path]) -> tuple[set[Path], list[str]]:
    res = gate.run(graph, files, repo)
    if res.ok:
        return set(), []
    bad = {f for f in res.failed if f in files}
    unexplained = [f for f in res.failed if f not in files]
    if not unexplained:
        return bad, []
    for h in (f for f in files if gate.is_header(f) and f not in bad):
        if not gate.run(graph, [h], repo).ok:
            bad.add(h)
    return bad, [f"gate failure in {f} not attributed to a staged file" for f in unexplained]


def apply(repo: Path, plan: CommitPlan, graph: Path) -> CommitResult:
    notes: list[str] = []
    reverted: list[Site] = []
    selected = _match(plan.hunks, parse_diff(git(repo, "diff", "-U0", "HEAD"))[0])
    if len(selected) < len(plan.hunks):
        notes.append(f"{len(plan.hunks) - len(selected)} planned hunks no longer in the diff")
    if not selected:
        return CommitResult(None, reverted, notes)
    files = list(dict.fromkeys(h.file for h in selected))
    dirty = [Path(p) for p in git(repo, "diff", "--name-only", "HEAD").splitlines()]
    saved = {f: (repo / f).read_bytes() for f in dirty}
    try:
        git(repo, "apply", "--cached", "--unidiff-zero", "-", input=build_patch(selected))
        staged = {f: index_sha(repo, f) for f in files}
        gone: set[int] = set()
        for s in check_hunks(git(repo, "diff", "--cached", "-U0")):
            for h in selected:
                if h.file == s.file and s.line in h.old_lines() and id(h) not in gone:
                    gone.add(id(h))
                    reverted += _skip(h, Reason.COMMENT_STRANDED, s.text)
                    _revert_cached(repo, h.file, {h.old_start})
        if shutil.which("clang-format"):
            for f in files:
                _format(repo, f)
        else:
            notes.append("clang-format not on PATH; staged hunks left unformatted")
        left = [Path(p) for p in git(repo, "diff", "--cached", "--name-only").splitlines()]
        for f in dirty:
            (repo / f).write_bytes(git_bytes(repo, "show", f":{f.as_posix()}"))
        bad, why = _failing_files(repo, graph, left) if left else (set(), [])
        notes += why
        for f in sorted(bad):
            _revert_cached(repo, f, None)
            for h in selected:
                if h.file == f and id(h) not in gone:
                    gone.add(id(h))
                    reverted += _skip(h, Reason.GATE_FAILED, "")
        sha = None
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode:
            applied = []
            for h in selected:
                if id(h) not in gone:
                    applied += [s for s in h.sites if not any(s is a for a in applied)]
            body = f"Sites: {len(applied)}, skipped: {len(reverted)}"
            git(repo, "commit", "-q", "-F", "-", input=f"{plan.message}\n\n{body}\n")
            sha = git(repo, "rev-parse", "HEAD").strip()
    except BaseException:
        git(repo, "reset", "-q", "--", *(f.as_posix() for f in files))
        for f, content in saved.items():
            (repo / f).write_bytes(content)
        raise
    for f, content in saved.items():
        (repo / f).write_bytes(content)
    for f, before in staged.items():
        after = index_sha(repo, f)
        if after != before and not apply_to_worktree(repo, blob_patch(repo, f, before, after)):
            notes.append(f"{f}: could not mirror the commit into the working tree")
    return CommitResult(sha, reverted, notes)
