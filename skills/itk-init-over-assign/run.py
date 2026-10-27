#!/usr/bin/env python3
"""Run every init-over-assign stage on one forest consumer and write a reviewable branch."""
import argparse
import os
import subprocess
import sys
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
    ap.add_argument("--dry-run", action="store_true", help="preflight, then print the stage commands")
    return ap.parse_args(argv)


def _refuse(code: str, message: str) -> int:
    print(f"refused ({code}): {message}", file=sys.stderr)
    return 2


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        selected = pipeline.select(args.stages.split(",") if args.stages else None)
    except ValueError as exc:
        return _refuse("bad-stages", str(exc))
    os.environ["FOREST_REFERENCE_SUFFIX"] = args.forest
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
    if args.dry_run:
        print(f"Branch: {branch} (not created)")
        for line in pipeline.dry_run_lines(selected, repo, coords.graph, run_dir):
            print(line)
        return 0
    if _git(repo, "branch", "--list", branch).stdout.strip():
        return _refuse("dirty-tree", f"branch {branch} already exists in {repo}; delete or rename it")
    try:
        base = baseline.ensure(coords, KIT)
    except RuntimeError as exc:
        print(f"baseline failed: {exc}", file=sys.stderr)
        return 1
    created = _git(repo, "checkout", "-q", "-b", branch)
    if created.returncode != 0:
        print(f"cannot create {branch}: {created.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"Branch: {branch}")
    return _run(repo, coords, selected, branch, run_dir, base)


def _run(repo, coords, selected, branch, run_dir, base) -> int:
    records = []
    for kind, stage in selected:
        print(f"stage {kind}", flush=True)
        try:
            records.append(pipeline.run_stage(kind, stage, repo, coords.graph, run_dir))
        except pipeline.StageFailed as exc:
            path = _write(repo, coords, [], _skips(records, []), None, None, branch, run_dir, exc.failure)
            print(f"stage {kind} failed; report: {path}", file=sys.stderr)
            return 1
    plans = partition.plan(repo, records)
    results = [(p, partition.apply(repo, p, coords.graph)) for p in plans]
    commits = [pipeline.commit_row(repo, p, r) for p, r in results]
    skips = _skips(records, [r for _, r in results])
    precommit = pipeline.pre_commit(repo)
    build = pipeline.full_build(KIT, coords.repo_slug, precommit)
    ctest = pipeline.run_ctest(KIT, coords.repo_slug, base, run_dir) if build.ok else None
    path = _write(repo, coords, commits, skips, build, ctest, branch, run_dir, None)
    print(f"report: {path}")
    return 0 if build.ok and ctest and ctest.ok else 1


def _skips(records, results) -> list:
    out = [s for r in records for s in r.manifest.skipped()]
    return out + [s for res in results for s in res.reverted]


def _write(repo, coords, commits, skips, build, ctest, branch, run_dir, failed) -> Path:
    tip = _git(repo, "rev-parse", "HEAD").stdout.strip() or "unknown"
    return report.write(
        KIT, coords, commits, skips, build, ctest,
        branch=branch, tip=tip, run_dir=run_dir, failed=failed,
    )


if __name__ == "__main__":
    sys.exit(main())
