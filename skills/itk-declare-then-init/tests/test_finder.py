import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ioa.manifest import Manifest
from ioa.skip import Reason

FINDER = Path(__file__).parent.parent / "find_declare_then_init.py"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tree(tmp_path) -> Path:
    root = tmp_path / "src"
    shutil.copytree(FIXTURES, root)
    return root


def run_finder(root: Path, *args: str, check: bool = True):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, str(FINDER), *args],
        cwd=root, env=env, capture_output=True, text=True, check=check,
    )


def run_manifest(root: Path, *args: str) -> Manifest:
    out = root.parent / "manifest.json"
    run_finder(root, *args, "--manifest", str(out))
    return Manifest.read(out)


def test_classes_flag_runs_only_listed_classes(tree):
    m = run_manifest(tree, "--classes", "assign,elem_zero", "--apply", "-r", ".")
    assert m.kind == "local-init"
    assert {s.cls for s in m.applied()} == {"assign", "elem_zero"}
    assert "SizeType size{};" in (tree / "ElemZero.cxx").read_text()
    assert "size[1]" not in (tree / "ElemZero.cxx").read_text()


def test_classes_flag_excludes_unlisted_classes(tree):
    m = run_manifest(tree, "--classes", "elem_zero", "--apply", "-r", ".")
    assert {s.cls for s in m.sites} == {"elem_zero"}
    assert "a = ComputeA();" in (tree / "Assign.cxx").read_text()


def test_classes_and_pattern_together_is_an_error(tree):
    r = run_finder(tree, "--classes", "assign", "--pattern", "assign", "-r", ".", check=False)
    assert r.returncode != 0


def test_preprocessor_gap_is_skipped_with_reason(tree):
    m = run_manifest(tree, "--classes", "assign", "-r", ".")
    assert any(s.skipped == Reason.PREPROCESSOR for s in m.sites)


def test_sites_track_lines_after_edit(tree):
    m = run_manifest(tree, "--classes", "assign", "--apply", "-r", ".")
    lines = (tree / "Assign.cxx").read_text().splitlines()
    a = next(s for s in m.applied() if s.file == Path("Assign.cxx"))
    assert lines[a.start - 1] == "  int a = ComputeA();" and a.end == a.start
    b = next(s for s in m.skipped() if s.file == Path("Assign.cxx"))
    assert lines[b.start - 1] == "  int b;"


def test_graph_flag_scans_compile_commands_files_only(tree, tmp_path):
    graph = tmp_path / "build" / "src-build"
    graph.mkdir(parents=True)
    entries = [
        {"directory": str(graph), "command": f"c++ -c {tree / n}", "file": str(tree / n)}
        for n in ("Assign.cxx", "ElemZero.cxx")
    ]
    (graph / "compile_commands.json").write_text(json.dumps(entries))
    (graph / ".ioa-deps.json").write_text(json.dumps({"Hdr.h": ["Assign.cxx"]}))
    m = run_manifest(
        tree, "--graph", str(tmp_path / "build"), "--classes", "assign", "--apply"
    )
    files = {str(s.file) for s in m.sites}
    assert "NotInBuild.cxx" not in files
    assert {"Assign.cxx", "Hdr.h"} <= files
    assert "z = ComputeZ();" in (tree / "NotInBuild.cxx").read_text()


def test_pattern_alone_keeps_interactive_output(tree):
    r = run_finder(tree, "--pattern", "elem_zero", "-r", ".")
    assert "[elem_zero] SizeType size;" in r.stdout
    assert "Found 1 pattern(s)" in r.stderr
