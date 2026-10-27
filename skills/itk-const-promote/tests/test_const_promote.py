import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import const_promote  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.skip import Reason  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
CLANG_FORMAT = Path(__file__).resolve().parents[2] / "itk-member-init" / "tests" / "fixtures" / ".clang-format"
TOOLS = ["clang-tidy", "run-clang-tidy", "clang-apply-replacements", "clang-format", "cmake", "ninja"]


def _tool(name: str) -> str | None:
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix and (Path(prefix) / "bin" / name).exists():
        return str(Path(prefix) / "bin" / name)
    return shutil.which(name)


needs_tools = pytest.mark.skipif(
    any(_tool(t) is None for t in TOOLS), reason="clang tools, cmake, or ninja not available"
)


@dataclass
class Graph:
    repo: Path
    build: Path


@dataclass
class Result:
    repo: Path
    manifest: Manifest | None
    stdout: str

    def read(self, name: str) -> str:
        return (self.repo / name).read_text()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def fixture_graph(tmp_path):
    def make(name: str, base: Path | None = None) -> Graph:
        base = base or tmp_path
        repo = base / name
        shutil.copytree(FIXTURES / name, repo)
        shutil.copy(CLANG_FORMAT, repo / ".clang-format")
        _git(repo, "init", "-q")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "fixture")
        build = base / "build"
        subprocess.run(
            [_tool("cmake"), "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={_tool('ninja')}",
             "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", "-S", str(repo), "-B", str(build)],
            check=True, capture_output=True, text=True,
        )
        return Graph(repo, build)

    return make


def prior(g: Graph, ranges: dict[str, tuple[int, int]] | None = None) -> Path:
    """A prior-stage manifest; by default one applied site spanning each .cxx."""
    if ranges is None:
        ranges = {
            p.name: (1, p.read_text().count("\n")) for p in sorted(g.repo.glob("*.cxx"))
        }
    sites = [Site(Path(name), a, b, "local-init", "assign") for name, (a, b) in ranges.items()]
    path = g.repo.parent / "prior.json"
    Manifest("local-init", sites).write(path)
    return path


def assert_formatted(g: Graph, name: str) -> None:
    res = subprocess.run(
        [_tool("clang-format"), "--dry-run", "-Werror", "--style=file", name],
        cwd=g.repo, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr


def run_promote(g: Graph, only_from: Path | None = None, apply: bool = True, capsys=None,
                kind: str = "local-const") -> Result:
    manifest = g.repo.parent / "manifest.json"
    argv = ["--graph", str(g.build), "--repo", str(g.repo), "--manifest", str(manifest),
            "--only-from", str(only_from or prior(g)), "--kind", kind]
    assert const_promote.main(argv + (["--apply"] if apply else [])) == 0
    out = capsys.readouterr().out if capsys else ""
    return Result(g.repo, Manifest.read(manifest) if manifest.exists() else None, out)


@needs_tools
def test_never_mutated_local_becomes_const(fixture_graph):
    g = fixture_graph("locals")
    out = run_promote(g)
    text = out.read("a.cxx")
    assert "  const int n = f();\n  int       m = 0;\n" in text
    assert_formatted(g, "a.cxx")
    assert_formatted(g, "b.cxx")
    assert out.manifest.kind == "local-const"
    assert [(s.file, s.start, s.end, s.cls, s.skipped) for s in out.manifest.sites] == [
        (Path("a.cxx"), 7, 7, "const", None), (Path("b.cxx"), 7, 7, "const", None)]


@needs_tools
def test_filled_literal_becomes_constexpr(fixture_graph):
    g = fixture_graph("constexpr")
    out = run_promote(g, kind="itk-helpers-constexpr")
    text = out.read("a.cxx")
    assert (
        "  constexpr SizeType size = SizeType::Filled(2);\n"
        "  constexpr int      lit = 3;\n"
        "  const int          n = f();\n"
        "  constexpr double   big = std::numeric_limits<double>::max();\n"
        "  constexpr int      arr[] = { 1, 2 };\n"
        "\n"
        "  auto w = f();\n"
    ) in text
    assert_formatted(g, "a.cxx")
    assert sorted((s.start, s.cls, s.skipped, s.note) for s in out.manifest.sites) == [
        (26, "constexpr", None, ""), (27, "constexpr", None, ""), (28, "const", None, ""),
        (29, "constexpr", None, ""), (30, "constexpr", None, ""),
        (32, "const", Reason.GATE_FAILED, "auto-unanalyzed")]
    assert {s.kind for s in out.manifest.sites} == {"itk-helpers-constexpr"}


@needs_tools
def test_promoted_file_still_compiles(fixture_graph):
    g = fixture_graph("constexpr")
    run_promote(g)
    res = subprocess.run([_tool("ninja"), "-C", str(g.build)], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


@needs_tools
def test_static_local_is_skipped(fixture_graph):
    g = fixture_graph("static_local")
    before = (g.repo / "a.cxx").read_text()
    out = run_promote(g)
    assert [(s.skipped, s.start) for s in out.manifest.sites] == [(Reason.STATIC_LOCAL, 7)]
    assert out.read("a.cxx") == before


@needs_tools
def test_only_from_restricts_to_prior_manifest_files(fixture_graph):
    g = fixture_graph("locals")
    out = run_promote(g, only_from=prior(g, {"a.cxx": (1, 11)}))
    assert {s.file.name for s in out.manifest.sites} == {"a.cxx"}
    assert "  int q = f();\n" in out.read("b.cxx")


@needs_tools
def test_only_from_ignores_sites_outside_prior_ranges(fixture_graph):
    g = fixture_graph("only_from")
    out = run_promote(g, only_from=prior(g, {"a.cxx": (8, 8)}))
    text = out.read("a.cxx")
    assert "  const int near = f();\n" in text
    assert "  int far = f();\n" in text
    assert [(s.start, s.cls) for s in out.manifest.sites] == [(7, "const")]


@needs_tools
def test_only_from_ignores_a_site_two_lines_away(fixture_graph):
    g = fixture_graph("only_from")
    before = (g.repo / "a.cxx").read_text()
    out = run_promote(g, only_from=prior(g, {"a.cxx": (9, 9)}))
    assert out.manifest.sites == []
    assert out.read("a.cxx") == before


@needs_tools
def test_symlinked_repo_path_is_still_analyzed(fixture_graph, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    g = fixture_graph("locals", base=link)
    out = run_promote(g)
    assert "  const int n = f();\n" in out.read("a.cxx")
    assert len(out.manifest.applied()) == 2


@needs_tools
def test_trailing_comment_stays_on_the_promoted_line(fixture_graph):
    text = run_promote(fixture_graph("trailing_comment")).read("a.cxx")
    assert "  const int k = f(); // the k\n" in text
    assert text.count("// the k") == 1


@needs_tools
def test_dry_run_prints_counts_and_writes_nothing(fixture_graph, capsys):
    g = fixture_graph("constexpr")
    before = (g.repo / "a.cxx").read_text()
    out = run_promote(g, apply=False, capsys=capsys)
    assert out.manifest is None
    assert out.read("a.cxx") == before
    assert _git(g.repo, "status", "--porcelain") == ""
    assert "constexpr a.cxx 4" in out.stdout
    assert "const a.cxx 1" in out.stdout
    assert "skipped:gate-failed a.cxx 1" in out.stdout


def test_second_declarator_ignores_template_and_call_commas():
    code = "int a = f(1, 2), b = 3;"
    assert const_promote.has_second_declarator(code, code.index("a") + 1, len(code) - 1)
    code = "std::map<int, int> m = g<int, long>(1, 2);"
    assert not const_promote.has_second_declarator(code, code.index(" m") + 2, len(code) - 1)
    code = "int v[] = { 1, 2 };"
    assert not const_promote.has_second_declarator(code, code.index("v") + 1, len(code) - 1)


def test_widen_to_block_stops_at_blank_and_brace_lines():
    from ioa.tidy import widen_to_block

    lines = ["{", "  int a;", "  int b;", "  int c;", "", "  int d;", "}"]
    assert widen_to_block(lines, 3, 3) == (2, 4)
    assert widen_to_block(lines, 6, 6) == (6, 6)
