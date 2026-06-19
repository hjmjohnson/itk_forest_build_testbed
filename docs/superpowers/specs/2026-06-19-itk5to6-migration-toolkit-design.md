# ITK v5.4.6 → v6.1 Migration Toolkit — Design Spec

- **Date:** 2026-06-19
- **Staging location:** `~/src/itk_forest_build_testbed/Maintenance/itk5to6/`
- **Eventual destination:** a single PR to `ITK/Utilities/Maintenance/` immediately
  before the ITK v6.1 full release. The entire `Maintenance/itk5to6/` tree —
  **including** the `skills/` subtree — travels into that PR, so the migration
  tooling and its self-documenting skill wrappers ship together with ITK.
- **Status:** approved design, pending implementation plan.

## 1. Purpose

Provide a set of **semi-automated, one-task-at-a-time** scripts (plus 
agent-skill wrappers) that simplify migrating a C++/CMake/Python consumer of ITK
from ITKv5 (specifically **ITKv5.4.6**) to **ITKv6.1** (current `main`). Each task:

- performs exactly one logically-cohesive transformation,
- is idempotent and discoverable,
- emits a **suggested commit message including the rationale** for *why* the
  change is beneficial (preserving the historical provenance already captured in
  `migrate-itk6-code-recommendations.sh`),  All of the migrate-itk6-code-recommendations.sh
  must be included in this work. Assume that `migrate-itk6-code-recommendations.sh` will be removed
  when this work is added to ITK.
- **never** branches, commits, or opens a PR — it applies the edit and stages it,
  leaving all git history decisions to the human.  If working on the "main/master" branch
  prompt human if a new branch should be created for this work.

Whenever a consumer is on a release older than v5.4.6, the recommended path is to
**funnel through v5.4.6 first**, then migrate to v6.1.  Review pre v5.4.6 -> v5 scripts and include
migration support to v5.4.6 as well in this infrastructure.

## 2. The funnel model

```
ITKv4 code ──[prep-v5 tasks]──▶ idiomatic on ITKv5.4.6 ──[drop-itk-before-v5]──▶ v5.4.6-floor
                                                                                      │
                                                          [migrate-v6: L1→L2→L3]──────┤
                                                                                      ▼
                                       ──[drop-itk-v5]──▶ ITKv6.1-only, no compat scaffolding
```

Two orthogonal axes of tooling:

- **Conversion tasks** modernize API *usage* while keeping the code compilable.
- **Drop tasks** delete dead multi-version *scaffolding* (`#if ITK_VERSION_MAJOR < N`
  branches, feature guards) once the consumer commits to a version floor. A mapping of
   if __has_include("itkMatrixExponential.h") mapped to version should be maintained
   so that when v6.1 is the floor, then we can assume itkMatrixExponential.h must exist,
   and this becomes dead code.

## 3. The instrumentation levels

A conversion task's level is the **strictest flag under which the *old* code stops
building**:

| Level | Old code breaks when… | Representative tasks |
|---|---|---|
| **prep-v5** (pre-funnel) | n/a — makes old code idiomatic on v5.4.6 | 16 C++11-keyword macros (`ITK_NULLPTR`→`nullptr`, `ITK_OVERRIDE`→`override`, …); `atoi/atof`→`std::stoi/stod`; CMake lowercase + block-end cleanup; doxygen `\doxygen`→`\itkref` |
| **L1 mandatory** | fails against v6 **default** build | `ITKv5_CONST`→`const`; removed `ITKDeprecated` classes; `find_package(VTK 9.1)`; GoogleTest target renames; `ITK_USE_FILE` → `ITK::` targets |
| **L2 `ITK_LEGACY_REMOVE`** | builds default; fails with `ITK_LEGACY_REMOVE=ON` | `itkTypeMacro`→`itkOverrideGetNameOfClassMacro`; `itkTypeMacroNoParent`→`itkVirtualGetNameOfClassMacro`; `ITK_DISALLOW_COPY_AND_ASSIGN`→`..._MOVE`; `itkStaticConstMacro`→`static constexpr`; `itkGetStaticConstMacro`→`Self::` |
| **L3 `ITK_FUTURE_LEGACY_REMOVE`** | builds with L2 on; fails with `ITK_FUTURE_LEGACY_REMOVE=ON` | `CoordRepType`→`CoordinateType` family (`Input`/`Output`/`ImagePoint` variants) |

The conversion driver runs **L1 first, then optionally L2, then optionally L3** —
the three tiers the user requested. `prep-v5` is offered as the pre-funnel step
for consumers coming from a release older than v5.4.6.

## 4. Directory layout

```
Maintenance/itk5to6/
  README.md                       # funnel philosophy, level model, usage, safety notes
  itk-migrate.sh                  # driver: list | status | run <task> | level <name> [opts]
  lib/
    migrate_common.sh             # shared bash: sed/gsed wrapper, git-grep discovery
                                  #   (excludes ThirdParty/), staging, --dry-run, idempotency
                                  #   guard, commit-message printer, build-check hook,
                                  #   branch-guard (prompt before editing on main/master)
    header_version_map.tsv        # maintained map: <header> <first-ITK-version-providing-it>
                                  #   e.g. itkMatrixExponential.h  5.0 ; drop scripts use it to
                                  #   resolve __has_include guards into KEEP/DELETE at a floor
  tasks/
    prep-v5/             NN-<task>.sh
    mandatory/           NN-<task>.sh
    legacy-remove/       NN-<task>.sh
    future-legacy-remove/ NN-<task>.sh
  manual/                         # assisted/interactive scripts for high-complexity items
    threaded-generate-data.sh     #   ThreadedGenerateData → DynamicThreadedGenerateData
    spatialobject-space.sh        #   IsInside → IsInsideInObjectSpace/InWorldSpace, etc.
    barrier-to-parallelize.sh     #   itk::Barrier → ParallelizeImageRegion
    mutex-to-std.sh               #   itk::*MutexLock → std::mutex (+include rewrite)
    stl-replacements.sh           #   itksys::hash_map, mpl::* → std::*
    vtk-version-bump.sh           #   find_package(VTK 9.1) guidance + edit
    cmake-itk-targets.sh          #   ${ITK_LIBRARIES} → ITK:: namespaced targets
    python-cleanups.sh            #   LazyLoading, long double wrapping, numpy transpose
  drop/
    drop-itk-v5.sh                # remove <v6 guarded branches in consumer code
    drop-itk-before-v5.sh         # remove <v5 (ITKv4) guarded branches
  commit-messages/<task>.msg      # suggested commit message + rationale, sourced by each task
  skills/                         # agent-skill wrappers (NOT part of the ITK PR)
    itk-migrate-v6/SKILL.md
    itk-drop-version/SKILL.md
```

The `Maintenance/itk5to6/` tree **AND the `skills/`** is what becomes the single ITK
PR. Self-contained bash + python only; portable macOS (`gsed`) + Linux; no agent
runtime dependency — matching the existing `Utilities/Maintenance` style.

## 5. Per-task script contract

Every `tasks/**/NN-*.sh` and `manual/*.sh` script conforms to one contract,
provided by sourcing `lib/migrate_common.sh`:

1. **Discovery** — finds candidate files with `git grep -l <pattern>`, excluding
   `ThirdParty/` (and any path in a configurable exclude list). Operating repo is
   the current working directory (or `$1` if a path is given), mirroring the
   existing `migrate-itk6-code-recommendations.sh` calling convention.
2. **Modes** — `--dry-run` prints a unified diff of what *would* change and exits
   without writing; **default applies** the transform and runs `git add` on the
   changed files. `--no-stage` applies without staging.
3. **Idempotency** — re-running detects no residual pattern and is a clean no-op
   (exit 0, "nothing to do").
4. **Commit message** — prints the suggested commit message (prefix per ITK
   convention: `STYLE:`/`ENH:`/`COMP:`/`BUG:`), the *rationale* ("why beneficial"),
   the level/flag context, and historical provenance, to stdout; also writes it to
   `commit-messages/<task>.msg` for reuse. Messages follow `commit-attribution.md`
   and `code-comment-minimization.md` (no AI co-author trailer; concise).
5. **No git history actions** — never creates branches, never commits, never runs
   `gh`. Honors `pr-no-unsolicited.md` and `pre-commit-mandatory.md` (validation is
   the human's gate after staging).
6. **Reporting** — prints count of files changed and, for transforms that cannot
   be fully verified by regex (the 3 argument-reordering macros), a
   "⚠ review these N sites" list with `file:line`.
7. **Exit codes** — `0` applied or no-op; `2` partial/ambiguous (human review
   required); `1` hard error (bad repo, missing tool).

### 5.1 Sed-able vs. assisted tasks

- **Sed-able** (≈30 items): apply the verbatim sed/regex from the source scripts
  (see the inventory appendix). gsed on macOS, sed on Linux, selected by
  `lib/migrate_common.sh`.
- **Regex-with-review** (3 items): `itkStaticConstMacro`, `itkTypeMacro`
  arg-extraction, `itkGetStaticConstMacro` — apply the existing regex *and* emit
  the review list (exit 2).
- **Assisted/manual** (`manual/*.sh`, ≈24 items): perform what regex safely can
  (e.g. `SetNumberOfThreads`→`SetNumberOfWorkUnits` is a pure rename), then print
  structured guidance for the parts needing human judgment. The
  `itk-migrate-v6` skill drives these interactively with Claude judgment.

## 6. The two drop scripts

`drop-itk-v5.sh` and `drop-itk-before-v5.sh` operate on **consumer** code that
carries multi-version compatibility branches. Per the user's instruction,
detection uses this **precedence**:

1. **Feature / header guards first** — `#if defined(ITK_FEATURE_X)` and
   `__has_include(<itkXxx.h>)` checks; resolve by keeping the branch that is true
   for the target floor.
2. **Per-feature ITK defines** when available.
3. **Fallback** — `#if ITK_VERSION_MAJOR <cmp>` / `ITK_VERSION_MINOR` arithmetic;
   evaluate against the floor (v6 for `drop-itk-v5`, v5 for `drop-itk-before-v5`),
   keep the live branch, delete the dead branch, and remove the `#if/#elif/#else/#endif`
   scaffolding.

Because `#if`-arithmetic resolution is error-prone, **drop scripts default to
`--dry-run`** and emit an annotated report:
`block at file:line → KEEP <branch> / DELETE <branch> / ⚠ AMBIGUOUS (manual)`.
`--apply` acts only on **unambiguous** blocks; ambiguous blocks are left intact
and flagged. A small C-preprocessor-aware block parser (Python helper in
`lib/`) handles nesting; it does **not** attempt full macro expansion.

`drop-itk-v5` floor = v6.0 (keep `ITK_VERSION_MAJOR >= 6` / drop `< 6`).
`drop-itk-before-v5` floor = v5.0 (keep `>= 5` / drop `< 5`).

## 7. The driver `itk-migrate.sh`

```
itk-migrate.sh list   [--level prep-v5|L1|L2|L3|manual]   # tasks + one-line descriptions
itk-migrate.sh status [path]                              # scan repo, report residual patterns
itk-migrate.sh run    <task> [--dry-run] [--no-stage] [path]
itk-migrate.sh level  L1|L2|L3|prep-v5 [--dry-run] [--build-check "cmd"] [path]
```

- `status` greps for every task's source pattern and reports which migrations are
  still pending — the "where am I in the funnel" view.
- `level` runs each task in that level **one at a time**, pausing between them
  (semi-automated); with `--build-check "<cmd>"` it runs the consumer's build
  between tasks so a breakage is caught immediately (honors `pr-local-test-first.md`).
- The driver itself never commits; it prints, after each task, the suggested
  commit message and a reminder of the human's commit/validate step.

## 8. Skills (`Maintenance/itk5to6/skills/`)

Authored here and shipped **inside** the ITK PR alongside the scripts (v2
skill-framework conventions: full frontmatter contract, `<scope>-<verb>` naming,
doctor-validated). They may additionally be deployed to `~/src/agent-skills/skills/`
for local use, but the canonical home is the ITK tree so the skills version with
the scripts they drive.

- **`itk-migrate-v6`** — umbrella skill. Drives the leveled conversion one task at
  a time, runs the consumer build/tests between commits, handles the
  manual-judgment cases with Claude reasoning, proposes commit messages, and
  **stops at the commit gate** (no PRs). Triggers: "migrate to ITK v6", "itk5to6",
  "apply ITK_LEGACY_REMOVE migration", etc.
- **`itk-drop-version`** — drives the two drop scripts, applying judgment to the
  `⚠ AMBIGUOUS` blocks the scripts cannot resolve automatically.
- ** CMake should be brought to the floor of the minimum ITK version.  Bring to
     human attention, but not required to fix (but allowed if it's a trivial fix).
- ** Set C++ floor to C++17, aleart if lower versions found, make suggestions,
     not required to fix (but allowed if it's a trivial fix).
- ** Recommmended cmake changes are often have un-recognizable inter-project implecations
     and should provide warnings, diagnostic suggestions, and recommended scripts
     to assist with approved changes.

## 9. Safety / non-negotiables

- No script branches, commits, or opens PRs (`pr-no-unsolicited.md`).
- **Branch guard:** if the target repo's current branch is `main`/`master`, the
  tooling prompts the human whether to create a working branch before editing
  (it does not create one silently, and does not block if the human declines).
- Drop scripts default to dry-run; only unambiguous blocks are auto-edited.
- `ThirdParty/` is always excluded from discovery.
- Suggested commit messages obey `commit-attribution.md` (no AI co-author) and
  `code-comment-minimization.md` (no narration of replaced code in source comments).
- Portability: `grep -E` not `-P`; `gsed` on macOS; no `sed -i` BSD/GNU traps
  (handled centrally in `lib/migrate_common.sh`).
- Verify by artifact (build between steps), not by pipe exit code.

## 10. Out of scope (first build)

- Automatic PR creation of any kind.
- Rewriting ITK's *own* internal legacy code (these tools target consumers).
- Full C-preprocessor macro expansion in the drop parser (only structural
  `#if/#elif/#else/#endif` resolution against the version floor + simple defines).
- Being perfect is out of scope.  Human intervention is expected at every stage, and
  followup human refinements are expected at every step. The scripts are intended
  to expose and mechanically accelerate the conversions.

## Appendix A — task inventory (source of truth for the implementation plan)

Derived from `ITK/Documentation/docs/migration_guides/itk_{5,6}_migration_guide.md`,
`ITK/Utilities/ITKMigrationPreparation/*`, and
`ITK/Utilities/Maintenance/migrate-itk6-code-recommendations.sh`.

### prep-v5 (idiomatic on v5.4.6)
- 16 C++11-keyword macros → keywords (`ITK_NULLPTR`,`ITK_OVERRIDE`,`ITK_FINAL`,
  `ITK_CONSTEXPR*`,`ITK_NOEXCEPT*`,`ITK_ALIGNAS`,`ITK_ALIGNOF`,`ITK_EXTERN_TEMPLATE`,
  `ITK_THREAD_LOCAL`,`ITK_STATIC_ASSERT*`,`ITK_FALLTHROUGH`,`ITK_DEPRECATED*`,
  `ITK_DELETE(D)_FUNCTION`) — verbatim sed from `ReplaceOutdatedMacroNames.sh`.
- `atoi`→`std::stoi`, `atof`→`std::stod` — from `replace_atoi_atof.sh`.
- CMake lowercase commands — from `cmakeToLowerCase.sh`.
- CMake block-end cruft (`endif(x)`→`endif()`) — from `cmakeRemoveBlockEndCruft.sh`.
- Doxygen `\doxygen`→`\itkref`, `\subdoxygen`→`\itksubref` — from `update_doxygen_for_itkv6.py`.

### L1 mandatory
- `ITKv5_CONST`→`const`.
- `ITKDeprecated` module classes (TreeNode, Barrier, VectorResample, …) → alternatives (assisted).
- `find_package(VTK 9.1 …)` bump (assisted).
- GoogleTest targets `GTest::GTest`→`GTest::gtest`, `GTest::Main`→`GTest::gtest_main`.
- `${ITK_LIBRARIES}` / `ITK_USE_FILE` → `ITK::` namespaced targets (assisted; uses `WhatModulesITK.py`).

### L2 `ITK_LEGACY_REMOVE`
- `itkTypeMacro(Class,Super)`→`itkOverrideGetNameOfClassMacro(Class)` (regex-with-review).
- `itkTypeMacroNoParent(Class)`→`itkVirtualGetNameOfClassMacro(Class)` (regex-with-review).
- `ITK_DISALLOW_COPY_AND_ASSIGN`→`ITK_DISALLOW_COPY_AND_MOVE` (sed).
- `itkStaticConstMacro(n,t,v)`→`static constexpr t n = v` (regex-with-review).
- `itkGetStaticConstMacro(n)`→`Self::n` (regex-with-review).

### L3 `ITK_FUTURE_LEGACY_REMOVE`
- `CoordRepType`/`InputCoordRepType`/`OutputCoordRepType`/`ImagePointCoordRepType`
  → `CoordinateType` family (sed).

### manual / assisted (v4→v5 + v5→v6 judgment)
- Threading: `ThreadedGenerateData`→`DynamicThreadedGenerateData`,
  `MultiThreader`→`MultiThreaderBase`/`PoolMultiThreader`/`PlatformMultiThreader`,
  `SetNumberOfThreads`→`SetNumberOfWorkUnits` (rename), `ThreadInfoStruct`→`WorkUnitInfo`,
  `itk::Barrier`→`ParallelizeImageRegion`.
- Mutex/atomic: `itk::SimpleFastMutexLock`/`FastMutexLock`/`MutexLock`→`std::mutex`,
  `itk::AtomicInt<T>`→`std::atomic<T>` (+include rewrites).
- STL: `itksys::hash_map`→`std::unordered_map`, `mpl::EnableIf/IsSame/IsBaseOf/IsConvertible`
  →`std::enable_if_t/is_same/is_base_of/is_convertible`.
- SpatialObject: `IsInside`→`IsInsideInObjectSpace`/`InWorldSpace`,
  `ComputeMyBoundingBox`/`ComputeObjectToWorldTransform`→`Update`, `Dimension`→`ObjectDimension`,
  `AddSpatialObject`/`RemoveSpatialObject`→`AddChild`/`RemoveChild`, `GetObjects`→`GetChildren`,
  `ScenePointer`→`GroupPointer`, char* APIs→`std::string`.
- VerifyPreconditions/VerifyInputInformation const-qualifier additions.
- Python: remove `itkConfig.LazyLoading`, long-double wrapping, numpy `.T` no-op assumptions.
- VTK 8.1→9.1 bump; FFT Vnl→PocketFFT (baseline-affecting, flagged).
