import os
import subprocess
import sys
from pathlib import Path

import pytest

from ioa.manifest import Manifest
from ioa.skip import Reason

FINDER = Path(__file__).parent.parent / "find_declare_then_init.py"
FIXTURES = Path(__file__).parent / "fixtures"
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


def test_existing_fixture_results_unchanged_by_new_classes(tmp_path):
    base = FIXTURES
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    runs = []
    for classes in ("assign,elem_zero", "assign,elem_zero,sized_ctor,stream_open,bool_branch,placeholder"):
        out = tmp_path / classes.replace(",", "_")
        out.mkdir()
        for name in ("Assign.cxx", "ElemZero.cxx"):
            (out / name).write_text((base / name).read_text())
        subprocess.run(
            [sys.executable, str(FINDER), "--classes", classes, "--apply", "Assign.cxx", "ElemZero.cxx"],
            cwd=out, env=env, capture_output=True, text=True, check=True,
        )
        runs.append({n: (out / n).read_text() for n in ("Assign.cxx", "ElemZero.cxx")})
    assert runs[0] == runs[1]
