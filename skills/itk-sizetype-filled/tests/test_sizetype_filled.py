import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sizetype_filled  # noqa: E402
from ioa.manifest import Manifest  # noqa: E402

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


def run_sizetype(g: Graph, apply: bool = True, capsys=None) -> Result:
    manifest = g.repo.parent / "manifest.json"
    argv = ["--graph", str(g.build), "--repo", str(g.repo), "--manifest", str(manifest)]
    assert sizetype_filled.main(argv + (["--apply"] if apply else [])) == 0
    out = capsys.readouterr().out if capsys else ""
    return Result(g.repo, Manifest.read(manifest) if manifest.exists() else None, out)


def assert_builds(g: Graph) -> None:
    res = subprocess.run([_tool("ninja"), "-C", str(g.build)], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


@needs_tools
def test_zero_fill_becomes_brace(fixture_graph):
    assert "  IndexType start{};\n\n" in run_sizetype(fixture_graph("sizetype")).read("a.cxx")


@needs_tools
def test_nonzero_fill_prefers_Filled_over_MakeFilled(fixture_graph):
    text = run_sizetype(fixture_graph("sizetype")).read("a.cxx")
    assert "  auto grown = SizeType::Filled(2);\n  grown[1] = 3;\n" in text
    assert "MakeFilled<SizeType>" not in text


@needs_tools
def test_literal_size_never_mutated_is_constexpr(fixture_graph):
    out = run_sizetype(fixture_graph("sizetype"))
    assert "  constexpr auto size = SizeType::Filled(2);\n" in out.read("a.cxx")
    assert "  constexpr auto size = TImage::SizeType::Filled(3);\n  return size[0];\n" in out.read("b.cxx")


@needs_tools
def test_type_without_Filled_uses_MakeFilled(fixture_graph):
    assert "  auto weights = itk::MakeFilled<ArrayType>(7);\n" in run_sizetype(fixture_graph("sizetype")).read("b.cxx")


@needs_tools
def test_inherited_Filled_is_not_used_because_it_returns_the_base(fixture_graph):
    text = run_sizetype(fixture_graph("sizetype")).read("a.cxx")
    assert "  auto origin = itk::MakeFilled<PointType>(spacing); // half a voxel\n" in text
    assert "PointType::Filled" not in text


@needs_tools
def test_offset_literal_is_constexpr_and_keeps_its_trailing_comment(fixture_graph):
    text = run_sizetype(fixture_graph("sizetype")).read("a.cxx")
    assert "  constexpr auto step = itk::MakeFilled<OffsetType>(1); // neighbor step\n" in text


@needs_tools
def test_zero_fill_of_user_constructed_type_is_not_brace(fixture_graph):
    assert "  auto m = itk::MakeFilled<MatrixType>(0);\n" in run_sizetype(fixture_graph("sizetype")).read("b.cxx")


@needs_tools
def test_self_referencing_fill_is_untouched(fixture_graph):
    assert "  SizeType self;\n  self.Fill(self[0]);\n" in run_sizetype(fixture_graph("sizetype")).read("a.cxx")


@needs_tools
def test_manifest_sites_classes_and_post_edit_lines(fixture_graph):
    g = fixture_graph("sizetype")
    out = run_sizetype(g)
    assert out.manifest.kind == "itk-helpers"
    got = [(str(s.file), s.start, s.end, s.cls, s.skipped) for s in out.manifest.sites]
    assert got == [
        ("a.cxx", 11, 11, "fill_zero", None), ("a.cxx", 13, 13, "fill_nonzero", None),
        ("a.cxx", 15, 15, "fill_nonzero", None), ("a.cxx", 18, 18, "fill_nonzero", None),
        ("a.cxx", 20, 20, "fill_nonzero", None),
        ("b.cxx", 10, 10, "fill_nonzero", None), ("b.cxx", 22, 22, "fill_nonzero", None),
        ("b.cxx", 24, 24, "fill_zero", None),
    ]
    for s in out.manifest.sites:
        line = out.read(str(s.file)).splitlines()[s.start - 1]
        assert "auto " in line or line.endswith("{};")
    assert_builds(g)


@needs_tools
def test_dry_run_prints_counts_and_writes_nothing(fixture_graph, capsys):
    g = fixture_graph("sizetype")
    before = {n: (g.repo / n).read_text() for n in ("a.cxx", "b.cxx")}
    out = run_sizetype(g, apply=False, capsys=capsys)
    assert out.manifest is None
    assert {n: (g.repo / n).read_text() for n in before} == before
    assert "fill_zero a.cxx 1" in out.stdout and "fill_nonzero a.cxx 4" in out.stdout
    assert "fill_zero b.cxx 1" in out.stdout and "fill_nonzero b.cxx 2" in out.stdout


@needs_tools
def test_stranded_comment_reverts_the_file(fixture_graph, monkeypatch):
    g = fixture_graph("sizetype")
    original = (g.repo / "a.cxx").read_text()
    real = sizetype_filled.render

    def drop_comment(p):
        return real(p).split(" //")[0]

    monkeypatch.setattr(sizetype_filled, "render", drop_comment)
    out = run_sizetype(g)
    assert out.read("a.cxx") == original
    assert {str(s.skipped) for s in out.manifest.sites if str(s.file) == "a.cxx"} == {"comment-stranded"}


def test_apply_requires_manifest(tmp_path):
    with pytest.raises(SystemExit):
        sizetype_filled.main(["--graph", str(tmp_path), "--repo", str(tmp_path), "--apply"])
