import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ioa.manifest import Manifest
from ioa.skip import Reason

SKILL = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
CLANG_FORMAT = SKILL.parent / "itk-member-init" / "tests" / "fixtures" / ".clang-format"
MEMBER_INIT = SKILL / "patterns" / "in-class-member-init" / "transform.sh"
FILLBUFFER = SKILL / "patterns" / "fillbuffer-over-iterate" / "transform.sh"
LIB = SKILL.parent / "itk-init-over-assign" / "lib"


def _tool(name: str) -> str | None:
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix and (Path(prefix) / "bin" / name).exists():
        return str(Path(prefix) / "bin" / name)
    return shutil.which(name)


needs_tools = pytest.mark.skipif(_tool("clang-format") is None, reason="clang-format not available")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True, text=True)


@pytest.fixture
def tmp_repo(tmp_path):
    def make(name: str) -> Path:
        repo = tmp_path / name
        shutil.copytree(FIXTURES / name, repo)
        shutil.copy(CLANG_FORMAT, repo / ".clang-format")
        _git(repo, "init", "-q")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "fixture")
        return repo

    return make


def transform(script: Path, repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(LIB))
    return subprocess.run(["bash", str(script), str(repo), *args], check=True,
                          capture_output=True, text=True, env=env)


@needs_tools
def test_transform_sh_writes_manifest(tmp_repo, tmp_path):
    repo = tmp_repo("member_init")
    out = tmp_path / "m.json"
    transform(MEMBER_INIT, repo, "--apply", "--manifest", str(out), "--graph", str(tmp_path))
    m = Manifest.read(out)
    assert m.kind == "member-default-init"
    assert [(str(s.file), s.start, s.end, s.cls, s.skipped) for s in m.sites] == [
        ("itkThing.h", 11, 12, "in-class-member-init", None)]
    text = (repo / "itkThing.h").read_text()
    assert "  int        m_Count{};\n  double     m_Scale{}; // pixels\n  static int m_Shared;\n" in text


@needs_tools
def test_member_init_relative_manifest_path_is_resolved_before_cd(tmp_repo, tmp_path):
    repo = tmp_repo("member_init")
    subprocess.run(["bash", str(MEMBER_INIT), str(repo), "--apply", "--manifest", "rel.json"],
                   check=True, capture_output=True, text=True, cwd=tmp_path,
                   env=dict(os.environ, PYTHONPATH=str(LIB)))
    assert Manifest.read(tmp_path / "rel.json").kind == "member-default-init"


def test_member_init_dry_run_writes_nothing(tmp_repo, tmp_path):
    repo = tmp_repo("member_init")
    before = (repo / "itkThing.h").read_text()
    res = transform(MEMBER_INIT, repo, "--manifest", str(tmp_path / "m.json"))
    assert "WOULD EDIT: itkThing.h" in res.stdout
    assert (repo / "itkThing.h").read_text() == before and not (tmp_path / "m.json").exists()


@needs_tools
def test_fillbuffer_rewrites_only_the_safe_shapes(tmp_repo, tmp_path):
    repo = tmp_repo("fillbuffer")
    transform(FILLBUFFER, repo, "--apply", "--manifest", str(tmp_path / "m.json"))
    text = (repo / "a.cxx").read_text()
    assert ("  // Clear the output.\n  output->FillBuffer(outputPixel);\n\n"
            "  image->FillBuffer(static_cast<PixelType>(0));\n\n") in text
    assert "    idx.Set(idx.GetIndex()[0]);\n" in text
    assert "  for (IteratorType sub(image, crop); !sub.IsAtEnd(); ++sub)\n" in text


@needs_tools
def test_fillbuffer_manifest_has_applied_and_skipped_sites(tmp_repo, tmp_path):
    repo = tmp_repo("fillbuffer")
    transform(FILLBUFFER, repo, "--apply", "--manifest", str(tmp_path / "m.json"))
    m = Manifest.read(tmp_path / "m.json")
    a = [(s.start, s.end, s.cls, s.skipped, s.note) for s in m.sites if str(s.file) == "a.cxx"]
    assert a == [
        (9, 9, "fillbuffer-over-iterate", None, ""),
        (11, 11, "fillbuffer-over-iterate", None, ""),
        (13, 16, "fillbuffer-over-iterate", Reason.LOOP_CARRIED, "not-fill-shape"),
        (18, 21, "fillbuffer-over-iterate", Reason.LOOP_CARRIED, "not-fill-shape"),
    ]


@needs_tools
def test_fillbuffer_loop_holding_a_comment_is_skipped(tmp_repo, tmp_path):
    repo = tmp_repo("fillbuffer")
    before = (repo / "b.cxx").read_text()
    transform(FILLBUFFER, repo, "--apply", "--manifest", str(tmp_path / "m.json"))
    assert (repo / "b.cxx").read_text() == before
    b = [s for s in Manifest.read(tmp_path / "m.json").sites if str(s.file) == "b.cxx"]
    assert [(s.start, s.end, s.skipped, s.note) for s in b] == [(6, 9, Reason.COMMENT_STRANDED, "comment-in-loop")]


@needs_tools
def test_helper_restores_a_file_whose_edit_strands_a_comment(tmp_repo, tmp_path, monkeypatch):
    repo = tmp_repo("member_init")
    path = repo / "itkThing.h"
    orig = tmp_path / "orig.h"
    shutil.copy(path, orig)
    before = path.read_text()
    path.write_text(before.replace("  double     m_Scale; // pixels\n", "  double     m_Scale{};\n"))
    monkeypatch.syspath_prepend(str(SKILL / "lib"))
    import manifest_from_diff

    m = manifest_from_diff.build(repo, "in-class-member-init", [(orig, "itkThing.h")], None)
    assert path.read_text() == before
    assert [(s.start, s.end, s.skipped, s.note) for s in m.sites] == [
        (12, 12, Reason.COMMENT_STRANDED, "// pixels")]


def test_fillbuffer_dry_run_writes_nothing(tmp_repo, tmp_path):
    repo = tmp_repo("fillbuffer")
    before = (repo / "a.cxx").read_text()
    res = transform(FILLBUFFER, repo, "--manifest", str(tmp_path / "m.json"))
    assert "WOULD EDIT: a.cxx" in res.stdout and "files_changed: 1  skipped_loops: 3" in res.stdout
    assert (repo / "a.cxx").read_text() == before and not (tmp_path / "m.json").exists()


def test_invariant_allows_only_type_conversions_and_pure_calls(monkeypatch):
    monkeypatch.syspath_prepend(str(FILLBUFFER.parent))
    import fill_loops

    assert fill_loops.invariant("PixelType(0)", "it")
    assert fill_loops.invariant("static_cast<PixelType>(0)", "it")
    assert not fill_loops.invariant("helper.MakeType(0)", "it")
    assert not fill_loops.invariant("factory->NewType()", "it")
    assert not fill_loops.invariant("nextType(1)", "it")


@needs_tools
def test_helper_keeps_the_skip_reason_of_a_restored_file(tmp_repo, tmp_path, monkeypatch):
    repo = tmp_repo("member_init")
    path = repo / "itkThing.h"
    orig = tmp_path / "orig.h"
    shutil.copy(path, orig)
    path.write_text(path.read_text().replace("  double     m_Scale; // pixels\n", "  double     m_Scale{};\n"))
    skips = tmp_path / "skips.tsv"
    skips.write_text("itkThing.h\t13\t13\tloop-carried\tnot-fill-shape\n")
    monkeypatch.syspath_prepend(str(SKILL / "lib"))
    import manifest_from_diff

    m = manifest_from_diff.build(repo, "x", [(orig, "itkThing.h")], skips)
    assert [(s.start, s.skipped, s.note) for s in m.sites] == [
        (12, Reason.COMMENT_STRANDED, "// pixels"), (13, Reason.LOOP_CARRIED, "not-fill-shape")]


@needs_tools
def test_smart_pointer_members_get_no_default_initializer(tmp_repo, tmp_path):
    repo = tmp_repo("member_init")
    out = tmp_path / "m.json"
    transform(MEMBER_INIT, repo, "--apply", "--manifest", str(out))
    holder = (repo / "itkThing.h").read_text().split("class Holder")[1]
    assert "{}" not in holder
    assert [s.start for s in Manifest.read(out).sites] == [11]
