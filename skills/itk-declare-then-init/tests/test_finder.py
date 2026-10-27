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
    m = run_manifest(tree, "--classes", "assign", "--apply", "-r", ".")
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


def test_manifest_without_apply_is_an_error_and_writes_nothing(tree):
    out = tree.parent / "manifest.json"
    r = run_finder(tree, "--classes", "assign", "--manifest", str(out), "-r", ".", check=False)
    assert r.returncode != 0 and "--manifest requires --apply" in r.stderr
    assert not out.exists()


def test_path_outside_repo_root_fails_before_any_edit(tree):
    out = tree.parent / "manifest.json"
    sub = tree / "sub"
    sub.mkdir()
    before = (tree / "Assign.cxx").read_text()
    r = run_finder(
        tree, "--classes", "assign", "--apply", "--manifest", str(out),
        "--repo-root", str(sub), str(tree / "Assign.cxx"), check=False,
    )
    assert r.returncode != 0 and "Assign.cxx" in r.stderr and "outside" in r.stderr
    assert (tree / "Assign.cxx").read_text() == before
    assert not out.exists()


def test_indent_mismatch_in_elem_sequence_yields_one_skipped_site(tree):
    (tree / "Mismatch.cxx").write_text(
        "void\nM()\n{\n  SizeType size;\n    size[0] = 0;\n    size[1] = 0;\n}\n"
    )
    only = tree / "only"
    only.mkdir()
    (tree / "Mismatch.cxx").rename(only / "Mismatch.cxx")
    m = run_manifest(
        tree, "--classes", "elem_same,elem_diff,elem_zero", "--apply", "-r", "only"
    )
    assert [(s.cls, s.skipped, s.note) for s in m.sites] == [
        ("elem_zero", Reason.LOOP_CARRIED, "indent-mismatch")
    ]


def test_multiline_removal_shifts_earlier_recorded_site(tree):
    (tree / "Shift.cxx").write_text(
        "void\nG()\n{\n  SizeType size;\n  size[0] = 0;\n  size[1] = 0;\n"
        "  size[2] = 0;\n  int q;\n  q = Compute();\n}\n"
    )
    m = run_manifest(tree, "--classes", "assign,elem_zero", "--apply", "Shift.cxx")
    lines = (tree / "Shift.cxx").read_text().splitlines()
    q = next(s for s in m.applied() if s.cls == "assign")
    assert lines[q.start - 1] == "  int q = Compute();"
    z = next(s for s in m.applied() if s.cls == "elem_zero")
    assert lines[z.start - 1] == "  SizeType size{};"


def test_statement_between_declaration_and_assignment_is_skipped(tree):
    src = (
        "void\nH(Reader * reader)\n{\n  SpacingType x;\n  reader->Update();\n"
        "  x = reader->GetOutput()->GetSpacing();\n  Use(x);\n}\n"
    )
    only = tree / "only"
    only.mkdir()
    (only / "Gap.cxx").write_text(src)
    m = run_manifest(tree, "--classes", "assign", "--apply", "-r", "only")
    assert (only / "Gap.cxx").read_text() == src
    assert [(s.cls, s.skipped, s.note, s.start) for s in m.sites] == [
        ("assign", Reason.LOOP_CARRIED, "gap-statement", 4)
    ]


def test_comment_only_gap_still_applies(tree):
    only = tree / "only"
    only.mkdir()
    (only / "Gap.cxx").write_text("void\nH()\n{\n  int x;\n  // why\n\n  x = F();\n}\n")
    m = run_manifest(tree, "--classes", "assign", "--apply", "-r", "only")
    assert [s.skipped for s in m.sites] == [None]
    assert "  int x = F();" in (only / "Gap.cxx").read_text()


def test_interactive_pattern_mode_keeps_max_gap_behavior(tree):
    only = tree / "only"
    only.mkdir()
    (only / "Gap.cxx").write_text("void\nH()\n{\n  int x;\n  Prep();\n  x = F();\n}\n")
    r = run_finder(tree, "--pattern", "assign", "-r", "only")
    assert "[assign]" in r.stdout and "gap=1" in r.stdout


def test_trailing_comment_of_removed_line_moves_to_declaration(tree):
    only = tree / "only"
    only.mkdir()
    (only / "C.cxx").write_text("void\nH()\n{\n  int x;\n  x = F(); // why\n}\n")
    m = run_manifest(tree, "--classes", "assign", "--apply", "-r", "only")
    assert [s.skipped for s in m.sites] == [None]
    assert "  int x = F(); // why\n}" in (only / "C.cxx").read_text()


def test_two_trailing_comments_decline_the_site(tree):
    only = tree / "only"
    only.mkdir()
    src = "void\nH()\n{\n  SizeType s;\n  s[0] = 1; // a\n  s[1] = 2; // b\n}\n"
    (only / "C.cxx").write_text(src)
    m = run_manifest(tree, "--classes", "elem_diff", "--apply", "-r", "only")
    assert [(s.skipped, s.note) for s in m.sites] == [(Reason.COMMENT_STRANDED, "comment-stranded")]
    assert (only / "C.cxx").read_text() == src


def test_applied_site_spans_its_comment_gap(tree):
    only = tree / "only"
    only.mkdir()
    (only / "C.cxx").write_text("void\nH()\n{\n  int x;\n  // a\n  // b\n  x = F();\n}\n")
    m = run_manifest(tree, "--classes", "assign", "--apply", "-r", "only")
    assert [(s.start, s.end) for s in m.sites] == [(4, 6)]


@pytest.mark.parametrize("note,reason", [
    ("gap-statement", Reason.LOOP_CARRIED), ("indent-mismatch", Reason.LOOP_CARRIED),
    ("else-branch", Reason.LOOP_CARRIED), ("later-write", Reason.LOOP_CARRIED),
    ("by-ref-arg", Reason.LOOP_CARRIED), ("comment-stranded", Reason.COMMENT_STRANDED),
    ("vector-bool", Reason.INIT_LIST_CTOR), ("auto-type", Reason.NARROWING),
])
def test_declined_note_is_the_check_and_reason_matches_the_table(note, reason):
    sys.path.insert(0, str(FINDER.parent))
    import find_declare_then_init as f

    lines = ["  int x;\n", "  Prep();\n", "  x = 1;\n"]
    found = f.declined_finding("a.cxx", 0, 2, "int", "x", "assign", note)
    assert f.skip_reason(found, lines) == (reason, note)
