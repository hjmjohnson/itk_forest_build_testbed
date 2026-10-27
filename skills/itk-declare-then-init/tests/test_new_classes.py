import os
import subprocess
import sys
from pathlib import Path

import pytest

from ioa.manifest import Manifest
from ioa.skip import Reason

FINDER = Path(__file__).parent.parent / "find_declare_then_init.py"
FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"
CLASSES = ["sized_ctor", "stream_open", "bool_branch", "placeholder"]


def fixture(cls: str, name: str) -> str:
    return (FIXTURES / cls / f"{name}.cxx").read_text()


def run_class(tmp_path: Path, cls: str, text: str) -> tuple[Manifest, str]:
    src = tmp_path / "t.cxx"
    src.write_text(text)
    out = tmp_path / "manifest.json"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    subprocess.run(
        [sys.executable, str(FINDER), "--classes", cls, "--apply", "--manifest", str(out),
         "--repo-root", str(tmp_path), str(src)],
        env=env, capture_output=True, text=True, check=True,
    )
    return Manifest.read(out), src.read_text()


@pytest.mark.parametrize("cls", CLASSES)
def test_before_becomes_after(tmp_path, cls):
    m, text = run_class(tmp_path, cls, fixture(cls, "before"))
    assert text == fixture(cls, "after")
    assert m.skipped() == []


def test_sized_ctor_covers_resize_set_size_SetSize(tmp_path):
    m, _ = run_class(tmp_path, "sized_ctor", fixture("sized_ctor", "before"))
    assert len(m.applied()) == 3


def test_sized_ctor_vector_bool_declined_as_init_list_ctor(tmp_path):
    src = fixture("sized_ctor", "skip_vector_bool")
    m, text = run_class(tmp_path, "sized_ctor", src)
    assert text == src and m.applied() == []
    assert [(s.skipped, s.note) for s in m.skipped()] == [(Reason.INIT_LIST_CTOR, "vector-bool")]


@pytest.mark.parametrize("cls", ["sized_ctor", "stream_open"])
def test_statement_between_declaration_and_call_is_left_alone(tmp_path, cls):
    src = fixture(cls, "skip_not_next")
    m, text = run_class(tmp_path, cls, src)
    assert text == src and m.applied() == []


def test_stream_open_keeps_mode_argument(tmp_path):
    _, text = run_class(tmp_path, "stream_open", fixture("stream_open", "before"))
    assert "std::ofstream f(x, std::ios::binary);" in text


def test_placeholder_skips_conditional_assignment(tmp_path):
    src = fixture("placeholder", "skip_conditional")
    m, text = run_class(tmp_path, "placeholder", src)
    assert text == src and m.applied() == []


def test_placeholder_skips_read_before_assignment_and_self_reference(tmp_path):
    src = fixture("placeholder", "skip_read_between")
    m, text = run_class(tmp_path, "placeholder", src)
    assert text == src and m.applied() == []


def test_bool_branch_skips_when_else(tmp_path):
    src = fixture("bool_branch", "skip_else")
    m, text = run_class(tmp_path, "bool_branch", src)
    assert text == src and m.applied() == []
    assert [s.note for s in m.skipped()] == ["else-branch"]


def test_bool_branch_later_write_is_loop_carried(tmp_path):
    src = fixture("bool_branch", "skip_later_write")
    m, text = run_class(tmp_path, "bool_branch", src)
    assert text == src and m.applied() == []
    assert [(s.skipped, s.note) for s in m.skipped()] == [(Reason.LOOP_CARRIED, "later-write")]


OLD_CLASSES = "fill_zero,fill_nonzero,elem_same,elem_diff,elem_zero,assign,setsize_fill"
GOLDEN_FILES = ["Assign.cxx", "ElemZero.cxx", "Hdr.h", "NotInBuild.cxx"]


@pytest.mark.parametrize("classes", [OLD_CLASSES, OLD_CLASSES + "," + ",".join(CLASSES)])
def test_existing_fixture_results_match_pre_task6_goldens(tmp_path, classes):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    for name in GOLDEN_FILES:
        (tmp_path / name).write_text((FIXTURES / name).read_text())
    subprocess.run(
        [sys.executable, str(FINDER), "--classes", classes, "--apply", *GOLDEN_FILES],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=True,
    )
    for name in GOLDEN_FILES:
        assert (tmp_path / name).read_text() == (GOLDEN / name).read_text()


def test_placeholder_declines_auto_as_narrowing(tmp_path):
    src = fixture("placeholder", "skip_auto")
    m, text = run_class(tmp_path, "placeholder", src)
    assert text == src and m.applied() == []
    assert [(s.skipped, s.note) for s in m.skipped()] == [(Reason.NARROWING, "auto-type")]


def test_placeholder_skips_same_line_conditional(tmp_path):
    src = fixture("placeholder", "skip_conditional_same_line")
    m, text = run_class(tmp_path, "placeholder", src)
    assert text == src and m.applied() == []


@pytest.mark.parametrize(
    ("name", "note"),
    [("skip_by_ref_arg", "by-ref-arg"), ("skip_compound_write", "later-write"),
     ("skip_self_or", "later-write")],
)
def test_bool_branch_declines_later_use_hazards(tmp_path, name, note):
    src = fixture("bool_branch", name)
    m, text = run_class(tmp_path, "bool_branch", src)
    assert text == src and m.applied() == []
    assert [(s.skipped, s.note) for s in m.skipped()] == [(Reason.LOOP_CARRIED, note)]
