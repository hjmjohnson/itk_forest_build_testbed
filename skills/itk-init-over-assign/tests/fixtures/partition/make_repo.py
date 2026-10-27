"""Build a temp git repo with three edited files and the stage manifests."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

from ioa.manifest import Manifest, Site


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _lines(prefix: str, n: int) -> list[str]:
    return [f"int {prefix}{i} = {i};" for i in range(1, n + 1)]


def _edit(lines: list[str], line: int, new: list[str]) -> None:
    lines[line - 1 : line] = new


def build(root: Path, clang_format: str = "DisableFormat: true\n") -> SimpleNamespace:
    repo = root / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    a, b, c = _lines("a", 60), _lines("b", 110), _lines("c", 20)
    b[59] = "// TODO: keep this"
    files = {"a.cxx": a, "b.cxx": b, "c.cxx": c}
    for name, lines in files.items():
        (repo / name).write_text("\n".join(lines) + "\n")
    (repo / ".clang-format").write_text(clang_format)
    _git(repo, "add", "a.cxx", "b.cxx", "c.cxx", ".clang-format")
    _git(repo, "commit", "-q", "-m", "initial")

    _edit(a, 10, ["const int a10 = 10;"])
    _edit(a, 40, ["constexpr int a40 = 40;"])
    _edit(b, 99, ["int b99 =", "    99;"])
    _edit(b, 60, [])
    b[59] = "const int b61 = 61;"
    _edit(b, 20, ["const int b20 = 20;"])
    _edit(c, 5, ["const int c5 = 5;"])
    for name, lines in files.items():
        (repo / name).write_text("\n".join(lines) + "\n")

    def site(file, start, end, kind, cls):
        return Site(Path(file), start, end, kind, cls)

    manifests = {
        "m_local": Manifest(
            "local-init",
            [
                site("a.cxx", 10, 10, "local-init", "int"),
                site("a.cxx", 40, 40, "local-init", "int"),
                site("b.cxx", 20, 20, "local-init", "int"),
            ],
        ),
        "m_helpers": Manifest(
            "itk-helpers", [site("a.cxx", 40, 40, "itk-helpers", "int")]
        ),
        "m_todo_bad": Manifest(
            "local-const", [site("b.cxx", 60, 61, "local-const", "int")]
        ),
    }
    mdir = root / "manifests"
    mdir.mkdir()
    for name, m in manifests.items():
        m.write(mdir / f"{name}.json")
    graph = root / "build"
    graph.mkdir()
    return SimpleNamespace(
        path=repo,
        graph=graph,
        **{name: Manifest.read(mdir / f"{name}.json") for name in manifests},
    )
