# Design: `itk-parallel-cleanup` — worktree-isolated parallel cleanup fan-out

- **Date:** 2026-07-15
- **Repo:** `hjmjohnson/itk_forest_build_testbed` (kit repo), avenue **(a)**
- **Tracks:** issue #6 (Archon-learnings epic #1)

## Problem

Running several mechanical ITK cleanups at once (each destined for its own draft
PR) is done ad hoc. Archon's "run 5 fixes in parallel, no conflicts" has no
codified analog here — including the coordination that makes it *safe*.

Two facts make this thin:

1. **The lifecycle already self-isolates.** `itk-cleanup-pr-lifecycle` step 1 runs
   `/itk-start-worktree new:cleanup-<pattern-skill>` — each run gets its own
   sibling worktree on a distinct branch keyed by payload. Different payloads →
   different branches → different worktrees → **conflict-free by construction.**
2. So #6 is just a **coordination layer** over #2 (lifecycle) + the Agent tool
   (real parallelism) + #5 (work-state).

## Decision

A thin **fan-out skill** `itk-parallel-cleanup` (agent-followed, like #2/#3) —
NOT a Workflow-JS script. The per-arm unit is itself an agent-followed skill that
already creates its own worktree and owns its human gate, so deterministic
`parallel()` + `isolation:'worktree'` would be redundant and fight the built-in
worktree/gate.

### The one safety invariant — parallel work, serial PR creation

Letting N arms each run the *full* lifecycle (through the PR gate) would recreate
the 16-simultaneous-PR incident. So:

- Each arm runs the lifecycle **steps 1–7 only** (worktree → detect →
  transform-loop → verify → pre-commit → local-test → commit) and **STOPS before
  the human PR gate (step 8).**
- The controller aggregates all arms, then walks the **PR gate one arm at a
  time** — present summary, get an explicit human "yes", open one draft PR,
  repeat. #4's `pr_gate` hook independently requires a per-PR approval marker, so
  this is belt-and-suspenders against parallel unsolicited PRs.

## The fan-out procedure (`/itk-parallel-cleanup <pattern-1> [<pattern-2> …] [--scope PATH]`)

1. **Validate payloads** — each `<pattern-N>` must be an eligible cleanup skill
   (run `itk-cleanup-pr-lifecycle`'s `list-cleanup-patterns.sh`, plus the
   script-based refactors like `itk-declare-then-init`). No/one arg → print the
   eligible set and stop.
2. **Bounded fan-out** — dispatch one subagent per payload **concurrently** (the
   Agent / superpowers:dispatching-parallel-agents pattern). Each subagent runs
   `/itk-cleanup-pr-lifecycle <pattern-N> [--scope PATH] --stop-at-commit` — i.e.
   lifecycle steps 1–7 then STOP. Cap concurrency to a sane number (default ≤ 3)
   because **each arm builds ITK** (ccache/CPU pressure); note any payloads
   deferred past the cap.
3. **Aggregate** — collect each arm's report: payload, worktree dir, branch,
   commit count, verify/pre-commit/local-test outcome (pass/fail), and any
   blocker. Print a coordinates-labeled table (repo + branch per arm).
4. **Serial PR gate** — for each arm that reached a clean commit, in turn:
   summarize it, ask *"open a single draft PR for `<payload>`?"*, wait for an
   explicit human yes, run `pr_gate.py approve` + `gh pr create --draft`, then
   record #5: `pr_workstate.py set <repo> <pr#> --status pushed
   --skill itk-parallel-cleanup:<payload> --gate approved`. Never batch; one PR
   per confirmation.

## Companion edit — `--stop-at-commit` on the lifecycle

`itk-cleanup-pr-lifecycle/SKILL.md` gains a documented option
`--stop-at-commit`: run steps 1–7 and STOP before step 8 (do not summarize-for-PR,
do not open a PR). This gives the fan-out arms a crisp contract instead of "tell
the subagent to stop." Absent the flag, the lifecycle behaves exactly as today.

## Validation / testing

`itk-parallel-cleanup` is an agent-followed coordination skill (prose, no new
scripts). Validation reuses the existing `validate-lifecycle-refs.sh`
(referenced skills/rules resolve) plus `list-cleanup-patterns.sh` for payload
eligibility. No network/build is exercised in validation — the parallel dispatch
and builds are runtime behavior, out of scope for a unit check (documented, like
the lifecycle's own gates).

## Out of scope

- A deterministic Workflow-JS orchestrator (redundant with the self-isolating
  lifecycle; the Agent tool provides the parallelism).
- Parallelizing the *forest* build sweep — that's avenue (b), a separate concern.
- Auto-selecting payloads / "fix everything" — the caller names the payloads.
- Recording pre-PR per-arm state in #5 (its schema is PR-number-keyed; state is
  recorded at the serial gate once a PR# exists). Pre-PR aggregation is the
  controller's in-memory table.

## Success criteria

1. `/itk-parallel-cleanup a b c` dispatches three concurrent lifecycle arms, each
   in its own worktree, each stopping at commit (no PR opened during fan-out).
2. The serial PR gate opens draft PRs one at a time, each behind an explicit
   human yes; the `pr_gate` approval marker is required per PR.
3. Each opened PR is recorded in #5 via `pr_workstate.py set`.
4. `--stop-at-commit` on `itk-cleanup-pr-lifecycle` halts after step 7; without
   it, behavior is unchanged.
5. Both skills' references validate; `itk-parallel-cleanup` is deployed and
   trigger-discoverable.

## Risks

- **Resource pressure** — N parallel ITK builds are heavy. Mitigation: default
  concurrency cap ≤ 3, documented; ccache shared across worktrees softens it.
- **A rogue arm opening a PR** — mitigation is layered: arms use
  `--stop-at-commit`, the gate is serial, and #4's `pr_gate` hook blocks any
  `gh pr create` without a fresh per-PR approval marker.
- **Agent adherence to "stop at commit"** — residual (agent-followed), bounded by
  the `pr_gate` backstop; acceptable, consistent with #2/#3.
