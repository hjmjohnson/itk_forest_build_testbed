import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from test_run import KINDS, World

from ioa import baseline, pipeline, preflight, report
from ioa.preflight import Coordinates, PreflightError

ENSURE_STANDALONE = baseline.ensure_standalone
APPLE_NOTE = "tidy-series: skipped (AppleClang 21.0.0 vs clang-tidy 19.1.7)"


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def commit(repo, name, subject=None):
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", subject or name)


def _compiler(build: Path, ident: str, version: str):
    d = build / "CMakeFiles" / "4.3.4"
    d.mkdir(parents=True, exist_ok=True)
    (d / "CMakeCXXCompiler.cmake").write_text(
        f'set(CMAKE_CXX_COMPILER_ID "{ident}")\nset(CMAKE_CXX_COMPILER_VERSION "{version}")\n'
    )


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    upstream = tmp_path / "BRAINSTools.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(upstream))
    repo = tmp_path / "src" / "BRAINSTools"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a")
    git(repo, "remote", "add", "origin", str(upstream))
    git(repo, "push", "-q", "origin", "main")
    build = repo / "build" / "BRAINSTools-Release-EPRelease-build"
    build.mkdir(parents=True)
    (build / "compile_commands.json").write_text("[]")
    (build / "CMakeCache.txt").write_text("ITK_DIR:PATH=" + str(tmp_path / "itk") + "\n")
    (tmp_path / "itk").mkdir()
    (tmp_path / "itk" / "ITKConfigVersion.cmake").write_text('set(PACKAGE_VERSION "6.0.0")\n')
    _compiler(build, "AppleClang", "21.0.0.21000334")
    monkeypatch.setattr(preflight, "tidy_full_version", lambda: "19.1.7")
    return repo, build, tmp_path / "kit"


def test_standalone_preflight_passes_on_main_at_tip(checkout):
    repo, build, kit = checkout
    c = preflight.check_standalone(repo, build, "origin/main", kit)
    assert c.repo_slug == "BRAINSTools" and c.forest_name == "standalone"
    assert c.graph == build and c.repo == repo
    assert c.itk_version == "6.0.0" and len(c.sha) == 40
    assert c.note == f"{preflight.llvm_note()}; {APPLE_NOTE}" and c.forest_local == []


def test_standalone_preflight_passes_on_any_branch(checkout):
    repo, build, kit = checkout
    git(repo, "checkout", "-q", "-b", "work")
    commit(repo, "p", "COMP: forest-local local patch")
    c = preflight.check_standalone(repo, build, "origin/main", kit)
    assert c.forest_local == ["COMP: forest-local local patch"]


def test_standalone_preflight_refuses_dirty(checkout):
    repo, build, kit = checkout
    (repo / "a").write_text("changed")
    with pytest.raises(PreflightError) as e:
        preflight.check_standalone(repo, build, "origin/main", kit)
    assert e.value.code == "dirty-tree"


def test_standalone_preflight_refuses_missing_graph(checkout):
    repo, build, kit = checkout
    (build / "compile_commands.json").unlink()
    with pytest.raises(PreflightError) as e:
        preflight.check_standalone(repo, build, "origin/main", kit)
    assert e.value.code == "no-graph"


def test_standalone_preflight_refuses_behind_tip(checkout, tmp_path):
    repo, build, kit = checkout
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "BRAINSTools.git"), str(other))
    commit(other, "b")
    git(other, "push", "-q", "origin", "main")
    with pytest.raises(PreflightError) as e:
        preflight.check_standalone(repo, build, "origin/main", kit)
    assert e.value.code == "not-at-upstream-tip"
    assert f"git -C {repo} fetch origin && git -C {repo} merge --ff-only origin/main" in str(e.value)


def test_standalone_preflight_refuses_existing_run_branch(checkout):
    repo, build, kit = checkout
    git(repo, "branch", f"style-init-over-assign-{datetime.now():%Y%m%d}")
    with pytest.raises(PreflightError) as e:
        preflight.check_standalone(repo, build, "origin/main", kit)
    assert e.value.code == "branch-exists"


def test_llvm_clang_still_checks_the_tidy_series(checkout):
    repo, build, kit = checkout
    _compiler(build, "Clang", "20.1.8")
    with pytest.raises(PreflightError) as e:
        preflight.check_standalone(repo, build, "origin/main", kit)
    assert e.value.code == "tidy-series-mismatch"
    _compiler(build, "Clang", "19.1.7")
    assert preflight.check_standalone(repo, build, "origin/main", kit).note == preflight.llvm_note()


@pytest.mark.parametrize("text, token", [
    ("100% tests passed, 0 tests failed out of 554\n", "T:554/554"),
    ("x\n98% tests passed, 11 tests failed out of 554\n\nTotal Test time", "T:543/554"),
    ("No tests were found!!!\n", "no token"),
])
def test_token_synthesis(text, token):
    assert baseline.ctest_token(text) == token


class StandaloneWorld(World):
    def __init__(self, tmp_path, monkeypatch):
        super().__init__(tmp_path, monkeypatch)
        self.ctest_dir = self.graph
        self.summary = "100% tests passed, 0 tests failed out of 554\n"
        self.ctest_kwargs: list[dict] = []
        self.coords = Coordinates(
            "BRAINSTools", "a" * 40, "standalone", self.graph, "6.0.0",
            repo=self.repo, note=APPLE_NOTE,
        )
        monkeypatch.setattr(preflight, "check_standalone", lambda repo, build, up, kit: self.coords)
        monkeypatch.setattr(baseline, "ensure_standalone", lambda c, kit, jobs=None: self.ensure(c, kit))

    def record(self, argv, *args, **kwargs):
        argv = [str(a) for a in argv]
        if argv[0] == "ctest":
            self.calls.append(argv)
            self.envs.append(kwargs.get("env"))
            if self.ctest_failed:
                log = self.ctest_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text("".join(f"{i}:{t}\n" for i, t in enumerate(self.ctest_failed)))
            self.ctest_kwargs.append(kwargs)
            return subprocess.CompletedProcess(argv, 8 if self.ctest_failed else 0, self.summary, "")
        if argv[0] == "ninja":
            self.calls.append(argv)
            self.envs.append(kwargs.get("env"))
            assert not self.dirty, "build saw files rewritten by pre-commit"
            out = "[1/2] x\nfoo.cxx:3:1: warning: unused variable 'q'\n"
            self.builds += 1
            rc = self.prebuild_rc if self.builds <= self.prebuild_tries else self.build_rc
            return subprocess.CompletedProcess(argv, rc, out, "")
        return super().record(argv, *args, **kwargs)

    def main(self, *extra: str) -> int:
        return self.run.main(["--repo", str(self.repo), "--build", str(self.graph), *extra])


@pytest.fixture
def sworld(tmp_path, monkeypatch):
    return StandaloneWorld(tmp_path, monkeypatch)


def _report(world) -> str:
    found = sorted((world.kit / ".devlocal" / "init-over-assign").glob("BRAINSTools-*.md"))
    assert len(found) == 1
    return found[0].read_text()


def test_standalone_run_uses_ninja_and_ctest_after_the_stages(sworld, capsys):
    assert sworld.main() == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first == f"Repo: BRAINSTools (aaaaaaaaaaaa) | Standalone: {sworld.repo}, build {sworld.graph}"
    assert [r.kind for r in sworld.plan_args[0]] == KINDS
    assert sworld.applied == ["local-init", "narrow-scope"]
    assert len(sworld.stage_calls()) == 13
    assert not any(c[:2] == ["pixi", "run"] for c in sworld.calls)
    assert not any(any(a.endswith("run-matrix.sh") for a in c) for c in sworld.calls)
    ninja = max(i for i, c in enumerate(sworld.calls) if c == ["ninja", "-C", str(sworld.graph)])
    ctest = max(i for i, c in enumerate(sworld.calls) if c[0] == "ctest")
    assert sworld.calls.index(sworld.stage_calls()[-1]) < ninja < ctest
    argv = sworld.calls[ctest]
    assert argv[:3] == ["ctest", "--test-dir", str(sworld.graph)]
    assert argv[3].startswith("-j") and int(argv[3][2:]) >= 2
    assert argv[4:] == ["--timeout", "300", "--output-on-failure"]
    text = _report(sworld)
    assert f"Standalone: {sworld.repo}, build {sworld.graph}" in text
    assert "- Result: T:554/554" in text and APPLE_NOTE in text
    assert "warning: unused variable 'q'" in text
    assert "- Full build: pass" in text and "artifact check" not in text
    body = (sworld.kit / ".devlocal" / "pr-bodies" / "BRAINSTools-init-over-assign.md").read_text()
    assert "- Full build with ninja in the standalone build tree: pass" in body


def test_standalone_new_ctest_failure_exits_1(sworld):
    sworld.ctest_failed = ["known", "fresh"]
    sworld.summary = "99% tests passed, 2 tests failed out of 554\n"
    assert sworld.main() == 1
    assert "`fresh`" in _report(sworld)


def test_standalone_ctest_without_summary_is_not_green(sworld):
    sworld.summary = "No tests were found!!!\n"
    assert sworld.main() == 1
    assert "ctest did not run" in _report(sworld)


def test_standalone_build_failure_skips_ctest(sworld):
    sworld.build_rc = 1
    assert sworld.main() == 1
    assert not any(c[0] == "ctest" for c in sworld.calls)
    assert f"ninja -C {sworld.graph} exited 1" in _report(sworld)


def test_standalone_dry_run_prints_ninja_and_ctest(sworld, capsys):
    assert sworld.main("--dry-run") == 0
    out = capsys.readouterr().out
    assert f"build: ninja -C {sworld.graph}" in out
    assert f"ctest: ctest --test-dir {sworld.graph}" in out
    assert "pixi run build-" not in out and "run-matrix" not in out
    assert sworld.plan_args == []


def test_upstream_option_reaches_preflight(sworld, monkeypatch):
    seen = []
    monkeypatch.setattr(preflight, "check_standalone",
                        lambda repo, build, up, kit: seen.append(up) or sworld.coords)
    sworld.main("--dry-run")
    sworld.main("--dry-run", "--upstream", "upstream/release")
    assert seen == ["origin/main", "upstream/release"]


@pytest.mark.parametrize("argv", [
    ["BRAINSTools", "--repo", "/r", "--build", "/b"],
    ["--repo", "/r"],
    ["--build", "/b"],
    ["--repo", "/r", "--build", "/b", "--forest", "x"],
    ["BRAINSTools", "--upstream", "origin/main"],
    [],
])
def test_modes_are_mutually_exclusive(sworld, argv):
    assert sworld.run.main(argv) == 2
    assert sworld.calls == []


def _fake_ctest(monkeypatch, summary, failed):
    calls = []

    def run(argv, *a, **kw):
        argv = [str(x) for x in argv]
        calls.append(argv)
        build = Path(argv[2])
        if failed:
            log = build / "Testing" / "Temporary" / "LastTestsFailed.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("".join(f"{i}:{t}\n" for i, t in enumerate(failed, 1)))
        return subprocess.CompletedProcess(argv, 0, summary, "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_ensure_standalone_records_failures(tmp_path, monkeypatch):
    build = tmp_path / "build"
    stale = build / "Testing" / "Temporary" / "LastTestsFailed.log"
    stale.parent.mkdir(parents=True)
    stale.write_text("9:stale\n")
    calls = _fake_ctest(monkeypatch, "98% tests passed, 2 tests failed out of 100\n", ["b", "a"])
    coords = Coordinates("BRAINSTools", "abc", "standalone", build, "6.0.0", repo=tmp_path)
    path = baseline.ensure_standalone(coords, tmp_path / "kit", jobs=3)
    assert calls == [["ctest", "--test-dir", str(build), "-j3", "--timeout", "300",
                      "--output-on-failure"]]
    assert json.loads(path.read_text())["failed"] == ["a", "b"]
    assert baseline.ensure_standalone(coords, tmp_path / "kit", jobs=3) == path
    assert len(calls) == 1


def test_ensure_standalone_refuses_when_ctest_did_not_run(tmp_path, monkeypatch):
    _fake_ctest(monkeypatch, "No tests were found!!!\n", [])
    coords = Coordinates("BRAINSTools", "abc", "standalone", tmp_path, "6.0.0", repo=tmp_path)
    with pytest.raises(RuntimeError, match="no token"):
        baseline.ensure_standalone(coords, tmp_path / "kit")


def test_run_ctest_standalone_synthesizes_the_token(tmp_path, monkeypatch):
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"failed": ["old"]}))
    _fake_ctest(monkeypatch, "98% tests passed, 11 tests failed out of 554\n", ["old"])
    got = pipeline.run_ctest_standalone(tmp_path / "b", base, tmp_path / "run", jobs=2)
    assert got.ok and got.token == "T:543/554" and got.new == []


def test_report_coordinate_line_for_standalone(tmp_path):
    coords = Coordinates("BRAINSTools", "b" * 40, "standalone", tmp_path / "bld", "6.0.0",
                         repo=tmp_path / "src")
    assert report.coordinate_line(coords) == (
        f"Repo: BRAINSTools (bbbbbbbbbbbb) | Standalone: {tmp_path / 'src'}, build {tmp_path / 'bld'}"
    )


def test_standalone_builds_before_the_baseline_ctest(sworld, monkeypatch):
    monkeypatch.setattr(baseline, "ensure_standalone", ENSURE_STANDALONE)
    assert sworld.main() == 0
    ninja = [i for i, c in enumerate(sworld.calls) if c[0] == "ninja"]
    ctest = [i for i, c in enumerate(sworld.calls) if c[0] == "ctest"]
    first_stage = sworld.calls.index(sworld.stage_calls()[0])
    assert len(ninja) == 2 and len(ctest) == 2
    assert ninja[0] < ctest[0] < first_stage < ninja[1] < ctest[1]
    assert "baseline build:" in _report(sworld)


def test_failing_standalone_baseline_build_refuses_without_branch(sworld, capsys):
    sworld.prebuild_rc, sworld.prebuild_tries = 1, 2
    assert sworld.main() == 2
    assert "refused (build-failed)" in capsys.readouterr().err
    assert not any("checkout" in c for c in sworld.calls)
    assert not any(c[0] == "ctest" for c in sworld.calls)
    text = _report(sworld)
    assert "## Baseline build failed" in text and f"ninja -C {sworld.graph} exited 1" in text


def test_standalone_build_and_ctest_drop_forest_env(sworld, monkeypatch):
    monkeypatch.setenv("FOREST", "/elsewhere")
    monkeypatch.setenv("BUILD_FOREST_ROOT", "/elsewhere")
    sworld.main()
    envs = [e for c, e in zip(sworld.calls, sworld.envs) if c[0] in ("ninja", "ctest")]
    assert len(envs) == 3
    for env in envs:
        assert env is not None and "FOREST" not in env and "BUILD_FOREST_ROOT" not in env
    assert all(kw.get("timeout") == 1800 for kw in sworld.ctest_kwargs)


def test_standalone_baseline_oserror_is_a_refusal(sworld, monkeypatch, capsys):
    def boom(coords, kit, jobs=None):
        raise FileNotFoundError("ctest: not found")

    monkeypatch.setattr(baseline, "ensure_standalone", boom)
    assert sworld.main() == 2
    assert "refused (baseline)" in capsys.readouterr().err


def test_standalone_baseline_is_keyed_on_the_build_dir(tmp_path, monkeypatch):
    _fake_ctest(monkeypatch, "100% tests passed, 0 tests failed out of 3\n", [])
    kit = tmp_path / "kit"
    paths = []
    for name in ("b1", "b2"):
        coords = Coordinates("BRAINSTools", "abc", "standalone", tmp_path / name, "6.0.0",
                             repo=tmp_path)
        paths.append(baseline.ensure_standalone(coords, kit))
    import hashlib
    want = hashlib.sha1(str(tmp_path / "b1").encode()).hexdigest()[:8]
    assert paths[0].name == f"BRAINSTools-standalone-abc-{want}.json"
    assert paths[0] != paths[1]


def test_ctest_timeout_is_did_not_run(tmp_path, monkeypatch):
    def slow(argv, *a, **kw):
        assert kw["timeout"] == 1800
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr(subprocess, "run", slow)
    coords = Coordinates("BRAINSTools", "abc", "standalone", tmp_path, "6.0.0", repo=tmp_path)
    with pytest.raises(RuntimeError, match="did not run.*T:timeout"):
        baseline.ensure_standalone(coords, tmp_path / "kit")
    got = pipeline.run_ctest_standalone(tmp_path, tmp_path / "b.json", tmp_path / "run")
    assert not got.ok and got.token == "T:timeout" and got.note == "ctest did not run"


def test_non_git_repo_is_named(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(PreflightError) as e:
        preflight.check_standalone(plain, tmp_path, "origin/main", tmp_path)
    assert e.value.code == "not-a-repo" and "not a git" in e.value.message


def test_standalone_pre_commit_runs_without_the_pixi_toolchain(sworld, monkeypatch):
    monkeypatch.setenv("CC", "/conda/bin/clang")
    monkeypatch.setenv("LIBRARY_PATH", "/conda/lib")
    (sworld.repo / ".pre-commit-config.yaml").write_text("repos: []\n")
    sworld.main()
    envs = [e for c, e in zip(sworld.calls, sworld.envs) if c[0] == "pre-commit"]
    assert envs and all(e is not None and "CC" not in e and "LIBRARY_PATH" not in e for e in envs)
