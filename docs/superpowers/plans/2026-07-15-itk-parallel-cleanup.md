# itk-parallel-cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a thin fan-out skill that runs N mechanical ITK cleanups in parallel (each in its own worktree, via the self-isolating lifecycle), aggregates outcomes, and opens draft PRs one at a time behind the human gate.

**Architecture:** `itk-parallel-cleanup` is an agent-followed coordination `SKILL.md` (no new scripts). It dispatches one subagent per payload running `itk-cleanup-pr-lifecycle <payload> --stop-at-commit` concurrently (the Agent tool provides parallelism), aggregates, then walks a serial PR gate. `itk-cleanup-pr-lifecycle` gains a documented `--stop-at-commit` option so arms stop after the local commit.

**Tech Stack:** Markdown + YAML frontmatter (skills); validation via the existing `gh-comment-cache`-adjacent bash helpers (`validate-lifecycle-refs.sh`, `list-cleanup-patterns.sh`).

## Global Constraints

- **Avenue (a) only** — kit repo; no forest/downstream code.
- **Safety invariant** — parallel work, **serial PR creation**: arms run lifecycle steps 1–7 only (`--stop-at-commit`); PRs open one at a time behind an explicit human yes; #4's `pr_gate` requires a per-PR approval marker (backstop).
- **Concurrency cap** default ≤ 3 (each arm builds ITK).
- **No new artifact type, no runtime** — agent-followed `SKILL.md`, reusing the v2 frontmatter (`dependencies.skills`).
- **Rules resolve at deployed `~/.claude/rules`** (kit `rules/` is gitignored).
- Stage explicitly; commit prefix `ENH:`.

---

## File Structure

- `skills/itk-cleanup-pr-lifecycle/SKILL.md` — MODIFY: document `--stop-at-commit` (argument + step 8 stop note).
- `skills/itk-parallel-cleanup/SKILL.md` — CREATE: the fan-out coordination contract.

No new scripts; validation reuses `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh` + `list-cleanup-patterns.sh`.

---

## Task 1: Add `--stop-at-commit` to `itk-cleanup-pr-lifecycle`

**Files:**
- Modify: `skills/itk-cleanup-pr-lifecycle/SKILL.md`

**Interfaces:**
- Produces: the `--stop-at-commit` contract that Task 2's fan-out arms rely on.

- [ ] **Step 1: Document the option in the Argument section**

In `skills/itk-cleanup-pr-lifecycle/SKILL.md`, replace this exact block:

```
- `[scope]` — optional narrowing passed through to the payload: a module path
  (e.g. `Modules/Core/Common`) or a payload-specific filter (e.g.
  `--varname size`). Treat the payload's interface as opaque; read its
  `SKILL.md` for the flags it accepts.
```

with:

```
- `[scope]` — optional narrowing passed through to the payload: a module path
  (e.g. `Modules/Core/Common`) or a payload-specific filter (e.g.
  `--varname size`). Treat the payload's interface as opaque; read its
  `SKILL.md` for the flags it accepts.
- `--stop-at-commit` — run steps 1–7 (through the local commit) and **STOP**
  before step 8: do not summarize-for-PR and do not open a PR. Used by
  `itk-parallel-cleanup` to fan out arms safely. Without it, the full lifecycle
  runs to the draft PR.
```

- [ ] **Step 2: Add the stop note at step 8**

Replace this exact block:

```
### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
Summarize the change set (pattern, modules touched, commit count) to the user
```

with:

```
### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
**If invoked with `--stop-at-commit`, STOP here — the local commits are ready; do
not run steps 8–9.** Otherwise:
Summarize the change set (pattern, modules touched, commit count) to the user
```

- [ ] **Step 3: Validate**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
grep -c -- '--stop-at-commit' skills/itk-cleanup-pr-lifecycle/SKILL.md
```
Expected: `OK: all references resolve`, then `2` (argument doc + step-8 note).

- [ ] **Step 4: Commit**

```bash
git add skills/itk-cleanup-pr-lifecycle/SKILL.md
git commit -m "ENH: itk-cleanup-pr-lifecycle documents --stop-at-commit for fan-out (issue #6)"
```

---

## Task 2: Author `itk-parallel-cleanup/SKILL.md`

**Files:**
- Create: `skills/itk-parallel-cleanup/SKILL.md`

**Interfaces:**
- Consumes: `itk-cleanup-pr-lifecycle --stop-at-commit` (Task 1), `pr_gate.py`, `pr_workstate.py`, `list-cleanup-patterns.sh`.
- Produces: the `/itk-parallel-cleanup` trigger-discoverable fan-out contract.

- [ ] **Step 1: Write the file**

Create `skills/itk-parallel-cleanup/SKILL.md` with exactly this content:

````markdown
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
````

- [ ] **Step 2: Validate references + frontmatter**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-parallel-cleanup/SKILL.md
python3 - <<'PY'
txt = open("skills/itk-parallel-cleanup/SKILL.md").read()
assert txt.startswith("---\n")
fm = txt.split("---\n",2)[1]
try:
    import yaml; d = yaml.safe_load(fm)
    assert d["name"] == "itk-parallel-cleanup"
    assert d["contract"]["side_effects"]["user_confirmation_required"] is True
    assert "itk-cleanup-pr-lifecycle" in d["dependencies"]["skills"]
    print("frontmatter OK")
except ModuleNotFoundError:
    for k in ("name:","triggers:","contract:","dependencies:","deployment:"):
        assert k in fm, f"missing {k}"
    print("frontmatter OK (line-check fallback)")
PY
```
Expected: `OK: all references resolve`, then `frontmatter OK` (or the fallback).

- [ ] **Step 3: Confirm the safety wiring is present in the body**

Run:
```bash
f=skills/itk-parallel-cleanup/SKILL.md
grep -q -- '--stop-at-commit' "$f" && echo "STOP-AT-COMMIT: ok" || echo "STOP-AT-COMMIT: FAIL"
grep -qi 'serial PR' "$f" && echo "SERIAL-GATE: ok" || echo "SERIAL-GATE: FAIL"
grep -q 'pr_gate.py approve' "$f" && echo "PR-GATE-BACKSTOP: ok" || echo "PR-GATE-BACKSTOP: FAIL"
grep -q 'pr_workstate.py set' "$f" && echo "WORKSTATE-RECORD: ok" || echo "WORKSTATE-RECORD: FAIL"
```
Expected: all four print `ok`.

- [ ] **Step 4: Commit**

```bash
git add skills/itk-parallel-cleanup/SKILL.md
git commit -m "ENH: Add itk-parallel-cleanup fan-out skill (issue #6)"
```

---

## Task 3: Deploy + acceptance

**Files:** none (symlink is machine-local).

- [ ] **Step 1: Deploy the skill (symlink, matching other itk-* skills)**

Run:
```bash
ln -sfn "$(pwd)/skills/itk-parallel-cleanup" "$HOME/.claude/skills/itk-parallel-cleanup"
ls -l "$HOME/.claude/skills/itk-parallel-cleanup"
```
Expected: a symlink pointing at `.../skills/itk-parallel-cleanup`.

- [ ] **Step 2: Acceptance — both skills validate + cross-reference**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-parallel-cleanup/SKILL.md
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
grep -l 'itk-parallel-cleanup\|--stop-at-commit' skills/itk-parallel-cleanup/SKILL.md skills/itk-cleanup-pr-lifecycle/SKILL.md
```
Expected: both validators print `OK: all references resolve`; the grep lists both files.

- [ ] **Step 3: Dry-run trace (read-only)**

Read `skills/itk-parallel-cleanup/SKILL.md` top to bottom: confirm the 4-step
procedure, the bounded concurrency cap, `--stop-at-commit` in the arm dispatch,
and the serial PR gate are all present and internally consistent. No commit.

- [ ] **Step 4: Report + gate**

Report: fan-out skill added, lifecycle documents `--stop-at-commit`, validators
green, skill deployed. Per `rules/pr-no-unsolicited.md`, do not push or open any
PR without an explicit human request; ask how to land it.

---

## Self-Review

**Spec coverage:**
- Fan-out skill (agent-followed), not a Workflow script → Task 2. ✔
- Parallel work / serial PR gate → Task 2 procedure steps 2 & 4. ✔
- `--stop-at-commit` companion edit on the lifecycle → Task 1. ✔
- Bounded concurrency ≤ 3 → Task 2 step 2. ✔
- #5 recording at the serial gate (PR-number-keyed) → Task 2 step 4.4. ✔
- pr_gate backstop against parallel PRs → Task 2 Safety. ✔
- Validation reuses validate-lifecycle-refs.sh / list-cleanup-patterns.sh; deploy via symlink → Tasks 1–3. ✔

**Placeholder scan:** the full `itk-parallel-cleanup` SKILL.md and both lifecycle edits are given; `<pattern-N>`/`<pr#>` are runtime arguments, not plan placeholders. No TBD/TODO. ✔

**Type consistency:** `--stop-at-commit` spelled identically in Task 1 (lifecycle) and Task 2 (fan-out dispatch); skill name `itk-parallel-cleanup` and the validator path used identically across Tasks 1–3. ✔
