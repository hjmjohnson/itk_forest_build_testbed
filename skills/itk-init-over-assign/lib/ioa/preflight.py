import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ioa import compile_commands, tidy

FOREST_LOCAL = "COMP: forest-local"
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
    forest_local: list[str] = field(default_factory=list)
    repo: Path | None = None
    note: str = ""


def run_branch(now: datetime) -> str:
    return f"style-init-over-assign-{now:%Y%m%d}"


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


def _tidy_output() -> str:
    try:
        return subprocess.run(
            [tidy.tool("clang-tidy"), "--version"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (SystemExit, OSError, subprocess.CalledProcessError) as exc:
        raise PreflightError("tidy-series-mismatch", f"clang-tidy is unusable: {exc}") from exc


def tidy_version() -> str:
    m = re.search(r"version\s+(\d+\.\d+)", _tidy_output())
    return m.group(1) if m else "unknown"


def tidy_full_version() -> str:
    m = re.search(r"version\s+(\d+\.\d+(?:\.\d+)?)", _tidy_output())
    return m.group(1) if m else "unknown"


def _cache_value(graph: Path, pattern: str) -> str | None:
    cache = graph / "CMakeCache.txt"
    if not cache.exists():
        return None
    m = re.search(pattern, cache.read_text(), re.M)
    return m.group(1).strip() if m else None


def _compiler_setting(graph: Path, name: str) -> str | None:
    for f in sorted(graph.glob("CMakeFiles/*/CMakeCXXCompiler.cmake")):
        m = re.search(rf'set\({name} "([^"]*)"\)', f.read_text())
        if m:
            return m.group(1)
    return None


def compiler_version(graph: Path) -> str:
    m = re.match(r"\d+\.\d+", _compiler_setting(graph, "CMAKE_CXX_COMPILER_VERSION") or "")
    return m.group(0) if m else "unknown"


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


def _forest_local_commits(repo: Path, tip: str, head: str) -> list[str] | None:
    if head == tip:
        return []
    if _git(repo, "rev-list", "--merges", f"{tip}..{head}"):
        return None
    shas = _git(repo, "rev-list", "--first-parent", f"{tip}..{head}").split()
    if not shas or _git(repo, "rev-parse", f"{shas[-1]}^") != tip:
        return None
    subjects = _git(repo, "log", "--first-parent", "--format=%s", f"{tip}..{head}").splitlines()
    if not all(t.startswith(FOREST_LOCAL) for t in subjects):
        return None
    return subjects[::-1]


def check(repo: Path, forest: Path, kit: Path) -> Coordinates:
    suffix = forest.name.removeprefix("build_forest-")
    refresh = (
        f"refresh the forest with `FOREST_REFERENCE_SUFFIX={suffix} APPLY=1 "
        f"bash bin/refresh-forest.sh {repo.name}` then "
        f"`FOREST_REFERENCE_SUFFIX={suffix} pixi run build-{repo.name}`"
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
    forest_local = _forest_local_commits(repo, tip, sha)
    if forest_local is None:
        raise PreflightError(
            "not-at-upstream-tip",
            f"HEAD {sha[:12]} differs from upstream {floating} {tip[:12]} by more than "
            f"`{FOREST_LOCAL}` commits; {refresh}",
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
    return Coordinates(repo.name, sha, forest.name, graph, itk_version(graph), forest_local)


def _series(version: str) -> str:
    return ".".join(version.split(".")[:2])


def _standalone_tidy_note(graph: Path) -> str:
    have = tidy_full_version()
    if _compiler_setting(graph, "CMAKE_CXX_COMPILER_ID") == "AppleClang":
        full = _compiler_setting(graph, "CMAKE_CXX_COMPILER_VERSION") or "unknown"
        shown = ".".join(full.split(".")[:3])
        return f"tidy-series: skipped (AppleClang {shown} vs clang-tidy {have})"
    want = compiler_version(graph)
    if _series(have) != want:
        raise PreflightError(
            "tidy-series-mismatch", f"clang-tidy {have} but the build compiler is {want}"
        )
    return ""


def check_standalone(repo: Path, build: Path, upstream: str, kit: Path) -> Coordinates:
    remote, _, branch = upstream.partition("/")
    if not remote or not branch:
        raise PreflightError("not-at-upstream-tip", f"--upstream {upstream} is not <remote>/<branch>")
    refresh = (
        f"refresh with `git -C {repo} fetch {remote} && "
        f"git -C {repo} merge --ff-only {remote}/{branch}`"
    )
    if not repo.is_dir() or subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-dir"], capture_output=True, check=False
    ).returncode != 0:
        raise PreflightError("not-a-repo", f"{repo} is not a git checkout")
    if _git(repo, "status", "--porcelain", "--untracked-files=no", code="dirty-tree"):
        raise PreflightError("dirty-tree", f"{repo} has uncommitted changes")
    _git(repo, "fetch", "--quiet", remote, branch)
    tip = _git(repo, "rev-parse", f"refs/remotes/{remote}/{branch}")
    sha = _git(repo, "rev-parse", "HEAD")
    forest_local = _forest_local_commits(repo, tip, sha)
    if forest_local is None:
        raise PreflightError(
            "not-at-upstream-tip",
            f"HEAD {sha[:12]} differs from {upstream} {tip[:12]} by more than "
            f"`{FOREST_LOCAL}` commits; {refresh}",
        )
    if not (build / "compile_commands.json").is_file():
        raise PreflightError("no-graph", f"no compile_commands.json in {build}")
    run = run_branch(datetime.now())
    if _git(repo, "branch", "--list", run):
        raise PreflightError("branch-exists", f"branch {run} already exists in {repo}; delete or rename it")
    note = _standalone_tidy_note(build)
    slug = _norm_url(_git(repo, "remote", "get-url", remote)).rsplit("/", 1)[-1]
    return Coordinates(slug, sha, "standalone", build, itk_version(build), forest_local,
                       repo=repo, note=note)
