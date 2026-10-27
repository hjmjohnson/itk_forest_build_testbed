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
    diff,
    git,
    git_bytes,
    index_sha,
    parse_diff,
    reverse_in_worktree,
    write_index,
)
from ioa.skip import Reason
from ioa.stages import StageRecord, load, snapshot  # noqa: F401

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
    manifests: list[Manifest] = field(default_factory=list)


@dataclass
class CommitResult:
    sha: str | None
    reverted: list[Site]
    notes: list[str] = field(default_factory=list)


def plan(repo: Path, stages: list[StageRecord]) -> list[CommitPlan]:
    for rec in stages:
        if rec.kind not in SUBJECTS:
            raise ValueError(f"unknown transform kind: {rec.kind}")
    order = [k for k in SUBJECTS if any(r.kind == k for r in stages)]
    if not order:
        return []
    rank = {k: i for i, k in enumerate(order)}
    loaded = sorted(
        (load(repo, r) for r in stages), key=lambda s: rank[s.record.kind]
    )
    hunks, skipped = parse_diff(diff(repo, "-U0", "HEAD"))
    notes: dict[str, list[str]] = {k: [] for k in order}
    for h in hunks:
        owners = [st for st in loaded if st.owns(h)]
        if owners:
            h.kind = owners[-1].record.kind
            h.sites = owners[-1].sites(h)
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
    plans = [
        CommitPlan(
            k, SUBJECTS[k], [h for h in hunks if h.kind == k], notes[k],
            [r.manifest for r in stages if r.kind == k],
        )
        for k in order
        if any(h.kind == k for h in hunks)
    ]
    if plans:
        plans[0].notes += [f"{f}: added or deleted file left out" for f in skipped]
    return plans


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
    staged, _ = parse_diff(diff(repo, "--cached", "-U0", "--", file.as_posix()))
    picked = [h for h in staged if old_starts is None or h.old_start in old_starts]
    if picked:
        patch = build_patch(picked, renumber=False)
        git(repo, "apply", "-R", "--cached", "--unidiff-zero", "-", input=patch)


def _format(repo: Path, file: Path) -> None:
    staged, _ = parse_diff(diff(repo, "--cached", "-U0", "--", file.as_posix()))
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


def _sync_from_index(repo: Path, files) -> None:
    for f in files:
        (repo / f).write_bytes(git_bytes(repo, "show", f":{f.as_posix()}"))


def _gate_failures(repo: Path, graph: Path, files: list[Path]) -> tuple[set[Path], list[Path]]:
    """Staged files the gate blames, and failures it could not place on one."""
    res = gate.run(graph, files, repo)
    if res.ok:
        return set(), []
    bad = {f for f in res.failed if f in files}
    unplaced = [f for f in res.failed if f not in files]
    if unplaced:
        for h in (f for f in files if gate.is_header(f) and f not in bad):
            if not gate.run(graph, [h], repo).ok:
                bad.add(h)
    return bad, unplaced


def apply(repo: Path, commit_plan: CommitPlan, graph: Path) -> CommitResult:
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode:
        raise RuntimeError(f"{repo}: index has staged changes; apply needs a clean index")
    notes: list[str] = []
    reverted: list[Site] = []
    selected = _match(commit_plan.hunks, parse_diff(diff(repo, "-U0", "HEAD"))[0])
    if len(selected) < len(commit_plan.hunks):
        notes.append(f"{len(commit_plan.hunks) - len(selected)} planned hunks no longer in the diff")
    if not selected:
        return CommitResult(None, reverted, notes)
    files = list(dict.fromkeys(h.file for h in selected))
    dirty = [Path(p) for p in diff(repo, "--name-only", "HEAD").splitlines()]
    saved = {f: (repo / f).read_bytes() for f in dirty}
    notes.append(f"backup-tree: {snapshot(repo)}")
    gone: list[Hunk] = []
    whole: set[Path] = set()

    def drop(hunks: list[Hunk], reason: Reason, note: str = "") -> None:
        for h in hunks:
            if not any(h is g for g in gone):
                gone.append(h)
                reverted.extend(_skip(h, reason, note))

    try:
        git(repo, "apply", "--cached", "--unidiff-zero", "-", input=build_patch(selected))
        for s in check_hunks(diff(repo, "--cached", "-U0")):
            hits = [h for h in selected if h.file == s.file and s.line in h.old_lines()]
            if not hits:
                notes.append(f"{s.file}:{s.line}: stranded comment outside the plan: {s.text}")
            for h in hits:
                if not any(h is g for g in gone):
                    _revert_cached(repo, h.file, {h.old_start})
                drop([h], Reason.COMMENT_STRANDED, s.text)
        unformatted = {f: index_sha(repo, f) for f in files}
        if shutil.which("clang-format"):
            for f in files:
                _format(repo, f)
        else:
            notes.append("clang-format not on PATH; staged hunks left unformatted")
        formatted = {f: index_sha(repo, f) for f in files}
        left = [Path(p) for p in diff(repo, "--cached", "--name-only").splitlines()]
        _sync_from_index(repo, dirty)
        bad, unplaced = _gate_failures(repo, graph, left) if left else (set(), [])
        if unplaced:
            notes += [f"gate failure in {f} not attributed to a staged file" for f in unplaced]
            for f in bad:
                _revert_cached(repo, f, None)
            _sync_from_index(repo, bad)
            rest = [f for f in left if f not in bad]
            if rest and not gate.run(graph, rest, repo).ok:
                notes.append("unattributed gate failure persists; reverted every staged file")
                bad |= set(rest)
        for f in sorted(bad):
            _revert_cached(repo, f, None)
            whole.add(f)
            drop([h for h in selected if h.file == f], Reason.GATE_FAILED)
        sha = None
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode:
            originals = [s for h in gone for s in h.sites]
            applied = [
                s for m in commit_plan.manifests for s in m.applied()
                if not any(s is o for o in originals)
            ]
            body = f"Sites: {len(applied)}, skipped: {len(reverted)}"
            git(repo, "commit", "-q", "-F", "-", input=f"{commit_plan.message}\n\n{body}\n")
            sha = git(repo, "rev-parse", "HEAD").strip()
    except BaseException:
        git(repo, "reset", "-q", "--", *(f.as_posix() for f in files))
        for f, content in saved.items():
            (repo / f).write_bytes(content)
        raise
    for f, content in saved.items():
        (repo / f).write_bytes(content)
    for f in files:
        reverse_in_worktree(repo, [h for h in gone if h.file == f])
        if f in whole or unformatted[f] == formatted[f]:
            continue
        if not apply_to_worktree(repo, blob_patch(repo, f, unformatted[f], formatted[f])):
            raise RuntimeError(f"{f}: could not mirror clang-format into the working tree")
    return CommitResult(sha, reverted, notes)
