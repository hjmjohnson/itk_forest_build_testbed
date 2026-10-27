#!/usr/bin/env python3
"""Run every init-over-assign stage on one checkout and write a reviewable branch."""
import argparse
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from ioa import baseline, partition, pipeline, preflight, report  # noqa: E402

KIT = Path(__file__).resolve().parents[2]


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="run.py", description=__doc__)
    ap.add_argument("repo", nargs="?", help="consumer name in the forest, e.g. BRAINSTools")
    ap.add_argument("--forest", help="forest suffix (build_forest-<suffix>, default itk-main)")
    ap.add_argument("--repo", dest="standalone", type=Path, metavar="PATH",
                    help="standalone checkout (with --build; no forest)")
    ap.add_argument("--build", type=Path, metavar="DIR",
                    help="standalone build tree holding compile_commands.json")
    ap.add_argument("--upstream", help="standalone upstream tip <remote>/<branch> (default origin/main)")
    ap.add_argument("--stages", help="comma-separated stage kinds to run (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="preflight, then print the run's commands")
    args = ap.parse_args(argv)
    if args.standalone or args.build:
        if not (args.standalone and args.build):
            ap.error("--repo and --build go together")
        if args.repo or args.forest:
            ap.error("--repo/--build select standalone mode; drop <repo-name> and --forest")
        args.upstream = args.upstream or "origin/main"
    else:
        if not args.repo:
            ap.error("give <repo-name>, or --repo with --build")
        if args.upstream:
            ap.error("--upstream needs --repo and --build")
        args.forest = args.forest or "itk-main"
    return args


class ForestHarness:
    """Build and ctest through the forest's pixi tasks and run-matrix.sh."""

    def __init__(self, forest: Path, name: str):
        self.forest, self.repo = forest, forest / name

    def check(self):
        return preflight.check(self.repo, self.forest, KIT)

    def baseline(self, coords) -> Path:
        return baseline.ensure(coords, KIT)

    def build(self, coords, pc) -> report.Build:
        return pipeline.full_build(KIT, coords.repo_slug, baseline.suffix_of(coords.forest_name), pc)

    def ctest(self, coords, base: Path, run_dir: Path) -> report.Ctest:
        return pipeline.run_ctest(KIT, coords.repo_slug, base, run_dir,
                                  baseline.suffix_of(coords.forest_name))

    def post_commands(self, repo: Path, coords) -> list[str]:
        return pipeline.post_commands(repo, coords.repo_slug)


class StandaloneHarness:
    """Build with ninja and run ctest directly in the checkout's own build tree."""

    def __init__(self, repo: Path, build: Path, upstream: str):
        self.repo, self.build_dir, self.upstream = repo.resolve(), build.resolve(), upstream

    def check(self):
        return preflight.check_standalone(self.repo, self.build_dir, self.upstream, KIT)

    def baseline(self, coords) -> Path:
        return baseline.ensure_standalone(coords, KIT)

    def build(self, coords, pc) -> report.Build:
        return pipeline.full_build_standalone(coords.graph, pc)

    def ctest(self, coords, base: Path, run_dir: Path) -> report.Ctest:
        return pipeline.run_ctest_standalone(coords.graph, base, run_dir)

    def post_commands(self, repo: Path, coords) -> list[str]:
        return pipeline.post_commands_standalone(repo, coords.graph)


def _refuse(code: str, message: str) -> int:
    print(f"refused ({code}): {message}", file=sys.stderr)
    return 2


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def _error(step: str, exc: BaseException) -> report.Failure:
    frames = traceback.extract_tb(exc.__traceback__)
    where = f"\n  at {frames[-1].filename}:{frames[-1].lineno} in {frames[-1].name}" if frames else ""
    return report.Failure(step, [], None, f"{type(exc).__name__}: {exc}{where}")


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        selected = pipeline.select(args.stages.split(",") if args.stages else None)
    except ValueError as exc:
        return _refuse("bad-stages", str(exc))
    if args.standalone:
        harness = StandaloneHarness(args.standalone, args.build, args.upstream)
    else:
        harness = ForestHarness(KIT / f"build_forest-{args.forest}", args.repo)
    repo = harness.repo
    try:
        coords = harness.check()
    except preflight.PreflightError as exc:
        return _refuse(exc.code, exc.message)
    print(report.coordinate_line(coords))
    now = datetime.now()
    branch = preflight.run_branch(now)
    run_dir = KIT / ".devlocal" / "init-over-assign" / f"{coords.repo_slug}-{now:%Y%m%d_%H%M}"
    if _git(repo, "branch", "--list", branch).stdout.strip():
        return _refuse("branch-exists", f"branch {branch} already exists in {repo}; delete or rename it")
    if args.dry_run:
        print(f"Branch: {branch} (not created)")
        for line in pipeline.dry_run_lines(selected, repo, coords.graph, run_dir):
            print(line)
        for line in harness.post_commands(repo, coords):
            print(line)
        return 0
    notes = [coords.note] if coords.note else []
    try:
        built = harness.build(coords, pipeline.PreCommit("not run (baseline build)", True, []))
    except OSError as exc:
        built = report.Build("not run", False, f"{type(exc).__name__}: {exc}")
    if not built.ok:
        path = _write(repo, coords, [], [], None, None, f"{branch} (not created)", run_dir,
                      report.Failure("build-failed", [], None, built.detail), notes)
        print(f"refused (build-failed): the build before the baseline failed; report: {path}",
              file=sys.stderr)
        return 2
    notes.append(f"baseline build: rebuilt {coords.graph} at {coords.sha[:12]} "
                 "before the baseline ctest")
    try:
        base = harness.baseline(coords)
    except (RuntimeError, OSError) as exc:
        path = _write(repo, coords, [], [], None, None, f"{branch} (not created)", run_dir,
                      _error("baseline", exc), notes)
        print(f"refused (baseline): {exc}; report: {path}", file=sys.stderr)
        return 2
    created = _git(repo, "checkout", "-q", "-b", branch)
    if created.returncode != 0:
        print(f"cannot create {branch}: {created.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"Branch: {branch}")
    return _run(repo, coords, selected, branch, run_dir, base, harness, notes)


def _run(repo, coords, selected, branch, run_dir, base, harness, notes) -> int:
    records = []
    for kind, stage in selected:
        print(f"stage {kind}", flush=True)
        try:
            records.append(pipeline.run_stage(kind, stage, repo, coords.graph, run_dir, notes))
        except pipeline.StageFailed as exc:
            path = _write(repo, coords, [], _skips(records, []), None, None, branch, run_dir,
                          exc.failure, notes)
            print(f"stage {kind} failed; report: {path}", file=sys.stderr)
            return 1
    results, commits, build, ctest = [], [], None, None
    step = "partition.plan"
    try:
        plans = partition.plan(repo, records)
        for p in plans:
            step = f"partition.apply {p.kind}"
            r = partition.apply(repo, p, coords.graph)
            results.append(r)
            commits.append(pipeline.commit_row(repo, p, r))
        step = "pre-commit"
        pc = pipeline.pre_commit(repo)
        step = "build"
        build = harness.build(coords, pc)
        step = "ctest"
        ctest = harness.ctest(coords, base, run_dir) if build.ok else None
    except Exception as exc:
        path = _write(repo, coords, commits, _skips(records, results), build, ctest, branch,
                      run_dir, _error(step, exc), notes)
        print(f"{step} raised {type(exc).__name__}: {exc}; report: {path}", file=sys.stderr)
        return 1
    path = _write(repo, coords, commits, _skips(records, results), build, ctest, branch,
                  run_dir, None, notes)
    print(f"report: {path}")
    return 0 if build.ok and build.precommit_ok and ctest and ctest.ok else 1


def _skips(records, results) -> list:
    out = [s for r in records for s in r.manifest.skipped()]
    return out + [s for res in results for s in res.reverted]


def _write(repo, coords, commits, skips, build, ctest, branch, run_dir, failed, notes) -> Path:
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip() or "unknown"
    return report.write(
        KIT, coords, commits, skips, build, ctest,
        branch=branch, tip=tip, run_dir=run_dir, failed=failed, notes=notes,
    )


if __name__ == "__main__":
    sys.exit(main())
