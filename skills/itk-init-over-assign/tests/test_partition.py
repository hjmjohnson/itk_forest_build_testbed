import subprocess
import sys
from pathlib import Path

import pytest

from ioa import gate, partition
from ioa.gate import GateResult
from ioa.manifest import Manifest
from ioa.partition import StageRecord, apply, plan, snapshot
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
    plans = plan(repo.path, [repo.s_local, repo.s_helpers])
    assert hunk_at(plans, "a.cxx", 40).kind == "itk-helpers"
    assert hunk_at(plans, "a.cxx", 10).kind == "local-init"


def test_ownership_follows_content_not_shifted_line_numbers(repo):
    # itk-helpers' manifest says line 48 (post-stage-1); HEAD line 48 is local-init's.
    plans = plan(repo.path, [repo.s_local, repo.s_helpers])
    assert hunk_at(plans, "a.cxx", 48).kind == "local-init"
    assert hunk_at(plans, "a.cxx", 50).kind == "itk-helpers"


def test_uncovered_hunk_attaches_to_nearest_stage_above(repo):
    plans = plan(repo.path, [repo.s_local, repo.s_helpers])
    assert hunk_at(plans, "b.cxx", 99) is not None  # clang-format spill
    assert hunk_at(plans, "b.cxx", 99).kind == "local-init"


def test_uncovered_hunk_with_nothing_above_attaches_below(repo):
    plans = plan(repo.path, [repo.s_todo])
    assert hunk_at(plans, "b.cxx", 20).kind == "local-const"


def test_plans_follow_fixed_kind_order_with_subjects(repo):
    plans = plan(repo.path, [repo.s_helpers, repo.s_local])
    assert [p.kind for p in plans] == ["local-init", "itk-helpers"]
    assert plans[0].message == "STYLE: Initialize locals at declaration instead of assigning"
    assert plans[1].message == "STYLE: Use Filled, MakeFilled, and AllocateInitialized helpers"
    assert plans[0].manifests == [repo.s_local.manifest]


def test_file_without_covered_hunk_goes_to_first_kind_with_note(repo):
    plans = plan(repo.path, [repo.s_todo])
    assert hunk_at(plans, "c.cxx", 5).kind == "local-const"
    assert any("c.cxx" in n for n in plans[0].notes)


def test_unknown_kind_is_rejected(repo):
    t = repo.s_local.tree_after
    with pytest.raises(ValueError):
        plan(repo.path, [StageRecord("bogus", Manifest("bogus", []), t, t)])


def test_snapshot_leaves_the_real_index_alone(repo):
    before = git(repo.path, "ls-files", "-s")
    tree = snapshot(repo.path)
    assert git(repo.path, "ls-files", "-s") == before
    assert git(repo.path, "diff", "--cached") == ""
    assert git(repo.path, "show", f"{tree}:b.cxx") == (repo.path / "b.cxx").read_text()


def test_apply_reverts_hunk_that_strands_comment(repo, fake_gate_ok):
    res = apply(repo.path, plan(repo.path, [repo.s_todo])[0], repo.graph)
    assert res.reverted and res.reverted[0].skipped == Reason.COMMENT_STRANDED
    assert "// TODO: keep this" in git(repo.path, "show", "HEAD:b.cxx")
    assert "// TODO: keep this" in (repo.path / "b.cxx").read_text()
    assert git(repo.path, "diff", "HEAD") == ""


def test_apply_reverts_hunk_that_fails_gate(repo, fake_gate_fail_b):
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    assert {s.file.name for s in res.reverted} == {"b.cxx"}
    assert {s.skipped for s in res.reverted} >= {Reason.GATE_FAILED}
    assert res.sha is not None
    assert git(repo.path, "diff", "HEAD", "--", "b.cxx") == ""
    assert "int a10 = 10;" in git(repo.path, "show", "HEAD:a.cxx")
    assert "b.cxx" not in git(repo.path, "show", "--name-only", "--format=", "HEAD")


def test_unattributed_gate_failure_reverts_every_staged_file(repo, monkeypatch):
    monkeypatch.setattr(
        gate, "run", lambda g, files, r: GateResult(False, {Path("z.cxx"): "error: boom"})
    )
    head = git(repo.path, "rev-parse", "HEAD")
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    assert res.sha is None and git(repo.path, "rev-parse", "HEAD") == head
    assert {s.file.name for s in res.reverted} == {"a.cxx", "b.cxx", "c.cxx"}
    assert any("z.cxx" in n for n in res.notes)
    assert git(repo.path, "diff", "HEAD") == ""


def test_commit_message_and_body(repo, fake_gate_ok):
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    msg = git(repo.path, "log", "-1", "--format=%B")
    assert msg.startswith("STYLE: Initialize locals at declaration instead of assigning\n\n")
    assert "Sites: 6, skipped: 1" in msg
    assert res.sha == git(repo.path, "rev-parse", "HEAD").strip()


def test_backup_tree_is_recorded(repo, fake_gate_ok):
    text = (repo.path / "a.cxx").read_text()
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    [sha] = [n.split(": ")[1] for n in res.notes if n.startswith("backup-tree: ")]
    assert git(repo.path, "cat-file", "-t", sha).strip() == "tree"
    assert git(repo.path, "show", f"{sha}:a.cxx") == text


def test_prestaged_index_is_refused(repo, fake_gate_ok):
    git(repo.path, "add", "c.cxx")
    with pytest.raises(RuntimeError):
        apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)


def test_sequential_plans_split_the_diff_and_gate_sees_only_staged(repo, gate_calls):
    plans = plan(repo.path, [repo.s_local, repo.s_helpers])
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


def test_revert_in_first_kind_keeps_adjacent_hunk_of_next_kind(tmp_path, fake_gate_ok):
    d = make_repo.lines("d", 20)
    d[9] = "// TODO: keep this"
    files = {"d.cxx": d}
    r = make_repo.init_repo(tmp_path, files, "DisableFormat: true\n")

    def local(f):
        f["d.cxx"][9:11] = ["const int d11 = 11;"]

    def const(f):
        f["d.cxx"][11] = "const int d13 = 13;"

    stages = [
        make_repo.stage(r, files, "local-init", local, [("d.cxx", 10, 11)]),
        make_repo.stage(r, files, "local-const", const, [("d.cxx", 12, 12)]),
    ]
    first, second = plan(r, stages)
    assert apply(r, first, tmp_path).reverted[0].skipped == Reason.COMMENT_STRANDED
    text = (r / "d.cxx").read_text()
    assert "// TODO: keep this\nint d11 = 11;\nint d12 = 12;\nconst int d13 = 13;" in text
    assert apply(r, second, tmp_path).sha is not None
    assert "const int d13 = 13;" in git(r, "show", "HEAD:d.cxx")
    assert git(r, "diff", "HEAD") == ""


def test_nothing_left_gives_no_sha(repo, monkeypatch):
    monkeypatch.setattr(
        gate, "run", lambda g, files, r: GateResult(False, {f: "x" for f in files})
    )
    head = git(repo.path, "rev-parse", "HEAD")
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    assert res.sha is None
    assert git(repo.path, "rev-parse", "HEAD") == head
    assert git(repo.path, "diff", "HEAD") == ""


def test_missing_clang_format_is_noted(repo, fake_gate_ok, monkeypatch):
    monkeypatch.setattr(partition.shutil, "which", lambda name: None)
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    assert any("clang-format" in n for n in res.notes)


@pytest.mark.skipif(not partition.shutil.which("clang-format"), reason="no clang-format")
def test_clang_format_applies_to_commit_and_worktree(tmp_path, fake_gate_ok):
    r = make_repo.build(tmp_path, clang_format="BasedOnStyle: LLVM\n")
    a = r.path / "a.cxx"
    a.write_text(a.read_text().replace("int a20 = 20;", "int  a20=20;"))
    res = apply(r.path, plan(r.path, [r.s_local, r.s_helpers])[0], r.graph)
    assert res.sha is not None
    assert "\nint a20 = 20;" in git(r.path, "show", "HEAD:a.cxx")
    assert "\nint a20 = 20;" in a.read_text()
    assert "constexpr int a40" in a.read_text()
