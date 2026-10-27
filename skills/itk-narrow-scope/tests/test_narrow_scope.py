import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import narrow_scope  # noqa: E402
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

    def read(self, name: str = "a.cxx") -> str:
        return (self.repo / name).read_text()

    def sites(self) -> list[tuple]:
        return [(s.start, s.end, s.skipped, s.note) for s in self.manifest.sites]


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


def run_narrow(g: Graph, apply: bool = True, capsys=None) -> Result:
    manifest = g.repo.parent / "manifest.json"
    argv = ["--graph", str(g.build), "--repo", str(g.repo), "--manifest", str(manifest)]
    assert narrow_scope.main(argv + (["--apply"] if apply else [])) == 0
    out = capsys.readouterr().out if capsys else ""
    return Result(g.repo, Manifest.read(manifest) if manifest.exists() else None, out)


def assert_formatted(g: Graph, name: str = "a.cxx") -> None:
    res = subprocess.run(
        [_tool("clang-format"), "--dry-run", "-Werror", "--style=file", name],
        cwd=g.repo, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr


def assert_builds(g: Graph) -> None:
    res = subprocess.run([_tool("ninja"), "-C", str(g.build)], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


def assert_unchanged(g: Graph) -> None:
    assert _git(g.repo, "status", "--porcelain") == ""


@needs_tools
def test_moves_into_single_using_block(fixture_graph):
    g = fixture_graph("into_block")
    out = run_narrow(g)
    text = out.read()
    assert "{\n  if (c > 0)\n  {\n    int total = 0;\n    total += c;\n" in text
    assert "  int total = 0;\n  if (c > 0)\n  {\n    total = c;\n  }\n  return total;\n" in text
    assert "    if (c > 1)\n    {\n      double scale = 2.0;\n      scale *= c;\n" in text
    assert out.manifest.kind == "narrow-scope"
    assert [(s.file, s.cls) for s in out.manifest.sites] == [(Path("a.cxx"), "narrow-scope")] * 2
    assert out.sites() == [(4, 6, None, "block"), (28, 32, None, "block")]
    assert_formatted(g)
    assert_builds(g)


@needs_tools
def test_moves_into_if_init_statement(fixture_graph):
    g = fixture_graph("init_statement")
    out = run_narrow(g)
    text = out.read()
    assert "{\n  if (const auto n = f(); n > 0)\n" in text
    assert "{\n  for (int i = 0; i < m; ++i)\n" in text
    assert "{\n  switch (const int v = k * 2; v)\n" in text
    assert out.sites() == [(7, 7, None, "init-statement"), (17, 17, None, "init-statement"),
                           (27, 27, None, "init-statement")]
    assert_formatted(g)
    assert_builds(g)


@needs_tools
def test_trivial_local_moves_into_loop_body(fixture_graph):
    g = fixture_graph("loop_trivial")
    out = run_narrow(g)
    assert ("{\n  double sum = 0.0;\n  for (int i = 0; i < m; ++i)\n  {\n"
            "    double                value;\n    itk::Point<double, 3> p;\n    value = i * 0.5;\n") in out.read()
    assert out.sites() == [(6, 9, None, "loop-body"), (6, 10, None, "loop-body")]
    assert_formatted(g)
    assert_builds(g)


@needs_tools
def test_loop_carried_value_is_skipped(fixture_graph):
    g = fixture_graph("loop_carried")
    out = run_narrow(g)
    assert out.manifest.sites[0].skipped == Reason.LOOP_CARRIED
    assert out.sites() == [(4, 4, Reason.LOOP_CARRIED, "")]
    assert_unchanged(g)


@needs_tools
def test_New_object_never_moves_into_loop(fixture_graph):
    g = fixture_graph("costly")
    out = run_narrow(g)
    assert out.manifest.sites[0].skipped == Reason.COSTLY_CONSTRUCT
    assert out.sites() == [(19, 19, Reason.COSTLY_CONSTRUCT, "call"),
                           (30, 30, Reason.COSTLY_CONSTRUCT, "non-trivial")]
    assert_unchanged(g)


@needs_tools
def test_goto_and_case_boundaries_are_skipped(fixture_graph):
    g = fixture_graph("goto_case")
    out = run_narrow(g)
    assert out.sites() == [(4, 4, Reason.GOTO_OR_CASE, ""), (21, 21, Reason.GOTO_OR_CASE, "")]
    assert_unchanged(g)


@needs_tools
def test_try_read_after_is_skipped(fixture_graph):
    g = fixture_graph("try_after")
    out = run_narrow(g)
    assert out.sites() == [(7, 7, Reason.TRY_READ_AFTER, ""), (22, 22, Reason.TRY_READ_AFTER, "")]
    assert_unchanged(g)


@needs_tools
def test_comments_above_and_trailing_travel_with_declaration(fixture_graph):
    g = fixture_graph("comments")
    out = run_narrow(g)
    text = out.read()
    assert "  if (c > 0)\n  {\n    // The running total.\n    int total = 0;\n    total = c * 2;\n" in text
    assert "  if (c > 0)\n  {\n    int total = 1; // starts at one\n    total += c;\n" in text
    assert ("  if (c > 0)\n  {\n    /** The scale.\n     *  Applied once. */\n    double scale = 3.0;\n"
            "    return static_cast<int>(scale * c);\n") in text
    assert "The running total" not in text.split("if (c > 0)")[0]
    assert out.sites() == [(4, 7, None, "block"), (17, 19, None, "block"), (29, 33, None, "block")]
    assert_formatted(g)
    assert_builds(g)


@needs_tools
def test_stranded_comment_reverts_file(fixture_graph, monkeypatch):
    g = fixture_graph("comments")
    real = narrow_scope.edits

    def lose_trailing(src, mv):
        return [(a, b, t.replace(" // starts at one", "")) for a, b, t in real(src, mv)]

    monkeypatch.setattr(narrow_scope, "edits", lose_trailing)
    out = run_narrow(g)
    assert_unchanged(g)
    assert [s.skipped for s in out.manifest.sites] == [Reason.COMMENT_STRANDED] * 3
    assert "// starts at one" in out.manifest.sites[1].note
    assert [(s.start, s.end) for s in out.manifest.sites] == [(5, 5), (17, 17), (31, 31)]


@needs_tools
def test_preprocessor_between_is_skipped(fixture_graph):
    g = fixture_graph("preprocessor")
    out = run_narrow(g)
    assert out.sites() == [(4, 4, Reason.PREPROCESSOR, "")]
    assert_unchanged(g)


@needs_tools
def test_address_taken_or_reference_capture_is_skipped(fixture_graph):
    g = fixture_graph("address_taken")
    out = run_narrow(g)
    assert out.sites() == [(7, 7, Reason.LOOP_CARRIED, "address-taken"),
                           (19, 19, Reason.LOOP_CARRIED, "address-taken")]
    assert_unchanged(g)


@needs_tools
def test_static_and_thread_local_are_skipped(fixture_graph):
    g = fixture_graph("static_local")
    out = run_narrow(g)
    assert out.sites() == [(4, 4, Reason.STATIC_LOCAL, ""), (16, 16, Reason.STATIC_LOCAL, "")]
    assert_unchanged(g)


@needs_tools
def test_uses_in_sibling_blocks_are_not_a_site(fixture_graph):
    g = fixture_graph("sibling_blocks")
    out = run_narrow(g)
    assert out.manifest.sites == []
    assert_unchanged(g)


@needs_tools
def test_dry_run_prints_counts_and_writes_nothing(fixture_graph, capsys):
    g = fixture_graph("costly")
    out = run_narrow(g, apply=False, capsys=capsys)
    assert out.manifest is None
    assert_unchanged(g)
    assert "skipped:costly-construct a.cxx 2" in out.stdout


@needs_tools
def test_dry_run_counts_planned_moves(fixture_graph, capsys):
    g = fixture_graph("into_block")
    out = run_narrow(g, apply=False, capsys=capsys)
    assert_unchanged(g)
    assert "narrow-scope a.cxx 2" in out.stdout


def test_apply_requires_manifest(tmp_path):
    with pytest.raises(SystemExit):
        narrow_scope.main(["--graph", str(tmp_path), "--repo", str(tmp_path), "--apply"])


@needs_tools
def test_declaration_never_moves_into_a_try_block(fixture_graph):
    g = fixture_graph("try_inside")
    out = run_narrow(g)
    assert out.sites() == [(11, 11, Reason.TRY_READ_AFTER, ""), (24, 24, Reason.TRY_READ_AFTER, "")]
    assert_unchanged(g)


@needs_tools
def test_pointer_into_nontrivial_value_escaping_the_target_is_skipped(fixture_graph):
    g = fixture_graph("escapes")
    out = run_narrow(g)
    assert out.sites() == [(11, 11, Reason.LOOP_CARRIED, "escapes")]
    assert_unchanged(g)


@needs_tools
def test_constructor_arguments_are_a_call(fixture_graph):
    g = fixture_graph("ctor_call")
    out = run_narrow(g)
    assert out.sites() == [(15, 15, Reason.COSTLY_CONSTRUCT, "side-effect")]
    assert_unchanged(g)


@needs_tools
def test_mutating_initializer_is_a_side_effect(fixture_graph):
    g = fixture_graph("mutating")
    out = run_narrow(g)
    assert out.sites() == [(7, 7, Reason.COSTLY_CONSTRUCT, "side-effect"),
                           (19, 19, Reason.COSTLY_CONSTRUCT, "side-effect")]
    assert_unchanged(g)


@needs_tools
def test_array_decay_and_data_pointer_escapes_are_skipped(fixture_graph):
    g = fixture_graph("escapes_trivial")
    out = run_narrow(g)
    assert out.sites() == [(9, 9, Reason.LOOP_CARRIED, "escapes"), (22, 22, Reason.LOOP_CARRIED, "escapes")]
    assert_unchanged(g)
