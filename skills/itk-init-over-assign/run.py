#!/usr/bin/env python3
"""Run every init-over-assign stage on one forest consumer and write a reviewable branch."""
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
    ap.add_argument("repo", help="consumer name in the forest, e.g. BRAINSTools")
    ap.add_argument("--forest", default="itk-main", help="forest suffix (build_forest-<suffix>)")
    ap.add_argument("--stages", help="comma-separated stage kinds to run (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="preflight, then print the run's commands")
    return ap.parse_args(argv)


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
    forest = KIT / f"build_forest-{args.forest}"
    repo = forest / args.repo
    try:
        coords = preflight.check(repo, forest, KIT)
    except preflight.PreflightError as exc:
        return _refuse(exc.code, exc.message)
    print(report.coordinate_line(coords))
    now = datetime.now()
    branch = f"style-init-over-assign-{now:%Y%m%d}"
    run_dir = KIT / ".devlocal" / "init-over-assign" / f"{coords.repo_slug}-{now:%Y%m%d_%H%M}"
    if _git(repo, "branch", "--list", branch).stdout.strip():
        return _refuse("branch-exists", f"branch {branch} already exists in {repo}; delete or rename it")
    if args.dry_run:
        print(f"Branch: {branch} (not created)")
        for line in pipeline.dry_run_lines(selected, repo, coords.graph, run_dir):
            print(line)
        for line in pipeline.post_commands(repo, coords.repo_slug):
            print(line)
        return 0
    try:
        base = baseline.ensure(coords, KIT)
    except RuntimeError as exc:
        path = _write(repo, coords, [], [], None, None, f"{branch} (not created)", run_dir,
                      _error("baseline", exc), [])
        print(f"refused (baseline): {exc}; report: {path}", file=sys.stderr)
        return 2
    created = _git(repo, "checkout", "-q", "-b", branch)
    if created.returncode != 0:
        print(f"cannot create {branch}: {created.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"Branch: {branch}")
    return _run(repo, coords, selected, branch, run_dir, base)


def _run(repo, coords, selected, branch, run_dir, base) -> int:
    records, notes = [], []
    for kind, stage in selected:
        print(f"stage {kind}", flush=True)
        try:
            records.append(pipeline.run_stage(kind, stage, repo, coords.graph, run_dir, notes))
        except pipeline.StageFailed as exc:
            path = _write(repo, coords, [], _skips(records, []), None, None, branch, run_dir,
                          exc.failure, notes)
            print(f"stage {kind} failed; report: {path}", file=sys.stderr)
            return 1
    suffix = baseline.suffix_of(coords.forest_name)
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
        build = pipeline.full_build(KIT, coords.repo_slug, suffix, pc)
        step = "ctest"
        ctest = pipeline.run_ctest(KIT, coords.repo_slug, base, run_dir, suffix) if build.ok else None
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
