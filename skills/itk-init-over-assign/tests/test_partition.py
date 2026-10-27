import subprocess
import sys
from pathlib import Path

import pytest

from ioa import gate, partition, tidy
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
    assert git(repo.path, "rev-parse", "refs/ioa/backup/local-init").strip() == sha


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
        make_repo.stage(r, files, "local-init", local, [("d.cxx", 10, 10)]),
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
    monkeypatch.setattr(partition, "_clang_format", lambda: None)
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    assert any("clang-format" in n for n in res.notes)


@pytest.mark.skipif(partition._clang_format() is None, reason="no clang-format")
def test_clang_format_applies_to_commit_and_worktree(tmp_path, fake_gate_ok):
    r = make_repo.build(tmp_path, clang_format="BasedOnStyle: LLVM\n")
    a = r.path / "a.cxx"
    a.write_text(a.read_text().replace("int a20 = 20;", "int  a20=20;"))
    res = apply(r.path, plan(r.path, [r.s_local, r.s_helpers])[0], r.graph)
    assert res.sha is not None
    assert "\nint a20 = 20;" in git(r.path, "show", "HEAD:a.cxx")
    assert "\nint a20 = 20;" in a.read_text()
    assert "constexpr int a40" in a.read_text()


def staged_repo(tmp_path, name, n, edits, clang_format="DisableFormat: true\n"):
    files = {name: make_repo.lines(name[0], n)}
    r = make_repo.init_repo(tmp_path, files, clang_format)
    stages = [make_repo.stage(r, files, kind, fn, sites) for kind, fn, sites in edits]
    return r, files, stages


def test_identical_text_from_two_stages_goes_to_the_stage_that_wrote_it(tmp_path):
    def local(f):
        f["e.cxx"][4] = "unsigned int i = 0;"

    def const(f):
        f["e.cxx"][14] = "unsigned int i = 0;"

    r, _, stages = staged_repo(tmp_path, "e.cxx", 20, [
        ("local-init", local, [("e.cxx", 5, 5)]),
        ("local-const", const, [("e.cxx", 15, 15)]),
    ])
    plans = plan(r, stages)
    assert hunk_at(plans, "e.cxx", 5).kind == "local-init"
    assert hunk_at(plans, "e.cxx", 15).kind == "local-const"
    assert [s.start for s in hunk_at(plans, "e.cxx", 5).sites] == [5]


def test_brace_only_lines_cannot_steal_a_hunk(tmp_path):
    def local(f):
        f["f.cxx"][9] = "const int f10 = 10;"

    def scope(f):
        f["f.cxx"][31:31] = ["}"]
        f["f.cxx"][29:29] = ["{"]

    r, files, stages = staged_repo(tmp_path, "f.cxx", 40, [
        ("local-init", local, [("f.cxx", 10, 10)]),
        ("narrow-scope", scope, [("f.cxx", 30, 31)]),
    ])
    files["f.cxx"][11] = "}"
    make_repo.write(r, files)
    plans = plan(r, stages)
    assert hunk_at(plans, "f.cxx", 10).kind == "local-init"
    assert hunk_at(plans, "f.cxx", 12).kind == "local-init"
    assert {h.kind for p in plans for h in p.hunks if h.file.name == "f.cxx"
            and h.added in (["{"], ["}"]) and h.old_start > 20} == {"narrow-scope"}


ITK_CLANG_FORMAT = (
    Path(__file__).resolve().parents[2] / "itk-member-init" / "tests" / "fixtures" / ".clang-format"
)


def _clang_format() -> str | None:
    try:
        return tidy.tool("clang-format")
    except SystemExit:
        return None


def assert_clang_format_clean(repo: Path, name: str) -> None:
    res = subprocess.run(
        [_clang_format(), "--dry-run", "-Werror", "--style=file", name],
        cwd=repo, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(_clang_format() is None, reason="no clang-format")
def test_formatting_mirror_survives_next_kind_hunk_nearby(tmp_path, fake_gate_ok):
    def local(f):
        f["g.cxx"][9] = "const int  g10=10;"

    def const(f):
        f["g.cxx"][11] = "const int g12 = 12;"

    r, _, stages = staged_repo(tmp_path, "g.cxx", 20, [
        ("local-init", local, [("g.cxx", 10, 10)]),
        ("local-const", const, [("g.cxx", 12, 12)]),
    ], clang_format=ITK_CLANG_FORMAT.read_text())
    first, second = plan(r, stages)
    assert apply(r, first, tmp_path).sha is not None
    text = (r / "g.cxx").read_text()
    assert "const int g10 = 10;\nint       g11 = 11;\nconst int g12 = 12;" in text
    assert apply(r, second, tmp_path).sha is not None
    assert git(r, "diff", "HEAD") == ""
    assert_clang_format_clean(r, "g.cxx")


@pytest.mark.skipif(_clang_format() is None, reason="no clang-format")
def test_realignment_onto_a_later_kinds_line_lands_in_both_commits(tmp_path, fake_gate_ok):
    def local(f):
        f["h.cxx"][6] = "const int h7 = 7;"

    def const(f):
        f["h.cxx"][8] = "const int h9 = 9;"

    r, _, stages = staged_repo(tmp_path, "h.cxx", 12, [
        ("local-init", local, [("h.cxx", 7, 7)]),
        ("local-const", const, [("h.cxx", 9, 9)]),
    ], clang_format=ITK_CLANG_FORMAT.read_text())
    first, second = plan(r, stages)
    a = apply(r, first, tmp_path)
    assert a.sha is not None
    assert any("another kind's lines" in n for n in a.notes)
    assert git(r, "show", "HEAD:h.cxx") != (r / "h.cxx").read_text()
    b = apply(r, second, tmp_path)
    assert b.sha is not None and b.sha != a.sha
    assert git(r, "rev-list", "--count", "HEAD") == "3\n"
    assert git(r, "diff", "HEAD") == ""
    assert "const int h9 = 9;" in (r / "h.cxx").read_text()
    assert_clang_format_clean(r, "h.cxx")


def test_widen_to_block_stops_at_statements_and_comments():
    lines = [
        "{", "  int a = 1;", "  int b = 2;", "  return a;", "  int c = 3;",
        "  // note", "  int d = 4;", "#if X", "  int e = 5;", "  if (a)", "  b = 1;",
    ]
    assert tidy.widen_to_block(lines, 2, 2) == (2, 3)
    assert tidy.widen_to_block(lines, 5, 5) == (5, 5)
    assert tidy.widen_to_block(lines, 7, 7) == (7, 7)
    assert tidy.widen_to_block(lines, 11, 11) == (11, 11)


def test_run_tidy_raises_when_no_requested_file_is_in_the_database(tmp_path):
    try:
        tidy.tool("run-clang-tidy")
    except SystemExit:
        pytest.skip("run-clang-tidy not available")
    graph = tmp_path / "build"
    graph.mkdir()
    (tmp_path / "a.cxx").write_text("int x;\n")
    (graph / "compile_commands.json").write_text(
        '[{"directory": "%s", "file": "%s", "command": "c++ -c a.cxx"}]' % (tmp_path, tmp_path / "a.cxx")
    )
    with pytest.raises(RuntimeError, match="matched none"):
        tidy.run_tidy(graph, tmp_path, "misc-const-correctness", files=[tmp_path / "missing.cxx"])


def test_sites_match_stage_hunks_on_the_post_edit_side(tmp_path):
    def local(f):
        f["k.cxx"][10] = "const int k11 = 11;"
        f["k.cxx"][2:4] = ["int k3 = 4;"]

    r, _, stages = staged_repo(tmp_path, "k.cxx", 20, [
        ("local-init", local, [("k.cxx", 3, 3), ("k.cxx", 10, 10)]),
    ])
    plans = plan(r, stages)
    assert [s.start for s in hunk_at(plans, "k.cxx", 11).sites] == [10]
    assert [s.start for s in hunk_at(plans, "k.cxx", 3).sites] == [3]


def _compiles(text: str) -> bool:
    """Stand-in compiler: each local is assigned exactly once."""
    return text.count("x = f();") == 1 and text.count("y = g();") == 1


@pytest.fixture
def fake_gate_compiles(monkeypatch):
    calls = []

    def fake(graph, files, repo_root):
        failed = {f: "error: x" for f in files if not _compiles((repo_root / f).read_text())}
        calls.append(sorted(failed))
        return GateResult(ok=not failed, failed=failed)

    monkeypatch.setattr(gate, "run", fake)
    return calls


@pytest.mark.skipif(_clang_format() is None, reason="no clang-format")
def test_site_touched_by_a_later_kind_moves_whole_to_that_kind(tmp_path, fake_gate_compiles):
    src = ["void", "F()", "{", "  int x;", "  // why", "  x = f();", "  Use(x);",
           "  int y;", "  y = g();", "  Use(y);", "}"]
    files = {"i.cxx": src}
    r = make_repo.init_repo(tmp_path, files, ITK_CLANG_FORMAT.read_text())

    def local(f):
        f["i.cxx"][7:9] = ["  int y = g();"]
        f["i.cxx"][3:6] = ["  int x = f();", "  // why"]

    def const(f):
        f["i.cxx"][3] = "  const int x = f();"

    stages = [
        make_repo.stage(r, files, "local-init", local, [("i.cxx", 4, 5), ("i.cxx", 7, 7)]),
        make_repo.stage(r, files, "local-const", const, [("i.cxx", 4, 4)]),
    ]
    first, second = plan(r, stages)
    assert [first.kind, second.kind] == ["local-init", "local-const"]
    assert not any("  x = f();" in h.removed for h in first.hunks)
    removed = [h.removed for h in second.hunks]
    assert ["  int x;"] in removed and ["  x = f();"] in removed
    assert any("moved to local-const" in n for n in first.notes)
    for p in (first, second):
        res = apply(r, p, tmp_path)
        assert res.sha is not None and not res.reverted
        assert _compiles(git(r, "show", "HEAD:i.cxx"))
    assert "  int x;" in git(r, "show", "HEAD~1:i.cxx")
    assert "const int x = f();" in git(r, "show", "HEAD:i.cxx")
    assert all(not failed for failed in fake_gate_compiles)
    assert git(r, "diff", "HEAD") == ""


def test_stranded_comment_reverts_every_hunk_of_its_site(tmp_path, fake_gate_compiles):
    src = ["void", "F()", "{", "  int x;", "  // keep", "  x = f(); // note", "  Use(x);",
           "  int y;", "  y = g();", "}"]
    files = {"j.cxx": src}
    r = make_repo.init_repo(tmp_path, files, "DisableFormat: true\n")

    def local(f):
        f["j.cxx"][7:9] = ["  int y = g();"]
        f["j.cxx"][3:6] = ["  int x = f();", "  // keep"]

    stages = [make_repo.stage(r, files, "local-init", local, [("j.cxx", 4, 5), ("j.cxx", 7, 7)])]
    [only] = plan(r, stages)
    res = apply(r, only, tmp_path)
    assert res.sha is not None
    head = git(r, "show", "HEAD:j.cxx")
    assert "  int x;\n  // keep\n  x = f(); // note\n" in head and "int y = g();" in head
    assert [(s.start, s.skipped) for s in res.reverted] == [(4, Reason.COMMENT_STRANDED)]
    assert git(r, "diff", "HEAD") == ""


def test_gate_failure_in_a_header_reverts_its_partner_source(tmp_path, monkeypatch):
    files = {
        "foo.h": ["class Foo", "{", "  Foo();", "  int m_A;", "};"],
        "foo.cxx": ["#include \"foo.h\"", "Foo::Foo()", "  : m_A(0)", "{", "}"],
        "bar.cxx": ["int b1 = 1;", "int b2;"],
    }
    r = make_repo.init_repo(tmp_path, files, "DisableFormat: true\n")

    def member(f):
        f["foo.h"][3] = "  int m_A{ 0 };"
        f["foo.cxx"][2:3] = []
        f["bar.cxx"][1] = "int b2{};"

    rec = make_repo.stage(r, files, "member-init", member,
                          [("foo.h", 4, 4), ("foo.cxx", 2, 2), ("bar.cxx", 2, 2)])
    for site in rec.manifest.sites[:2]:
        site.group = "dmi-0"
    monkeypatch.setattr(gate, "run", lambda g, fs, root: GateResult(
        False, {f: "error: h" for f in fs if f.name == "foo.h"}))
    [only] = plan(r, [rec])
    res = apply(r, only, tmp_path)
    assert res.sha is not None
    assert git(r, "show", "--name-only", "--format=", "HEAD").split() == ["bar.cxx"]
    assert {s.file.name for s in res.reverted} == {"foo.h", "foo.cxx"}
    assert git(r, "diff", "HEAD") == ""


def test_unattributed_failure_gates_the_headers_in_one_batch(tmp_path, monkeypatch):
    calls = []

    def fake(graph, files, root):
        calls.append(sorted(f.name for f in files))
        return GateResult(False, {Path("z.cxx"): "error: boom"})

    monkeypatch.setattr(gate, "run", fake)
    monkeypatch.setattr(gate, "expand", lambda fs, g, r: (
        [Path("z.cxx")] if fs[0].name == "a.h" else [Path("y.cxx")], []))
    bad, unplaced = partition._gate_failures(
        tmp_path, tmp_path, [Path("a.h"), Path("b.h"), Path("c.cxx")])
    assert calls == [["a.h", "b.h", "c.cxx"], ["a.h", "b.h"]]
    assert bad == {Path("a.h")} and unplaced == [Path("z.cxx")]


def test_index_formatting_never_falls_back_to_a_default_style(tmp_path):
    r, _, _ = staged_repo(tmp_path, "n.cxx", 5, [])
    (r / "n.cxx").write_text("int  n1=1;\nint n2 = 2;\nint n3 = 3;\nint n4 = 4;\nint n5 = 5;\n")
    git(r, "add", "n.cxx")
    log = tmp_path / "args.txt"
    fake = tmp_path / "clang-format"
    fake.write_text(f"#!/bin/sh\necho \"$@\" > {log}\ncat\n")
    fake.chmod(0o755)
    partition._format(r, Path("n.cxx"), str(fake))
    assert "--fallback-style=none" in log.read_text().split()


def test_only_the_member_site_a_later_kind_touches_moves_with_its_source(tmp_path, fake_gate_ok):
    files = {
        "foo.h": ["class Foo", "{", "  Foo();", "  Foo(int);", "  int m_A;", "",
                  "  int m_B;", "  int m_C;", "};"],
        "foo.cxx": ["#include \"foo.h\"", "Foo::Foo()", "  : m_A(0)", "{}", "",
                    "Foo::Foo(int)", "  : m_B(1)", "{}"],
    }
    r = make_repo.init_repo(tmp_path, files, "DisableFormat: true\n")

    def member(f):
        f["foo.h"][4] = "  int m_A{ 0 };"
        f["foo.h"][6] = "  int m_B{ 1 };"
        del f["foo.cxx"][6]
        del f["foo.cxx"][2]

    def default(f):
        f["foo.h"][7] = "  int m_C{};"

    mi = make_repo.stage(r, files, "member-init", member,
                         [("foo.h", 5, 5), ("foo.cxx", 2, 2), ("foo.h", 7, 7), ("foo.cxx", 5, 5)])
    for site, group in zip(mi.manifest.sites, ["dmi-0", "dmi-0", "dmi-1", "dmi-1"]):
        site.group = group
    dmi = make_repo.stage(r, files, "member-default-init", default, [("foo.h", 8, 8)])
    first, second = plan(r, [mi, dmi])
    assert [first.kind, second.kind] == ["member-init", "member-default-init"]
    assert sorted((h.file.name, h.old_start) for h in first.hunks) == [("foo.cxx", 3), ("foo.h", 5)]
    assert sorted((h.file.name, h.old_start) for h in second.hunks) == [("foo.cxx", 7), ("foo.h", 7)]
    assert apply(r, first, tmp_path).sha and apply(r, second, tmp_path).sha
    head1 = git(r, "show", "HEAD~1:foo.cxx")
    assert "m_A(0)" not in head1 and "m_B(1)" in head1
    assert "m_B{ 1 }" not in git(r, "show", "HEAD~1:foo.h")
    assert git(r, "diff", "HEAD") == ""


def test_reverting_an_insertion_above_a_pure_deletion_restores_the_file(tmp_path, monkeypatch):
    src = ["F::F()", "{", "  int pad = 0;", "  m_A = 0;", "", "  m_B = 1;", "}", "int z = 0;"]
    original = "\n".join(src) + "\n"
    files = {"l.cxx": list(src)}
    r = make_repo.init_repo(tmp_path, files, "DisableFormat: true\n")

    def member(f):
        f["l.cxx"][3:6] = []
        f["l.cxx"][1:1] = ["  : m_A(0)", "  , m_B(1)"]

    rec = make_repo.stage(r, files, "member-init", member, [("l.cxx", 2, 3), ("l.cxx", 5, 5)])
    staged = (r / "l.cxx").read_text()
    monkeypatch.setattr(gate, "run", lambda g, fs, root: GateResult(
        False, {f: "error: x" for f in fs if f.name == "l.cxx"}))
    [only] = plan(r, [rec])
    assert sorted((h.old_count, h.new_count) for h in only.hunks) == [(0, 2), (3, 0)]
    res = apply(r, only, tmp_path)
    assert res.sha is None and {s.skipped for s in res.reverted} == {Reason.GATE_FAILED}
    assert (r / "l.cxx").read_text() == original
    assert staged != (r / "l.cxx").read_text()


def test_reverse_bytes_checks_lines_and_keeps_crlf():
    from ioa.patch import Hunk, reverse_bytes

    data = b"a\r\nI\r\nb\r\nd\r\n"
    ins = Hunk(Path("f"), 1, 0, 2, 1, ["+I\r"])
    dele = Hunk(Path("f"), 3, 1, 3, 0, ["-c\r"])
    assert reverse_bytes(data, [ins, dele]) == b"a\r\nb\r\nc\r\nd\r\n"
    with pytest.raises(ValueError):
        reverse_bytes(b"a\r\nX\r\n", [ins])


def test_failed_worktree_reversal_restores_the_file_from_the_backup_tree(repo, fake_gate_fail_b, monkeypatch):
    before = (repo.path / "b.cxx").read_bytes()

    def boom(r, hunks):
        if any(h.file.name == "b.cxx" for h in hunks):
            raise ValueError("b.cxx:1: lines differ from the hunk's new side")

    monkeypatch.setattr(partition, "reverse_in_worktree", boom)
    res = apply(repo.path, plan(repo.path, [repo.s_local])[0], repo.graph)
    assert res.sha is not None
    assert (repo.path / "b.cxx").read_bytes() == before
    assert any("restored the file from backup tree" in n for n in res.notes)
