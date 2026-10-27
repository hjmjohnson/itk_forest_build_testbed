import subprocess
import sys
from pathlib import Path

import pytest

from ioa import gate, partition
from ioa.gate import GateResult
from ioa.manifest import Manifest, Site
from ioa.partition import apply, plan
from ioa.skip import Reason

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "partition"))
import make_repo  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def hunk_at(plans, name, line):
    for p in plans:
        for h in p.hunks:
            if h.file.name == name and line in h.lines():
                return h
    return None


@pytest.fixture
def repo(tmp_path):
    return make_repo.build(tmp_path)


@pytest.fixture
def gate_calls(monkeypatch):
    calls = []

    def fake(graph, files, repo_root):
        calls.append((list(files), {f: (repo_root / f).read_text() for f in files}))
        return GateResult(ok=True)

    monkeypatch.setattr(gate, "run", fake)
    return calls


@pytest.fixture
def fake_gate_ok(gate_calls):
    return gate_calls


@pytest.fixture
def fake_gate_fail_b(monkeypatch):
    def fake(graph, files, repo_root):
        failed = {f: "error: boom" for f in files if f.name == "b.cxx"}
        return GateResult(ok=not failed, failed=failed)

    monkeypatch.setattr(gate, "run", fake)


def test_hunk_claimed_by_two_manifests_goes_to_later_stage(repo):
    plans = plan(repo.path, [repo.m_local, repo.m_helpers])
    assert hunk_at(plans, "a.cxx", 40).kind == "itk-helpers"
    assert hunk_at(plans, "a.cxx", 10).kind == "local-init"


def test_uncovered_hunk_attaches_to_nearest_stage_above(repo):
    plans = plan(repo.path, [repo.m_local, repo.m_helpers])
    assert hunk_at(plans, "b.cxx", 99) is not None  # clang-format spill
    assert hunk_at(plans, "b.cxx", 99).kind == "local-init"


def test_uncovered_hunk_with_nothing_above_attaches_below(repo):
    m = Manifest("local-init", [Site(Path("b.cxx"), 99, 99, "local-init", "int")])
    plans = plan(repo.path, [m])
    assert hunk_at(plans, "b.cxx", 20).kind == "local-init"


def test_plans_follow_fixed_kind_order_with_subjects(repo):
    plans = plan(repo.path, [repo.m_helpers, repo.m_local])
    assert [p.kind for p in plans] == ["local-init", "itk-helpers"]
    assert plans[0].message == "STYLE: Initialize locals at declaration instead of assigning"
    assert plans[1].message == "STYLE: Use Filled, MakeFilled, and AllocateInitialized helpers"


def test_file_without_covered_hunk_goes_to_first_kind_with_note(repo):
    plans = plan(repo.path, [repo.m_local, repo.m_helpers])
    assert hunk_at(plans, "c.cxx", 5).kind == "local-init"
    assert any("c.cxx" in n for n in plans[0].notes)


def test_unknown_kind_is_rejected(repo):
    with pytest.raises(ValueError):
        plan(repo.path, [Manifest("bogus", [])])


def test_apply_reverts_hunk_that_strands_comment(repo, fake_gate_ok):
    res = apply(repo.path, plan(repo.path, [repo.m_todo_bad])[0], repo.graph)
    assert res.reverted and res.reverted[0].skipped == Reason.COMMENT_STRANDED
    assert "// TODO: keep this" in git(repo.path, "show", "HEAD:b.cxx")
    assert "// TODO: keep this" in (repo.path / "b.cxx").read_text()
    assert git(repo.path, "diff", "HEAD") == ""


def test_apply_reverts_hunk_that_fails_gate(repo, fake_gate_fail_b):
    res = apply(repo.path, plan(repo.path, [repo.m_local])[0], repo.graph)
    assert {s.file.name for s in res.reverted} == {"b.cxx"}
    assert all(s.file.name == "b.cxx" for s in res.reverted)
    assert {s.skipped for s in res.reverted} >= {Reason.GATE_FAILED}
    assert res.sha is not None
    assert git(repo.path, "diff", "HEAD", "--", "b.cxx") == ""
    assert "const int a10" in git(repo.path, "show", "HEAD:a.cxx")
    assert "b.cxx" not in git(repo.path, "show", "--name-only", "--format=", "HEAD")


def test_commit_message_and_body(repo, fake_gate_ok):
    res = apply(repo.path, plan(repo.path, [repo.m_local])[0], repo.graph)
    msg = git(repo.path, "log", "-1", "--format=%B")
    assert msg.startswith("STYLE: Initialize locals at declaration instead of assigning\n\n")
    assert "Sites: 3, skipped: 1" in msg
    assert res.sha == git(repo.path, "rev-parse", "HEAD").strip()


def test_sequential_plans_split_the_diff_and_gate_sees_only_staged(repo, gate_calls):
    plans = plan(repo.path, [repo.m_local, repo.m_helpers])
    shas = [apply(repo.path, p, repo.graph).sha for p in plans]
    assert all(shas)
    subjects = git(repo.path, "log", "--format=%s", "-2").splitlines()
    assert subjects == [
        "STYLE: Use Filled, MakeFilled, and AllocateInitialized helpers",
        "STYLE: Initialize locals at declaration instead of assigning",
    ]
    assert "constexpr int a40" not in git(repo.path, "show", "HEAD~1:a.cxx")
    assert "constexpr int a40" in git(repo.path, "show", "HEAD:a.cxx")
    files, seen = gate_calls[0]
    assert "constexpr int a40" not in seen[Path("a.cxx")]
    assert git(repo.path, "diff", "HEAD") == ""


def test_nothing_left_gives_no_sha(repo, monkeypatch):
    monkeypatch.setattr(
        gate, "run", lambda g, files, r: GateResult(False, {f: "x" for f in files})
    )
    head = git(repo.path, "rev-parse", "HEAD")
    res = apply(repo.path, plan(repo.path, [repo.m_local])[0], repo.graph)
    assert res.sha is None
    assert git(repo.path, "rev-parse", "HEAD") == head
    assert git(repo.path, "diff", "HEAD") == ""


def test_missing_clang_format_is_noted(repo, fake_gate_ok, monkeypatch):
    monkeypatch.setattr(partition.shutil, "which", lambda name: None)
    res = apply(repo.path, plan(repo.path, [repo.m_local])[0], repo.graph)
    assert any("clang-format" in n for n in res.notes)


@pytest.mark.skipif(not partition.shutil.which("clang-format"), reason="no clang-format")
def test_clang_format_applies_to_commit_and_worktree(tmp_path, fake_gate_ok):
    r = make_repo.build(tmp_path, clang_format="BasedOnStyle: LLVM\n")
    (r.path / "a.cxx").write_text(
        (r.path / "a.cxx").read_text().replace("const int a10 = 10;", "const int  a10=10;")
    )
    res = apply(r.path, plan(r.path, [r.m_local, r.m_helpers])[0], r.graph)
    assert res.sha is not None
    assert "const int a10 = 10;" in git(r.path, "show", "HEAD:a.cxx")
    assert "const int a10 = 10;" in (r.path / "a.cxx").read_text()
    assert "constexpr int a40" in (r.path / "a.cxx").read_text()
