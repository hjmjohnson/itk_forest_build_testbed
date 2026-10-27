import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import list_init  # noqa: E402
from ioa.manifest import Manifest  # noqa: E402
from ioa.skip import Reason  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
CLANG_FORMAT = Path(__file__).resolve().parents[2] / "itk-member-init" / "tests" / "fixtures" / ".clang-format"
TOOLS = ["clang-query", "clang-apply-replacements", "clang-format", "cmake", "ninja"]


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
    def make(name: str) -> Graph:
        repo = tmp_path / name
        shutil.copytree(FIXTURES / name, repo)
        shutil.copy(CLANG_FORMAT, repo / ".clang-format")
        _git(repo, "init", "-q")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "fixture")
        build = tmp_path / "build"
        subprocess.run(
            [_tool("cmake"), "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={_tool('ninja')}",
             "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", "-S", str(repo), "-B", str(build)],
            check=True, capture_output=True, text=True,
        )
        return Graph(repo, build)

    return make


def run_list_init(g: Graph, apply: bool = True, capsys=None) -> Result:
    manifest = g.repo.parent / "manifest.json"
    argv = ["--graph", str(g.build), "--repo", str(g.repo), "--manifest", str(manifest)]
    assert list_init.main(argv + (["--apply"] if apply else [])) == 0
    out = capsys.readouterr().out if capsys else ""
    return Result(g.repo, Manifest.read(manifest) if manifest.exists() else None, out)


def assert_formatted(g: Graph, name: str) -> None:
    res = subprocess.run(
        [_tool("clang-format"), "--dry-run", "-Werror", "--style=file", name],
        cwd=g.repo, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr


def assert_builds(g: Graph) -> None:
    res = subprocess.run([_tool("ninja"), "-C", str(g.build)], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


@needs_tools
def test_push_back_run_becomes_brace_list(fixture_graph):
    g = fixture_graph("push_back")
    out = run_list_init(g)
    text = out.read("a.cxx")
    assert "  std::vector<int>    v{ 1, 2, 3 };\n  std::vector<double> w{ 1.5 };\n  w.push_back(w[0]);\n" in text
    assert "  std::vector<double> u{ 0.5, 1.5 };\n  return u.size();\n" in out.read("h.h")
    assert out.manifest.kind == "container-list-init"
    assert [(s.file, s.start, s.end, s.cls, s.skipped) for s in out.manifest.sites] == [
        (Path("a.cxx"), 8, 8, "push_back_run", None), (Path("a.cxx"), 9, 9, "push_back_run", None),
        (Path("h.h"), 7, 7, "push_back_run", None)]
    assert_formatted(g, "a.cxx")
    assert_builds(g)


@needs_tools
def test_element_count_verified_by_reparse(fixture_graph):
    out = run_list_init(fixture_graph("push_back"))
    assert [s.note for s in out.manifest.applied()] == ["elements:3", "elements:1", "elements:2"]


@needs_tools
def test_index_assign_run_requires_full_coverage(fixture_graph):
    g = fixture_graph("index_assign")
    m = run_list_init(g).manifest
    assert len(m.applied()) == 1 and m.sites[1].note == "partial-coverage"
    assert (m.sites[0].cls, m.sites[1].cls, m.sites[1].skipped) == (
        "index_assign_run", "index_assign_run", Reason.NARROWING)
    text = (g.repo / "a.cxx").read_text()
    assert "  std::array<double, 3> a{ 1.0, 2.0, 3.0 };\n  std::array<double, 3> b;\n  b[0] = 1.0;\n" in text
    assert_builds(g)


@needs_tools
def test_unsigned_into_vector_int_is_narrowing(fixture_graph):
    g = fixture_graph("narrowing")
    before = (g.repo / "a.cxx").read_text()
    out = run_list_init(g)
    assert out.manifest.sites[0].skipped == Reason.NARROWING
    assert out.read("a.cxx") == before


@needs_tools
def test_vector_size_t_with_one_element_is_init_list_ctor(fixture_graph):
    out = run_list_init(fixture_graph("init_list_ctor"))
    assert out.manifest.sites[0].skipped == Reason.INIT_LIST_CTOR


@needs_tools
def test_vnl_vector_is_skipped(fixture_graph):
    g = fixture_graph("vnl")
    before = (g.repo / "a.cxx").read_text()
    out = run_list_init(g)
    assert [(s.skipped, s.note) for s in out.manifest.sites] == [(Reason.INIT_LIST_CTOR, "no-init-list")]
    assert out.read("a.cxx") == before


@needs_tools
def test_std_array_full_coverage_is_aggregate_init(fixture_graph):
    g = fixture_graph("std_array")
    out = run_list_init(g)
    assert "  std::array<int, 2> a{ 1, 2 };\n  std::array<int, 3> p;\n" in out.read("a.cxx")
    assert [(s.start, s.skipped, s.note) for s in out.manifest.sites] == [
        (6, None, "elements:2"), (7, Reason.NARROWING, "partial-coverage")]
    assert_builds(g)


@needs_tools
def test_two_argument_emplace_back_constructs_element(fixture_graph):
    g = fixture_graph("emplace_multi")
    out = run_list_init(g)
    assert ("  std::vector<std::pair<int, int>> p{ std::pair<int, int>(1, 2), std::pair<int, int>(3, 4) };\n"
            in out.read("a.cxx"))
    assert [(s.skipped, s.note) for s in out.manifest.sites] == [
        (None, "elements:2"), (Reason.INIT_LIST_CTOR, "element-type-unknown")]
    assert_formatted(g, "a.cxx")
    assert_builds(g)


@needs_tools
def test_trailing_comment_moves_to_declaration_or_reverts_file(fixture_graph):
    g = fixture_graph("trailing_comment")
    before_b = (g.repo / "b.cxx").read_text()
    out = run_list_init(g)
    assert "  std::vector<double> v{ 1.5, 2.5 }; // the v\n" in out.read("a.cxx")
    assert out.read("b.cxx") == before_b
    assert [(s.file, s.skipped) for s in out.manifest.sites] == [
        (Path("a.cxx"), None), (Path("b.cxx"), Reason.COMMENT_STRANDED)]


@needs_tools
def test_preprocessor_inside_run_is_skipped(fixture_graph):
    g = fixture_graph("preprocessor")
    before = (g.repo / "a.cxx").read_text()
    out = run_list_init(g)
    assert [s.skipped for s in out.manifest.sites] == [Reason.PREPROCESSOR]
    assert out.read("a.cxx") == before


@needs_tools
def test_dry_run_prints_counts_and_writes_nothing(fixture_graph, capsys):
    g = fixture_graph("index_assign")
    out = run_list_init(g, apply=False, capsys=capsys)
    assert out.manifest is None
    assert _git(g.repo, "status", "--porcelain") == ""
    assert "index_assign_run a.cxx 1" in out.stdout
    assert "skipped:narrowing a.cxx 1" in out.stdout
