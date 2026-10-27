import subprocess
from pathlib import Path

import pytest

from ioa import preflight
from ioa.preflight import PreflightError


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def git_out(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo, name, subject=None):
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", subject or name)


@pytest.fixture
def world(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(upstream))
    forest = tmp_path / "build_forest-itk-main"
    repo = forest / "BRAINSTools"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a")
    git(repo, "remote", "add", "upstream", str(upstream))
    git(repo, "push", "-q", "upstream", "main")
    git(repo, "checkout", "-q", "-b", "BRAINSTools-itk-downstream-itk-main")
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "CATALOG.md").write_text(
        "## Consumers\n\n| Tree | Repository | Floating branch |\n|---|---|---|\n"
        f"| BRAINSTools | {upstream} | `main` |\n"
    )
    graph = repo / "build" / "BRAINSTools-build"
    graph.mkdir(parents=True)
    (graph / "compile_commands.json").write_text("[]")
    (graph / "CMakeCache.txt").write_text("ITK_DIR:PATH=" + str(tmp_path / "itk") + "\n")
    (graph / "CMakeFiles" / "4.3.4").mkdir(parents=True)
    (graph / "CMakeFiles" / "4.3.4" / "CMakeCXXCompiler.cmake").write_text(
        'set(CMAKE_CXX_COMPILER_VERSION "19.1.7")\n'
    )
    (tmp_path / "itk").mkdir()
    (tmp_path / "itk" / "ITKConfigVersion.cmake").write_text('set(PACKAGE_VERSION "6.0.0")\n')
    monkeypatch.setattr(preflight, "tidy_version", lambda: "19.1")
    return repo, forest, kit


def test_clean_state_returns_coordinates(world):
    repo, forest, kit = world
    c = preflight.check(repo, forest, kit)
    assert c.repo_slug == "BRAINSTools" and c.forest_name == "build_forest-itk-main"
    assert c.itk_version == "6.0.0"
    assert c.graph.name == "BRAINSTools-build"
    assert len(c.sha) == 40


def test_dirty_tree_is_refused(world):
    repo, forest, kit = world
    (repo / "a").write_text("changed")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "dirty-tree"


def test_protected_branch_is_refused(world):
    repo, forest, kit = world
    git(repo, "checkout", "-q", "main")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "on-main"


def test_worktree_ahead_of_upstream_tip_is_refused(world):
    repo, forest, kit = world
    commit(repo, "b")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "not-at-upstream-tip"
    assert "FOREST_REFERENCE_SUFFIX=itk-main APPLY=1 bash bin/refresh-forest.sh BRAINSTools" in str(e.value)
    assert "FOREST_REFERENCE_SUFFIX=itk-main pixi run build-BRAINSTools" in str(e.value)


def test_missing_graph_is_refused(world):
    repo, forest, kit = world
    for p in sorted((repo / "build").rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "no-graph"


def test_tidy_series_must_match_compiler(world, monkeypatch):
    repo, forest, kit = world
    monkeypatch.setattr(preflight, "tidy_version", lambda: "20.1")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "tidy-series-mismatch"


def test_url_spellings_are_equivalent():
    assert preflight._norm_url("git@github.com:a/b.git") == preflight._norm_url("https://github.com/a/b")


def test_itk_version_unknown_when_unreadable(tmp_path):
    assert preflight.itk_version(tmp_path) == "unknown"


def test_ssh_url_forms_are_equivalent():
    want = preflight._norm_url("https://github.com/a/b")
    assert preflight._norm_url("ssh://git@github.com/a/b.git") == want
    assert preflight._norm_url("ssh://git@github.com:a/b") == want


def test_worktree_behind_upstream_tip_is_refused(world, tmp_path):
    repo, forest, kit = world
    git(repo, "checkout", "-q", "main")
    commit(repo, "b")
    git(repo, "push", "-q", "upstream", "main")
    git(repo, "checkout", "-q", "BRAINSTools-itk-downstream-itk-main")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "not-at-upstream-tip"


def test_staged_change_is_dirty(world):
    repo, forest, kit = world
    (repo / "new").write_text("x")
    git(repo, "add", "new")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "dirty-tree"


@pytest.mark.parametrize("name", ["master", "release", "dashboard"])
def test_other_protected_branches_are_refused(world, name):
    repo, forest, kit = world
    git(repo, "checkout", "-q", "-b", name)
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "on-main"


def test_detached_head_is_refused(world):
    repo, forest, kit = world
    git(repo, "checkout", "-q", "--detach")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "not-at-upstream-tip" and "detached" in str(e.value)


def test_unusable_clang_tidy_is_a_preflight_error(world, monkeypatch):
    repo, forest, kit = world
    monkeypatch.undo()
    monkeypatch.setattr(preflight.tidy, "tool", lambda n: "/nonexistent/clang-tidy")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "tidy-series-mismatch"


def test_forest_local_commit_on_the_tip_passes(world):
    repo, forest, kit = world
    commit(repo, "p1", "COMP: forest-local tbb patch")
    commit(repo, "p2", "COMP: forest-local kwsys patch")
    c = preflight.check(repo, forest, kit)
    assert c.forest_local == ["COMP: forest-local tbb patch", "COMP: forest-local kwsys patch"]
    assert c.sha == git_out(repo, "rev-parse", "HEAD")


def test_at_tip_has_no_forest_local(world):
    assert preflight.check(*world).forest_local == []


def test_other_commit_on_the_tip_is_refused(world):
    repo, forest, kit = world
    commit(repo, "p1", "ENH: something else")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "not-at-upstream-tip"


def test_forest_local_then_other_commit_is_refused(world):
    repo, forest, kit = world
    commit(repo, "p1", "COMP: forest-local tbb patch")
    commit(repo, "p2", "ENH: something else")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "not-at-upstream-tip"


def test_merge_commit_above_the_tip_is_refused(world):
    repo, forest, kit = world
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, "s1", "COMP: forest-local side patch")
    git(repo, "checkout", "-q", "BRAINSTools-itk-downstream-itk-main")
    commit(repo, "p1", "COMP: forest-local tbb patch")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff",
        "-m", "COMP: forest-local merge side", "side")
    with pytest.raises(PreflightError) as e:
        preflight.check(repo, forest, kit)
    assert e.value.code == "not-at-upstream-tip"
