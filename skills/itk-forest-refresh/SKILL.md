---
name: itk-forest-refresh
version: 1.0.0
purpose: Bring the forest's ITK (v5=itk-release-5.4, v6=itk-main, or both) and every downstream consumer to their latest tip, building any requested in-flight-PR integration branches (shared across v5/v6 where possible) and warming the ccache build.
description: >-
  Refresh the ITK forest testbed end to end: float every downstream consumer
  worktree to its latest upstream main/master, repoint ITK itself to the
  latest upstream/main (v6) or upstream/release-5.4 (v5), and build ITK in
  each targeted forest to keep the ccache hot. When
  skills/itk-forest-refresh/integration-requests.toml names an in-flight PR
  for a downstream consumer, build (or refresh) a shared
  `itk-forest-integration` branch on that consumer's hjmjohnson fork — latest
  default branch plus the requested PR head(s), merged with --no-ff — and
  wire it into versions.toml [scenarios.<suffix>.<Name>] for both v5 and v6
  by default, per docs/integration-branches.md's "same fork branch, kept per
  forest only when a fix is known incompatible with one of them" convention.
  Use when starting a work session on this testbed, before running the
  consumer matrix, or whenever asked to catch the forest(s) up to upstream.
  Trigger on: "itk-forest-refresh", "/itk-forest-refresh", "refresh the
  forest", "get latest itk-main", "get latest itk-release-5.4", "warm the
  ccache", "update integration branches".
triggers:
  - itk-forest-refresh
  - /itk-forest-refresh
user_invocable: true
cmd: false
argument_hint: "all | v5 | v6"
contract:
  inputs:
    - argument
    - integration-requests.toml
  outputs:
    - stdout
    - versions.toml (scenario blocks added/updated)
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - versions.toml
    writes_outside_repo: true
    writes_outside_repo_paths:
      - build_forest-itk-main/
      - build_forest-itk-release-5.4/
      - forest_git_repos/
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools:
    - git
    - python3
    - pixi
  python_packages: []
  scripts:
    - itk-forest-refresh.sh
    - lib/set_scenario.py
deployment:
  tier: always
  target_projects:
    - /Users/johnsonhj/src/itk_forest_build_testbed
  needs_loader_dir: true
  adapters:
    - claude-code
---

# itk-forest-refresh

`itk-forest-refresh [all|v5|v6]` — the one-command morning routine for this
testbed: get the ITK ref(s) under test to the latest upstream tip, get every
downstream consumer to latest, stand up any requested PR-integration
branches, and warm the ccache build.

## What `v5` / `v6` / `all` mean

| Argument | Forest | ITK tracks |
|---|---|---|
| `v6` | `itk-main` | `upstream/main` |
| `v5` | `itk-release-5.4` | `upstream/release-5.4` |
| `all` (default) | both | both, independently |

## The four steps, in order

1. **ITK-side integration (rare).** If
   `skills/itk-forest-refresh/integration-requests.toml` lists PRs under
   `[itk.v6]` or `[itk.v5]`, build `itk-forest-integration-<suffix>` on
   ITK's hjmjohnson fork: latest `upstream/<branch>` plus each requested PR
   head, merged `--no-ff`. Most ITK PR testing does NOT need this — repoint
   straight at the PR instead (`ITK_REF=pr/NNNN`, see docs/workflow.md).
   Reach for this only when two in-flight ITK PRs must be tested together.
2. **Downstream integration, shared by default.** For every
   `[downstream.<Name>]` entry in the request file, rebuild a single
   `itk-forest-integration` branch on that consumer's fork (latest
   default branch + requested PR heads, `--no-ff`), then write
   `[scenarios.<suffix>.<Name>]` into `versions.toml` for **both** `itk-main`
   and `itk-release-5.4` unless the entry's `forests = [...]` narrows it —
   narrow it only when the fix is known wrong for one forest (the
   BRAINSTools#616 MIH-baseline case in docs/integration-branches.md is the
   template for when to do this).
3. **Float everything else.** Calls the existing
   `bin/refresh-forest.sh APPLY=1` for each targeted forest, which rebases
   every non-dirty, non-scenario-overridden worktree onto its upstream
   default branch (and picks up the scenario overrides written in step 2).
   A dirty worktree is left untouched and reported, never discarded.
4. **Repoint and build ITK.** `ITK_REF=<resolved ref> pixi run repoint-itk`
   then `pixi run build-ITK`, per targeted forest, so the ccache is warm for
   whatever comes next.

## Retiring an integration request

When the PR merges: delete its entry from `integration-requests.toml`. The
next `itk-forest-refresh` run then has nothing to build for that consumer, so
`refresh-forest.sh` floats it straight to the new upstream default branch —
no manual `versions.toml` cleanup needed for the request file's own entries,
**but the `[scenarios.*]` block this skill wrote stays in `versions.toml`
until you remove it.** This mirrors
docs/integration-branches.md's existing "retiring one" checklist: remove the
scenario block, confirm the consumer is back on upstream, done.

## Format of `integration-requests.toml`

See the comments in the file itself (`skills/itk-forest-refresh/integration-requests.toml`)
for the authoritative, example-bearing format. Summary: `[itk.v6]`/`[itk.v5]`
for ITK-side PRs (rare), `[downstream.<Name>]` with `prs = ["pr/N", ...]` and
an optional `forests = [...]` override for everything else.

## Known limits

- PR refs are GitHub-only (`pr/<N>` → `pull/<N>/head` on `origin`). A fix that
  needs a non-GitHub PR or a hand-picked set of commits still goes through
  `docs/integration-branches.md`'s manual recipe.
- The fork remote is found by URL pattern (`hjmjohnson/` or `hjmjohnson:`),
  tolerating this workspace's inconsistent remote naming (`hj`, `hjfork`,
  `hjmjohnson`). A consumer with no such remote fails that consumer's
  integration step with a clear message and the run continues for the rest.
- A merge conflict aborts that one consumer's integration branch build (with
  a message) and leaves `versions.toml` and the worktree untouched for it;
  it does not stop the rest of the run.
- `versions.toml` edits are text-surgical (regex block replace/insert), not a
  TOML-library round-trip, so the file's existing comments and formatting
  elsewhere are preserved exactly. Review the diff before committing.
