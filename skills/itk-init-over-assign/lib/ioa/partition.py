import dataclasses
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ioa import gate
from ioa.comments import check_hunks
from ioa.manifest import Manifest, Site
from ioa.patch import (
    Hunk,
    build_patch,
    diff,
    git,
    git_bytes,
    index_sha,
    mirror_format,
    parse_diff,
    reverse_bytes,
    reverse_in_worktree,
    write_index,
)
from ioa.skip import Reason
from ioa.stages import StageRecord, load, snapshot  # noqa: F401
from ioa.tidy import tool, widen_to_block

SUBJECTS = {
    "member-init": "STYLE: Initialize members in constructor initializer lists",
    "member-default-init": "STYLE: Give uninitialized members a default initializer",
    "local-init": "STYLE: Initialize locals at declaration instead of assigning",
    "local-const": "STYLE: Make initialized locals const where never mutated",
    "container-list-init": "STYLE: Replace push_back and index sequences with list initialization",
    "container-const": "STYLE: Make list-initialized containers const where never mutated",
    "itk-helpers": "STYLE: Use Filled, MakeFilled, and AllocateInitialized helpers",
    "itk-helpers-constexpr": "STYLE: Make Filled values with literal arguments constexpr",
    "narrow-scope": "STYLE: Declare variables in the narrowest scope that uses them",
    "narrow-init": "STYLE: Initialize narrowed locals at declaration instead of assigning",
    "narrow-const": "STYLE: Make narrowed locals const where never mutated",
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
        owners = [st for st in loaded if st.at(h)] or [st for st in loaded if st.by_text(h)]
        if owners:
            h.kind = owners[-1].record.kind
            h.sites = owners[-1].sites(h)
    _group_sites(hunks, loaded, rank, notes)
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


def _group_sites(hunks: list[Hunk], loaded, rank: dict[str, int], notes) -> None:
    """Join the hunks of each site group and give them all to the group's latest kind."""
    parent = list(range(len(hunks)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for st in loaded:
        for spans in st.groups():
            idx = [i for i, h in enumerate(hunks)
                   if any(f == h.file and sp.meets(h) for f, sp in spans)]
            for i in idx[1:]:
                parent[find(i)] = find(idx[0])
    members: dict[int, list[Hunk]] = {}
    for i, h in enumerate(hunks):
        h.group = find(i)
        members.setdefault(h.group, []).append(h)
    for group in members.values():
        kinds = {h.kind for h in group if h.kind}
        if len(group) < 2 or not kinds:
            continue
        last = max(kinds, key=rank.__getitem__)
        sites = list({id(s): s for h in group for s in h.sites}.values())
        for h in group:
            if h.kind and h.kind != last:
                notes[h.kind].append(
                    f"{h.file}:{h.old_start}: hunk moved to {last} with the rest of its site"
                )
            h.kind, h.sites = last, sites


def _site_group(h: Hunk, hunks: list[Hunk]) -> list[Hunk]:
    if h.group is None:
        return [h]
    return [g for g in hunks if g.group == h.group]


def _close_files(bad: set[Path], hunks: list[Hunk]) -> set[Path]:
    """Grow a set of reverted files until no site group straddles its edge."""
    bad = set(bad)
    grew = True
    while grew:
        grew = False
        for h in hunks:
            if h.file in bad:
                for g in _site_group(h, hunks):
                    if g.file not in bad:
                        bad.add(g.file)
                        grew = True
    return bad


def _norm(lines: list[str]) -> tuple[str, ...]:
    return tuple(" ".join(ln.split()) for ln in lines)


def _core(h: Hunk) -> tuple:
    """A hunk's key without whitespace and without lines that only realigned."""
    removed, added = h.removed, h.added
    if len(removed) == len(added):
        kept = [(r, a) for r, a in zip(_norm(removed), _norm(added)) if r != a]
        return (h.file, tuple(r for r, _ in kept), tuple(a for _, a in kept))
    return (h.file, _norm(removed), _norm(added))


def _match(plan_hunks: list[Hunk], fresh: list[Hunk]) -> list[Hunk]:
    """Relocate plan hunks in a fresh diff, since earlier commits shift lines.

    An earlier commit's formatting may have realigned a plan hunk's lines; such a hunk
    is found by its whitespace-free core, and pure realignment hunks next to a found
    hunk come along as spill.
    """
    free = list(fresh)
    found: list[Hunk] = []
    matched: list[Hunk] = []
    for key in (Hunk.key, _core):
        for h in plan_hunks:
            if any(h is m for m in matched):
                continue
            cands = [f for f in free if key(f) == key(h)]
            if not cands:
                continue
            f = min(cands, key=lambda f: abs(f.old_start - h.old_start))
            free.remove(f)
            f.kind, f.sites, f.group = h.kind, h.sites, h.group
            found.append(f)
            matched.append(h)
    grew = bool(found)
    while grew:
        grew = False
        for f in list(free):
            if _core(f)[1:] != ((), ()):
                continue
            if any(g.file == f.file and g.old_start - 1 <= f.old_start + f.old_count
                   and f.old_start - 1 <= g.old_start + g.old_count for g in found):
                free.remove(f)
                f.kind = found[0].kind
                found.append(f)
                grew = True
    return found


def _skip(h: Hunk, reason: Reason, note: str, done: list[Site]) -> list[Site]:
    if h.sites:
        fresh = [s for s in h.sites if not any(s is d for d in done)]
        done.extend(fresh)
        return [dataclasses.replace(s, skipped=reason, note=note) for s in fresh]
    lines = h.lines()
    end = max(lines.start, lines.stop - 1)
    return [Site(h.file, lines.start, end, h.kind, "uncovered", reason, note)]


def _revert_cached(repo: Path, file: Path, old_starts: set[int] | None,
                   notes: list[str] | None = None) -> bool:
    """Unstage the picked hunks of file; False when that failed and the whole file was reset."""
    staged, _ = parse_diff(diff(repo, "--cached", "-U0", "--", file.as_posix()))
    picked = [h for h in staged if old_starts is None or h.old_start in old_starts]
    if old_starts is None and picked:
        git(repo, "reset", "-q", "--", file.as_posix())
    elif picked:
        data = git_bytes(repo, "show", f":{file.as_posix()}")
        try:
            write_index(repo, file, reverse_bytes(data, picked))
        except ValueError as exc:
            git(repo, "reset", "-q", "--", file.as_posix())
            if notes is not None:
                notes.append(f"{file}: unstaging dropped hunks failed ({exc}); reset the file "
                             "to HEAD in the index")
            return False
    return True


def _format(repo: Path, file: Path, clang_format: str) -> list[tuple[int, int]]:
    """Format the staged hunks of file in the index; return the widened line ranges."""
    staged, _ = parse_diff(diff(repo, "--cached", "-U0", "--", file.as_posix()))
    before = git_bytes(repo, "show", f":{file.as_posix()}")
    lines = before.decode("utf-8", "surrogateescape").splitlines()
    spans = [
        widen_to_block(lines, h.new_start, h.new_start + h.new_count - 1)
        for h in staged
        if h.new_count
    ]
    if not spans:
        return []
    p = subprocess.run(
        [clang_format, "--fallback-style=none", f"--assume-filename={repo / file}",
         *(f"--lines={a}:{b}" for a, b in spans)],
        cwd=repo, check=True, capture_output=True, input=before,
    )
    if p.stdout != before:
        write_index(repo, file, p.stdout)
    return spans


def _clang_format() -> str | None:
    try:
        return tool("clang-format")
    except SystemExit:
        return None


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
    headers = [f for f in files if gate.is_header(f) and f not in bad] if unplaced else []
    if headers:
        batch = gate.run(graph, headers, repo)
        for h in headers:
            tus, _ = gate.expand([h], graph, repo)
            if h in batch.failed or any(t in batch.failed for t in tus):
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
    backup = snapshot(repo)
    git(repo, "update-ref", f"refs/ioa/backup/{commit_plan.kind}", backup)
    notes.append(f"backup-tree: {backup}")
    gone: list[Hunk] = []
    originals: list[Site] = []
    whole: set[Path] = set()

    def drop(hunks: list[Hunk], reason: Reason, note: str = "") -> None:
        for h in hunks:
            if not any(h is g for g in gone):
                gone.append(h)
                reverted.extend(_skip(h, reason, note, originals))

    try:
        git(repo, "apply", "--cached", "--unidiff-zero", "-", input=build_patch(selected))
        for s in check_hunks(diff(repo, "--cached", "-U0")):
            hits = [h for h in selected if h.file == s.file and s.line in h.old_lines()]
            if not hits:
                notes.append(f"{s.file}:{s.line}: stranded comment outside the plan: {s.text}")
            for h in hits:
                group = _site_group(h, selected)
                fell_back: set[Path] = set()
                for g in group:
                    if not any(g is x for x in gone) and g.file not in fell_back:
                        if not _revert_cached(repo, g.file, {g.old_start}, notes):
                            fell_back.add(g.file)
                if fell_back:
                    closed = _close_files(fell_back, selected)
                    for f in sorted(closed - fell_back):
                        _revert_cached(repo, f, None)
                    group += [x for x in selected
                              if x.file in closed and not any(x is y for y in group)]
                    notes.append("index revert fell back to HEAD; dropped every hunk of the site "
                                 "groups in " + ", ".join(str(f) for f in sorted(closed)))
                drop(group, Reason.COMMENT_STRANDED, s.text)
        unformatted = {f: index_sha(repo, f) for f in files}
        spans: dict[Path, list[tuple[int, int]]] = {}
        clang_format = _clang_format()
        if clang_format:
            for f in files:
                spans[f] = _format(repo, f, clang_format)
        else:
            notes.append("clang-format not found; staged hunks left unformatted")
        formatted = {f: index_sha(repo, f) for f in files}
        left = [Path(p) for p in diff(repo, "--cached", "--name-only").splitlines()]
        _sync_from_index(repo, dirty)
        bad, unplaced = _gate_failures(repo, graph, left) if left else (set(), [])
        bad = _close_files(bad, selected)
        if unplaced:
            notes += [f"gate failure in {f} not attributed to a staged file" for f in unplaced]
            for f in bad:
                _revert_cached(repo, f, None)
            _sync_from_index(repo, bad)
            rest = [f for f in left if f not in bad]
            if rest and not gate.run(graph, rest, repo).ok:
                notes.append("unattributed gate failure persists; reverted every staged file")
                bad |= set(rest)
        bad = _close_files(bad, selected)
        for f in sorted(bad):
            _revert_cached(repo, f, None)
            whole.add(f)
            drop([h for h in selected if h.file == f], Reason.GATE_FAILED)
        for f, content in saved.items():
            (repo / f).write_bytes(content)
        for f in files:
            try:
                reverse_in_worktree(repo, [h for h in gone if h.file == f])
            except ValueError as exc:
                (repo / f).write_bytes(git_bytes(repo, "show", f"{backup}:{f.as_posix()}"))
                notes.append(f"{f}: reverting dropped hunks failed ({exc}); restored the file "
                             f"from backup tree {backup}, so its dropped hunks stay unpartitioned")
            if f not in whole and unformatted[f] != formatted[f]:
                if not mirror_format(repo, f, unformatted[f], formatted[f], spans[f], clang_format):
                    notes.append(f"{f}: formatting reached another kind's lines; formatted them in place")
        sha = None
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode:
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
    return CommitResult(sha, reverted, notes)
