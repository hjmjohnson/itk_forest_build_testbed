# Forest TUI — design spec (2026-07-14)

Repo: kit repo (`hjmjohnson/itk_forest_build_testbed`). Forest-agnostic.

## Purpose

A Python TUI (`pixi run tui`) that walks the operator through the full
forest-testing workflow the README describes in prose: pick a forest,
pick the ITK ref under test, pick which consumers to build, pick what to
test — then execute the plan live with per-step status, scored by
artifact.

## Decisions (user-confirmed)

- **End action:** the TUI executes the plan itself (checkout /
  repoint-itk / builds / tests), streaming progress live.
- **Framework:** Textual (added to `pixi.toml` dependencies,
  conda-forge, macOS + Linux).
- **Forest step:** lists existing `build_forest*` dirs AND offers
  "New forest…" (prompts for `FOREST_REFERENCE_SUFFIX`, runs
  `checkout` as the first live step).
- **Test step:** artifact verification (always on), optional
  per-project ctest with `CTEST_INCLUDE` regex and timeouts, and a
  "full run-matrix.sh sweep" single-action alternative.

## Architecture

New package `bin/forest_tui/` (Python 3, Textual). The TUI is a thin
orchestrator: all build/checkout/repoint work is delegated to the
existing engine `bin/setup-itk-downstream-testbed.sh` via async
subprocesses with `FOREST_REFERENCE_SUFFIX` / `ITK_REF` in the
environment. Artifact and ctest knowledge stays in `bin/run-matrix.sh`,
which gains three additive subcommand modes so there is exactly one
source of truth:

- `run-matrix.sh --list-targets` — prints the `TARGETS` list in
  dependency order (plus deferred targets with their reason).
- `run-matrix.sh --check-artifact <X>` — exit 0/1 from `artifact_ok`.
- `run-matrix.sh --ctest-dir <X>` — prints the ctest harness dir.

Default (no-flag) `run-matrix.sh` behavior is unchanged.

## Wizard flow

1. **Forest picker** — scan repo root for `build_forest*`; each row
   shows suffix, ITK worktree branch + SHA + `git describe`, whether
   the ITK artifact exists, and the newest matrix log mtime. A
   `[ New forest… ]` entry prompts for a suffix and queues `checkout`
   as the first run step.
2. **ITK ref** — text input prefilled with the forest's current ref;
   accepts `pr/NNNN`, `<remote>/<branch>`, tag, SHA; a "keep current
   checkout (skip repoint)" option; validation: non-empty, `pr/`
   requires digits.
3. **Project selection** — checkbox list from `--list-targets`, in
   dependency order. Deferred/known-broken targets are shown unchecked
   with their reason (from the DEFERRED comment block). Selecting a
   dependent auto-selects prerequisites (ITK→ANTs→BRAINSTools,
   Slicer→SlicerExtensions, Slicer before the VTK consumers
   OpenIGTLinkIO/vtkAddon/IGSIO/PlusLib).
4. **Test selection** — either the single "full run-matrix.sh sweep"
   toggle (supersedes screens 3–4), or per selected project: artifact
   check (always on), ctest on/off, optional `CTEST_INCLUDE` regex,
   `CTEST_TIMEOUT` / `CTEST_TARGET_TIMEOUT` overrides.

## Confirmation screen

Shows the coordinates banner
(`Forest: build_forest[-<suffix>] | ITK: <ref>`) and the exact command
plan (env vars + engine invocations). The identical plan is written to
`<forest>/logs/tui-plan-<timestamp>.sh` so every run is reproducible
without the TUI.

## Run dashboard

- One table row per step: checkout → repoint-itk → build-ITK →
  build-X… → ctest-X. States: queued / running / PASS / FAIL / SKIP.
- Live tail of the current step's log in a scrollable pane; full logs
  land in `<forest>/logs/` exactly as today.
- Build success is decided by `--check-artifact`, never by exit code.
- ctest results parsed from the summary line into `N/M` tokens (same
  format as the matrix).
- ITK build failure aborts the remaining queue (matrix rule).
- Steps run sequentially (each build is internally parallel).
- Final summary mirrors the `==== MATRIX ====` block. `q` quits;
  quitting mid-run terminates the current subprocess group.

## Error handling

Every subprocess logs to file first. On FAIL the dashboard shows the
same 3-line error grep the matrix uses
(`error:|CMake Error|library not found|No such module|undefined sym`)
and the log path.

## File changes (all in the kit repo)

| File | Change |
|---|---|
| `bin/forest_tui/` | new package: `app.py`, screens, plan model, runner |
| `bin/run-matrix.sh` | additive `--list-targets`, `--check-artifact`, `--ctest-dir` |
| `pixi.toml` | `textual` dependency; `[tasks.tui]` |
| `docs/workflow.md` | one-line pointer to `pixi run tui` |

## Testing

- `--dry-run` flag: no subprocesses; emits the plan script only
  (unit-testable plan construction).
- Smoke test asserting `--list-targets` / `--check-artifact` agree
  with the matrix's own behavior (same functions, so this guards the
  flag-parsing wrapper).
- Manual: drive the TUI once against an existing forest with a cheap
  target (e.g. elastix) per the local-test-first rule.
