from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MATRIX = "bin/run-matrix.sh"
ERROR_RE = re.compile(r"error:|CMake Error|library not found|No such module|undefined sym", re.I)


@dataclass
class ForestInfo:
    suffix: str
    path: Path
    itk_branch: str = ""
    itk_sha: str = ""
    itk_describe: str = ""
    itk_artifact: bool = False
    last_matrix_log: float | None = None


def _git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def testbed_root(cwd: Path | None = None) -> Path:
    base = (cwd or Path.cwd()).resolve()
    env = os.environ.get("TESTBED")
    if env:
        return Path(env).resolve()
    common = _git(["rev-parse", "--git-common-dir"], base)
    if common:
        common_path = (base / common).resolve() if not os.path.isabs(common) else Path(common)
        if common_path.name == ".git" and common_path.parent != base:
            return common_path.parent
    return base


def list_forests(root: Path) -> list[ForestInfo]:
    out: list[ForestInfo] = []
    for d in sorted(root.glob("build_forest*")):
        if not d.is_dir():
            continue
        suffix = d.name.removeprefix("build_forest").removeprefix("-")
        info = ForestInfo(suffix=suffix, path=d)
        itk = d / "ITK"
        if itk.is_dir():
            info.itk_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], itk)
            info.itk_sha = _git(["rev-parse", "--short=12", "HEAD"], itk)
            info.itk_describe = _git(["describe", "--tags", "--always"], itk)
        info.itk_artifact = any((itk / "build" / "lib").glob("libITKCommon-*.a")) or \
                            any((d / "ITK-build" / "lib").glob("libITKCommon-*.a"))
        logs = list((d / "logs").glob("matrix-*.log")) if (d / "logs").is_dir() else []
        if logs:
            info.last_matrix_log = max(p.stat().st_mtime for p in logs)
        out.append(info)
    return out


def list_targets(root: Path) -> list[str]:
    r = subprocess.run(["bash", MATRIX, "--list-targets"], cwd=root, capture_output=True, text=True)
    return r.stdout.split()


def list_deferred(root: Path) -> list[tuple[str, str]]:
    r = subprocess.run(["bash", MATRIX, "--list-deferred"], cwd=root, capture_output=True, text=True)
    rows = [line.split("\t", 1) for line in r.stdout.strip().splitlines() if "\t" in line]
    return [(n, reason) for n, reason in rows]


def check_artifact(root: Path, forest: Path, target: str) -> bool:
    env = {**os.environ, "FOREST": str(forest)}
    r = subprocess.run(["bash", MATRIX, "--check-artifact", target], cwd=root, env=env,
                       capture_output=True, text=True)
    return r.returncode == 0


def error_grep(log: Path, n: int = 3) -> list[str]:
    hits: list[str] = []
    try:
        for line in log.read_text(errors="replace").splitlines():
            if ERROR_RE.search(line):
                hits.append(line)
                if len(hits) == n:
                    break
    except OSError:
        pass
    return hits
