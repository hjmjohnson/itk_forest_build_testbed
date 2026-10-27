import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import allocate_initialized  # noqa: E402
from ioa.manifest import Manifest  # noqa: E402
from ioa.skip import Reason  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
CLANG_FORMAT = Path(__file__).resolve().parents[2] / "itk-member-init" / "tests" / "fixtures" / ".clang-format"


def _tool(name: str) -> str | None:
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix and (Path(prefix) / "bin" / name).exists():
        return str(Path(prefix) / "bin" / name)
    return shutil.which(name)


needs_tools = pytest.mark.skipif(_tool("clang-format") is None, reason="clang-format not available")


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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True, text=True)


@pytest.fixture
def fixture_graph(tmp_path):
    def make(name: str, version: tuple[int, int] | None = (6, 0)) -> Graph:
        repo = tmp_path / name
        shutil.copytree(FIXTURES / name, repo)
        shutil.copy(CLANG_FORMAT, repo / ".clang-format")
        _git(repo, "init", "-q")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "fixture")
        build = tmp_path / "build"
        itk = tmp_path / "itk-build"
        build.mkdir()
        itk.mkdir()
        (build / "CMakeCache.txt").write_text(f"CMAKE_BUILD_TYPE:STRING=Release\nITK_DIR:PATH={itk}\n")
        if version is not None:
            (itk / "ITKConfig.cmake").write_text(
                f'set(ITK_VERSION_MAJOR "{version[0]}")\nset(ITK_VERSION_MINOR "{version[1]}")\n')
        return Graph(repo, build)

    return make


def run_allocate(g: Graph, apply: bool = True, capsys=None) -> Result:
    manifest = g.repo.parent / "manifest.json"
    argv = ["--graph", str(g.build), "--repo", str(g.repo), "--manifest", str(manifest)]
    assert allocate_initialized.main(argv + (["--apply"] if apply else [])) == 0
    out = capsys.readouterr().out if capsys else ""
    return Result(g.repo, Manifest.read(manifest) if manifest.exists() else None, out)


@needs_tools
def test_allocate_true_becomes_AllocateInitialized(fixture_graph):
    text = run_allocate(fixture_graph("allocate")).read("a.cxx")
    assert text.count("  image->AllocateInitialized();\n") == 2
    assert "  ref.AllocateInitialized(); // zeroed\n" in text


@needs_tools
def test_false_default_comment_string_definition_and_vendored_are_untouched(fixture_graph):
    out = run_allocate(fixture_graph("allocate"))
    text = out.read("a.cxx")
    assert "image->Allocate(false);" in text and "image->Allocate();" in text
    assert "// image->Allocate(true) stays in a comment" in text and '"->Allocate(true)"' in text
    assert "return this->Allocate(true);" in out.read("itkImageBase.h")
    assert "image->Allocate(true);" in out.read("ThirdParty/vendored.cxx")


@needs_tools
def test_manifest_lists_each_call_at_its_line(fixture_graph):
    m = run_allocate(fixture_graph("allocate")).manifest
    assert m.kind == "itk-helpers"
    assert [(str(s.file), s.start, s.end, s.cls, s.skipped) for s in m.sites if str(s.file) == "a.cxx"] == [
        ("a.cxx", 6, 6, "allocate_true", None), ("a.cxx", 7, 7, "allocate_true", None),
        ("a.cxx", 12, 12, "allocate_true", None)]


@needs_tools
def test_itk_older_than_5_3_is_skipped(fixture_graph):
    g = fixture_graph("allocate", version=(5, 2))
    before = (g.repo / "a.cxx").read_text()
    out = run_allocate(g)
    assert out.read("a.cxx") == before
    assert {s.skipped for s in out.manifest.sites} == {Reason.ITK_VERSION}
    assert out.manifest.sites[0].note == "itk:5.2"


@needs_tools
def test_unreadable_itk_version_is_assumed_new_and_noted(fixture_graph, capsys):
    out = run_allocate(fixture_graph("allocate", version=None), capsys=capsys)
    assert len(out.manifest.applied()) == 5
    assert {s.note for s in out.manifest.sites} == {"itk-version:unknown"}
    assert "ITK version unreadable" in out.stdout


@needs_tools
def test_dry_run_prints_counts_and_writes_nothing(fixture_graph, capsys):
    g = fixture_graph("allocate")
    before = (g.repo / "a.cxx").read_text()
    out = run_allocate(g, apply=False, capsys=capsys)
    assert out.manifest is None and out.read("a.cxx") == before
    assert "allocate_true a.cxx 3" in out.stdout


@needs_tools
def test_stranded_comment_reverts_the_file(fixture_graph, monkeypatch):
    g = fixture_graph("allocate")
    before = (g.repo / "a.cxx").read_text()

    def lose_comment(path, old):
        path.write_text(path.read_text().replace(" // zeroed", ""))

    monkeypatch.setattr(allocate_initialized, "format_changed", lose_comment)
    out = run_allocate(g)
    assert out.read("a.cxx") == before
    a = [s for s in out.manifest.sites if str(s.file) == "a.cxx"]
    assert {s.skipped for s in a} == {Reason.COMMENT_STRANDED} and a[0].note == "// zeroed"
    assert all(s.skipped is None for s in out.manifest.sites if str(s.file) == "wrap.cxx")


@needs_tools
def test_wrapped_line_shifts_later_sites_to_their_post_edit_lines(fixture_graph):
    out = run_allocate(fixture_graph("allocate"))
    lines = out.read("wrap.cxx").splitlines()
    sites = [(s.start, s.end) for s in out.manifest.sites if str(s.file) == "wrap.cxx"]
    assert sites == [(4, 6), (7, 7)]
    assert lines[5] == "    ->AllocateInitialized();" and lines[6] == "  image->AllocateInitialized();"


@needs_tools
def test_comment_dropped_by_an_earlier_helper_is_not_blamed_on_this_edit(fixture_graph):
    g = fixture_graph("allocate")
    path = g.repo / "a.cxx"
    path.write_text(path.read_text().replace("  // image->Allocate(true) stays in a comment\n", ""))
    out = run_allocate(g)
    assert "  ref.AllocateInitialized(); // zeroed\n" in out.read("a.cxx")
    assert not out.manifest.skipped()


def test_apply_requires_manifest(tmp_path):
    with pytest.raises(SystemExit):
        allocate_initialized.main(["--graph", str(tmp_path), "--repo", str(tmp_path), "--apply"])
