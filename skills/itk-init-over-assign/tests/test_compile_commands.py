import json
import os
import time
from pathlib import Path

import pytest

from ioa import compile_commands as cc
from ioa.compile_commands import command_for, find_graph, including_tus


def test_including_tus_capped_and_one_per_top_dir(fake_graph):
    tus = including_tus(Path("Common/foo.h"), fake_graph, cap=8)
    assert len(tus) == 8 and len({t.parts[0] for t in tus[:3]}) == 3


def test_header_with_no_including_tu_returns_empty(fake_graph):
    assert including_tus(Path("Dead/dead.hxx"), fake_graph) == []
    assert including_tus(Path("Dead/other.h"), fake_graph) == []


def test_absolute_header_under_root_is_found(fake_graph, tmp_path):
    assert including_tus(tmp_path / "src" / "Common" / "one.h", fake_graph) == [
        Path("Common/tu0.cxx")
    ]


def test_command_for_splits_command(fake_graph):
    argv = command_for(Path("IO/tu0.cxx"), fake_graph)
    assert argv[0] == "c++" and "-c" in argv and argv[-1] == "IO/tu0.cxx.o"


def test_command_for_prefers_arguments(tmp_path):
    g = tmp_path / "g"
    g.mkdir()
    (g / "compile_commands.json").write_text(
        json.dumps([{"directory": str(g), "file": "a.cxx", "arguments": ["cc", "a b"]}])
    )
    assert command_for(Path("a.cxx"), g) == ["cc", "a b"]


def test_command_for_unknown_tu_raises(fake_graph):
    with pytest.raises(KeyError):
        command_for(Path("Nope/x.cxx"), fake_graph)


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


def test_cache_built_from_ninja_then_reused(fake_graph, monkeypatch):
    (fake_graph / ".ioa-deps.json").unlink()
    (fake_graph / "build.ninja").write_text("")
    old = time.time() - 100
    os.utime(fake_graph / "build.ninja", (old, old))
    calls = []

    def fake_run(graph):
        calls.append(graph)
        return NINJA_TEXT

    monkeypatch.setattr(cc, "run_ninja_deps", fake_run)
    got = including_tus(Path("Common/foo.h"), fake_graph)
    assert got == [Path("Common/tu0.cxx"), Path("IO/tu0.cxx")]
    assert (fake_graph / ".ioa-deps.json").exists()
    including_tus(Path("Common/foo.h"), fake_graph)
    assert len(calls) == 1


def test_stale_cache_rebuilt(fake_graph, monkeypatch):
    (fake_graph / "build.ninja").write_text("")
    old = time.time() - 100
    os.utime(fake_graph / ".ioa-deps.json", (old, old))
    monkeypatch.setattr(cc, "run_ninja_deps", lambda g: "")
    assert including_tus(Path("Common/foo.h"), fake_graph) == []


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
