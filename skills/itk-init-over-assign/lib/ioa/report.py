import shlex
import subprocess
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ioa.manifest import Site


@dataclass
class Commit:
    sha: str | None
    kind: str
    files: list[str]
    sites: int
    gate: str


@dataclass
class Build:
    precommit: str
    ok: bool
    detail: str = ""
    warnings: list[str] = field(default_factory=list)
    precommit_ok: bool = True
    precommit_changed: list[str] = field(default_factory=list)


@dataclass
class Ctest:
    ok: bool
    token: str
    new: list[str] = field(default_factory=list)
    baseline: Path | None = None
    note: str = ""


@dataclass
class Failure:
    """A stage that exited non-zero, or a step that raised (returncode None)."""

    kind: str
    argv: list[str]
    returncode: int | None
    stderr_tail: str


def _standalone(coords) -> bool:
    return coords.forest_name == "standalone"


def coordinate_line(coords) -> str:
    if _standalone(coords):
        return (
            f"Repo: {coords.repo_slug} ({coords.sha[:12]}) | "
            f"Standalone: {coords.repo}, build {coords.graph}"
        )
    return (
        f"Repo: {coords.repo_slug} ({coords.sha[:12]}) | "
        f"Forest: {coords.forest_name} | ITK: {coords.itk_version}"
    )


def _forest_local_lines(coords) -> list[str]:
    local = getattr(coords, "forest_local", [])
    if not local:
        return []
    return ["", "Forest-local commits (drop before opening the PR):", "",
            *(f"- {t}" for t in local)]


def _wrap(text: str) -> str:
    return textwrap.fill(text, 80, break_on_hyphens=False, break_long_words=False)


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "none"


def disjoint(commits: list[Commit]) -> list[Commit]:
    """Commits sharing no file with any other commit."""
    live = [c for c in commits if c.sha]
    return [
        c for c in live
        if not any(set(c.files) & set(o.files) for o in live if o is not c)
    ]


def _skip_section(skips: list[Site]) -> list[str]:
    if not skips:
        return ["No site was skipped."]
    out: list[str] = []
    for reason in sorted({str(s.skipped) for s in skips}):
        group = sorted(
            (s for s in skips if str(s.skipped) == reason),
            key=lambda s: (str(s.file), s.start),
        )
        out += ["", f"### {reason} ({len(group)})", ""]
        for s in group:
            note = f" ({s.note})" if s.note else ""
            out.append(f"- {s.file}:{s.start} {s.kind}/{s.cls}{note}")
    return out[1:]


def _build_lines(build: Build | None, coords) -> list[str]:
    if build is None:
        return ["Not run."]
    label = "Full build" if _standalone(coords) else "Full build and artifact check"
    out = [
        f"- pre-commit: {build.precommit}",
        f"- {label}: {'pass' if build.ok else 'FAIL'}",
    ]
    if build.precommit_changed:
        out += ["", "### pre-commit changed files (not committed)", ""]
        out += [f"- {f}" for f in build.precommit_changed]
        out += ["", _wrap("These were restored to the branch tip before the build.")]
    if build.detail:
        out += ["", "```text", build.detail.rstrip(), "```"]
    if build.warnings:
        out += ["", "Warnings in the rebuild log:", ""]
        out += [f"> {w}" for w in build.warnings]
    return out


def _ctest_lines(ctest: Ctest | None) -> list[str]:
    if ctest is None:
        return ["Not run."]
    out = [f"- Result: {ctest.token}"]
    out.append(f"- Baseline: {ctest.baseline}" if ctest.baseline else "- Baseline: none")
    if ctest.note:
        out.append(f"- Note: {ctest.note}")
    if ctest.new:
        out.append("- New failures against the baseline:")
        out += [f"  - `{t}`" for t in ctest.new]
    elif ctest.ok:
        out.append("- No new failures against the baseline.")
    return out


def _kit_commit(kit: Path) -> str:
    done = subprocess.run(
        ["git", "-C", str(kit), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else "unknown"


def _failure_lines(failed: Failure) -> list[str]:
    if failed.kind == "build-failed":
        head = ["## Baseline build failed", "", _wrap(
            "The build before the baseline ctest failed (build-failed); no branch "
            "was created and no stage ran.")]
        body = [failed.stderr_tail.rstrip()]
    elif failed.returncode is None:
        head = ["## Run error", "", _wrap(
            f"Step `{failed.kind}` raised; the run stopped and left the branch "
            "and working tree in place.")]
        body = [failed.stderr_tail.rstrip()]
    else:
        head = ["## Failing stage", "", _wrap(
            f"Stage `{failed.kind}` exited {failed.returncode}; the run stopped "
            "and left the branch and working tree in place.")]
        body = [shlex.join(failed.argv), failed.stderr_tail.rstrip()]
    return ["", *head, "", "```text", *body, "```"]


def _report_text(coords, commits, skips, build, ctest, branch, tip, run_dir, failed, notes) -> str:
    lines = [
        f"# init-over-assign: {coords.repo_slug} {run_dir.name.rsplit('-', 1)[-1]}",
        "",
        coordinate_line(coords),
        *_forest_local_lines(coords),
        "",
        f"- Branch: `{branch}`",
        f"- Tip: `{tip}`",
        f"- Run directory: {run_dir}",
    ]
    if failed:
        lines += _failure_lines(failed)
    lines += ["", "## Commits", ""]
    if commits:
        lines += ["| SHA | Kind | Files | Sites | Gate |", "|---|---|---|---|---|"]
        lines += [
            f"| `{_short(c.sha)}` | {c.kind} | {len(c.files)} | {c.sites} | {c.gate} |"
            for c in commits
        ]
    else:
        lines.append("No commits.")
    alone = disjoint(commits)
    lines += ["", "## Disjoint commits", ""]
    lines.append(_wrap("Disjoint from every other commit (candidates for separate PRs):"))
    lines += [f"- `{_short(c.sha)}` {c.kind}" for c in alone] or ["- none"]
    lines += ["", "## Skip list", "", *_skip_section(skips)]
    lines += ["", "## Build", "", *_build_lines(build, coords)]
    lines += ["", "## ctest", "", *_ctest_lines(ctest)]
    if notes:
        lines += ["", "## Notes", "", *(f"- {n}" for n in notes)]
    return "\n".join(lines) + "\n"


def _pr_body(kit, coords, commits, skips, build, ctest, run_dir) -> str:
    live = [c for c in commits if c.sha]
    summary = _wrap(
        f"Initialize variables at declaration, in constructor initializer lists, "
        f"and in the narrowest scope that uses them across {coords.repo_slug}, "
        f"in {len(live)} commits with one refactor kind each."
    )
    reasons = Counter(str(s.skipped) for s in skips)
    changed = ["| Kind | Commit | Sites |", "|---|---|---|"]
    changed += [f"| {c.kind} | `{_short(c.sha)}` | {c.sites} |" for c in live]
    left = [f"- `{r}`: {n}" for r, n in sorted(reasons.items())] or ["- none"]
    tests = [
        f"- pre-commit: {build.precommit if build else 'not run'}"
        + (f"; changed and restored: {', '.join(build.precommit_changed)}"
           if build and build.precommit_changed else ""),
        ("- Full build with ninja in the standalone build tree: " if _standalone(coords)
         else f"- Full build in {coords.forest_name}: ")
        + ("not run" if build is None else "pass" if build.ok else "FAIL"),
        f"- ctest: {ctest.token if ctest else 'not run'}"
        + (f", new failures: {', '.join(ctest.new)}" if ctest and ctest.new else "")
        + (", no new failures against the base commit" if ctest and ctest.ok else ""),
    ]
    disclosure = _wrap(
        "Claude Code's itk-init-over-assign skill produced this branch unattended: "
        "it ran each refactor stage over the working tree, compiled every touched "
        "translation unit, and split the diff into one commit per kind. A human "
        "must review every commit before this pull request is marked ready."
    )
    baseline = ctest.baseline if ctest else None
    return "\n".join([
        summary,
        "",
        "<details>",
        "<summary>What changed, and what was left alone</summary>",
        "",
        *changed,
        "",
        "Sites left alone, by reason:",
        "",
        *left,
        "",
        "</details>",
        "",
        "<details>",
        "<summary>Testing and AI disclosure</summary>",
        "",
        *tests,
        "",
        disclosure,
        "",
        "</details>",
        "",
        "<!--",
        f"provenance: itk-init-over-assign {run_dir.name}",
        f"kit_commit: {_kit_commit(kit)}",
        f"run_dir: {run_dir}",
        f"baseline: {baseline}",
        f"base_sha: {coords.sha}",
        *(
            ["forest_local: the base carries these forest-local commits; drop them before "
             "opening the PR: " + "; ".join(coords.forest_local)]
            if getattr(coords, "forest_local", None) else []
        ),
        "-->",
        "",
    ])


def write(
    kit: Path, coords, commits: list[Commit], skips: list[Site],
    build: Build | None, ctest: Ctest | None, *,
    branch: str, tip: str, run_dir: Path, failed: Failure | None = None,
    notes: list[str] | None = None,
) -> Path:
    path = run_dir.parent / f"{run_dir.name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_report_text(
        coords, commits, skips, build, ctest, branch, tip, run_dir, failed, notes or []
    ))
    body = kit / ".devlocal" / "pr-bodies" / f"{coords.repo_slug}-init-over-assign.md"
    body.parent.mkdir(parents=True, exist_ok=True)
    body.write_text(_pr_body(kit, coords, commits, skips, build, ctest, run_dir))
    return path
