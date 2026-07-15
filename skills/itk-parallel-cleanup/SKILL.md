---
name: itk-parallel-cleanup
version: 1.0.0
purpose: Run N mechanical ITK cleanups in parallel — each in its own self-isolating lifecycle worktree, stopped at the local commit — then open draft PRs one at a time behind the human gate.
description: >-
  Fan out several itk-cleanup-pr-lifecycle runs concurrently (one per cleanup
  pattern), each in its own worktree via the lifecycle's built-in
  itk-start-worktree isolation, each stopping at the local commit
  (--stop-at-commit). Aggregate the outcomes, then walk a SERIAL PR gate: open
  one draft PR at a time, each behind an explicit human yes. Parallel work,
  serial PR creation — never parallel unsolicited PRs. Use when applying several
  mechanical cleanups to ITK at once. Trigger on: "itk-parallel-cleanup",
  "/itk-parallel-cleanup", "parallel cleanup", "run N cleanups in parallel",
  "fan out cleanups".
triggers:
  - itk-parallel-cleanup
  - /itk-parallel-cleanup
  - parallel cleanup
  - fan out cleanups
user_invocable: true
cmd: false
argument_hint: "<pattern-1> [<pattern-2> ...] [--scope PATH]"
contract:
  inputs:
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/**"
    writes_outside_repo: false
    writes_outside_repo_paths: []
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
  skills:
    - itk-cleanup-pr-lifecycle
    - itk-start-worktree
  external_tools:
    - git
    - gh
  python_packages: []
  scripts: []
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Parallel Cleanup Fan-Out

Run several mechanical cleanups at once, safely. Each cleanup is a full
`itk-cleanup-pr-lifecycle` run in its OWN worktree (the lifecycle's step 1
already creates `new:cleanup-<pattern>`, so distinct payloads never conflict),
stopped at the local commit. PRs are then opened ONE AT A TIME behind the human
gate — **parallel work, serial PR creation.**

## Argument

`/itk-parallel-cleanup <pattern-1> [<pattern-2> ...] [--scope PATH]`

- each `<pattern-N>` — an eligible cleanup skill (the payload). Validate against
  `~/.claude/skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh` (the
  detect.sh/transform.sh family) plus script-based refactors like
  `itk-declare-then-init`. No/one arg → print the eligible set and stop.
- `--scope PATH` — optional, applied to every arm (a module path or payload filter).

## Procedure

### 1. Validate payloads
Confirm each `<pattern-N>` is eligible (see Argument). Reject unknowns with the
eligible list.

### 2. Fan out (bounded, concurrent) — steps 1–7 per arm
Dispatch ONE subagent per payload, **concurrently** (see
superpowers:dispatching-parallel-agents). Each subagent runs:
`/itk-cleanup-pr-lifecycle <pattern-N> [--scope PATH] --stop-at-commit`
— i.e. lifecycle steps 1–7 (worktree → detect → transform-loop → verify →
pre-commit → local-test → commit), then STOP. **Cap concurrency at ≤ 3** — each
arm builds ITK (ccache/CPU pressure); if more payloads are given, run the excess
in a second wave and say so.
Each subagent returns: payload, `WORKTREE_DIR`, branch, commit count, and
verify/pre-commit/local-test outcome (pass/fail + any blocker).

### 3. Aggregate
Print a coordinates-labeled table — one row per arm:
`payload | Repo: InsightSoftwareConsortium/ITK branch: cleanup-<payload> | commits | outcome`.
Call out any failed/blocked arm (it does NOT proceed to a PR).

### 4. SERIAL PR gate (rules/pr-no-unsolicited.md, one at a time)
For each arm that reached a clean commit, in turn — never batched:
1. Summarize that arm (payload, modules touched, commit count).
2. Ask: *"Open a single draft PR for `<payload>`?"* and **wait for an explicit
   human yes.**
3. On yes, from that arm's worktree: `python3 ~/src/agent-skills/bin/pr_gate.py approve`,
   then `gh pr create --draft …` (rules/pr-always-draft.md, rules/pr-message-format.md).
4. Record work-state:
   `python3 ~/.claude/skills/gh-comment-cache/scripts/pr_workstate.py set
   InsightSoftwareConsortium/ITK <pr#> --status pushed
   --skill itk-parallel-cleanup:<payload> --gate approved`.
Move to the next arm only after this one's PR is opened (or explicitly skipped).

## Safety
Arms NEVER open PRs during fan-out (`--stop-at-commit`). The PR gate is serial
and per-arm. #4's `pr_gate` hook independently blocks any `gh pr create` without
a fresh per-PR approval marker — so parallel unsolicited PRs cannot happen even
if an arm misbehaves.

## Self-check
`bash ~/.claude/skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh ~/.claude/skills/itk-parallel-cleanup/SKILL.md`
must print `OK: all references resolve`.
