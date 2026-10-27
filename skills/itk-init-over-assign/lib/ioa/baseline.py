import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _matrix(kit: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(kit / "bin" / "run-matrix.sh"), *args],
        cwd=kit, capture_output=True, text=True, check=False,
    )


def failed_tests(ctest_dir: Path) -> list[str]:
    log = ctest_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
    if not log.exists():
        return []
    names = {
        line.split(":", 1)[1].strip()
        for line in log.read_text().splitlines()
        if ":" in line
    }
    return sorted(names)


def ensure(coords, kit: Path) -> Path:
    path = (
        kit / ".devlocal" / "init-over-assign" / "baselines"
        / f"{coords.repo_slug}-{coords.sha}.json"
    )
    if path.exists():
        return path
    got = _matrix(kit, "--ctest-dir", coords.repo_slug)
    if got.returncode != 0 or not got.stdout.strip():
        raise RuntimeError(f"run-matrix.sh --ctest-dir failed: {got.stderr.strip()}")
    ctest_dir = Path(got.stdout.strip().splitlines()[-1])
    _matrix(kit, "--run-ctest", coords.repo_slug)
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
