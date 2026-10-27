import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ioa import compile_commands, tidy

PROTECTED = ("main", "master", "release", "dashboard")


class PreflightError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Coordinates:
    repo_slug: str
    sha: str
    forest_name: str
    graph: Path
    itk_version: str


def _git(repo: Path, *args: str, code: str = "not-at-upstream-tip") -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise PreflightError(code, f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def _norm_url(url: str) -> str:
    url = url.strip().rstrip("/").removesuffix(".git")
    m = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.*)$", url)
    if m:
        url = f"https://{m.group(1)}/{m.group(2)}"
    return url


def catalog_entry(kit: Path, tree: str) -> tuple[str, str]:
    in_consumers = False
    for line in (kit / "CATALOG.md").read_text().splitlines():
        if line.startswith("## "):
            in_consumers = line.startswith("## Consumers")
            continue
        if not in_consumers or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == tree:
            branch = re.search(r"`([^`]+)`", cells[2])
            return cells[1], (branch.group(1) if branch else cells[2])
    raise PreflightError("not-at-upstream-tip", f"{tree} is not in {kit / 'CATALOG.md'}")


def _upstream_tip(repo: Path, url: str, branch: str, refresh: str) -> str:
    want = _norm_url(url)
    remotes = _git(repo, "remote").split()
    for name in remotes:
        if _norm_url(_git(repo, "remote", "get-url", name)) == want:
            _git(repo, "fetch", "--quiet", name, branch)
            return _git(repo, "rev-parse", f"refs/remotes/{name}/{branch}")
    raise PreflightError(
        "not-at-upstream-tip", f"no remote of {repo.name} matches {url}; {refresh}"
    )


def tidy_version() -> str:
    try:
        out = subprocess.run(
            [tidy.tool("clang-tidy"), "--version"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (SystemExit, OSError, subprocess.CalledProcessError) as exc:
        raise PreflightError("tidy-series-mismatch", f"clang-tidy is unusable: {exc}") from exc
    m = re.search(r"version\s+(\d+\.\d+)", out)
    return m.group(1) if m else "unknown"


def _cache_value(graph: Path, pattern: str) -> str | None:
    cache = graph / "CMakeCache.txt"
    if not cache.exists():
        return None
    m = re.search(pattern, cache.read_text(), re.M)
    return m.group(1).strip() if m else None


def compiler_version(graph: Path) -> str:
    for f in sorted(graph.glob("CMakeFiles/*/CMakeCXXCompiler.cmake")):
        m = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "(\d+\.\d+)', f.read_text())
        if m:
            return m.group(1)
    return "unknown"


def itk_version(graph: Path) -> str:
    itk_dir = _cache_value(graph, r"^ITK_DIR:[A-Z]+=(.+)$")
    if not itk_dir:
        return "unknown"
    for name, pat in (
        ("ITKConfigVersion.cmake", r'PACKAGE_VERSION\s+"([^"]+)"'),
        ("ITKConfig.cmake", None),
    ):
        path = Path(itk_dir) / name
        if not path.exists():
            continue
        text = path.read_text()
        if pat:
            m = re.search(pat, text)
            if m:
                return m.group(1)
        else:
            parts = [
                re.search(rf"set\(ITK_VERSION_{k}\s+(\d+)\)", text)
                for k in ("MAJOR", "MINOR", "PATCH")
            ]
            if all(parts):
                return ".".join(p.group(1) for p in parts)
    return "unknown"


def check(repo: Path, forest: Path, kit: Path) -> Coordinates:
    suffix = forest.name.removeprefix("build_forest-")
    refresh = (
        f"refresh the forest with `FOREST_REFERENCE_SUFFIX={suffix} pixi run checkout` "
        f"then `pixi run build-{repo.name}`"
    )
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise PreflightError("dirty-tree", f"{repo} has uncommitted changes")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        raise PreflightError("not-at-upstream-tip", f"{repo} has a detached HEAD; {refresh}")
    if branch in PROTECTED:
        raise PreflightError("on-main", f"{repo} is on protected branch {branch}")
    url, floating = catalog_entry(kit, repo.name)
    tip = _upstream_tip(repo, url, floating, refresh)
    sha = _git(repo, "rev-parse", "HEAD")
    if sha != tip:
        raise PreflightError(
            "not-at-upstream-tip",
            f"HEAD {sha[:12]} differs from upstream {floating} {tip[:12]}; {refresh}",
        )
    try:
        graph = compile_commands.find_graph(repo / "build", repo.name)
    except FileNotFoundError as exc:
        raise PreflightError("no-graph", str(exc)) from exc
    have, want = tidy_version(), compiler_version(graph)
    if have != want:
        raise PreflightError(
            "tidy-series-mismatch", f"clang-tidy {have} but the forest compiler is {want}"
        )
    return Coordinates(repo.name, sha, forest.name, graph, itk_version(graph))
