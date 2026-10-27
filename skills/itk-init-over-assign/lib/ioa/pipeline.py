import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ioa import baseline, stages
from ioa.manifest import Manifest
from ioa.patch import DIFF_FLAGS, parse_diff
from ioa.report import Build, Commit, Ctest, Failure

SKILLS = Path(__file__).resolve().parents[3]
PATTERNS = SKILLS / "itk-mechanical-cleanup" / "patterns"
LOCAL_CLASSES = "assign,elem_diff,elem_zero,sized_ctor,stream_open,bool_branch,placeholder"
WARNING = re.compile(r"\bwarning:")
DIAG = re.compile(r"^(?P<file>[^\s:][^:]*):(?P<line>\d+):(?:\d+:)?\s*warning:\s*(?P<text>.*?)\s*$")

Cmd = list[str]
Ctx = dict[str, str]


def _py(script: str, *extra: str) -> Cmd:
    return ["{py}", str(SKILLS / script), "--graph", "{graph}", "--repo", "{repo}",
            "--manifest", "{manifest}", "--apply", *extra]


def _sh(pattern: str) -> Cmd:
    return ["bash", str(PATTERNS / pattern / "transform.sh"), "{repo}", "--apply",
            "--manifest", "{manifest}", "--graph", "{graph}"]


def _helpers(ctx: Ctx) -> list[tuple[Cmd, str]]:
    parts = [
        ("sizetype-filled", _py("itk-sizetype-filled/sizetype_filled.py")),
        ("allocate-initialized", _py("itk-allocate-initialized/allocate_initialized.py")),
        ("fillbuffer-over-iterate", _sh("fillbuffer-over-iterate")),
    ]
    return [(cmd, str(Path(ctx["manifest"]).with_name(f"itk-helpers.{name}.json")))
            for name, cmd in parts]


@dataclass(frozen=True)
class Stage:
    kind: str
    cmd: Cmd | Callable[[Ctx], list[tuple[Cmd, str]]]
    const_after: str | None


STAGES: list[Stage] = [
    Stage("member-init", _py("itk-member-init/member_init.py"), None),
    Stage("member-default-init", _sh("in-class-member-init"), None),
    Stage("local-init", [
        "{py}", str(SKILLS / "itk-declare-then-init" / "find_declare_then_init.py"),
        "--classes", LOCAL_CLASSES, "--graph", "{graph}", "--repo-root", "{repo}",
        "--apply", "--manifest", "{manifest}",
    ], "local-const"),
    Stage("container-list-init", _py("itk-container-list-init/list_init.py"), "container-const"),
    Stage("itk-helpers", _helpers, "itk-helpers-constexpr"),
    Stage("narrow-scope", _py("itk-narrow-scope/narrow_scope.py"), None),
]


def _const(kind: str, parent: str) -> Stage:
    cmd = _py("itk-const-promote/const_promote.py", "--only-from", "{dir}/" + f"{parent}.json",
              "--kind", kind)
    return Stage(kind, cmd, None)


def select(names: list[str] | None) -> list[tuple[str, Stage]]:
    """The stages to run, in order, with each const stage after its parent."""
    known = {s.kind for s in STAGES} | {s.const_after for s in STAGES if s.const_after}
    unknown = sorted(set(names or []) - known)
    if unknown:
        raise ValueError(f"unknown stage kind(s): {', '.join(unknown)}")
    out: list[tuple[str, Stage]] = []
    for s in STAGES:
        if names is None or s.kind in names:
            out.append((s.kind, s))
        if s.const_after and (names is None or s.const_after in names):
            if names is not None and s.kind not in names:
                raise ValueError(f"{s.const_after} needs {s.kind} in the same run")
            out.append((s.const_after, _const(s.const_after, s.kind)))
    return out


def commands(stage: Stage, ctx: Ctx) -> list[tuple[Cmd, str]]:
    """Concrete (argv, manifest) pairs for one stage."""
    pairs = stage.cmd(ctx) if callable(stage.cmd) else [(stage.cmd, ctx["manifest"])]
    return [([a.format(**{**ctx, "manifest": m}) for a in cmd], m) for cmd, m in pairs]


def context(kind: str, repo: Path, graph: Path, run_dir: Path) -> Ctx:
    mdir = run_dir / "manifests"
    return {
        "py": sys.executable, "repo": str(repo), "graph": str(graph), "dir": str(mdir),
        "manifest": str(mdir / f"{kind}.json"),
    }


class StageFailed(Exception):
    def __init__(self, failure: Failure):
        super().__init__(f"stage {failure.kind} exited {failure.returncode}")
        self.failure = failure


def _merge(kind: str, parts: list[str], dest: Path, notes: list[str]) -> Manifest:
    merged = Manifest(kind)
    for p in map(Path, parts):
        if p.exists():
            part = Manifest.read(p)
            merged.sites += part.sites
            merged.partners += part.partners
            merged.notes += part.notes
            notes += [f"{kind}: {n}" for n in part.notes]
        else:
            notes.append(f"{kind}: no manifest written at {p}; counted as zero sites")
    merged.write(dest)
    return merged


def run_stage(
    kind: str, stage: Stage, repo: Path, graph: Path, run_dir: Path,
    notes: list[str] | None = None,
) -> stages.StageRecord:
    ctx = context(kind, repo, graph, run_dir)
    Path(ctx["dir"]).mkdir(parents=True, exist_ok=True)
    before = stages.snapshot(repo)
    pairs = commands(stage, ctx)
    env = {**os.environ, "PYTHON": sys.executable}
    for argv, _ in pairs:
        done = subprocess.run(argv, cwd=repo, capture_output=True, text=True, check=False, env=env)
        if done.returncode != 0:
            tail = "\n".join((done.stderr or "").splitlines()[-20:])
            raise StageFailed(Failure(kind, argv, done.returncode, tail))
    after = stages.snapshot(repo)
    manifest = _merge(kind, [m for _, m in pairs], Path(ctx["manifest"]),
                      notes if notes is not None else [])
    rec = stages.StageRecord(kind, manifest, before, after)
    log = run_dir / "snapshots.json"
    seen = json.loads(log.read_text()) if log.exists() else []
    seen.append({"kind": kind, "tree_before": before, "tree_after": after})
    log.write_text(json.dumps(seen, indent=2) + "\n")
    return rec


def dry_run_lines(selected: list[tuple[str, Stage]], repo: Path, graph: Path, run_dir: Path) -> list[str]:
    return [
        f"{kind}: {shlex.join(argv)}"
        for kind, st in selected
        for argv, _ in commands(st, context(kind, repo, graph, run_dir))
    ]


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return done.stdout


def gate_text(result) -> str:
    counts = Counter(str(s.skipped) for s in result.reverted)
    return ", ".join(f"{n} {r}" for r, n in sorted(counts.items())) or "pass"


def commit_row(repo: Path, plan, result) -> Commit:
    files = _git(repo, "show", "--name-only", "--format=", result.sha).split() if result.sha else []
    applied = sum(len(m.applied()) for m in plan.manifests)
    return Commit(result.sha, plan.kind, files, max(0, applied - len(result.reverted)),
                  gate_text(result), [*plan.notes, *result.notes])


def leftover(repo: Path) -> list[str]:
    """Working-tree changes against HEAD that no commit took."""
    hunks, skipped = parse_diff(_git(repo, "diff", *DIFF_FLAGS, "-U0", "HEAD"))
    return [f"{h.file}:{h.old_start} (-{h.old_count} +{h.new_count})" for h in hunks] + [
        f"{f}: added or deleted file" for f in skipped
    ]


@dataclass
class PreCommit:
    status: str
    ok: bool
    changed: list[str]


def dirty(repo: Path) -> list[str]:
    return sorted(_dirty(repo))


def _dirty(repo: Path) -> set[str]:
    out = _git(repo, "status", "--porcelain", "--untracked-files=no")
    return {ln[3:] for ln in out.splitlines() if len(ln) > 3}


def pre_commit(repo: Path) -> PreCommit:
    """Run the hooks, then restore any file they rewrote so the build sees the branch tip."""
    if not (repo / ".pre-commit-config.yaml").exists():
        return PreCommit("no .pre-commit-config.yaml", True, [])
    before = _dirty(repo)
    done = subprocess.run(["pre-commit", "run", "--all-files"], cwd=repo,
                          capture_output=True, text=True, check=False)
    changed = sorted(_dirty(repo) - before)
    if changed:
        _git(repo, "checkout", "--", *changed)
    if done.returncode == 0 and not changed:
        return PreCommit("passed", True, [])
    failed = [ln for ln in (done.stdout or "").splitlines() if ln.rstrip().endswith("Failed")]
    return PreCommit("FAILED: " + ("; ".join(failed) or f"exit {done.returncode}"), False, changed)


def post_commands(repo: Path, repo_name: str) -> list[str]:
    kit_matrix = "bash bin/run-matrix.sh"
    return [
        f"pre-commit: (cd {shlex.quote(str(repo))} && pre-commit run --all-files)",
        f"build: pixi run build-{repo_name}",
        f"build: {kit_matrix} --check-artifact {repo_name}",
        f"ctest: {kit_matrix} --run-ctest {repo_name}",
    ]


def post_commands_standalone(repo: Path, build: Path, jobs: int | None = None) -> list[str]:
    return [
        f"pre-commit: (cd {shlex.quote(str(repo))} && pre-commit run --all-files)",
        f"build: {shlex.join(['ninja', '-C', str(build)])}",
        f"ctest: {shlex.join(baseline.ctest_argv(build, jobs))}",
    ]


def warning_keys(log: str, repo: Path | None, base: Path | None) -> list[str]:
    """`file:line: warning: text` per compiler warning, with paths relative to repo."""
    out: dict[str, None] = {}
    for ln in log.splitlines():
        m = DIAG.match(ln.strip())
        if not m:
            continue
        path = Path(m["file"])
        if base is not None and not path.is_absolute():
            path = base / path
        if repo is not None and path.is_absolute():
            full, root = path.resolve(), repo.resolve()
            if full.is_relative_to(root):
                path = full.relative_to(root)
        out[f"{path.as_posix()}:{m['line']}: warning: {m['text']}"] = None
    return list(out)


def _unlined(key: str) -> str:
    return re.sub(r":\d+: warning: ", ": warning: ", key, count=1)


def new_warnings(before: list[str], after: list[str]) -> list[str]:
    """Rebuild warnings whose (file, text) the baseline lacks; a shifted line is not new."""
    seen = {_unlined(w) for w in before}
    return [w for w in after if _unlined(w) not in seen]


HUNK_SLACK = 2


def changed_ranges(repo: Path, base: str) -> dict[str, list[tuple[int, int]]]:
    """New-side line ranges of `git diff <base>..HEAD`, widened by HUNK_SLACK."""
    hunks, _ = parse_diff(_git(repo, "diff", *DIFF_FLAGS, "-U0", f"{base}..HEAD"))
    out: dict[str, list[tuple[int, int]]] = {}
    for h in hunks:
        last = h.new_start + max(h.new_count, 1) - 1
        out.setdefault(h.file.as_posix(), []).append((h.new_start - HUNK_SLACK, last + HUNK_SLACK))
    return out


def classify_warnings(repo: Path, base: str, before: list[str],
                      after: list[str]) -> tuple[list[str], list[str]]:
    """(new, pre-existing in touched files): new means inside a changed hunk and not in the
    baseline by file and text."""
    ranges = changed_ranges(repo, base)
    fresh = set(new_warnings(before, after))
    new, touched = [], []
    for w in after:
        m = re.match(r"(.*):(\d+): warning: ", w)
        if not m or m[1] not in ranges:
            continue
        inside = any(a <= int(m[2]) <= b for a, b in ranges[m[1]])
        if inside and w in fresh:
            new.append(w)
        elif not inside:
            touched.append(w)
    return new, touched


def _built(done: subprocess.CompletedProcess, label: str, pc: PreCommit,
           repo: Path | None = None, base: Path | None = None) -> Build:
    log = (done.stdout or "") + (done.stderr or "")
    warnings = list(dict.fromkeys(ln.strip() for ln in log.splitlines() if WARNING.search(ln)))
    build = Build(pc.status, True, "", warnings, pc.ok, pc.changed,
                  warning_keys(log, repo, base))
    if done.returncode != 0:
        build.ok, build.detail = False, f"{label} exited {done.returncode}\n{failure_excerpt(log)}"
    return build


def failure_excerpt(log: str, context: int = 20) -> str:
    """Every FAILED: line with the lines before it, then the log's last lines."""
    lines = log.splitlines()
    keep: set[int] = set(range(max(0, len(lines) - context), len(lines)))
    for i, ln in enumerate(lines):
        if ln.startswith("FAILED:"):
            keep.update(range(max(0, i - context), i + 1))
    out: list[str] = []
    for i in sorted(keep):
        if out and i - 1 not in keep:
            out.append("...")
        out.append(lines[i])
    return "\n".join(out)


def full_build(kit: Path, repo_name: str, suffix: str, pc: PreCommit,
               repo: Path | None = None, graph: Path | None = None) -> Build:
    done = subprocess.run(["pixi", "run", f"build-{repo_name}"], cwd=kit,
                          capture_output=True, text=True, check=False,
                          env=baseline.forest_env(suffix))
    build = _built(done, f"pixi run build-{repo_name}", pc, repo, graph)
    if build.ok and baseline.matrix(kit, "--check-artifact", repo_name, suffix=suffix).returncode != 0:
        build.ok, build.detail = False, f"artifact check failed for {repo_name}"
    return build


def full_build_standalone(build: Path, pc: PreCommit, repo: Path | None = None) -> Build:
    argv = ["ninja", "-C", str(build)]
    done = subprocess.run(argv, cwd=build, capture_output=True, text=True, check=False,
                          env=baseline.forest_env(None))
    return _built(done, shlex.join(argv), pc, repo, build)


def run_ctest(kit: Path, repo_name: str, base: Path, run_dir: Path, suffix: str) -> Ctest:
    where = baseline.matrix(kit, "--ctest-dir", repo_name, suffix=suffix).stdout.strip().splitlines()
    if not where:
        return Ctest(False, "no ctest directory", [], base)
    return _compare(Path(where[-1]), base, run_dir, lambda: baseline.last_token(
        baseline.matrix(kit, "--run-ctest", repo_name, suffix=suffix).stdout))


def run_ctest_standalone(build: Path, base: Path, run_dir: Path, jobs: int | None = None) -> Ctest:
    return _compare(build, base, run_dir, lambda: baseline.run_ctest(build, jobs))


def _compare(ctest_dir: Path, base: Path, run_dir: Path, run: Callable[[], str]) -> Ctest:
    log = ctest_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
    log.unlink(missing_ok=True)
    token = run()
    m = re.fullmatch(r"T:(\d+)/(\d+)", token)
    if not m or int(m.group(2)) == 0:
        return Ctest(False, token, [], base, "ctest did not run")
    if m.group(1) != m.group(2) and not log.exists():
        return Ctest(False, token, [], base, f"failures reported but no {log}")
    after = run_dir / "ctest-after.json"
    after.parent.mkdir(parents=True, exist_ok=True)
    after.write_text(json.dumps({"failed": baseline.failed_tests(ctest_dir)}, indent=2) + "\n")
    new = baseline.new_failures(base, after)
    return Ctest(not new, token, new, base)
