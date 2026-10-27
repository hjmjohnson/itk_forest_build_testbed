import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import member_init  # noqa: E402
from ioa.manifest import Manifest  # noqa: E402
from ioa.skip import Reason  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
TOOLS = ["clang-tidy", "run-clang-tidy", "clang-apply-replacements", "clang-format", "cmake", "ninja"]


def _tool(name: str) -> str | None:
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix and (Path(prefix) / "bin" / name).exists():
        return str(Path(prefix) / "bin" / name)
    return shutil.which(name)


pytestmark = pytest.mark.skipif(
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


def run_member_init(g: Graph, apply: bool, capsys=None) -> Result:
    manifest = g.repo.parent / "manifest.json"
    argv = ["--graph", str(g.build), "--repo", str(g.repo), "--manifest", str(manifest)]
    member_init.main(argv + (["--apply"] if apply else []))
    out = capsys.readouterr().out if capsys else ""
    return Result(g.repo, Manifest.read(manifest) if manifest.exists() else None, out)


def test_assignment_moves_to_initializer_list(fixture_graph):
    out = run_member_init(fixture_graph("basic"), apply=True)
    text = out.read("foo.cxx")
    assert ": m_A(1)\n  , m_B(2)" in text
    assert "m_A = 1;" not in text


def test_out_of_order_assignments_are_reordered_to_declaration_order(fixture_graph):
    text = run_member_init(fixture_graph("basic"), apply=True).read("foo.cxx")
    assert "Foo::Foo()\n  : m_A(0)\n  , m_B(0)\n  , m_C(0.5)\n{}" in text


def test_trailing_comment_travels_with_the_moved_assignment(fixture_graph):
    text = run_member_init(fixture_graph("basic"), apply=True).read("foo.cxx")
    assert "  , m_B(2) // the B\n" in text
    assert text.count("// the B") == 1


def test_applied_sites_are_recorded_with_post_edit_lines(fixture_graph):
    out = run_member_init(fixture_graph("basic"), apply=True)
    m = out.manifest
    assert m.kind == "member-init"
    assert m.skipped() == []
    assert {s.cls for s in m.sites} == {"prefer-member-initializer"}
    lines = out.read("foo.cxx").splitlines()
    for s in m.sites:
        assert s.file == Path("foo.cxx")
        assert any("m_" in lines[i - 1] for i in range(s.start, s.end + 1))


def test_dependent_out_of_order_initializer_is_skipped(fixture_graph):
    g = fixture_graph("order_violation")
    before = (g.repo / "foo.cxx").read_text()
    out = run_member_init(g, apply=True)
    assert [s.skipped for s in out.manifest.sites] == [Reason.ORDER_VIOLATION]
    assert out.read("foo.cxx") == before


def test_smart_pointer_member_gets_no_brace_init(fixture_graph):
    out = run_member_init(fixture_graph("smart_ptr"), apply=True)
    header = out.read("foo.h")
    assert "m_Reader{}" not in header
    assert "m_Reader{ }" not in header
    assert "m_Count{ 0 };" in header
    assert ": m_Reader()\n{" in out.read("foo.cxx")


def test_constant_initializers_become_default_member_initializers(fixture_graph):
    out = run_member_init(fixture_graph("comments"), apply=True)
    assert "int    m_Count{ 0 }; // reset on construction" in out.read("foo.h")
    assert "double m_Scale{ 1.5 };" in out.read("foo.h")
    assert "Foo::Foo(int a)\n  : m_Size(a) // from the caller\n{}" in out.read("foo.cxx")
    assert "reset on construction" not in out.read("foo.cxx")
    assert {s.cls for s in out.manifest.applied()} == {
        "prefer-member-initializer", "use-default-member-init"}


def test_doxygen_block_stays_above_member_that_gains_initializer(fixture_graph):
    header = run_member_init(fixture_graph("comments"), apply=True).read("foo.h")
    assert "  /** Number of reads since construction. */\n  int    m_Count{ 0 };" in header


def test_no_stranded_comments_after_apply(fixture_graph):
    from ioa.comments import check_hunks

    g = fixture_graph("comments")
    run_member_init(g, apply=True)
    assert check_hunks(_git(g.repo, "diff", "-U0")) == []


def test_without_apply_prints_plan_and_writes_nothing(fixture_graph, capsys):
    g = fixture_graph("basic")
    out = run_member_init(g, apply=False, capsys=capsys)
    assert out.manifest is None
    assert _git(g.repo, "status", "--porcelain") == ""
    assert "prefer-member-initializer foo.cxx 6" in out.stdout
