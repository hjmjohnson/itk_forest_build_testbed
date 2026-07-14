# Forest TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Textual TUI (`pixi run tui`) that wizards through forest / ITK-ref / project / test selection, then executes the plan live with per-step PASS/FAIL scored by artifact.

**Architecture:** New Python package `bin/forest_tui/` is a thin orchestrator over the existing bash engine. `bin/run-matrix.sh` gains additive query/action subcommands (`--list-targets`, `--list-deferred`, `--check-artifact`, `--ctest-dir`, `--run-ctest`) so target/artifact/ctest knowledge has one source of truth. The TUI spawns those scripts as async subprocesses with `FOREST_REFERENCE_SUFFIX` / `ITK_REF` / `CTEST_*` in the environment.

**Tech Stack:** Python ≥3.11, Textual (conda-forge, via pixi), bash engine scripts already in the kit.

**Spec:** `docs/superpowers/specs/2026-07-14-forest-tui-design.md`

## Global Constraints

- Repo: the **kit repo** (`hjmjohnson/itk_forest_build_testbed`). Never touch consumer source trees.
- Default `run-matrix.sh` behavior (no flags) must be byte-for-byte unchanged.
- Build success is decided by artifact check, never by subprocess exit code.
- Cross-platform bash: `grep -E` only, no `sed -i`, no GNU-only flags (macOS BSD + Linux GNU).
- Tests follow the existing `bin/tests/` convention: pytest-compatible functions PLUS a standalone `if __name__ == "__main__":` runner loop (see `bin/tests/test_compare.py`). Run them with plain `python3`.
- Every subprocess step logs to a file under `<forest>/logs/` before anything else.
- Per `code-comment-minimization`: near-zero comments; one line max, why-only.
- Commit after each task. No pushes, no PRs (per `pr-no-unsolicited`).

**Run all tests from repo root as:** `for t in bin/tests/test_*.py; do python3 "$t" || break; done`

---

### Task 1: `run-matrix.sh` query/action subcommands

**Files:**
- Modify: `bin/run-matrix.sh` (insert after the `TARGETS=(...)` array, before the `for t in` loop, currently lines ~136–142)
- Test: `bin/tests/test_matrix_cli.py`

**Interfaces:**
- Produces (consumed by Tasks 2, 4):
  - `bash bin/run-matrix.sh --list-targets` → active targets, one per line, dependency order, exit 0
  - `bash bin/run-matrix.sh --list-deferred` → `name<TAB>reason` lines, exit 0
  - `bash bin/run-matrix.sh --check-artifact <X>` → exit 0 iff artifact exists (respects `FOREST` / `FOREST_REFERENCE_SUFFIX` env)
  - `bash bin/run-matrix.sh --ctest-dir <X>` → prints ctest harness dir (empty if none), exit 0
  - `bash bin/run-matrix.sh --run-ctest <X>` → runs the suite (honors `CTEST_INCLUDE`, `CTEST_JOBS`, `CTEST_TIMEOUT`, `CTEST_TARGET_TIMEOUT` env), prints one token `T:<passed>/<total>` / `T:skip:no-harness` / `T:timeout` / `T:unknown`, exit 0

- [ ] **Step 1: Write the failing test**

Create `bin/tests/test_matrix_cli.py`:

```python
import os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATRIX = os.path.join(ROOT, "bin", "run-matrix.sh")

def _run(args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(["bash", MATRIX] + args, capture_output=True, text=True, env=e)

def test_list_targets_dependency_order():
    r = _run(["--list-targets"])
    assert r.returncode == 0
    targets = r.stdout.split()
    assert targets[0] == "ITK"
    assert "elastix" in targets and "Slicer" in targets
    assert targets.index("ANTs") < targets.index("BRAINSTools")
    assert targets.index("Slicer") < targets.index("SlicerExtensions")

def test_list_deferred_has_reasons():
    r = _run(["--list-deferred"])
    assert r.returncode == 0
    rows = [l.split("\t") for l in r.stdout.strip().splitlines()]
    names = [row[0] for row in rows]
    assert "Ultrasound" in names and "LesionSizingToolkit" in names
    assert all(len(row) == 2 and row[1] for row in rows)

def test_check_artifact_fails_on_empty_forest():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(["--check-artifact", "ITK"], env={"FOREST": tmp})
        assert r.returncode != 0

def test_ctest_dir_empty_on_empty_forest():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(["--ctest-dir", "elastix"], env={"FOREST": tmp})
        assert r.returncode == 0
        assert r.stdout.strip() == ""

def test_run_ctest_no_harness_token():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(["--run-ctest", "elastix"], env={"FOREST": tmp})
        assert r.returncode == 0
        assert r.stdout.strip().endswith("T:skip:no-harness")

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_matrix_cli.py`
Expected: FAIL — `--list-targets` is not recognized, so `run-matrix.sh` starts a real matrix run; the first assertion on stdout content fails (interrupt if it starts building: the test env `FOREST` guard only applies to two tests). If it hangs, Ctrl-C — the failure mode confirms the flag is missing.

- [ ] **Step 3: Implement the subcommands**

In `bin/run-matrix.sh`, immediately AFTER the `TARGETS=(...)` array and BEFORE the `for t in "${TARGETS[@]}"` loop, insert:

```bash
# Deferred targets (see docs/DEFERRED-FAILURES.md) as machine-readable rows.
DEFERRED_TARGETS=(
  $'TubeTK\tneeds its own module/data deps'
  $'c3d\tneeds its own module/data deps'
  $'BioCell\tneeds its own module/data deps'
  $'HASI\tneeds its own module/data deps'
  $'Shape\tneeds its own module/data deps'
  $'SkullStrip\tneeds its own module/data deps'
  $'Ultrasound\textra ITK COMPILE_DEPENDS / clFFT not resolved'
  $'LesionSizingToolkit\tneeds more ITK modules enabled (missing headers)'
  $'SphinxExamples\tExternalData test-data fetch failure'
)

# Query/action modes for tooling (forest_tui); default no-flag behavior unchanged.
case "${1:-}" in
  --list-targets)   printf '%s\n' "${TARGETS[@]}"; exit 0 ;;
  --list-deferred)  printf '%s\n' "${DEFERRED_TARGETS[@]}"; exit 0 ;;
  --check-artifact) artifact_ok "${2:?usage: --check-artifact <target>}"; exit $? ;;
  --ctest-dir)      ctest_dir "${2:?usage: --ctest-dir <target>}"; exit 0 ;;
  --run-ctest)      run_ctest "${2:?usage: --run-ctest <target>}"; exit 0 ;;
esac
```

Also update the usage comment block at the top of the file (lines 4–6) to mention the query modes in one line:

```bash
#   bin/run-matrix.sh --list-targets|--list-deferred|--check-artifact <X>|--ctest-dir <X>|--run-ctest <X>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_matrix_cli.py`
Expected: `ok test_...` ×5, `PASS`

- [ ] **Step 5: Verify default behavior unchanged**

Run: `bash -n bin/run-matrix.sh && FOREST=$(mktemp -d) bash bin/run-matrix.sh 2>&1 | head -5`
Expected: syntax OK; output starts `==================== BUILD ITK ====================` then `RESULT ITK: build FAIL` and `ITK FAILED — aborting` (empty forest, nothing builds — proves the no-flag path still enters the matrix loop). This finishes in seconds since the build log fails immediately.

- [ ] **Step 6: Commit**

```bash
git add bin/run-matrix.sh bin/tests/test_matrix_cli.py
git commit -m "ENH: run-matrix.sh gains query/action subcommands for tooling"
```

---

### Task 2: Plan model — selections → steps → reproducible script

**Files:**
- Create: `bin/forest_tui/__init__.py` (empty)
- Create: `bin/forest_tui/plan.py`
- Test: `bin/tests/test_tui_plan.py`

**Interfaces:**
- Consumes: engine paths only (`bin/setup-itk-downstream-testbed.sh`, `bin/run-matrix.sh`).
- Produces (consumed by Tasks 4, 5):
  - `CtestOpts(enabled: bool, include_regex: str, test_timeout: int, target_timeout: int)`
  - `Selections(forest_suffix: str, create_forest: bool, itk_ref: str, full_matrix: bool, projects: list[str], ctest: dict[str, CtestOpts])` — `forest_suffix=""` means default `build_forest`; `itk_ref=""` means keep current checkout
  - `Step(name: str, argv: list[str], env: dict[str, str], kind: str, target: str)` — `kind ∈ {"checkout","repoint","build","ctest","matrix"}`
  - `forest_dir(root: Path, suffix: str) -> Path`
  - `prereq_closure(selected: list[str], order: list[str]) -> list[str]`
  - `build_steps(sel: Selections) -> list[Step]`
  - `emit_plan_script(sel: Selections, steps: list[Step]) -> str`

- [ ] **Step 1: Write the failing test**

Create `bin/tests/test_tui_plan.py`:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from forest_tui.plan import (CtestOpts, Selections, build_steps, emit_plan_script,
                             forest_dir, prereq_closure)

ORDER = ["ITK", "elastix", "SimpleITK", "ANTs", "BRAINSTools",
         "OpenIGTLink", "Slicer", "SlicerExtensions", "OpenIGTLinkIO"]

def test_forest_dir():
    assert forest_dir(Path("/r"), "") == Path("/r/build_forest")
    assert forest_dir(Path("/r"), "pr6487") == Path("/r/build_forest-pr6487")

def test_prereq_closure_pulls_chain_in_order():
    assert prereq_closure(["BRAINSTools"], ORDER) == ["ITK", "ANTs", "BRAINSTools"]
    assert prereq_closure(["OpenIGTLinkIO"], ORDER) == ["ITK", "OpenIGTLink", "Slicer", "OpenIGTLinkIO"]
    assert prereq_closure(["elastix"], ORDER) == ["ITK", "elastix"]

def test_build_steps_repoint_and_builds_and_ctest():
    sel = Selections(forest_suffix="pr9999", create_forest=False, itk_ref="pr/9999",
                     full_matrix=False, projects=["ITK", "elastix"],
                     ctest={"elastix": CtestOpts(True, "elx", 100, 900)})
    steps = build_steps(sel)
    kinds = [s.kind for s in steps]
    assert kinds == ["repoint", "build", "build", "ctest"]
    assert steps[0].env["ITK_REF"] == "pr/9999"
    assert all(s.env.get("FOREST_REFERENCE_SUFFIX") == "pr9999" for s in steps)
    ct = steps[-1]
    assert ct.argv[-2:] == ["--run-ctest", "elastix"]
    assert ct.env["CTEST_INCLUDE"] == "elx"
    assert ct.env["CTEST_TIMEOUT"] == "100"
    assert ct.env["CTEST_TARGET_TIMEOUT"] == "900"

def test_build_steps_new_forest_starts_with_checkout():
    sel = Selections("fresh", True, "upstream/main", False, ["ITK"], {})
    assert [s.kind for s in build_steps(sel)] == ["checkout", "repoint", "build"]

def test_build_steps_full_matrix_supersedes_projects():
    sel = Selections("", False, "", True, ["ITK", "elastix"], {})
    steps = build_steps(sel)
    assert [s.kind for s in steps] == ["matrix"]
    assert "FOREST_REFERENCE_SUFFIX" not in steps[0].env

def test_emit_plan_script_is_runnable_shell():
    sel = Selections("pr9999", False, "pr/9999", False, ["ITK"], {})
    txt = emit_plan_script(sel, build_steps(sel))
    assert txt.startswith("#!/usr/bin/env bash")
    assert "Forest: build_forest-pr9999 | ITK: pr/9999" in txt
    assert "FOREST_REFERENCE_SUFFIX=pr9999 ITK_REF=pr/9999 bash bin/setup-itk-downstream-testbed.sh repoint-itk" in txt

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_tui_plan.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'forest_tui'`

- [ ] **Step 3: Implement `bin/forest_tui/plan.py`** (and empty `bin/forest_tui/__init__.py`)

```python
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

ENGINE = "bin/setup-itk-downstream-testbed.sh"
MATRIX = "bin/run-matrix.sh"

PREREQS: dict[str, list[str]] = {
    "ITK": [],
    "ANTs": ["ITK"],
    "BRAINSTools": ["ANTs"],
    "Slicer": ["ITK"],
    "SlicerExtensions": ["Slicer"],
    "OpenIGTLinkIO": ["Slicer", "OpenIGTLink"],
    "vtkAddon": ["Slicer"],
    "IGSIO": ["Slicer"],
    "PlusLib": ["Slicer"],
}


@dataclass
class CtestOpts:
    enabled: bool = False
    include_regex: str = ""
    test_timeout: int = 300
    target_timeout: int = 1800


@dataclass
class Selections:
    forest_suffix: str = ""
    create_forest: bool = False
    itk_ref: str = ""
    full_matrix: bool = False
    projects: list[str] = field(default_factory=list)
    ctest: dict[str, CtestOpts] = field(default_factory=dict)


@dataclass
class Step:
    name: str
    argv: list[str]
    env: dict[str, str]
    kind: str
    target: str = ""


def forest_dir(root: Path, suffix: str) -> Path:
    return root / (f"build_forest-{suffix}" if suffix else "build_forest")


def prereq_closure(selected: list[str], order: list[str]) -> list[str]:
    seen: set[str] = set()

    def add(t: str) -> None:
        if t in seen:
            return
        seen.add(t)
        for p in PREREQS.get(t, ["ITK"]):
            add(p)

    for t in selected:
        add(t)
    return [t for t in order if t in seen]


def _base_env(sel: Selections) -> dict[str, str]:
    return {"FOREST_REFERENCE_SUFFIX": sel.forest_suffix} if sel.forest_suffix else {}


def build_steps(sel: Selections) -> list[Step]:
    env = _base_env(sel)
    steps: list[Step] = []
    if sel.create_forest:
        steps.append(Step("checkout", ["bash", ENGINE, "checkout"], dict(env), "checkout"))
    if sel.itk_ref:
        steps.append(Step(f"repoint-itk {sel.itk_ref}", ["bash", ENGINE, "repoint-itk"],
                          {**env, "ITK_REF": sel.itk_ref}, "repoint"))
    if sel.full_matrix:
        steps.append(Step("run-matrix", ["bash", MATRIX], dict(env), "matrix"))
        return steps
    for p in sel.projects:
        steps.append(Step(f"build {p}", ["bash", ENGINE, "build", p], dict(env), "build", target=p))
        c = sel.ctest.get(p)
        if c and c.enabled:
            cenv = dict(env)
            if c.include_regex:
                cenv["CTEST_INCLUDE"] = c.include_regex
            cenv["CTEST_TIMEOUT"] = str(c.test_timeout)
            cenv["CTEST_TARGET_TIMEOUT"] = str(c.target_timeout)
            steps.append(Step(f"ctest {p}", ["bash", MATRIX, "--run-ctest", p], cenv, "ctest", target=p))
    return steps


def emit_plan_script(sel: Selections, steps: list[Step]) -> str:
    forest = f"build_forest-{sel.forest_suffix}" if sel.forest_suffix else "build_forest"
    ref = sel.itk_ref or "(current checkout)"
    lines = [
        "#!/usr/bin/env bash",
        f"# Forest: {forest} | ITK: {ref}",
        "# Generated by forest-tui; run from the kit repo root.",
        "set -euo pipefail",
        "",
    ]
    for s in steps:
        envs = " ".join(f"{k}={shlex.quote(v)}" for k, v in s.env.items())
        cmd = " ".join(shlex.quote(a) for a in s.argv)
        lines.append(f"{envs} {cmd}".strip())
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_tui_plan.py`
Expected: `ok test_...` ×6, `PASS`

- [ ] **Step 5: Commit**

```bash
git add bin/forest_tui/__init__.py bin/forest_tui/plan.py bin/tests/test_tui_plan.py
git commit -m "ENH: forest_tui plan model builds step lists and reproducible scripts"
```

---

### Task 3: Discovery — forests on disk, targets, deferred list

**Files:**
- Create: `bin/forest_tui/discover.py`
- Test: `bin/tests/test_tui_discover.py`

**Interfaces:**
- Consumes: Task 1 subcommands; `forest_dir` from `forest_tui.plan`.
- Produces (consumed by Task 5):
  - `ForestInfo(suffix: str, path: Path, itk_branch: str, itk_sha: str, itk_describe: str, itk_artifact: bool, last_matrix_log: float | None)`
  - `list_forests(root: Path) -> list[ForestInfo]` — scans `root` for `build_forest*` dirs
  - `list_targets(root: Path) -> list[str]`
  - `list_deferred(root: Path) -> list[tuple[str, str]]`
  - `check_artifact(root: Path, forest: Path, target: str) -> bool`
  - `error_grep(log: Path, n: int = 3) -> list[str]` — same pattern the matrix uses

- [ ] **Step 1: Write the failing test**

Create `bin/tests/test_tui_discover.py`:

```python
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from forest_tui import discover

ROOT = Path(__file__).resolve().parents[2]

def _mk_forest(root: Path, name: str) -> Path:
    f = root / name
    itk = f / "ITK"
    itk.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "itk-downstream"], cwd=itk, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=itk, check=True)
    return f

def test_list_forests_finds_and_describes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _mk_forest(root, "build_forest")
        f2 = _mk_forest(root, "build_forest-pr42")
        (f2 / "ITK" / "build" / "lib").mkdir(parents=True)
        (f2 / "ITK" / "build" / "lib" / "libITKCommon-6.0.a").touch()
        (f2 / "logs").mkdir()
        (f2 / "logs" / "matrix-ITK-pr42.log").touch()
        forests = discover.list_forests(root)
        by_suffix = {f.suffix: f for f in forests}
        assert set(by_suffix) == {"", "pr42"}
        assert by_suffix[""].itk_branch == "itk-downstream"
        assert len(by_suffix[""].itk_sha) >= 7
        assert by_suffix[""].itk_artifact is False
        assert by_suffix["pr42"].itk_artifact is True
        assert by_suffix["pr42"].last_matrix_log is not None

def test_list_forests_skips_forest_without_itk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "build_forest-empty").mkdir()
        forests = discover.list_forests(root)
        assert [f.suffix for f in forests] == ["empty"]
        assert forests[0].itk_sha == ""

def test_list_targets_and_deferred_against_real_matrix():
    targets = discover.list_targets(ROOT)
    assert targets[0] == "ITK" and "elastix" in targets
    deferred = dict(discover.list_deferred(ROOT))
    assert "Ultrasound" in deferred

def test_error_grep():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "x.log"
        log.write_text("ok line\nfoo.cxx:3: error: boom\nCMake Error at y\nnoise\n")
        assert discover.error_grep(log) == ["foo.cxx:3: error: boom", "CMake Error at y"]

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_tui_discover.py`
Expected: FAIL with `ImportError: cannot import name 'discover'` (or ModuleNotFoundError)

- [ ] **Step 3: Implement `bin/forest_tui/discover.py`**

```python
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MATRIX = "bin/run-matrix.sh"
ERROR_RE = re.compile(r"error:|CMake Error|library not found|No such module|undefined sym", re.I)


@dataclass
class ForestInfo:
    suffix: str
    path: Path
    itk_branch: str = ""
    itk_sha: str = ""
    itk_describe: str = ""
    itk_artifact: bool = False
    last_matrix_log: float | None = None


def _git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def list_forests(root: Path) -> list[ForestInfo]:
    out: list[ForestInfo] = []
    for d in sorted(root.glob("build_forest*")):
        if not d.is_dir():
            continue
        suffix = d.name.removeprefix("build_forest").removeprefix("-")
        info = ForestInfo(suffix=suffix, path=d)
        itk = d / "ITK"
        if itk.is_dir():
            info.itk_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], itk)
            info.itk_sha = _git(["rev-parse", "--short=12", "HEAD"], itk)
            info.itk_describe = _git(["describe", "--tags", "--always"], itk)
        info.itk_artifact = any((itk / "build" / "lib").glob("libITKCommon-*.a")) or \
                            any((d / "ITK-build" / "lib").glob("libITKCommon-*.a"))
        logs = list((d / "logs").glob("matrix-*.log")) if (d / "logs").is_dir() else []
        if logs:
            info.last_matrix_log = max(p.stat().st_mtime for p in logs)
        out.append(info)
    return out


def list_targets(root: Path) -> list[str]:
    r = subprocess.run(["bash", MATRIX, "--list-targets"], cwd=root, capture_output=True, text=True)
    return r.stdout.split()


def list_deferred(root: Path) -> list[tuple[str, str]]:
    r = subprocess.run(["bash", MATRIX, "--list-deferred"], cwd=root, capture_output=True, text=True)
    rows = [line.split("\t", 1) for line in r.stdout.strip().splitlines() if "\t" in line]
    return [(n, reason) for n, reason in rows]


def check_artifact(root: Path, forest: Path, target: str) -> bool:
    import os
    env = {**os.environ, "FOREST": str(forest)}
    r = subprocess.run(["bash", MATRIX, "--check-artifact", target], cwd=root, env=env,
                       capture_output=True, text=True)
    return r.returncode == 0


def error_grep(log: Path, n: int = 3) -> list[str]:
    hits: list[str] = []
    try:
        for line in log.read_text(errors="replace").splitlines():
            if ERROR_RE.search(line):
                hits.append(line)
                if len(hits) == n:
                    break
    except OSError:
        pass
    return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_tui_discover.py`
Expected: `ok test_...` ×4, `PASS`

- [ ] **Step 5: Commit**

```bash
git add bin/forest_tui/discover.py bin/tests/test_tui_discover.py
git commit -m "ENH: forest_tui discovery of forests, targets, deferred reasons"
```

---

### Task 4: Runner — async step execution scored by artifact

**Files:**
- Create: `bin/forest_tui/runner.py`
- Test: `bin/tests/test_tui_runner.py`

**Interfaces:**
- Consumes: `Step` from `forest_tui.plan`; `check_artifact`, `error_grep` from `forest_tui.discover`.
- Produces (consumed by Task 5):
  - `StepResult(status: str, detail: str, log: Path)` — `status ∈ {"PASS","FAIL","SKIP"}`
  - `async run_step(step: Step, root: Path, forest: Path, on_line: Callable[[str], None]) -> StepResult` — streams merged stdout/stderr lines to `on_line` AND to `<forest>/logs/tui-<step>.log`; decides build PASS/FAIL via `check_artifact`, ctest PASS/FAIL via the `T:` token; other kinds by exit code
  - `parse_ctest_token(text: str) -> tuple[str, str]` — returns `(status, token)`
  - `terminate(proc)` — kills the whole process group (steps start with `start_new_session=True`)

- [ ] **Step 1: Write the failing test**

Create `bin/tests/test_tui_runner.py`:

```python
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from forest_tui.plan import Step
from forest_tui import runner

def _run(coro):
    return asyncio.run(coro)

def test_parse_ctest_token():
    assert runner.parse_ctest_token("blah\nT:150/150\n") == ("PASS", "T:150/150")
    assert runner.parse_ctest_token("T:142/150") == ("FAIL", "T:142/150")
    assert runner.parse_ctest_token("T:skip:no-harness") == ("SKIP", "T:skip:no-harness")
    assert runner.parse_ctest_token("T:timeout") == ("FAIL", "T:timeout")
    assert runner.parse_ctest_token("T:0/0:no-tests") == ("PASS", "T:0/0:no-tests")
    assert runner.parse_ctest_token("garbage") == ("FAIL", "T:unknown")

def test_run_step_streams_and_logs():
    with tempfile.TemporaryDirectory() as tmp:
        forest = Path(tmp); (forest / "logs").mkdir()
        step = Step("echo hello", ["bash", "-c", "echo hello; echo two"], {}, "checkout")
        lines = []
        res = _run(runner.run_step(step, Path.cwd(), forest, lines.append))
        assert res.status == "PASS"
        assert "hello" in lines[0]
        assert "hello" in res.log.read_text()

def test_run_step_build_fail_by_artifact_despite_exit_zero():
    with tempfile.TemporaryDirectory() as tmp:
        forest = Path(tmp); (forest / "logs").mkdir()
        step = Step("build ITK", ["bash", "-c", "echo 'x.cxx:1: error: nope'; exit 0"],
                    {}, "build", target="ITK")
        res = _run(runner.run_step(step, Path.cwd(), forest, lambda s: None))
        assert res.status == "FAIL"
        assert "error: nope" in res.detail

def test_run_step_nonbuild_fails_by_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        forest = Path(tmp); (forest / "logs").mkdir()
        step = Step("repoint-itk bad", ["bash", "-c", "exit 3"], {}, "repoint")
        res = _run(runner.run_step(step, Path.cwd(), forest, lambda s: None))
        assert res.status == "FAIL"

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

Note: `test_run_step_build_fail_by_artifact_despite_exit_zero` relies on `check_artifact` failing because the temp forest has no ITK artifact — that is the point: exit 0 must not mean PASS.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_tui_runner.py`
Expected: FAIL with import error on `forest_tui.runner`

- [ ] **Step 3: Implement `bin/forest_tui/runner.py`**

```python
from __future__ import annotations

import asyncio
import os
import re
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .discover import check_artifact, error_grep
from .plan import Step

TOKEN_RE = re.compile(r"T:(\S+)")


@dataclass
class StepResult:
    status: str
    detail: str
    log: Path


def parse_ctest_token(text: str) -> tuple[str, str]:
    m = None
    for m in TOKEN_RE.finditer(text):
        pass
    if not m:
        return ("FAIL", "T:unknown")
    token = "T:" + m.group(1)
    body = m.group(1)
    if body.startswith("skip"):
        return ("SKIP", token)
    if body in ("timeout", "unknown"):
        return ("FAIL", token)
    nums = re.match(r"(\d+)/(\d+)", body)
    if nums:
        return ("PASS" if nums.group(1) == nums.group(2) else "FAIL", token)
    return ("FAIL", token)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def terminate(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


async def run_step(step: Step, root: Path, forest: Path,
                   on_line: Callable[[str], None]) -> StepResult:
    logdir = forest / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"tui-{_slug(step.name)}.log"
    env = {**os.environ, **step.env}
    proc = await asyncio.create_subprocess_exec(
        *step.argv, cwd=root, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        start_new_session=True)
    tail: list[str] = []
    with log.open("w", errors="replace") as fh:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip("\n")
            fh.write(line + "\n")
            fh.flush()
            tail.append(line)
            on_line(line)
    rc = await proc.wait()
    if step.kind == "build":
        if check_artifact(root, forest, step.target):
            return StepResult("PASS", "", log)
        return StepResult("FAIL", "; ".join(error_grep(log)), log)
    if step.kind == "ctest":
        status, token = parse_ctest_token("\n".join(tail[-20:]))
        return StepResult(status, token, log)
    return StepResult("PASS" if rc == 0 else "FAIL", f"exit {rc}" if rc else "", log)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_tui_runner.py`
Expected: `ok test_...` ×4, `PASS`

- [ ] **Step 5: Commit**

```bash
git add bin/forest_tui/runner.py bin/tests/test_tui_runner.py
git commit -m "ENH: forest_tui async runner scores steps by artifact and ctest token"
```

---

### Task 5: Textual app — wizard screens, run dashboard, `--dry-run` CLI

**Files:**
- Create: `bin/forest_tui/app.py`
- Create: `bin/forest_tui/__main__.py`
- Modify: `pixi.toml` (add `python`, `textual` deps; add `[tasks.tui]`)
- Test: `bin/tests/test_tui_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2–4.
- Produces:
  - `python3 -m forest_tui` — interactive wizard (needs `PYTHONPATH=bin`, provided by the pixi task)
  - `python3 -m forest_tui --dry-run --forest <suffix|''> [--new-forest] [--ref REF] [--projects A,B] [--full-matrix] [--ctest A,B] [--ctest-include RE]` — prints the plan script, runs nothing
  - `pixi run tui`

- [ ] **Step 1: Write the failing CLI test**

Create `bin/tests/test_tui_cli.py`:

```python
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _cli(args):
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "bin")}
    return subprocess.run([sys.executable, "-m", "forest_tui"] + args,
                          capture_output=True, text=True, cwd=ROOT, env=env)

def test_dry_run_emits_plan_script():
    r = _cli(["--dry-run", "--forest", "prX", "--ref", "pr/1234",
              "--projects", "elastix", "--ctest", "elastix"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert out.startswith("#!/usr/bin/env bash")
    assert "Forest: build_forest-prX | ITK: pr/1234" in out
    assert "build ITK" in out or "setup-itk-downstream-testbed.sh build ITK" in out
    assert "--run-ctest elastix" in out

def test_dry_run_prereq_closure_applied():
    r = _cli(["--dry-run", "--forest", "", "--projects", "BRAINSTools"])
    assert r.returncode == 0, r.stderr
    body = r.stdout
    assert body.index("build ITK") < body.index("build ANTs") < body.index("build BRAINSTools")

def test_dry_run_full_matrix():
    r = _cli(["--dry-run", "--forest", "", "--full-matrix"])
    assert r.returncode == 0, r.stderr
    assert "run-matrix.sh" in r.stdout

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_tui_cli.py`
Expected: FAIL — `No module named forest_tui.__main__`

- [ ] **Step 3: Implement `bin/forest_tui/__main__.py`**

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .discover import list_targets
from .plan import CtestOpts, Selections, build_steps, emit_plan_script, prereq_closure


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="forest_tui")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--forest", default=None, help="forest suffix; '' for default build_forest")
    p.add_argument("--new-forest", action="store_true")
    p.add_argument("--ref", default="")
    p.add_argument("--projects", default="")
    p.add_argument("--full-matrix", action="store_true")
    p.add_argument("--ctest", default="")
    p.add_argument("--ctest-include", default="")
    return p.parse_args(argv)


def selections_from_args(a: argparse.Namespace, root: Path) -> Selections:
    order = list_targets(root)
    projects = [t for t in a.projects.split(",") if t]
    if projects:
        projects = prereq_closure(projects, order)
    ctest = {t: CtestOpts(True, a.ctest_include) for t in a.ctest.split(",") if t}
    return Selections(a.forest or "", a.new_forest, a.ref, a.full_matrix, projects, ctest)


def main(argv: list[str] | None = None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    if a.dry_run:
        sel = selections_from_args(a, root)
        sys.stdout.write(emit_plan_script(sel, build_steps(sel)))
        return 0
    from .app import ForestTuiApp
    ForestTuiApp(root).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI test to verify it passes**

Run: `python3 bin/tests/test_tui_cli.py`
Expected: `ok test_...` ×3, `PASS` (dry-run path imports no textual)

- [ ] **Step 5: Commit the CLI**

```bash
git add bin/forest_tui/__main__.py bin/tests/test_tui_cli.py
git commit -m "ENH: forest_tui --dry-run CLI emits the reproducible plan script"
```

- [ ] **Step 6: Add pixi deps and task**

In `pixi.toml` `[dependencies]` add:

```toml
python = ">=3.11,<3.15"
textual = ">=1.0"
```

After the existing task tables add:

```toml
[tasks.tui]
cmd = "python3 -m forest_tui"
env = { PYTHONPATH = "bin" }
description = "Wizard TUI: pick forest, ITK ref, projects, tests; run live"
```

Run: `pixi install && pixi run python3 -c "import textual; print(textual.__version__)"`
Expected: a version string ≥1.0. If conda-forge solve fails on `textual`, fall back to `[pypi-dependencies] textual = ">=1.0"` and re-run.

- [ ] **Step 7: Implement `bin/forest_tui/app.py`**

```python
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (Button, Checkbox, DataTable, Footer, Header, Input,
                             Label, OptionList, RichLog, SelectionList, Static)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from .discover import ForestInfo, list_deferred, list_forests, list_targets
from .plan import (CtestOpts, Selections, Step, build_steps, emit_plan_script,
                   forest_dir, prereq_closure)
from .runner import StepResult, run_step

NEW_FOREST = "__new__"


class ForestScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Select a forest (build environment)", classes="title")
        yield OptionList(id="forests")
        yield Input(placeholder="new forest suffix (e.g. pr6500)", id="new-suffix", disabled=True)
        yield Button("Next", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        ol = self.query_one("#forests", OptionList)
        for f in app.forests:
            name = f"build_forest{'-' + f.suffix if f.suffix else ''}"
            art = "ITK built" if f.itk_artifact else "no ITK artifact"
            desc = f"{name}  [{f.itk_branch} @ {f.itk_sha or '?'}  {f.itk_describe}]  {art}"
            ol.add_option(Option(desc, id=f.suffix or "__default__"))
        ol.add_option(Option("[ New forest… ]", id=NEW_FOREST))

    @on(OptionList.OptionSelected, "#forests")
    def _picked(self, ev: OptionList.OptionSelected) -> None:
        self.query_one("#new-suffix", Input).disabled = ev.option.id != NEW_FOREST
        self._choice = ev.option.id

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        choice = getattr(self, "_choice", None)
        if choice is None:
            self.notify("Pick a forest first", severity="warning")
            return
        if choice == NEW_FOREST:
            suffix = self.query_one("#new-suffix", Input).value.strip()
            if not suffix:
                self.notify("New forest needs a suffix", severity="warning")
                return
            app.sel.forest_suffix, app.sel.create_forest = suffix, True
        else:
            app.sel.forest_suffix = "" if choice == "__default__" else choice
            app.sel.create_forest = False
        app.push_screen(RefScreen())


class RefScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("ITK ref under test (pr/NNNN, remote/branch, tag, SHA)", classes="title")
        yield Input(placeholder="pr/6250 | upstream/main | v5.4.0 | <sha>", id="ref")
        yield Checkbox("Keep current checkout (skip repoint-itk)", id="keep")
        yield Button("Next", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        cur = next((f for f in app.forests if f.suffix == app.sel.forest_suffix), None)
        if cur and cur.itk_branch:
            self.query_one("#ref", Input).value = cur.itk_branch

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        if self.query_one("#keep", Checkbox).value:
            app.sel.itk_ref = ""
        else:
            ref = self.query_one("#ref", Input).value.strip()
            if not ref or (ref.startswith("pr/") and not ref[3:].isdigit()):
                self.notify("Invalid ref (pr/ needs digits; must be non-empty)", severity="error")
                return
            app.sel.itk_ref = ref
        app.push_screen(ProjectsScreen())


class ProjectsScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Projects to build (prerequisites auto-added)", classes="title")
        yield Checkbox("Full run-matrix.sh sweep instead (supersedes selections)", id="sweep")
        yield SelectionList[str](id="projects")
        yield Static("", id="deferred-note")
        yield Button("Next", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        sl = self.query_one("#projects", SelectionList)
        for t in app.targets:
            sl.add_option(Selection(t, t, initial_state=(t == "ITK")))
        note = "Deferred (known-broken, excluded): " + "; ".join(
            f"{n} — {r}" for n, r in app.deferred)
        self.query_one("#deferred-note", Static).update(note)

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        app.sel.full_matrix = self.query_one("#sweep", Checkbox).value
        picked = list(self.query_one("#projects", SelectionList).selected)
        app.sel.projects = prereq_closure(picked, app.targets) if picked else []
        if not app.sel.full_matrix and not app.sel.projects:
            self.notify("Select at least one project or the full sweep", severity="warning")
            return
        app.push_screen(TestsScreen())


class TestsScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Tests (artifact check always on)", classes="title")
        yield SelectionList[str](id="ctest-projects")
        yield Input(placeholder="CTEST_INCLUDE regex (optional)", id="include")
        yield Input(placeholder="per-test timeout seconds (default 300)", id="timeout")
        yield Button("Review plan", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        sl = self.query_one("#ctest-projects", SelectionList)
        if app.sel.full_matrix:
            sl.disabled = True
            self.query_one("#include", Input).placeholder = "CTEST_INCLUDE for the sweep (optional)"
        else:
            for t in app.sel.projects:
                sl.add_option(Selection(f"ctest {t}", t))

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        include = self.query_one("#include", Input).value.strip()
        tmo = self.query_one("#timeout", Input).value.strip()
        timeout = int(tmo) if tmo.isdigit() else 300
        app.sel.ctest = {t: CtestOpts(True, include, timeout)
                         for t in self.query_one("#ctest-projects", SelectionList).selected}
        app.push_screen(ConfirmScreen())


class ConfirmScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("", id="coords", classes="title")
        yield RichLog(id="plan", wrap=False, highlight=False)
        with Horizontal():
            yield Button("Run", id="run", variant="success")
            yield Button("Quit", id="quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        app.steps = build_steps(app.sel)
        script = emit_plan_script(app.sel, app.steps)
        forest = forest_dir(app.root, app.sel.forest_suffix)
        coords = f"Forest: {forest.name} | ITK: {app.sel.itk_ref or '(current checkout)'}"
        self.query_one("#coords", Label).update(coords)
        self.query_one("#plan", RichLog).write(script)
        logs = forest / "logs"
        try:
            logs.mkdir(parents=True, exist_ok=True)
            app.plan_path = logs / f"tui-plan-{time.strftime('%Y%m%d-%H%M%S')}.sh"
            app.plan_path.write_text(script)
            self.query_one("#plan", RichLog).write(f"\n# saved: {app.plan_path}")
        except OSError:
            app.plan_path = None

    @on(Button.Pressed, "#run")
    def _run(self) -> None:
        self.app.push_screen(RunScreen())

    @on(Button.Pressed, "#quit")
    def _quit(self) -> None:
        self.app.exit()


class RunScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield DataTable(id="status")
            yield RichLog(id="tail", max_lines=2000, wrap=False)
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#status", DataTable)
        t.add_columns("step", "state", "detail")
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        for s in app.steps:
            t.add_row(s.name, "queued", "", key=s.name)
        self._execute()

    @work(exclusive=True)
    async def _execute(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        table = self.query_one("#status", DataTable)
        tail = self.query_one("#tail", RichLog)
        forest = forest_dir(app.root, app.sel.forest_suffix)
        summary: list[str] = []
        abort = False
        for s in app.steps:
            if abort:
                table.update_cell(s.name, "state", "SKIP")
                summary.append(f"SKIP  {s.name}")
                continue
            table.update_cell(s.name, "state", "running")
            res: StepResult = await run_step(s, app.root, forest,
                                             lambda line: self.app.call_from_thread(tail.write, line)
                                             if False else tail.write(line))
            table.update_cell(s.name, "state", res.status)
            table.update_cell(s.name, "detail", res.detail)
            summary.append(f"{res.status:4}  {s.name:24} {res.detail}")
            if s.target == "ITK" and s.kind == "build" and res.status == "FAIL":
                abort = True
                tail.write("ITK FAILED — aborting remaining steps")
        tail.write("\n==================== SUMMARY ====================")
        for line in summary:
            tail.write(line)
        if app.plan_path:
            tail.write(f"plan: {app.plan_path}")
        tail.write("press q to quit")


class ForestTuiApp(App[None]):
    BINDINGS = [("q", "quit", "Quit")]
    CSS = """
    .title { padding: 1; text-style: bold; }
    #status { height: 40%; }
    #tail { height: 1fr; border: solid $accent; }
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.sel = Selections()
        self.steps: list[Step] = []
        self.plan_path: Path | None = None
        self.forests: list[ForestInfo] = list_forests(root)
        self.targets: list[str] = list_targets(root)
        self.deferred: list[tuple[str, str]] = list_deferred(root)

    def on_mount(self) -> None:
        self.push_screen(ForestScreen())
```

Note: in `_execute`, the `on_line` lambda simplifies to `tail.write` — workers run on the app's event loop, so direct writes are safe. Use exactly `lambda line: tail.write(line)` (drop the dead `call_from_thread` branch when writing the file).

- [ ] **Step 8: Smoke-test app construction and full test suite**

Run:
```bash
pixi run python3 -c "
import sys; sys.path.insert(0, 'bin')
from pathlib import Path
from forest_tui.app import ForestTuiApp
app = ForestTuiApp(Path.cwd())
print('targets:', len(app.targets), 'forests:', len(app.forests))
assert app.targets[0] == 'ITK' and app.forests
print('OK')
"
for t in bin/tests/test_*.py; do python3 "$t" || break; done
```
Expected: `OK`, then every suite prints `PASS`.

- [ ] **Step 9: Commit**

```bash
git add bin/forest_tui/app.py pixi.toml pixi.lock
git commit -m "ENH: forest_tui Textual wizard and live run dashboard; pixi run tui"
```

---

### Task 6: Docs pointer + manual verification

**Files:**
- Modify: `docs/workflow.md` (after the Fast-path code block near the top)
- Modify: `README.md` only if it lists pixi tasks (check first; skip otherwise)

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the pointer**

In `docs/workflow.md`, immediately after the opening command block (line 18), insert:

```markdown
Prefer a guided flow? `pixi run tui` walks the same steps interactively
(forest → ITK ref → projects → tests) and saves each run's exact command
plan to `<forest>/logs/tui-plan-<timestamp>.sh`.
```

- [ ] **Step 2: Manual smoke run (local-test-first rule)**

Run: `pixi run tui`
Walk: existing forest `build_forest` → keep current checkout → project `elastix` (ITK auto-added) → no ctest → Run.
Verify by artifact when it finishes:
```bash
bash bin/run-matrix.sh --check-artifact elastix && echo ARTIFACT-OK
ls build_forest/logs/tui-plan-*.sh
```
Expected: `ARTIFACT-OK` and a saved plan script. If the ITK/elastix builds are already current this completes in minutes (ccache/ninja no-op).

- [ ] **Step 3: Run the full kit test suite one last time**

Run: `for t in bin/tests/test_*.py; do python3 "$t" || break; done`
Expected: every file ends with `PASS`.

- [ ] **Step 4: Commit**

```bash
git add docs/workflow.md
git commit -m "DOC: point workflow at pixi run tui guided flow"
```

---

## Self-review notes

- Spec coverage: forest picker incl. new-forest (Task 5 ForestScreen + plan `create_forest`), ITK ref with keep-current + validation (RefScreen), project selection with prereq closure + deferred display (ProjectsScreen, Tasks 1–2), test selection incl. full sweep supersede (TestsScreen, `build_steps`), confirmation + saved plan script (ConfirmScreen, `emit_plan_script`), run dashboard with artifact scoring, ctest tokens, ITK abort, error grep, logs under `<forest>/logs/` (Task 4 + RunScreen), `--dry-run` (Task 5 CLI), run-matrix additive flags (Task 1), pixi/textual/task (Task 5), docs pointer (Task 6).
- All engine mutations are additive; no-flag `run-matrix.sh` path verified in Task 1 Step 5.
