import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from ioa import baseline, partition, pipeline, preflight, report, stages
from ioa.manifest import Manifest, Site
from ioa.partition import CommitPlan, CommitResult
from ioa.preflight import Coordinates, PreflightError
from ioa.skip import Reason

RUN_PY = Path(__file__).resolve().parents[1] / "run.py"
KINDS = [
    "member-init", "local-init", "local-const", "container-list-init",
    "container-const", "itk-helpers", "itk-helpers-constexpr", "narrow-scope",
]
SCRIPTS = [
    "member_init.py", "find_declare_then_init.py", "const_promote.py", "list_init.py",
    "const_promote.py", "sizetype_filled.py", "allocate_initialized.py",
    "in-class-member-init/transform.sh", "fillbuffer-over-iterate/transform.sh",
    "const_promote.py", "narrow_scope.py",
]


def _load_run():
    spec = importlib.util.spec_from_file_location("ioa_run", RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flag(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else None


class World:
    def __init__(self, tmp_path: Path, monkeypatch):
        self.kit = tmp_path / "kit"
        self.forest = self.kit / "build_forest-itk-main"
        self.repo = self.forest / "BRAINSTools"
        self.repo.mkdir(parents=True)
        self.graph = self.repo / "build" / "BRAINSTools-build"
        self.graph.mkdir(parents=True)
        self.ctest_dir = self.graph
        self.calls: list[list[str]] = []
        self.fail_script: str | None = None
        self.existing_branch = ""
        self.plan_args: list = []
        self.applied: list[str] = []
        self.ctest_failed: list[str] = []
        self.ctest_token = "T:10/10"
        self.build_rc = 0
        self.apply_raises = False
        self.precommit_rewrites: list[str] = []
        self.dirty: set[str] = set()
        self.envs: list[dict | None] = []
        self.snap = 0
        self.coords = Coordinates("BRAINSTools", "a" * 40, "build_forest-itk-main", self.graph, "6.0.0")
        self.run = _load_run()
        monkeypatch.setattr(self.run, "KIT", self.kit)
        monkeypatch.setattr(subprocess, "run", self.record)
        monkeypatch.setattr(preflight, "check", lambda repo, forest, kit: self.coords)
        monkeypatch.setattr(baseline, "ensure", self.ensure)
        monkeypatch.setattr(stages, "snapshot", self.snapshot)
        monkeypatch.setattr(partition, "plan", self.plan)
        monkeypatch.setattr(partition, "apply", self.apply)

    def ensure(self, coords, kit):
        path = kit / ".devlocal" / "init-over-assign" / "baselines" / "b.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"failed": ["known"]}))
        return path

    def snapshot(self, repo):
        self.snap += 1
        return f"tree{self.snap}"

    def plan(self, repo, recs):
        self.plan_args.append(list(recs))
        return [
            CommitPlan("local-init", partition.SUBJECTS["local-init"], [], [], [recs[1].manifest]),
            CommitPlan("narrow-scope", partition.SUBJECTS["narrow-scope"], [], [], [recs[-1].manifest]),
        ]

    def apply(self, repo, plan, graph):
        self.applied.append(plan.kind)
        if self.apply_raises and plan.kind == "narrow-scope":
            raise RuntimeError("index has staged changes")
        if plan.kind == "narrow-scope":
            gone = Site(Path("b.cxx"), 9, 9, "narrow-scope", "narrow-scope", Reason.GATE_FAILED)
            return CommitResult("c2" * 20, [gone], [])
        return CommitResult("c1" * 20, [], [])

    def record(self, argv, *args, **kwargs):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        self.envs.append(kwargs.get("env"))
        out, rc, err = "", 0, ""
        joined = " ".join(argv)
        if self.fail_script and any(a.endswith(self.fail_script) for a in argv):
            return subprocess.CompletedProcess(argv, 3, "", "line1\nboom: stage blew up\n")
        if argv[:2] == ["git", "-C"] and "branch" in argv:
            out = self.existing_branch
        elif argv[0] == "pre-commit":
            self.dirty |= set(self.precommit_rewrites)
            rc = 1 if self.precommit_rewrites else 0
            out = "trim trailing whitespace....Failed\n" if rc else ""
        elif "status" in argv and "--porcelain" in argv:
            out = "".join(f" M {f}\n" for f in sorted(self.dirty))
        elif "checkout" in argv and "--" in argv:
            self.dirty -= set(argv[argv.index("--") + 1:])
        elif "rev-parse" in argv:
            out = "f" * 40 + "\n"
        elif "show" in argv and "--name-only" in argv:
            out = "a.cxx\n" if argv[-1].startswith("c1") else "b.cxx\nc.h\n"
        elif "--run-ctest" in argv:
            out = f"{self.ctest_token}\n"
            log = self.ctest_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
            if self.ctest_failed:
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text("".join(f"{i}:{t}\n" for i, t in enumerate(self.ctest_failed)))
        elif "--ctest-dir" in argv:
            out = f"{self.ctest_dir}\n"
        elif argv[:2] == ["pixi", "run"]:
            out = "[1/2] x\nfoo.cxx:3:1: warning: unused variable 'q'\n"
            rc = self.build_rc
            assert not self.dirty, "build saw files rewritten by pre-commit"
        manifest = _flag(argv, "--manifest")
        if manifest and "sizetype_filled.py" in joined:
            Manifest("itk-helpers", [Site(Path("s.cxx"), 1, 1, "itk-helpers", "fill")]).write(Path(manifest))
        if manifest and "allocate_initialized.py" in joined:
            Manifest("itk-helpers", [
                Site(Path("s.cxx"), 5, 5, "itk-helpers", "allocate", Reason.ITK_VERSION),
            ]).write(Path(manifest))
        return subprocess.CompletedProcess(argv, rc, out, err)

    def stage_calls(self) -> list[list[str]]:
        return [c for c in self.calls if any(a.endswith((".py", ".sh")) and "skills" in a for a in c)]


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def _report(world) -> str:
    found = sorted((world.kit / ".devlocal" / "init-over-assign").glob("BRAINSTools-*.md"))
    assert len(found) == 1
    return found[0].read_text()


def test_stages_run_in_spec_order():
    assert [s.kind for s in pipeline.STAGES] == [
        "member-init", "local-init", "container-list-init", "itk-helpers", "narrow-scope",
    ]
    assert [s.const_after for s in pipeline.STAGES] == [
        None, "local-const", "container-const", "itk-helpers-constexpr", None,
    ]
    assert [k for k, _ in pipeline.select(None)] == KINDS


def test_select_rejects_const_without_parent():
    with pytest.raises(ValueError, match="local-init"):
        pipeline.select(["local-const"])
    with pytest.raises(ValueError, match="unknown"):
        pipeline.select(["bogus"])
    assert [k for k, _ in pipeline.select(["local-init", "local-const"])] == ["local-init", "local-const"]


def test_run_refuses_on_preflight_error_with_exit_2(world, monkeypatch, capsys):
    def refuse(repo, forest, kit):
        raise PreflightError("dirty-tree", "uncommitted changes")

    monkeypatch.setattr(preflight, "check", refuse)
    assert world.run.main(["BRAINSTools"]) == 2
    assert "dirty-tree" in capsys.readouterr().err
    assert world.calls == []


def test_run_refuses_when_branch_exists(world, capsys):
    world.existing_branch = "  style-init-over-assign-20261027\n"
    assert world.run.main(["BRAINSTools"]) == 2
    assert "branch-exists" in capsys.readouterr().err
    assert not any("checkout" in c for c in world.calls)
    assert world.stage_calls() == []


def test_run_partitions_once_after_all_stages(world, capsys):
    assert world.run.main(["BRAINSTools"]) == 0
    assert capsys.readouterr().out.splitlines()[0].startswith("Repo: BRAINSTools (aaaaaaaaaaaa)")
    assert len(world.plan_args) == 1
    recs = world.plan_args[0]
    assert [r.kind for r in recs] == KINDS
    assert len(recs) == 8
    assert [(r.tree_before, r.tree_after) for r in recs][:2] == [("tree1", "tree2"), ("tree3", "tree4")]
    calls = world.stage_calls()
    seen = [next(a for a in c if a.endswith((".py", ".sh")) and "skills" in a) for c in calls]
    assert len(seen) == 11
    assert all(s.endswith(want) for s, want in zip(seen, SCRIPTS))
    kinds = [_flag(c, "--kind") for c in calls if _flag(c, "--kind")]
    assert kinds == ["local-const", "container-const", "itk-helpers-constexpr"]
    plan_at = world.calls.index(next(c for c in world.calls if c[:2] == ["pixi", "run"]))
    last_stage = world.calls.index(calls[-1])
    assert last_stage < plan_at
    assert world.applied == ["local-init", "narrow-scope"]


def test_const_stages_read_their_parent_manifest(world):
    world.run.main(["BRAINSTools"])
    calls = world.stage_calls()
    manifests = {_flag(c, "--kind") or "": c for c in calls}
    mdir = Path(_flag(calls[0], "--manifest")).parent
    assert _flag(manifests["local-const"], "--only-from") == str(mdir / "local-init.json")
    assert _flag(manifests["container-const"], "--only-from") == str(mdir / "container-list-init.json")
    assert _flag(manifests["itk-helpers-constexpr"], "--only-from") == str(mdir / "itk-helpers.json")
    dti = next(c for c in calls if any(a.endswith("find_declare_then_init.py") for a in c))
    assert _flag(dti, "--classes") == "assign,elem_diff,elem_zero,sized_ctor,stream_open,bool_branch,placeholder"
    assert _flag(dti, "--repo-root") == str(world.repo)
    merged = Manifest.read(mdir / "itk-helpers.json")
    assert merged.kind == "itk-helpers" and len(merged.sites) == 2
    snaps = json.loads((mdir.parent / "snapshots.json").read_text())
    assert [s["kind"] for s in snaps] == KINDS


def test_run_exits_1_on_failing_stage_and_names_it(world):
    world.fail_script = "list_init.py"
    assert world.run.main(["BRAINSTools"]) == 1
    text = _report(world)
    assert "## Failing stage" in text and "container-list-init" in text and "boom: stage blew up" in text
    assert world.plan_args == []
    assert not any(c[:2] == ["pixi", "run"] for c in world.calls)


def test_disjoint_commits_listed_in_report(world):
    world.run.main(["BRAINSTools"])
    text = _report(world)
    assert "Disjoint from every other commit" in text
    assert "`c1c1c1c1c1c1` local-init" in text
    assert "### gate-failed (1)" in text and "b.cxx:9" in text
    assert "### itk-version (1)" in text and "s.cxx:5" in text
    assert "warning: unused variable 'q'" in text
    body = (world.kit / ".devlocal" / "pr-bodies" / "BRAINSTools-init-over-assign.md").read_text()
    assert "<details>" in body and "<!--" in body


def test_run_never_pushes_or_opens_pr(world):
    world.run.main(["BRAINSTools"])
    assert world.calls
    assert not any("push" in c or c[0] == "gh" for c in world.calls)


def test_run_exits_1_on_new_ctest_failure(world):
    world.ctest_failed = ["known", "fresh"]
    assert world.run.main(["BRAINSTools"]) == 1
    assert "`fresh`" in _report(world)


def test_dry_run_prints_commands_without_running(world, capsys):
    assert world.run.main(["BRAINSTools", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert world.plan_args == []
    assert all(c[:2] == ["git", "-C"] and "--list" in c for c in world.calls)
    assert "member-init:" in out and "narrow_scope.py" in out and "--only-from" in out
    assert "pre-commit run --all-files" in out and "pixi run build-BRAINSTools" in out
    assert "--run-ctest BRAINSTools" in out


def test_dry_run_refuses_existing_branch(world, capsys):
    world.existing_branch = "style-init-over-assign-20261027\n"
    assert world.run.main(["BRAINSTools", "--dry-run"]) == 2
    assert "branch-exists" in capsys.readouterr().err


def test_precommit_rewrites_are_restored_before_build_and_fail_the_run(world):
    (world.repo / ".pre-commit-config.yaml").write_text("repos: []\n")
    world.precommit_rewrites = ["Common/x.cxx"]
    assert world.run.main(["BRAINSTools"]) == 1
    assert ["git", "-C", str(world.repo), "checkout", "--", "Common/x.cxx"] in world.calls
    assert any("--run-ctest" in c for c in world.calls)
    text = _report(world)
    assert "### pre-commit changed files (not committed)" in text and "- Common/x.cxx" in text
    assert "FAILED: trim trailing whitespace" in text


def test_exception_after_stages_still_writes_report(world, capsys):
    world.apply_raises = True
    assert world.run.main(["BRAINSTools"]) == 1
    text = _report(world)
    assert "## Run error" in text and "partition.apply narrow-scope" in text
    assert "RuntimeError: index has staged changes" in text and "in apply" in text
    assert "`c1c1c1c1c1c1`" in text
    assert "report:" in capsys.readouterr().err


def test_failures_token_without_log_is_not_green(world):
    world.ctest_token = "T:8/10"
    assert world.run.main(["BRAINSTools"]) == 1
    assert "failures reported but no" in _report(world)


def test_ctest_that_did_not_run_is_not_green(world):
    world.ctest_token = "T:0/0:no-tests"
    assert world.run.main(["BRAINSTools"]) == 1
    assert "ctest did not run" in _report(world)


def test_build_failure_exits_1_without_ctest(world):
    world.build_rc = 2
    assert world.run.main(["BRAINSTools"]) == 1
    assert not any("--run-ctest" in c for c in world.calls)
    text = _report(world)
    assert "Full build and artifact check: FAIL" in text and "exited 2" in text
    assert "Warnings in the rebuild log:" in text


def test_baseline_refusal_writes_report_and_exits_2(world, monkeypatch):
    def refuse(coords, kit):
        raise RuntimeError("ctest did not run for BRAINSTools: T:skip")

    monkeypatch.setattr(baseline, "ensure", refuse)
    assert world.run.main(["BRAINSTools"]) == 2
    text = _report(world)
    assert "## Run error" in text and "`baseline`" in text and "(not created)" in text
    assert not any("checkout" in c for c in world.calls)


def test_build_and_ctest_pin_the_forest_env(world, monkeypatch):
    monkeypatch.setenv("FOREST", "/elsewhere")
    monkeypatch.setenv("BUILD_FOREST_ROOT", "/elsewhere")
    monkeypatch.delenv("FOREST_REFERENCE_SUFFIX", raising=False)
    world.run.main(["BRAINSTools"])
    pinned = [e for c, e in zip(world.calls, world.envs)
              if c[:2] == ["pixi", "run"] or any(a.endswith("run-matrix.sh") for a in c)]
    assert len(pinned) == 4
    for env in pinned:
        assert env["FOREST_REFERENCE_SUFFIX"] == "itk-main"
        assert "FOREST" not in env and "BUILD_FOREST_ROOT" not in env
    import os
    assert "FOREST_REFERENCE_SUFFIX" not in os.environ


def test_missing_manifest_is_noted(world):
    world.run.main(["BRAINSTools"])
    text = _report(world)
    assert "## Notes" in text and "member-init: no manifest written" in text


def test_stages_option_restricts_the_run(world):
    assert world.run.main(["BRAINSTools", "--stages", "local-init,local-const,narrow-scope"]) == 0
    assert [r.kind for r in world.plan_args[0]] == ["local-init", "local-const", "narrow-scope"]
    assert world.run.main(["BRAINSTools", "--stages", "local-const"]) == 2


def test_report_write_sections(tmp_path):
    kit = tmp_path / "kit"
    run_dir = kit / ".devlocal" / "init-over-assign" / "ITK-20261027_0900"
    coords = Coordinates("ITK", "b" * 40, "build_forest-itk-main", tmp_path / "g", "6.0.0")
    commits = [
        report.Commit("1" * 40, "local-init", ["a.cxx"], 3, "pass"),
        report.Commit("2" * 40, "narrow-scope", ["a.cxx", "b.cxx"], 2, "1 gate-failed"),
        report.Commit("3" * 40, "itk-helpers", ["c.cxx"], 1, "pass"),
    ]
    skips = [Site(Path("a.cxx"), 4, 4, "local-init", "assign", Reason.LOOP_CARRIED, "x")]
    build = report.Build(precommit="passed", ok=True, detail="", warnings=[])
    ctest = report.Ctest(ok=True, token="T:5/5", new=[], baseline=tmp_path / "b.json")
    path = report.write(
        kit, coords, commits, skips, build, ctest,
        branch="style-init-over-assign-20261027", tip="9" * 40, run_dir=run_dir,
    )
    assert path == run_dir.parent / "ITK-20261027_0900.md"
    text = path.read_text()
    for heading in ("## Commits", "## Disjoint commits", "## Skip list", "## Build", "## ctest"):
        assert heading in text
    assert "Repo: ITK (bbbbbbbbbbbb) | Forest: build_forest-itk-main | ITK: 6.0.0" in text
    assert "### loop-carried (1)" in text and "a.cxx:4" in text
    assert "`333333333333` itk-helpers" in text and "`111111111111`" not in text.split("## Disjoint commits")[1].split("##")[0]
    assert "## Failing stage" not in text
    assert all(
        len(ln) <= 80 for ln in text.splitlines()
        if not (ln.startswith(("|", "-")) and "/" in ln)
    )
    body = (kit / ".devlocal" / "pr-bodies" / "ITK-init-over-assign.md").read_text()
    assert body.count("<details>") == 2
    assert "<summary>What changed, and what was left alone</summary>" in body
    assert "<summary>Testing and AI disclosure</summary>" in body
    assert "itk-init-over-assign" in body and "must review" in body
    assert "run_dir:" in body and "baseline:" in body and "kit_commit:" in body
    assert "—" not in body and "—" not in text


def test_report_lists_forest_local_commits(tmp_path):
    kit = tmp_path / "kit"
    run_dir = kit / ".devlocal" / "init-over-assign" / "ITK-20261027_0900"
    coords = Coordinates(
        "ITK", "b" * 40, "build_forest-itk-main", tmp_path / "g", "6.0.0",
        ["COMP: forest-local tbb patch"],
    )
    path = report.write(
        kit, coords, [], [], None, None, branch="b", tip="9" * 40, run_dir=run_dir
    )
    text = path.read_text()
    assert "Forest-local commits (drop before opening the PR):" in text
    assert "- COMP: forest-local tbb patch" in text
    body = (kit / ".devlocal" / "pr-bodies" / "ITK-init-over-assign.md").read_text()
    comment = body.split("<!--")[1]
    assert "COMP: forest-local tbb patch" in comment and "drop them before" in comment
    assert "COMP: forest-local" not in body.split("<!--")[0]
