import json
import os
import time
from pathlib import Path

import pytest

from ioa import compile_commands as cc
from ioa.compile_commands import command_for, find_graph, including_tus


def test_including_tus_capped_and_one_per_top_dir(fake_graph, repo_root):
    tus = including_tus(Path("Common/foo.h"), fake_graph, repo_root, cap=8)
    assert len(tus) == 8 and len({t.parts[0] for t in tus[:3]}) == 3


def test_header_with_no_including_tu_returns_empty(fake_graph, repo_root):
    assert including_tus(Path("Dead/dead.hxx"), fake_graph, repo_root) == []
    assert including_tus(Path("Dead/other.h"), fake_graph, repo_root) == []


def test_absolute_header_under_root_is_found(fake_graph, repo_root):
    assert including_tus(repo_root / "Common" / "one.h", fake_graph, repo_root) == [
        Path("Common/tu0.cxx")
    ]


def test_command_for_splits_command(fake_graph, repo_root):
    argv = command_for(Path("IO/tu0.cxx"), fake_graph, repo_root)
    assert argv[0] == "c++" and "-c" in argv and argv[-1] == "IO/tu0.cxx.o"


def test_command_for_prefers_arguments(tmp_path):
    g = tmp_path / "g"
    g.mkdir()
    (g / "compile_commands.json").write_text(
        json.dumps([{"directory": str(g), "file": "a.cxx", "arguments": ["cc", "a b"]}])
    )
    assert command_for(Path("a.cxx"), g, g) == ["cc", "a b"]


def test_command_for_unknown_tu_raises(fake_graph, repo_root):
    with pytest.raises(KeyError):
        command_for(Path("Nope/x.cxx"), fake_graph, repo_root)


NINJA_TEXT = """\
Common/tu0.cxx.o: #deps 3, deps mtime 1 (VALID)
    /usr/include/stdio.h
    ../../src/Common/foo.h
    ../../src/Common/bar.h

IO/tu0.cxx.o: #deps 1, deps mtime 1 (VALID)
    ../../src/Common/foo.h

stale.o: deps not found
"""


def test_parse_ninja_deps():
    assert cc.parse_ninja_deps(NINJA_TEXT) == {
        "Common/tu0.cxx.o": ["/usr/include/stdio.h", "../../src/Common/foo.h", "../../src/Common/bar.h"],
        "IO/tu0.cxx.o": ["../../src/Common/foo.h"],
    }


def test_cache_built_from_ninja_then_reused(fake_graph, repo_root, monkeypatch):
    (fake_graph / ".ioa-deps.json").unlink()
    (fake_graph / "build.ninja").write_text("")
    old = time.time() - 100
    os.utime(fake_graph / "build.ninja", (old, old))
    calls = []

    def fake_run(graph):
        calls.append(graph)
        return NINJA_TEXT

    monkeypatch.setattr(cc, "run_ninja_deps", fake_run)
    got = including_tus(Path("Common/foo.h"), fake_graph, repo_root)
    assert got == [Path("Common/tu0.cxx"), Path("IO/tu0.cxx")]
    assert (fake_graph / ".ioa-deps.json").exists()
    including_tus(Path("Common/foo.h"), fake_graph, repo_root)
    assert len(calls) == 1


def test_stale_cache_rebuilt(fake_graph, repo_root, monkeypatch):
    (fake_graph / "build.ninja").write_text("")
    old = time.time() - 100
    os.utime(fake_graph / ".ioa-deps.json", (old, old))
    monkeypatch.setattr(cc, "run_ninja_deps", lambda g: "")
    assert including_tus(Path("Common/foo.h"), fake_graph, repo_root) == []


def test_find_graph_prefers_repo_named_dir(tmp_path):
    for d in ("SlicerExecutionModel-Release-build", "BRAINSTools-Release-EPRelease-build"):
        (tmp_path / "build" / d).mkdir(parents=True)
        (tmp_path / "build" / d / "compile_commands.json").write_text("[]")
    assert find_graph(tmp_path / "build", "BRAINSTools").name == "BRAINSTools-Release-EPRelease-build"


def test_find_graph_falls_back_to_shallowest(tmp_path):
    deep = tmp_path / "build" / "x" / "y"
    deep.mkdir(parents=True)
    (deep / "compile_commands.json").write_text("[]")
    top = tmp_path / "build" / "z"
    top.mkdir()
    (top / "compile_commands.json").write_text("[]")
    assert find_graph(tmp_path / "build", "Nope") == top


def test_find_graph_depth_limit_and_missing(tmp_path):
    deep = tmp_path / "build" / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "compile_commands.json").write_text("[]")
    with pytest.raises(FileNotFoundError):
        find_graph(tmp_path / "build", "R")


def test_build_dir_tu_sorts_last_and_forms_no_group(fake_graph, repo_root):
    tus = including_tus(Path("Common/foo.h"), fake_graph, repo_root, cap=100)
    assert len(tus) == 21
    assert tus[-1] == (fake_graph / "moc_gen.cxx").resolve()
    assert len({t.parts[0] for t in tus[:3]}) == 3
    assert all(not t.is_absolute() for t in tus[:-1])


def test_command_for_build_dir_tu(fake_graph, repo_root):
    argv = command_for(fake_graph / "moc_gen.cxx", fake_graph, repo_root)
    assert argv[-1] == "moc_gen.cxx.o"


def test_symlinked_source_tree(tmp_path):
    real = tmp_path / "real" / "repo"
    (real / "Common").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real")
    graph = tmp_path / "build"
    graph.mkdir()
    via_link = link / "repo" / "Common" / "a.cxx"
    (graph / "compile_commands.json").write_text(
        json.dumps(
            [{"directory": str(graph), "command": "c++ -c a", "file": str(via_link), "output": "a.o"}]
        )
    )
    root = link / "repo"
    assert command_for(Path("Common/a.cxx"), graph, root) == ["c++", "-c", "a"]
    deps = "a.o: #deps 1, deps mtime 1 (VALID)\n    " + str(real / "Common/h.h") + "\n"
    import ioa.compile_commands as m

    orig = m.run_ninja_deps
    m.run_ninja_deps = lambda g: deps
    try:
        assert including_tus(Path("Common/h.h"), graph, root) == [Path("Common/a.cxx")]
        assert including_tus(root / "Common" / "h.h", graph, root) == [Path("Common/a.cxx")]
    finally:
        m.run_ninja_deps = orig


def test_corrupt_cache_falls_back_to_rebuild(fake_graph, repo_root, monkeypatch):
    (fake_graph / ".ioa-deps.json").write_text("{not json")
    monkeypatch.setattr(cc, "run_ninja_deps", lambda g: "")
    assert including_tus(Path("Common/foo.h"), fake_graph, repo_root) == []
    assert json.loads((fake_graph / ".ioa-deps.json").read_text()) == {}
    assert not (fake_graph / ".ioa-deps.json.tmp").exists()


def test_missing_ninja_is_a_distinct_error(fake_graph, repo_root, monkeypatch):
    (fake_graph / ".ioa-deps.json").unlink()
    monkeypatch.setenv("PATH", str(fake_graph))
    with pytest.raises(cc.NinjaNotFoundError):
        including_tus(Path("Common/foo.h"), fake_graph, repo_root)
