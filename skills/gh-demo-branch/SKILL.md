---
name: gh-demo-branch
version: 1.0.0
purpose: Assemble and maintain a demo-<suffix> staging branch on a fork that aggregates future-PR commits onto the latest upstream main, so a forest scenario can build a downstream project green before its fixes land.
description: >-
  Use when a forest build scenario (a FOREST_REFERENCE_SUFFIX, e.g. itkv6_main)
  needs a downstream project patched to build green and the fix may already
  exist as an open PR or on a fork. Covers assembling and maintaining a
  demo-<suffix> staging branch on the hjmjohnson fork that aggregates future-PR
  commits on the latest upstream main|master, surveying open PRs / forks /
  sibling demo-* branches for candidate fixes, and wiring a consumer's checkout
  to that branch. Keywords: demo branch, staging branch, build-staging-branch,
  inter-project reliability, aggregate PRs, cherry-pick fork, per-scenario override.
triggers:
  - gh-demo-branch
  - /gh-demo-branch
  - demo branch
  - staging branch
  - aggregate PRs
user_invocable: true
cmd: false
argument_hint: "<init|survey|incorporate|reconcile|push|status> <project> [suffix]"
contract:
  inputs:
    - argument
    - env
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "$DEMO_STAGING_DIR (default ~/.cache/git-demo-branch)"
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: true
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
    - gh
  python_packages: []
  scripts:
    - scripts/git_demo_branch.sh
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# gh-demo-branch

## Overview

A **demo branch** is a `demo-${FOREST_REFERENCE_SUFFIX}` branch on the
`hjmjohnson` fork of a project that **aggregates the commits needed to make one
build scenario green**, on top of the project's **latest upstream main|master**.

It is **not a PR**: it is one possible future version of the code that
demonstrates inter-project reliability for a scenario. Several `demo-*` branches
build different scenarios; they are reconciled until they converge, and only
then are clean PRs cut against the project.

**Core principle:** the open PR / fork commit is a *starting point*, not the
answer — survey what exists, incorporate what applies cleanly, and keep building
until the scenario is green.

## When to use

- A forest matrix red is a consumer that needs source changes ITK/upstream
  hasn't shipped, and you're testing a specific `FOREST_REFERENCE_SUFFIX`.
- A fix is likely already an open PR (yours or another author's) or on a fork.
- You need that scenario's forest to build the consumer from the staged branch
  instead of upstream — without affecting other forests.

Not for: cutting the actual PR (do that once demo branches converge); changes
that belong directly in `versions.toml` defaults (use those for all forests).

## Script

`scripts/git_demo_branch.sh <action> <project> [suffix]` — `suffix` defaults to
`$FOREST_REFERENCE_SUFFIX`; upstream URL comes from `versions.toml`; fork owner
is `$DEMO_FORK_OWNER` (default `hjmjohnson`); staging clone lives in
`$DEMO_STAGING_DIR` (default `~/.cache/git-demo-branch`).

| Action | What it does |
|---|---|
| `init <project> [suffix]` | Create/reset `demo-<suffix>` off the upstream default branch |
| `survey <project> [suffix]` | List open PRs, forks, and sibling `demo-*` branches as candidates |
| `incorporate <project> <commit-ish> [suffix]` | Cherry-pick onto `demo-<suffix>`; **keep if clean, skip+report on conflict** |
| `status <project> [suffix]` | Show `demo-<suffix>` (local or on fork) vs upstream + its commits |
| `push <project> [suffix]` | `--force-with-lease` push `demo-<suffix>` to the fork |
| `reconcile <project>` | `range-diff` across the fork's `demo-*` branches (conflicting/supportive) |

## Workflow

```bash
SUF=itkv6_main; export FOREST_REFERENCE_SUFFIX=$SUF
DB=skills/gh-demo-branch/scripts/git_demo_branch.sh

bash $DB survey elastix          # 1. find candidate PRs / fork branches / sibling demos
bash $DB init   elastix          # 2. demo-itkv6_main off latest SuperElastix/elastix main
bash $DB incorporate elastix <sha-or-pr-head>   # 3. auto cherry-pick reviewed candidates
bash $DB status elastix          # 4. inspect aggregated commits
bash $DB push   elastix          # 5. publish demo-itkv6_main to the fork (no PR)
```

**Auto-incorporate (clean only):** `incorporate` cherry-picks `-x`; a clean
apply is kept, a conflict is aborted, rolled back, and reported for manual
review. Before incorporating a commit **from another author**, review its diff
(provenance, scope, no unrelated changes) — clean-applying is necessary but not
sufficient. Genuinely ambiguous commits are skipped and reported, never forced.

**Convergence:** run `reconcile` across `demo-*` branches to spot a commit one
scenario needs that another conflicts with; resolve so the family can merge into
a final PR set.

## Wiring a scenario's forest to a demo branch

The forest engine applies a demo branch to **only the matching forest** via a
per-scenario override in `versions.toml` (read by `bin/config.py scenario` and
honored in `checkout_one`):

```toml
[scenarios.itkv6_main.elastix]
url    = "https://github.com/hjmjohnson/elastix.git"
branch = "demo-itkv6_main"
```

Then `FOREST_REFERENCE_SUFFIX=itkv6_main pixi run checkout` (or
`… checkout elastix`) puts `build_forest-itkv6_main/elastix` on the demo branch;
other forests still use the upstream default. See `docs/workflow.md`.

## Common mistakes

- Treating the open PR as complete — it usually fixes only part of the scenario;
  keep surveying and incorporating.
- Pointing `versions.toml`'s default `[components.<x>]` at the demo branch — that
  hits **all** forests. Use `[scenarios.<suffix>.<x>]` so it's scenario-scoped.
- Force-incorporating a conflicting commit — `incorporate` skips it on purpose;
  resolve the conflict in a dedicated commit on the demo branch instead.
- Opening a PR from a demo branch — demo branches are pre-PR staging; cut PRs
  only after the demo-* family converges.
