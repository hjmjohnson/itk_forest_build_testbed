# itk-init-over-assign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An unattended skill that rewrites one forest repo to initialize
at declaration, then leaves a branch of ordered, per-kind commits for
human review.

**Architecture:** A shared Python package `ioa` (manifest, skip reasons,
compile-commands lookup, comment check, partitioner, baseline, preflight)
under the master skill's `lib/`. Each stage is a sub-skill that edits the
working tree and writes a JSON manifest; the master runs stages in order,
partitions the diff into commits by manifest, and gates every commit with
`itk-compile-gate.sh`. clang-tidy and clang-query come from the kit's pixi
environment.

**Tech Stack:** Python 3.11+ (stdlib only), bash, clang-tidy 19.1 and
clang-query 19.1 (`clang-tools` in `pixi.toml`), ninja, git, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-itk-init-over-assign-design.md`

## Global Constraints

- Repo: the kit (`hjmjohnson/itk_forest_build_testbed`). Skills live in
  `skills/<name>/`; tests in `skills/<name>/tests/`; run by `pixi run test`.
- Skill names are `<scope>-<verb>`, scope `itk-`; every `SKILL.md` carries
  the full v2 frontmatter and `agent-skills doctor` passes.
- Cross-platform shell: `grep -E`, no `sed -i`, no bare `uname`; use
  `bin/platform.sh`. Python prefers `pathlib.Path`.
- Code comments: at most one short line, why only. Markdown wrapped at 80
  columns. US English, Oxford comma.
- Consumer commit messages: `STYLE: <sentence>`, body with site and skip
  counts, no reference to prior code. Kit commit messages: `ENH:` for new
  skills, `COMP:` for build or tooling.
- The skills never run `gh pr create`, never push, never stash, and never
  commit into the kit repo.
- Skip reason vocabulary (exact strings): `loop-carried`,
  `costly-construct`, `try-read-after`, `preprocessor`, `goto-or-case`,
  `narrowing`, `init-list-ctor`, `static-local`, `order-violation`,
  `no-including-tu`, `comment-stranded`, `gate-failed`, `itk-version`.
- Spellings: `T v{};` for zero fill; `T::Filled(k)` where `T` has
  `Filled`; `itk::MakeFilled<T>(k)` otherwise; no `{}` on smart-pointer
  members.
- Report and manifests go to `<kit>/.devlocal/init-over-assign/`, never
  into a consumer worktree.

## Review Focus

1. A header included by no TU in `compile_commands.json` (template-only
   or dead) must be skipped with `no-including-tu`, not silently edited.
   Test in Task 1.
2. A `TODO` comment on the line after a removed `v.Fill(0);` must land
   next to the new declaration, or the hunk is reverted. Test in Task 3.
3. A hunk clang-format produced in a file no stage's manifest covers must
   still be assigned to a commit (nearest line above), never dropped from
   the branch. Test in Task 4.
4. `Pointer p = nullptr; if (x) p = f();` must not match `placeholder`
   (the read of `p` after the `if` depends on `x`). Test in Task 6.
5. An initializer list where `m_B(m_A)` precedes `m_A` in declaration
   order must be skipped with `order-violation`, not reordered. Test in
   Task 7.

---

### Task 1: `ioa` package: manifest, skip reasons, compile-commands lookup

**Files:**
- Create: `skills/itk-init-over-assign/lib/ioa/__init__.py`
- Create: `skills/itk-init-over-assign/lib/ioa/manifest.py`
- Create: `skills/itk-init-over-assign/lib/ioa/skip.py`
- Create: `skills/itk-init-over-assign/lib/ioa/compile_commands.py`
- Test: `skills/itk-init-over-assign/tests/test_manifest.py`
- Test: `skills/itk-init-over-assign/tests/test_compile_commands.py`
- Modify: `pixi.toml` (`[tasks.test.env] PYTHONPATH` gains
  `skills/itk-init-over-assign/lib`)

**Interfaces:**
- Produces:
  - `skip.Reason` (`enum.StrEnum`, the 13 strings above).
  - `manifest.Site(file: Path, start: int, end: int, kind: str, cls: str, skipped: Reason | None = None, note: str = "")`.
  - `manifest.Manifest(kind: str, sites: list[Site])` with
    `write(path: Path)`, `read(path: Path) -> Manifest`,
    `covers(file: Path, line: int) -> bool`, `applied()`, `skipped()`.
  - `compile_commands.find_graph(repo_build: Path, repo_name: str) -> Path`
    (directory holding `compile_commands.json`, depth <= 2 under
    `build/`; when several, the one whose name starts with `repo_name`,
    else the shallowest; raises `FileNotFoundError`).
  - `compile_commands.including_tus(header: Path, graph: Path, cap: int = 8) -> list[Path]`
    (first TU per distinct top-level directory, then path order; uses
    `ninja -t deps` output cached in `graph/.ioa-deps.json`).
  - `compile_commands.command_for(tu: Path, graph: Path) -> list[str]`.

- [ ] **Step 1: Write failing tests**

```python
def test_manifest_roundtrip(tmp_path):
    m = Manifest("local-init", [Site(Path("a.cxx"), 10, 12, "local-init", "assign")])
    m.write(tmp_path / "m.json")
    assert Manifest.read(tmp_path / "m.json").covers(Path("a.cxx"), 11)

def test_skipped_sites_are_not_covered():
    s = Site(Path("a.cxx"), 1, 2, "k", "c", skipped=Reason.LOOP_CARRIED)
    assert not Manifest("k", [s]).covers(Path("a.cxx"), 1)

def test_including_tus_capped_and_one_per_top_dir(fake_graph):
    tus = including_tus(Path("Common/foo.h"), fake_graph, cap=8)
    assert len(tus) == 8 and len({t.parts[0] for t in tus[:3]}) == 3

def test_header_with_no_including_tu_returns_empty(fake_graph):
    assert including_tus(Path("Dead/dead.hxx"), fake_graph) == []

def test_find_graph_prefers_repo_named_dir(tmp_path):
    for d in ("SlicerExecutionModel-Release-build", "BRAINSTools-Release-EPRelease-build"):
        (tmp_path / "build" / d).mkdir(parents=True); (tmp_path / "build" / d / "compile_commands.json").write_text("[]")
    assert find_graph(tmp_path / "build", "BRAINSTools").name == "BRAINSTools-Release-EPRelease-build"
```

`fake_graph` is a fixture writing a `compile_commands.json` with 20 TUs
across 3 top-level directories and a `.ioa-deps.json` mapping headers to
TUs (the deps cache format Task 1 defines; the fixture bypasses ninja).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-init-over-assign/tests -v`
Expected: FAIL, `ModuleNotFoundError: ioa`

- [ ] **Step 3: Implement the three modules with the signatures above**

`including_tus` runs `ninja -C <graph> -t deps` once and parses it into
`{header: [tu, ...]}`, written to `.ioa-deps.json`; later calls read the
cache when it is newer than `build.ninja`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest skills/itk-init-over-assign/tests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pixi.toml skills/itk-init-over-assign/lib skills/itk-init-over-assign/tests
git commit -m "ENH: Add ioa manifest, skip-reason, and compile-commands library"
```

---

### Task 2: Header support in `itk-compile-gate.sh`

**Files:**
- Modify: `skills/itk-compile-gate.sh` (the `--changed` branch and TU
  list building)
- Create: `skills/itk-init-over-assign/lib/ioa/gate.py`
- Test: `skills/itk-init-over-assign/tests/test_gate.py`

**Interfaces:**
- Consumes: `compile_commands.including_tus`, `command_for`.
- Produces: `gate.run(graph: Path, files: list[Path]) -> GateResult`
  where `GateResult(ok: bool, failed: dict[Path, str])`; headers in
  `files` expand to their including TUs (cap 8); a header with none is
  reported in `failed` with text `no-including-tu`. `itk-compile-gate.sh`
  accepts `.h`/`.hxx` arguments and `--changed` includes them, delegating
  expansion to `python3 -m ioa.gate --expand`.

- [ ] **Step 1: Write failing tests**

```python
def test_header_expands_to_capped_tus(fake_graph, monkeypatch):
    calls = record_subprocess(monkeypatch)
    gate.run(fake_graph, [Path("Common/foo.h")])
    assert len(calls) == 8

def test_dead_header_fails_with_reason(fake_graph):
    r = gate.run(fake_graph, [Path("Dead/dead.hxx")])
    assert r.failed[Path("Dead/dead.hxx")] == "no-including-tu"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-init-over-assign/tests/test_gate.py -v`
Expected: FAIL, `AttributeError: module 'ioa' has no attribute 'gate'`

- [ ] **Step 3: Implement `gate.run` and wire `itk-compile-gate.sh`**

The shell script keeps its warning sets; `gate.run` builds each TU's
command from `command_for`, strips `-o/-MF/-MT/-MQ/-MD/-MMD/-c`, appends
the script's flags for the compiler family, sets `CCACHE_DISABLE=1`.

- [ ] **Step 4: Run tests and the script against a real header**

Run: `pixi run pytest skills/itk-init-over-assign/tests/test_gate.py -v`
Expected: PASS
Run: `bash skills/itk-compile-gate.sh build_forest-itk-main/BRAINSTools/build/BRAINSTools-Release-EPRelease-build build_forest-itk-main/BRAINSTools/BRAINSCommonLib/BRAINSFitHelper.h`
Expected: exit 0, at most 8 compile lines.

- [ ] **Step 5: Commit**

```bash
git add skills/itk-compile-gate.sh skills/itk-init-over-assign
git commit -m "ENH: Gate touched headers through their including TUs"
```

---

### Task 3: Comment check

**Files:**
- Create: `skills/itk-init-over-assign/lib/ioa/comments.py`
- Test: `skills/itk-init-over-assign/tests/test_comments.py`
- Test fixtures: `skills/itk-init-over-assign/tests/fixtures/comments/{doxygen,trailing,todo}/{before.cxx,after_ok.cxx,after_bad.cxx}`

**Interfaces:**
- Produces: `comments.check_hunks(diff_text: str) -> list[Stranded]`,
  `Stranded(file: Path, line: int, text: str)`; empty list means pass.
  Input is `git diff -U0` text for one commit's staged hunks.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("name", ["doxygen", "trailing", "todo"])
def test_moved_comment_passes(name):
    assert check_hunks(diff(name, "after_ok")) == []

@pytest.mark.parametrize("name", ["doxygen", "trailing", "todo"])
def test_stranded_comment_fails(name):
    s = check_hunks(diff(name, "after_bad"))
    assert s and s[0].text.strip().startswith(("//", "/*", "*"))

def test_todo_after_removed_fill_must_follow_new_decl():
    assert check_hunks(diff("todo", "after_bad"))[0].text.strip() == "// TODO: use spacing from input"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-init-over-assign/tests/test_comments.py -v`
Expected: FAIL, `ImportError`

- [ ] **Step 3: Implement `check_hunks`**

Rule from the spec: each removed comment line must reappear as an added
line in the same hunk, or in a hunk of the same diff whose added code
contains the identifier declared on the removed comment's neighbor line.
`TODO`, `FIXME`, `NOTE`, and `HACK` match by exact text.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest skills/itk-init-over-assign/tests/test_comments.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-init-over-assign
git commit -m "ENH: Add the stranded-comment check for init-over-assign commits"
```

---

### Task 4: Partitioner

**Files:**
- Create: `skills/itk-init-over-assign/lib/ioa/partition.py`
- Test: `skills/itk-init-over-assign/tests/test_partition.py`
- Test fixture: `skills/itk-init-over-assign/tests/fixtures/partition/` (a
  script `make_repo.py` that builds a temp git repo with 3 files, applies
  edits, and writes two manifests)

**Interfaces:**
- Consumes: `Manifest`, `comments.check_hunks`, `gate.run`.
- Produces: `partition.plan(repo: Path, manifests: list[Manifest]) -> list[CommitPlan]`,
  `CommitPlan(kind: str, message: str, hunks: list[Hunk])`;
  `partition.apply(repo: Path, plan: CommitPlan, graph: Path) -> CommitResult`
  with `CommitResult(sha: str | None, reverted: list[Site])`. Commit
  message subjects are the seven spec strings keyed by kind:
  `member-init`, `local-init`, `local-const`, `container-list-init`,
  `container-const`, `itk-helpers`, `itk-helpers-constexpr`,
  `narrow-scope`.

- [ ] **Step 1: Write failing tests**

```python
def test_hunk_claimed_by_two_manifests_goes_to_later_stage(repo):
    plans = plan(repo.path, [repo.m_local, repo.m_helpers])
    assert hunk_at(plans, "a.cxx", 40).kind == "itk-helpers"

def test_uncovered_hunk_attaches_to_nearest_stage_above(repo):
    plans = plan(repo.path, [repo.m_local, repo.m_helpers])
    assert hunk_at(plans, "b.cxx", 99) is not None  # clang-format spill

def test_apply_reverts_hunk_that_strands_comment(repo, fake_gate_ok):
    res = apply(repo.path, plan(repo.path, [repo.m_todo_bad])[0], repo.graph)
    assert res.reverted and res.reverted[0].skipped == Reason.COMMENT_STRANDED

def test_apply_reverts_hunk_that_fails_gate(repo, fake_gate_fail_b):
    res = apply(repo.path, plan(repo.path, [repo.m_local])[0], repo.graph)
    assert {s.file.name for s in res.reverted} == {"b.cxx"}
    assert res.sha is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-init-over-assign/tests/test_partition.py -v`
Expected: FAIL, `ImportError`

- [ ] **Step 3: Implement `plan` and `apply`**

`plan` parses `git diff -U0`, assigns hunks by manifest coverage (later
stage wins), then nearest-line-above for the rest. `apply` stages with
`git apply --cached --unidiff-zero`, runs `check_hunks` on the staged
diff, runs `clang-format -i` on touched files and restages, runs
`gate.run`, reverts failing hunks with `git checkout -- <hunk>` via a
reverse `git apply`, records them as skipped sites, and commits with the
body `Sites: N, skipped: M`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest skills/itk-init-over-assign/tests/test_partition.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-init-over-assign
git commit -m "ENH: Partition the init-over-assign diff into per-kind commits"
```

---

### Task 5: Refine `itk-declare-then-init` for unattended use

**Files:**
- Modify: `skills/itk-declare-then-init/find_declare_then_init.py`
  (`main`, `apply_findings`, `scan_paths`)
- Modify: `skills/itk-declare-then-init/SKILL.md` (usage, contract
  `writes_outside_repo_paths` gains the manifest path)
- Test: `skills/itk-declare-then-init/tests/test_finder.py`

**Interfaces:**
- Consumes: `ioa.manifest`, `ioa.skip`, `ioa.compile_commands`.
- Produces: CLI `--classes a,b,c` (replaces `--pattern` when given; the
  old flag stays), `--apply`, `--manifest <path>`, `--graph <build-dir>`
  (file list from `compile_commands.json` plus headers they include, so
  ANTs and BRAINSTools layouts work). Findings with `forward_refs` are
  written as skipped sites: `try-read-after` when the gap contains `try`,
  `preprocessor` when it contains `#if`, else `loop-carried`.

- [ ] **Step 1: Write failing tests**

```python
def test_classes_flag_runs_only_listed_classes(fixture_tree):
    m = run_finder(fixture_tree, "--classes", "assign,elem_zero", "--apply", "--manifest", out)
    assert {s.cls for s in m.applied()} == {"assign", "elem_zero"}

def test_graph_flag_scans_compile_commands_files_only(fixture_tree_with_graph):
    m = run_finder(..., "--graph", build_dir, "--classes", "assign")
    assert all("NotInBuild" not in str(s.file) for s in m.sites)

def test_preprocessor_gap_is_skipped_with_reason(fixture_tree):
    m = run_finder(fixture_tree, "--classes", "assign", "--manifest", out)
    assert any(s.skipped == Reason.PREPROCESSOR for s in m.sites)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-declare-then-init/tests -v`
Expected: FAIL, `unrecognized arguments: --classes`

- [ ] **Step 3: Implement the flags and manifest output**

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest skills/itk-declare-then-init/tests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-declare-then-init
git commit -m "ENH: Add manifest, class-list, and compile-commands modes to declare-then-init"
```

---

### Task 6: Four new stage 2 classes

**Files:**
- Create: `skills/itk-declare-then-init/classes/sized_ctor.py`,
  `stream_open.py`, `bool_branch.py`, `placeholder.py` (each exports
  `analyze(lines, start, ctx) -> list[Finding]`, registered in
  `PATTERN_ANALYZERS`)
- Test: `skills/itk-declare-then-init/tests/test_new_classes.py`
- Fixtures: `skills/itk-declare-then-init/tests/fixtures/<class>/{before,after}.cxx`
  and `<class>/skip_*.cxx` for each skip reason the class can emit

**Interfaces:**
- Consumes: `Finding`, helpers in `find_declare_then_init.py`
  (`find_next_use`, `check_gap_forward_refs`, `enters_new_block`).
- Produces: classes `sized_ctor`, `stream_open`, `bool_branch`,
  `placeholder` selectable by `--classes`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.parametrize("cls", ["sized_ctor", "stream_open", "bool_branch", "placeholder"])
def test_before_becomes_after(cls):
    assert apply_class(cls, fixture(cls, "before")) == fixture(cls, "after")

def test_placeholder_skips_conditional_assignment():
    # Pointer p = nullptr; if (x) p = f(); use(p);
    m = run_class("placeholder", fixture("placeholder", "skip_conditional"))
    assert m.applied() == []

def test_bool_branch_skips_when_else_or_second_write():
    assert run_class("bool_branch", fixture("bool_branch", "skip_else")).applied() == []

def test_sized_ctor_covers_resize_set_size_SetSize():
    assert len(run_class("sized_ctor", fixture("sized_ctor", "before")).applied()) == 3

def test_stream_open_keeps_mode_argument():
    assert "std::ofstream f(x, std::ios::binary);" in apply_class("stream_open", fixture("stream_open", "before"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-declare-then-init/tests/test_new_classes.py -v`
Expected: FAIL, `KeyError: 'sized_ctor'`

- [ ] **Step 3: Implement the four analyzers**

`placeholder` requires the assignment to be the next statement at the
same indentation with no read of the variable between; `bool_branch`
requires a single-statement `if` body, no `else`, and no later write;
`sized_ctor` keeps the argument expression verbatim and skips when the
element type is `bool` (vector<bool> proxies) with note `vector-bool`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest skills/itk-declare-then-init/tests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-declare-then-init
git commit -m "ENH: Add sized_ctor, stream_open, bool_branch, and placeholder classes"
```

---

### Task 7: `itk-member-init` skill

**Files:**
- Create: `skills/itk-member-init/SKILL.md`
- Create: `skills/itk-member-init/member_init.py`
- Create: `skills/itk-member-init/tests/test_member_init.py`
- Fixtures: `skills/itk-member-init/tests/fixtures/{basic,order_violation,smart_ptr}/`

**Interfaces:**
- Consumes: `ioa.manifest`, `ioa.compile_commands`, `clang-tidy`,
  `clang-apply-replacements` from `$CONDA_PREFIX/bin`.
- Produces: CLI `member_init.py --graph <build-dir> --repo <path> --manifest <path> [--apply]`;
  runs `run-clang-tidy -checks=-*,cppcoreguidelines-prefer-member-initializer -export-fixes`,
  then `modernize-use-default-member-init`, applies fixes, then
  post-checks every touched constructor: initializer order equals member
  declaration order (reorder when no initializer references a later
  member; otherwise revert that constructor and record `order-violation`),
  and strips `{}` added to members whose type contains `Pointer` or
  `unique_ptr` or `shared_ptr`.

- [ ] **Step 1: Write failing tests**

```python
def test_assignment_moves_to_initializer_list(fixture_graph("basic")):
    out = run_member_init(fixture_graph("basic"), apply=True)
    assert ": m_A(1)\n  , m_B(2)" in out.read("foo.cxx")

def test_dependent_out_of_order_initializer_is_skipped(fixture_graph("order_violation")):
    m = run_member_init(fixture_graph("order_violation"), apply=True).manifest
    assert [s.skipped for s in m.sites] == [Reason.ORDER_VIOLATION]

def test_smart_pointer_member_gets_no_brace_init(fixture_graph("smart_ptr")):
    out = run_member_init(fixture_graph("smart_ptr"), apply=True)
    assert "m_Reader{}" not in out.read("foo.h")
```

Fixture graphs are tiny CMake projects configured by the test with
`cmake -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON` into `tmp_path`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-member-init/tests -v`
Expected: FAIL, `ModuleNotFoundError: member_init`

- [ ] **Step 3: Implement `member_init.py` and write `SKILL.md`**

- [ ] **Step 4: Run tests and `agent-skills doctor`**

Run: `pixi run pytest skills/itk-member-init/tests -v && agent-skills doctor`
Expected: PASS; doctor lists `itk-member-init` valid.

- [ ] **Step 5: Commit**

```bash
git add skills/itk-member-init
git commit -m "ENH: Add itk-member-init stage over clang-tidy member-initializer checks"
```

---

### Task 8: `itk-const-promote` skill

**Files:**
- Create: `skills/itk-const-promote/SKILL.md`
- Create: `skills/itk-const-promote/const_promote.py`
- Create: `skills/itk-const-promote/tests/test_const_promote.py`
- Fixtures: `skills/itk-const-promote/tests/fixtures/{locals,constexpr,static_local}/`

**Interfaces:**
- Consumes: `ioa.manifest`, `clang-tidy` `misc-const-correctness` with
  `AnalyzeValues: true`, `AnalyzeReferences: true`,
  `WarnPointersAsValues: false`, restricted to files from a prior
  manifest (`--only-from <manifest>`).
- Produces: CLI `const_promote.py --graph --repo --manifest --only-from <manifest> --kind <local-const|container-const|itk-helpers-constexpr> [--apply]`.
  After applying `const`, promotes to `constexpr` when the initializer is
  a literal, a `constexpr` call on literals, or `T::Filled(<literal>)`;
  `static` locals are recorded with `static-local`.

- [ ] **Step 1: Write failing tests**

```python
def test_never_mutated_local_becomes_const(fixture_graph("locals")):
    assert "const int n = f();" in run_promote(..., apply=True).read("a.cxx")

def test_filled_literal_becomes_constexpr(fixture_graph("constexpr")):
    assert "constexpr auto size = SizeType::Filled(2);" in run_promote(...).read("a.cxx")

def test_static_local_is_skipped(fixture_graph("static_local")):
    assert run_promote(...).manifest.sites[0].skipped == Reason.STATIC_LOCAL

def test_only_from_restricts_to_prior_manifest_files(fixture_graph("locals")):
    m = run_promote(..., only_from=manifest_with_only("a.cxx"))
    assert {s.file.name for s in m.sites} == {"a.cxx"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-const-promote/tests -v`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement and write `SKILL.md`**

- [ ] **Step 4: Run tests and doctor**

Run: `pixi run pytest skills/itk-const-promote/tests -v && agent-skills doctor`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-const-promote
git commit -m "ENH: Add itk-const-promote stage for const and constexpr locals"
```

---

### Task 9: `itk-container-list-init` skill

**Files:**
- Create: `skills/itk-container-list-init/SKILL.md`
- Create: `skills/itk-container-list-init/list_init.py`
- Create: `skills/itk-container-list-init/matchers/push_back_run.cq`,
  `index_assign_run.cq` (clang-query scripts)
- Create: `skills/itk-container-list-init/tests/test_list_init.py`
- Fixtures: `fixtures/{push_back,index_assign,narrowing,init_list_ctor}/`

**Interfaces:**
- Consumes: `ioa.*`, `clang-query` from `$CONDA_PREFIX/bin`.
- Produces: CLI `list_init.py --graph --repo --manifest [--apply]`.
  Matches a default-constructed `std::vector`, `std::array`,
  `itk::Array`, or `vnl_vector` followed by only `push_back`/`emplace_back`
  calls or `[i] =` assignments with constant `i` covering `0..n-1` once
  each; rewrites to `T v{e0, e1, ...};` (or `T v({...})` when `T` has an
  `initializer_list` constructor that would be chosen over a size
  constructor: `init-list-ctor` skip); skips `narrowing` when any element
  is an unsigned or wider type than the element type.

- [ ] **Step 1: Write failing tests**

```python
def test_push_back_run_becomes_brace_list(fixture_graph("push_back")):
    assert "std::vector<int> v{1, 2, 3};" in run_list_init(...).read("a.cxx")

def test_index_assign_run_requires_full_coverage(fixture_graph("index_assign")):
    m = run_list_init(...).manifest
    assert len(m.applied()) == 1 and m.sites[1].note == "partial-coverage"

def test_unsigned_into_vector_int_is_narrowing(fixture_graph("narrowing")):
    assert run_list_init(...).manifest.sites[0].skipped == Reason.NARROWING

def test_vector_size_t_with_one_element_is_init_list_ctor(fixture_graph("init_list_ctor")):
    assert run_list_init(...).manifest.sites[0].skipped == Reason.INIT_LIST_CTOR

def test_element_count_verified_by_reparse(fixture_graph("push_back")):
    assert run_list_init(...).manifest.applied()[0].note == "elements:3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest skills/itk-container-list-init/tests -v`
Expected: FAIL

- [ ] **Step 3: Implement and write `SKILL.md`**

- [ ] **Step 4: Run tests and doctor**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-container-list-init
git commit -m "ENH: Add itk-container-list-init stage"
```

---

### Task 10: Manifest mode for the ITK-helper skills

**Files:**
- Modify: `skills/itk-sizetype-filled/SKILL.md`; create
  `skills/itk-sizetype-filled/sizetype_filled.py` (the SKILL.md's
  documented clang-query plus Python procedure, as a script)
- Modify: `skills/itk-allocate-initialized/SKILL.md`; create
  `skills/itk-allocate-initialized/allocate_initialized.py`
- Modify: `skills/itk-mechanical-cleanup/patterns/in-class-member-init/transform.sh`,
  `skills/itk-mechanical-cleanup/patterns/fillbuffer-over-iterate/` (add
  `transform.sh`): accept `--manifest <path>`
- Test: `skills/itk-sizetype-filled/tests/test_sizetype_filled.py`,
  `skills/itk-allocate-initialized/tests/test_allocate.py`,
  `skills/itk-mechanical-cleanup/tests/test_manifest_mode.py`

**Interfaces:**
- Produces: each script takes `--graph --repo --manifest [--apply]` and
  writes kind `itk-helpers`. Spelling order: zero fill to `T v{};`;
  nonzero to `auto v = T::Filled(k);` when `T` names Size, Index, Offset,
  Vector, Point, Spacing, or any `FixedArray`-derived type found by
  clang-query `isDerivedFrom("itk::FixedArray")`; else
  `auto v = itk::MakeFilled<T>(k);`. `allocate_initialized.py` records
  `itk-version` when the forest ITK is older than 5.3. Branch and PR
  creation text is removed from both SKILL.md files.

- [ ] **Step 1: Write failing tests**

```python
def test_zero_fill_becomes_brace(fixture_graph("sizetype")):
    assert "IndexType start{};" in run_sizetype(...).read("a.cxx")

def test_nonzero_fill_prefers_Filled_over_MakeFilled(fixture_graph("sizetype")):
    out = run_sizetype(...).read("a.cxx")
    assert "auto size = SizeType::Filled(2);" in out and "MakeFilled" not in out

def test_type_without_Filled_uses_MakeFilled(fixture_graph("sizetype")):
    assert "itk::MakeFilled<ArrayType>(7)" in run_sizetype(...).read("b.cxx")

def test_allocate_true_becomes_AllocateInitialized(fixture_graph("allocate")):
    assert "->AllocateInitialized();" in run_allocate(...).read("a.cxx")

def test_transform_sh_writes_manifest(tmp_repo):
    subprocess.run([... "transform.sh", tmp_repo, "--apply", "--manifest", out], check=True)
    assert Manifest.read(out).kind == "itk-helpers"
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL

- [ ] **Step 3: Implement the scripts and transform.sh changes**

- [ ] **Step 4: Run tests and doctor**

Run: `pixi run test && agent-skills doctor`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-sizetype-filled skills/itk-allocate-initialized skills/itk-mechanical-cleanup
git commit -m "ENH: Add manifest mode to the ITK helper refactor skills"
```

---

### Task 11: `itk-narrow-scope` skill

**Files:**
- Create: `skills/itk-narrow-scope/SKILL.md`, `narrow_scope.py`,
  `matchers/var_uses.cq`
- Create: `skills/itk-narrow-scope/tests/test_narrow_scope.py`
- Fixtures: `fixtures/{into_block,init_statement,loop_trivial,loop_carried,costly,goto_case,try_after}/`

**Interfaces:**
- Consumes: `ioa.*`, `clang-query`.
- Produces: CLI `narrow_scope.py --graph --repo --manifest [--apply]`,
  kind `narrow-scope`. Moves a local whose every use is inside one nested
  block, into that block's first statement or into a `for`
  init-statement when the first use is that statement's condition; for an
  `if`/`switch` condition, a wrapping block or an `empty()` simplification
  (rule amended 2026-10-28: no init-statements in `if`). Loop
  bodies only for trivially constructible types (`isTriviallyConstructible`
  via clang-query `hasType(isTrivial())` approximation: arithmetic,
  pointer, enum, and `FixedArray`-derived) never read before written in
  the body; otherwise `loop-carried` or `costly-construct`. `goto-or-case`
  and `try-read-after` as named; `preprocessor` when an `#if` lies between
  the declaration and the target.

- [ ] **Step 1: Write failing tests**

```python
def test_moves_into_single_using_block(fixture_graph("into_block")): ...
def test_moves_into_if_init_statement(fixture_graph("init_statement")):
    assert "if (const auto n = f(); n > 0)" in ...
def test_trivial_local_moves_into_loop_body(fixture_graph("loop_trivial")): ...
def test_loop_carried_value_is_skipped(fixture_graph("loop_carried")):
    assert ... == Reason.LOOP_CARRIED
def test_New_object_never_moves_into_loop(fixture_graph("costly")):
    assert ... == Reason.COSTLY_CONSTRUCT
def test_goto_and_case_boundaries_are_skipped(fixture_graph("goto_case")): ...
def test_try_read_after_is_skipped(fixture_graph("try_after")): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL

- [ ] **Step 3: Implement and write `SKILL.md`**

- [ ] **Step 4: Run tests and doctor**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-narrow-scope
git commit -m "ENH: Add itk-narrow-scope stage"
```

---

### Task 12: Preflight and ctest baseline

**Files:**
- Create: `skills/itk-init-over-assign/lib/ioa/preflight.py`
- Create: `skills/itk-init-over-assign/lib/ioa/baseline.py`
- Test: `skills/itk-init-over-assign/tests/test_preflight.py`, `test_baseline.py`

**Interfaces:**
- Consumes: `CATALOG.md` (table rows), `bin/run-matrix.sh --ctest-dir`,
  `clang-tidy --version`.
- Produces:
  - `preflight.check(repo: Path, forest: Path, kit: Path) -> Coordinates`
    with `Coordinates(repo_slug: str, sha: str, forest_name: str, graph: Path, itk_version: str)`;
    raises `PreflightError` with one of: `dirty-tree`, `on-main`,
    `not-at-upstream-tip` (message includes the `pixi run` refresh
    command), `no-graph`, `tidy-series-mismatch`.
  - `baseline.ensure(coords, kit) -> Path` returning
    `<kit>/.devlocal/init-over-assign/baselines/<repo>-<sha>.json`
    (`{"failed": [names]}`), running ctest through
    `bin/run-matrix.sh --run-ctest <repo>` only when the file is absent.
  - `baseline.new_failures(baseline: Path, after: Path) -> list[str]`.

- [ ] **Step 1: Write failing tests**

```python
def test_dirty_tree_is_refused(tmp_repo_dirty): raises(PreflightError, "dirty-tree")
def test_worktree_ahead_of_upstream_tip_is_refused(tmp_repo_ahead):
    with pytest.raises(PreflightError) as e: preflight.check(...)
    assert "pixi run" in str(e.value)
def test_tidy_series_must_match_compiler(monkeypatch_versions("19.1.7", "20.1.0")):
    raises(PreflightError, "tidy-series-mismatch")
def test_baseline_runs_once_per_sha(tmp_kit, fake_matrix):
    baseline.ensure(coords, tmp_kit); baseline.ensure(coords, tmp_kit)
    assert fake_matrix.calls == 1
def test_new_failures_excludes_baseline_failures():
    assert new_failures(b({"x"}), a({"x", "y"})) == ["y"]
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL

- [ ] **Step 3: Implement both modules**

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/itk-init-over-assign
git commit -m "ENH: Add preflight checks and the ctest baseline for init-over-assign"
```

---

### Task 13: Master skill `itk-init-over-assign`

**Files:**
- Create: `skills/itk-init-over-assign/SKILL.md`
- Create: `skills/itk-init-over-assign/run.py`
- Create: `skills/itk-init-over-assign/lib/ioa/stages.py`
- Create: `skills/itk-init-over-assign/lib/ioa/report.py`
- Test: `skills/itk-init-over-assign/tests/test_run.py` (stages faked)

**Interfaces:**
- Consumes: every sub-skill CLI above, `partition`, `preflight`,
  `baseline`, `gate`.
- Produces:
  - `stages.STAGES: list[Stage]`, `Stage(kind: str, cmd: list[str], const_after: str | None)`
    in the spec's order: `member-init`; `local-init` (declare-then-init
    with `--classes assign,elem_diff,elem_zero,sized_ctor,stream_open,bool_branch,placeholder`)
    then `local-const`; `container-list-init` then `container-const`;
    `itk-helpers` (sizetype_filled, allocate_initialized,
    in-class-member-init, fillbuffer-over-iterate) then
    `itk-helpers-constexpr`; `narrow-scope`.
  - CLI `run.py <repo-name> [--forest <suffix>] [--stages k1,k2] [--dry-run]`;
    branch `style-init-over-assign-<YYYYMMDD>`; exit 0 on a green branch,
    1 on new ctest failures or a build error (branch left in place),
    2 on preflight refusal.
  - `report.write(kit, coords, commits, skips, build, ctest) -> Path`
    at `<kit>/.devlocal/init-over-assign/<repo>-<YYYYMMDD_HHMM>.md` with
    the spec's sections, plus the PR body draft at
    `<kit>/.devlocal/pr-bodies/<repo>-init-over-assign.md` in the
    `pr-message-format` shape (summary, `<details>` for what changed and
    testing, HTML comment with provenance).

- [ ] **Step 1: Write failing tests**

```python
def test_stages_run_in_spec_order(fake_stages):
    assert [s.kind for s in STAGES] == ["member-init", "local-init", "container-list-init", "itk-helpers", "narrow-scope"]
    assert STAGES[1].const_after == "local-const" and STAGES[0].const_after is None

def test_run_refuses_on_preflight_error_with_exit_2(fake_preflight_dirty):
    assert run_main(["BRAINSTools"]) == 2

def test_run_partitions_once_after_all_stages(fake_everything):
    run_main(["BRAINSTools"])
    assert fake_everything.partition_calls == 1 and fake_everything.stage_calls == 8

def test_disjoint_commits_listed_in_report(fake_everything):
    assert "Disjoint from every other commit" in report_text()

def test_run_never_pushes_or_opens_pr(fake_everything):
    assert not any("push" in c or "gh" in c[0] for c in fake_everything.git_calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL

- [ ] **Step 3: Implement `run.py`, `stages.py`, `report.py`, write `SKILL.md`**

`SKILL.md` quick reference, the coordinate line printed first, and the
pointer that `itk-incremental-refactor-loop` is the interactive
alternative. Also add that pointer to
`skills/itk-incremental-refactor-loop/SKILL.md`.

- [ ] **Step 4: Run tests and doctor**

Run: `pixi run test && agent-skills doctor`
Expected: PASS, all new skills valid.

- [ ] **Step 5: Commit**

```bash
git add skills/itk-init-over-assign skills/itk-incremental-refactor-loop/SKILL.md
git commit -m "ENH: Add the itk-init-over-assign master skill"
```

---

### Task 14: End-to-end on BRAINSTools

**Files:**
- Modify: `docs/superpowers/specs/2026-10-27-itk-init-over-assign-design.md`
  only if the run exposes a spec error (record it under "Open questions
  settled as my calls").
- Create: `docs/analysis/init-over-assign-BRAINSTools-<YYYYMMDD>.md` (copy
  of the run report, since `.devlocal/` is not tracked)

- [ ] **Step 1: Refresh the BRAINSTools worktree to its upstream tip**

Run: `cd ~/src/itk_forest_build_testbed && FOREST_REFERENCE_SUFFIX=itk-main pixi run checkout && pixi run build-BRAINSTools`
Expected: BRAINSTools build artifact present (`run-matrix.sh --check-artifact BRAINSTools`);
the graph resolves to `build/BRAINSTools-Release-EPRelease-build/`.

- [ ] **Step 2: Run the master**

Run: `pixi run python skills/itk-init-over-assign/run.py BRAINSTools --forest itk-main`
Expected: exit 0; report path printed; branch
`style-init-over-assign-<date>` in `build_forest-itk-main/BRAINSTools`.

- [ ] **Step 3: Verify the branch by hand**

Run: `git -C build_forest-itk-main/BRAINSTools log --oneline main..HEAD`
Expected: at most 8 commits, subjects from the spec list, in stage order.
Run: `git -C build_forest-itk-main/BRAINSTools diff main..HEAD | grep -cE '^-\s*//'` and the same for `^\+\s*//`
Expected: equal counts (no comment lost).

- [ ] **Step 4: Copy the report into `docs/analysis/` and commit the kit**

```bash
git add docs/analysis/init-over-assign-BRAINSTools-*.md
git commit -m "DOC: Record the first itk-init-over-assign run on BRAINSTools"
```

- [ ] **Step 5: Hand the BRAINSTools branch to Hans**

Print the coordinate line, the report path, the disjoint-commit list, and
a diff summary against PR #645 (kinds present there but absent here, with
counts). Do not push; do not open a PR; closing #645 is Hans's call.
