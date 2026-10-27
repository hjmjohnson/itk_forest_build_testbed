"""Build a temp git repo, run edit stages with snapshots between them."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

from ioa.manifest import Manifest, Site
from ioa.partition import StageRecord, snapshot


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def lines(prefix: str, n: int) -> list[str]:
    return [f"int {prefix}{i} = {i};" for i in range(1, n + 1)]


def write(repo: Path, files: dict[str, list[str]]) -> None:
    for name, body in files.items():
        (repo / name).write_text("\n".join(body) + "\n")


def init_repo(root: Path, files: dict[str, list[str]], clang_format: str) -> Path:
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "commit.gpgsign", "false")
    write(repo, files)
    (repo / ".clang-format").write_text(clang_format)
    git(repo, "add", ".clang-format", *files)
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def stage(repo, files, kind, edit, sites) -> StageRecord:
    """Apply `edit` to `files` as one stage; sites are in the stage's input lines."""
    before = snapshot(repo)
    edit(files)
    write(repo, files)
    manifest = Manifest(kind, [Site(Path(f), s, e, kind, "int") for f, s, e in sites])
    return StageRecord(kind, manifest, before, snapshot(repo))


def build(root: Path, clang_format: str = "DisableFormat: true\n") -> SimpleNamespace:
    a, b, c = lines("a", 60), lines("b", 110), lines("c", 20)
    a[9], a[10], a[19], a[20] = "int a10;", "a10 = 10;", "int a20;", "a20 = 20;"
    b[59] = "// TODO: keep this"
    files = {"a.cxx": a, "b.cxx": b, "c.cxx": c}
    repo = init_repo(root, files, clang_format)

    def local(f):
        f["a.cxx"][47] = "const int a48 = 48;"
        f["a.cxx"][39] = "const int a40 = 40;"
        f["a.cxx"][19:21] = ["int a20 = 20;"]
        f["a.cxx"][9:11] = ["int a10 = 10;"]
        f["b.cxx"][19] = "const int b20 = 20;"
        f["c.cxx"][4] = "const int c5 = 5;"

    def todo(f):
        f["b.cxx"][59:61] = ["const int b61 = 61;"]

    def helpers(f):
        f["a.cxx"][47] = "constexpr int a50 = 50;"
        f["a.cxx"][37] = "constexpr int a40 = 40;"

    s_local = stage(
        repo, files, "local-init", local,
        [("a.cxx", 10, 11), ("a.cxx", 20, 21), ("a.cxx", 40, 40),
         ("a.cxx", 48, 48), ("b.cxx", 20, 20), ("c.cxx", 5, 5)],
    )
    s_todo = stage(repo, files, "local-const", todo, [("b.cxx", 60, 61)])
    s_helpers = stage(
        repo, files, "itk-helpers", helpers, [("a.cxx", 38, 38), ("a.cxx", 48, 48)]
    )
    i = files["b.cxx"].index("int b99 = 99;")
    files["b.cxx"][i : i + 1] = ["int b99 =", "    99;"]
    write(repo, files)
    graph = root / "build"
    graph.mkdir()
    return SimpleNamespace(
        path=repo, graph=graph, s_local=s_local, s_todo=s_todo, s_helpers=s_helpers
    )
