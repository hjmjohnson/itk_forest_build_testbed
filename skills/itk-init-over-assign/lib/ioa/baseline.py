import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


TOOLCHAIN_VARS = {
    "CC", "CXX", "LD", "AR", "RANLIB", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
    "LIBRARY_PATH", "CPATH", "CMAKE_PREFIX_PATH", "CONDA_BUILD_SYSROOT",
}
HOST_TOOLS = ("ninja", "ctest", "cmake", "pre-commit")


def _under(path: str, prefix: str) -> bool:
    return Path(path).is_relative_to(prefix) if path and Path(path).is_absolute() else False


def host_env(env: dict[str, str]) -> dict[str, str]:
    """env without the pixi/conda toolchain, so a standalone build links the host's libraries.

    CONDA_PREFIX stays, so ioa.tidy.tool still finds the clang tools by absolute path.
    """
    prefix = env.get("CONDA_PREFIX", "")
    out = {
        k: v for k, v in env.items()
        if k not in TOOLCHAIN_VARS and not k.startswith("PIXI_")
        and not (k.startswith("CONDA_") and k != "CONDA_PREFIX")
        and not (k == "SDKROOT" and prefix and _under(v, prefix))
    }
    if prefix and "PATH" in out:
        out["PATH"] = os.pathsep.join(p for p in out["PATH"].split(os.pathsep) if not _under(p, prefix))
    for name in HOST_TOOLS:
        found = shutil.which(name, path=env.get("PATH"))
        if found and not shutil.which(name, path=out.get("PATH", "")):
            out["PATH"] = os.pathsep.join(filter(None, [out.get("PATH", ""), str(Path(found).parent)]))
    return out


def forest_env(suffix: str | None) -> dict[str, str]:
    """The environment for kit tools, pinned to one forest; inherited overrides dropped.

    Without a suffix (standalone mode) the pixi toolchain is removed as well.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("FOREST", "BUILD_FOREST_ROOT")}
    if suffix:
        env["FOREST_REFERENCE_SUFFIX"] = suffix
        return env
    return host_env(env)


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


SUMMARY = re.compile(r"\d+% tests passed, (\d+) tests? failed out of (\d+)")


def last_token(stdout: str) -> str:
    tokens = [t for t in stdout.split() if t.startswith("T:")]
    return tokens[-1] if tokens else "no token"


def ctest_token(stdout: str) -> str:
    """The run-matrix `T:<passed>/<total>` token, built from ctest's own summary line."""
    found = SUMMARY.findall(stdout)
    if not found:
        return "no token"
    failed, total = map(int, found[-1])
    return f"T:{total - failed}/{total}"


def ctest_argv(build: Path, jobs: int | None = None) -> list[str]:
    jobs = jobs or max(2, (os.cpu_count() or 2) // 2)
    return ["ctest", "--test-dir", str(build), f"-j{jobs}", "--timeout", "300",
            "--output-on-failure"]


CTEST_TIMEOUT = 1800


def run_ctest(build: Path, jobs: int | None = None) -> str:
    try:
        done = subprocess.run(ctest_argv(build, jobs), cwd=build, capture_output=True,
                              text=True, check=False, env=forest_env(None),
                              timeout=CTEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "T:timeout"
    return ctest_token(done.stdout or "")


def _path(coords, kit: Path) -> Path:
    name = f"{coords.repo_slug}-{coords.sha}.json"
    if coords.forest_name == "standalone":
        where = hashlib.sha1(str(coords.graph).encode()).hexdigest()[:8]
        name = f"{coords.repo_slug}-standalone-{coords.sha}-{where}.json"
    return kit / ".devlocal" / "init-over-assign" / "baselines" / name


def ensure(coords, kit: Path) -> Path:
    path = _path(coords, kit)
    if path.exists():
        return path
    suffix = suffix_of(coords.forest_name)
    got = matrix(kit, "--ctest-dir", coords.repo_slug, suffix=suffix)
    if got.returncode != 0 or not got.stdout.strip():
        raise RuntimeError(f"run-matrix.sh --ctest-dir failed: {got.stderr.strip()}")
    ctest_dir = Path(got.stdout.strip().splitlines()[-1])
    return _record(path, coords, ctest_dir, lambda: last_token(
        matrix(kit, "--run-ctest", coords.repo_slug, suffix=suffix).stdout))


def ensure_standalone(coords, kit: Path, jobs: int | None = None) -> Path:
    path = _path(coords, kit)
    if path.exists():
        return path
    return _record(path, coords, coords.graph, lambda: run_ctest(coords.graph, jobs))


def _record(path: Path, coords, ctest_dir: Path, run: Callable[[], str]) -> Path:
    log = ctest_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
    log.unlink(missing_ok=True)
    token = run()
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
