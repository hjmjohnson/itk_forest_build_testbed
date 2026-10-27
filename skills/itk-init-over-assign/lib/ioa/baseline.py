import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def forest_env(suffix: str | None) -> dict[str, str]:
    """The environment for kit tools, pinned to one forest; inherited overrides dropped."""
    env = {k: v for k, v in os.environ.items() if k not in ("FOREST", "BUILD_FOREST_ROOT")}
    if suffix:
        env["FOREST_REFERENCE_SUFFIX"] = suffix
    return env


def suffix_of(forest_name: str) -> str:
    return forest_name.removeprefix("build_forest-")


def matrix(kit: Path, *args: str, suffix: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(kit / "bin" / "run-matrix.sh"), *args],
        cwd=kit, capture_output=True, text=True, check=False, env=forest_env(suffix),
    )


def failed_tests(ctest_dir: Path) -> list[str]:
    log = ctest_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
    if not log.exists():
        return []
    names = {
        m.group(1).strip()
        for m in map(re.compile(r"^\d+:(.+)$").match, log.read_text().splitlines())
        if m
    }
    return sorted(names)


def ensure(coords, kit: Path) -> Path:
    path = (
        kit / ".devlocal" / "init-over-assign" / "baselines"
        / f"{coords.repo_slug}-{coords.sha}.json"
    )
    if path.exists():
        return path
    suffix = suffix_of(coords.forest_name)
    got = matrix(kit, "--ctest-dir", coords.repo_slug, suffix=suffix)
    if got.returncode != 0 or not got.stdout.strip():
        raise RuntimeError(f"run-matrix.sh --ctest-dir failed: {got.stderr.strip()}")
    ctest_dir = Path(got.stdout.strip().splitlines()[-1])
    log = ctest_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
    log.unlink(missing_ok=True)
    run = matrix(kit, "--run-ctest", coords.repo_slug, suffix=suffix)
    tokens = [t for t in run.stdout.split() if t.startswith("T:")]
    token = tokens[-1] if tokens else "no token"
    m = re.fullmatch(r"T:(\d+)/(\d+)", token)
    if not m or int(m.group(2)) == 0:
        raise RuntimeError(f"ctest did not run for {coords.repo_slug}: {token}")
    if m.group(1) != m.group(2) and not log.exists():
        raise RuntimeError(f"ctest reported failures ({token}) but wrote no {log}")
    record = {
        "repo": coords.repo_slug,
        "sha": coords.sha,
        "failed": failed_tests(ctest_dir),
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ctest_dir": str(ctest_dir),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path


def new_failures(baseline: Path, after: Path) -> list[str]:
    known = set(json.loads(baseline.read_text())["failed"])
    return sorted(set(json.loads(after.read_text())["failed"]) - known)
