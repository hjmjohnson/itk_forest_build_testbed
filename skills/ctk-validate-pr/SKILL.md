---
name: ctk-validate-pr
version: 1.0.0
purpose: End-to-end validation of a CTK branch/PR against a reference baseline — builds CTK standalone for Qt5+Qt6, runs CTK tests, builds CTK-in-Slicer, runs Slicer's 670-test suite, and generates a GitHub-ready comparative markdown report.
description: Validate a CTK branch/PR by building and testing CTK (Qt5+Qt6) and Slicer, then generating a comparative GitHub-ready report against a reference baseline.
triggers:
  - ctk-validate-pr
  - /ctk-validate-pr
  - validate CTK PR
  - validate-ctk-pr
user_invocable: true
cmd: false
argument_hint: "[proposed_ref] [reference_ref] [pr_number]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
    - file
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "~/src/CTK/.claude/validate-cache/**"
      - "~/src/CTK/**"
      - "~/src/Slicer-bld/**"
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: true
    cache_root: "~/src/CTK/.claude/validate-cache"
    schema_version: 1
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools:
    - git
    - cmake
    - ninja
    - ctest
    - gh
  python_packages: []
  scripts:
    - scripts/00-run-all.sh
    - scripts/01-build-ctk.sh
    - scripts/02-test-ctk.sh
    - scripts/03-build-slicer.sh
    - scripts/04-test-slicer.sh
    - scripts/05-generate-report.sh
    - scripts/06-post-report.sh
    - known-failure-prs.txt
deployment:
  tier: project
  target_projects:
    - ctk
    - slicer
  needs_loader_dir: true
  adapters:
    - claude-code
---

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
ctk-validate-pr — Build + test CTK (Qt5+Qt6) + Slicer, generate report

Usage:
  /ctk-validate-pr                               Validate HEAD vs no baseline
  /ctk-validate-pr upstream/master               Validate HEAD vs upstream/master
  /ctk-validate-pr mybranch upstream/master 1234  Validate branch, reference, PR#
```

Validate a CTK commit against a reference baseline by building, testing, and generating a comparative report.

## Execution

**Single command — handles everything:**

```bash
bash ~/.claude/skills/ctk-validate-pr/scripts/00-run-all.sh <ctk_src> <slicer_bld> <proposed_ref> <reference_ref> [pr_number]
```

### Arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `ctk_src` | `~/src/CTK` | CTK source directory |
| `slicer_bld` | `~/src/Slicer-bld` | Slicer superbuild directory |
| `proposed_ref` | `.` (current HEAD) | Git ref to validate (see Ref Formats below) |
| `reference_ref` | `none` | Baseline ref for comparison (see Ref Formats below). Use `none` to skip. |
| `pr_number` | (none) | Optional PR number to include in the report header |

### Ref formats

Refs are always fetched from the remote before resolving, so they pick up the latest commit:

| Format | Example | What it does |
|--------|---------|-------------|
| `.` | `.` | Current HEAD (no fetch, no checkout) |
| `remote/branch` | `upstream/master` | Fetches `master` from `upstream`, resolves to latest hash |
| `pr/NNN` | `pr/1409` | Fetches `pull/1409/head` from `upstream`, resolves to PR tip |
| `NNN` (1-6 digits) | `1409` | Same as `pr/NNN` — tries as PR first, falls back to hash |
| branch name | `fix-non-pod-constexpr` | Fetches from `upstream`, resolves locally |
| tag | `v1.0.0` | Fetches from `upstream`, resolves locally |
| hash | `935c4e04` | Resolves directly (no fetch needed) |

### Common invocations

Validate CTK PR #1409 vs Slicer stock:
```bash
bash ~/.claude/skills/ctk-validate-pr/scripts/00-run-all.sh ~/src/CTK ~/src/Slicer-bld pr/1409 935c4e04 1409 2>&1
```

Validate upstream/master vs Slicer stock, for Slicer PR #9097:
```bash
bash ~/.claude/skills/ctk-validate-pr/scripts/00-run-all.sh ~/src/CTK ~/src/Slicer-bld upstream/master 935c4e04 9097 2>&1
```

Validate current branch vs upstream/master:
```bash
bash ~/.claude/skills/ctk-validate-pr/scripts/00-run-all.sh ~/src/CTK ~/src/Slicer-bld . upstream/master 2>&1
```

### Parsing user arguments

Map user input to the 5 script arguments:

| User says | `proposed_ref` | `reference_ref` | `pr_number` |
|-----------|---------------|-----------------|-------------|
| `/ctk-validate-pr` | `.` | `none` | -- |
| "validate PR 1409 vs Slicer stock" | `pr/1409` | `935c4e04` | `1409` |
| `/ctk-validate-pr upstream/master 935c4e04 9097` | `upstream/master` | `935c4e04` | `9097` |
| `/ctk-validate-pr upstream/master` | `upstream/master` | `none` | -- |
| "compare PR 1410 to Slicer default" | `pr/1410` | `935c4e04` | `1410` |
| "make a report for CTK PR 1400" | `pr/1400` | `935c4e04` | `1400` |

**Slicer stock CTK hash:** `935c4e04` (from `Slicer/SuperBuild/External_CTK.cmake`)

When the user mentions "Slicer default/stock CTK" as a comparison target, always use `935c4e04` as the reference_ref.

## Result caching

Results are cached by **full commit hash** in `~/src/CTK/.claude/validate-cache/<hash>/`. If cached results exist for a hash, build/test steps are **skipped entirely** and the cached summaries are reused. This means:

- Reference baselines are computed once and reused across all future runs
- Re-running the same proposed hash is instant (report-only)
- Cache is invalidated by commit hash — different code always gets fresh results

Cache contents per hash:
```
.claude/validate-cache/<full-hash>/
  commit-info.txt          # git log --oneline
  timestamp.txt            # when this was validated
  platform.txt             # uname -srm
  ctk-qt5-build.log        # CTK standalone Qt5 build log
  ctk-qt5-test-summary.txt # CTK standalone Qt5 test summary
  ctk-qt6-build.log        # CTK standalone Qt6 build log
  ctk-qt6-test-summary.txt # CTK standalone Qt6 test summary
  slicer-ctk-build.log     # CTK-in-Slicer clean build log
  slicer-build.log          # Slicer inner build log
  slicer-build-summary.txt # Classified build errors/warnings
  slicer-test-summary.txt  # Classified test failures
  validate-complete         # Marker file — cache is valid
```

## What it does

For each hash (proposed and reference), if not cached:

| # | Action | Scope | Qt | Description |
|---|--------|-------|----|-------------|
| 1 | Build | CTK standalone | Qt5 | Inner build with superbuild fallback |
| 2 | Build | CTK standalone | Qt6 | Inner build with superbuild fallback; continues on failure |
| 3 | Test | CTK standalone | Qt5 | CTest with 60s timeout |
| 4 | Test | CTK standalone | Qt6 | CTest with 60s timeout |
| 5 | Build | CTK-in-Slicer (clean) | Qt5 | Clean CTK build in Slicer superbuild |
| 6 | Build | Slicer inner build | Qt5 | Incremental rebuild to catch API breakage |
| 7 | Test | Slicer inner build | Qt5 | CTest with 120s timeout (670 tests) |

Then generates a comparative markdown report with:
- **Identity table**: proposed and reference CTK hash/commit with GitHub links
- **Status indicators** (comparing proposed vs reference):
  - :white_check_mark: = 0 errors/failures (clean)
  - :warning: = warnings increased vs reference
  - :no_entry_sign: = new errors or new test failures vs reference
  - (no icon) = unchanged or improved from reference
- **Action summary matrix**: all 7 actions x 2 hashes showing errors/warnings/pass-fail with indicators
- **Warning analysis** (auto-expands when warnings increase): classifies new warnings by `-W` category and source file, labeling each as CTK source, PythonQt (external), or Python headers (external)
- **Classified build warnings**: CTK source vs dependencies vs Slicer-CTK-related vs Slicer-own
- **Classified test failures**: CTK-related (DICOM/CTK/PythonQt) vs Slicer-own
- **Annotated failure details**: each test failure cross-referenced against `known-failure-prs.txt` with category icons and linked PRs:
  - :arrows_counterclockwise: = addressed in open PR (linked)
  - :desktop_computer: = infrastructure/display dependent (headless CI)
  - :bug: = known bug
  - :heavy_minus_sign: = wontfix

## Posting reports

When posting to a PR, **always use `06-post-report.sh`** — it replaces previous reports:

```bash
bash ~/.claude/skills/ctk-validate-pr/scripts/05-generate-report.sh ~/src/CTK ~/src/Slicer-bld <proposed_hash> <ref_hash> PR_NUM | \
  bash ~/.claude/skills/ctk-validate-pr/scripts/06-post-report.sh <repo> PR_NUM -
```

Where `<repo>` is `commontk/CTK` or `Slicer/Slicer` depending on which PR.

`06-post-report.sh` automatically:
- Finds all previous comments containing the `/ctk-validate-pr` signature
- Replaces their body with a strikethrough "outdated report superseded" notice
- Posts the new report as a fresh comment

To get the full proposed hash for posting (after `00-run-all.sh` resolves `pr/NNN`):
```bash
ls ~/src/CTK/.claude/validate-cache/<short_hash>* -d | xargs basename
```

## Known failure mapping

`known-failure-prs.txt` maps test failures to open PRs, known bugs, and infrastructure issues. Format:
```
TEST_PATTERN|CATEGORY|PR_OR_ISSUE|DESCRIPTION
```

Categories: `open-pr`, `infrastructure`, `known-bug`, `wontfix`

Update this file when:
- A new PR is created that addresses a test failure
- A PR is merged (change category or remove the entry)
- A new persistent failure is identified

## Scripts reference

| Script | Purpose |
|--------|---------|
| `00-run-all.sh` | Orchestrator: git management, build/test, caching, report |
| `01-build-ctk.sh` | Build CTK standalone for one Qt version |
| `02-test-ctk.sh` | Run CTK CTest for one Qt version |
| `03-build-slicer.sh` | Sync CTK source, clean-build CTK in Slicer, rebuild Slicer |
| `04-test-slicer.sh` | Run Slicer CTest suite (670 tests), classify failures |
| `05-generate-report.sh` | Read cached results, generate comparative markdown report |
| `06-post-report.sh` | Post report to PR, replacing previous reports |
| `known-failure-prs.txt` | Test failure to PR/issue mapping database |

## Error recovery

| Failure | Recovery |
|---------|----------|
| Uncommitted changes | Auto-stashed, restored on exit via trap |
| Inner build fails (missing deps) | Retries via superbuild target |
| Qt6 build fails | Continues with Qt5 + Slicer |
| Slicer build fails | Skips tests, records in report |
| Test failures | Captured (exit 0), classified and annotated in report |
| Script interrupted | EXIT trap restores branch + stash |
| Cached results exist | Skips all build/test, reuses summaries |

## Enhanced by

- **pr-review-toolkit** — When installed, can dispatch specialized review
  agents (code-reviewer, silent-failure-hunter, type-design-analyzer)
  for deeper analysis. Falls back to inline review when unavailable.
