# itk-incremental-refactor-loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable "loop" skill that drives a mechanical ITK refactor one pattern class per commit until the payload's detector is dry, and wire the existing lifecycle + one payload skill to it — so the loop discipline is no longer re-narrated in every refactor skill.

**Architecture:** A new skill `skills/itk-incremental-refactor-loop/` containing only a `SKILL.md` (an agent-followed contract — no scripts, no runtime). Validation reuses the sibling `itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh`. Two edits wire it in: `itk-cleanup-pr-lifecycle` step 3 delegates to it; `itk-declare-then-init` gains a cross-class loop pointer.

**Tech Stack:** Markdown + YAML frontmatter (the skill), bash (validation via the existing sibling validator), git.

## Global Constraints

- **Avenue (a) only** — ITK PR/issue management; no forest/downstream code.
- **No new framework schema** — reuse the existing v2 frontmatter; `determinism: hybrid`; `user_confirmation_required: false` (the loop does not open PRs).
- **No new scripts** — the loop skill is pure `SKILL.md`; validation reuses `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh`.
- **Payload interface is opaque** — eligible payloads are the `detect.sh`/`transform.sh` family (enumerated by `list-cleanup-patterns.sh`) PLUS script-based multi-class refactors like `itk-declare-then-init`; the loop reads the payload's `SKILL.md` for specifics.
- **Rules resolve at the deployed `${CLAUDE_RULES_DIR:-$HOME/.claude/rules}`**, not the kit repo (`rules/` is gitignored here).
- **Staging hygiene** — stage explicitly by path; never `git add -A`/`git add .`.
- **Commit prefix** `ENH:` for skill additions/edits.
- **Retrofit is additive** — `itk-declare-then-init` keeps its pattern-class table, `--apply` behavior, pitfalls, and N-Dekker convention; only a loop pointer is added.

---

## File Structure

- `skills/itk-incremental-refactor-loop/SKILL.md` — the loop contract (frontmatter + procedure + optional subagent-per-class mode).
- `skills/itk-cleanup-pr-lifecycle/SKILL.md` — MODIFY: step 3 delegates to the loop skill; add it to `dependencies.skills`.
- `skills/itk-declare-then-init/SKILL.md` — MODIFY: add a cross-class loop pointer near the top.

No new scripts; no test files (validation reuses the sibling validator + grep assertions).

---

## Task 1: Author the loop skill `SKILL.md`

**Files:**
- Create: `skills/itk-incremental-refactor-loop/SKILL.md`

**Interfaces:**
- Consumes: `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh` (validation) and `list-cleanup-patterns.sh` (referenced for eligibility).
- Produces: the `/itk-incremental-refactor-loop` trigger-discoverable contract that Tasks 2–3 reference.

- [ ] **Step 1: Write the file**

Create `skills/itk-incremental-refactor-loop/SKILL.md` with exactly this content:

````markdown
---
name: itk-incremental-refactor-loop
version: 1.0.0
purpose: Drive a mechanical ITK refactor one pattern class at a time until the payload's detector is dry, committing per class (N-Dekker incremental methodology), with an optional subagent-per-class mode for large mechanical sweeps.
description: >-
  Reusable incremental-refactor loop: given a payload refactor skill, detect
  candidate sites, then repeatedly pick ONE pattern class, transform just that
  class, verify it compiles, review the hunks, and commit that class alone —
  until the payload's detector reports zero sites. Preserves one-class-per-commit
  discipline. Eligible payloads are the detect.sh/transform.sh cleanup skills
  plus script-based multi-class refactors like itk-declare-then-init. Use when
  applying a mechanical cleanup across many sites. Trigger on:
  "itk-incremental-refactor-loop", "/itk-incremental-refactor-loop",
  "incremental refactor loop", "one class at a time", "loop until dry".
triggers:
  - itk-incremental-refactor-loop
  - /itk-incremental-refactor-loop
  - incremental refactor loop
  - loop until dry
user_invocable: true
cmd: false
argument_hint: "<pattern-skill> [scope]"
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
    network_required: false
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
  skills:
    # payload refactor skill chosen at runtime: the detect.sh/transform.sh
    # family (see itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh) plus
    # script-based multi-class refactors like itk-declare-then-init.
  external_tools:
    - git
    - clang-format
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

# ITK Incremental Refactor Loop

Apply ONE mechanical refactor across many sites, one pattern class per commit,
until the payload's detector is dry. This is the canonical loop procedure that
refactor skills and `itk-cleanup-pr-lifecycle` delegate to instead of
re-narrating it. It loops transform+commit only — it does NOT open PRs and does
NOT create a worktree; run it inside an existing sandbox (see itk-start-worktree).

## Argument

`/itk-incremental-refactor-loop <pattern-skill> [scope]`

- `<pattern-skill>` — the refactor skill to apply (the payload). Eligible
  payloads: the detect.sh/transform.sh cleanup skills (run
  `~/.claude/skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh` for the
  set) plus script-based multi-class refactors such as `itk-declare-then-init`.
  Treat the payload interface as **opaque** — read its `SKILL.md` for how it
  detects, enumerates pattern classes, and applies one class. No argument →
  print the eligible set and stop.
- `[scope]` — optional narrowing passed through to the payload (a module path,
  or a payload-specific filter like `--varname size`).

## The loop (default: supervised, sequential)

1. **Detect** — run the payload's detector over `[scope]` (its `detect.sh`, or a
   finder-script dry-run). Record the candidate count.
2. **Pick ONE pattern class** — the smallest coherent unit the payload exposes:
   one `--pattern`, one `--varname`/`--vartype` filter, or one clang-tidy check.
3. **Transform that class only** — the payload's `transform.sh --apply` /
   documented clang-tidy command / `--apply` script, scoped to that class.
4. **Normalize** — `clang-format --style=file -i` on modified files.
5. **Verify** — the target compiles (build it), and every changed hunk is a true
   instance of the pattern (the payload's "Common mistakes"/pitfalls).
6. **Commit that class alone** — correct ITK prefix, one class per commit,
   pre-commit clean (rules/pre-commit-mandatory.md).
7. **Re-detect** — rerun step 1. If sites remain in scope, go to step 2. The
   loop ends when the detector reports zero (NO_MATCHES_REMAIN).

**Termination guard:** if a class's transform leaves the detector count
unchanged (nothing transformed — e.g. forward-reference hazards or false
positives), STOP and flag those sites for manual review. Never re-loop the same
class expecting a different result.

## Optional: subagent-per-class (fresh context) mode

For LARGE, fully-mechanical `--apply` sweeps where the transform is deterministic
and hunk review is low-risk, dispatch one subagent per pattern class (see
superpowers:dispatching-parallel-agents). Each subagent does steps 3–6 for its
single class and reports; the controller aggregates. This keeps the controller's
context clean and isolates each class. Constraints: only for `--apply`
deterministic transforms; still one commit per class; still build-verified; hunk
review remains a required step.

## Self-check
`bash ~/.claude/skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh ~/.claude/skills/itk-incremental-refactor-loop/SKILL.md`
must print `OK: all references resolve` (reuses the lifecycle skill's validator).
````

- [ ] **Step 2: Validate references resolve**

Run: `bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-incremental-refactor-loop/SKILL.md`
Expected: `OK: all references resolve` (exit 0). (The only cited rule is
`rules/pre-commit-mandatory.md`, which exists at `~/.claude/rules`; `itk-start-worktree`
is mentioned and its skill dir exists; `list-cleanup-patterns.sh` returns ≥1.)

- [ ] **Step 3: Validate frontmatter parses as YAML**

Run:
```bash
python3 - <<'PY'
import sys
txt = open("skills/itk-incremental-refactor-loop/SKILL.md").read()
assert txt.startswith("---\n"), "no frontmatter fence"
fm = txt.split("---\n",2)[1]
try:
    import yaml; d = yaml.safe_load(fm)
except ModuleNotFoundError:
    for k in ("name:","triggers:","contract:","dependencies:","deployment:"):
        assert k in fm, f"missing {k}"
    print("frontmatter OK (line-check fallback)"); sys.exit(0)
for k in ("name","triggers","contract","dependencies","deployment"):
    assert k in d, f"missing {k}"
assert d["name"] == "itk-incremental-refactor-loop"
assert d["contract"]["determinism"] == "hybrid"
assert d["contract"]["side_effects"]["user_confirmation_required"] is False
print("frontmatter OK")
PY
```
Expected: `frontmatter OK` (or the fallback line).

- [ ] **Step 4: Commit**

```bash
git add skills/itk-incremental-refactor-loop/SKILL.md
git commit -m "ENH: Add itk-incremental-refactor-loop skill (issue #3)"
```

---

## Task 2: Delegate `itk-cleanup-pr-lifecycle` step 3 to the loop skill

**Files:**
- Modify: `skills/itk-cleanup-pr-lifecycle/SKILL.md`

**Interfaces:**
- Consumes: the loop skill from Task 1.
- Produces: a lifecycle whose step 3 references `/itk-incremental-refactor-loop` (no inline loop prose, no "issue #3" placeholder).

- [ ] **Step 1: Replace step 3**

In `skills/itk-cleanup-pr-lifecycle/SKILL.md`, replace this exact block:

```
### 3. Transform — one class at a time, loop until dry
Apply the payload's transform, then re-detect; while candidate sites remain in
scope, transform the **next single pattern class**, confirm it compiles, and
**commit before moving to the next class** (N-Dekker incremental per-commit).
Use the payload's `transform.sh --apply` (or its documented clang-tidy command).
Re-run step 2's detector after each class; the loop ends when it reports zero
sites in scope. (When issue #3's reusable loop construct lands, delegate to it.)
```

with:

```
### 3. Transform — delegate to the incremental-refactor loop
Run `/itk-incremental-refactor-loop <pattern-skill> [scope]`. It applies the
payload one pattern class at a time, verifies each class compiles, and commits
per class until the payload's detector is dry (N-Dekker incremental per-commit).
See its SKILL.md for the loop procedure and the optional subagent-per-class mode.
```

- [ ] **Step 2: Add the loop skill to `dependencies.skills`**

In the same file, replace this exact block:

```
dependencies:
  skills:
    - itk-start-worktree
    # payload cleanup skill is chosen at runtime from the detect/transform
    # family; run list-cleanup-patterns.sh for the eligible set.
```

with:

```
dependencies:
  skills:
    - itk-start-worktree
    - itk-incremental-refactor-loop
    # payload cleanup skill is chosen at runtime from the detect/transform
    # family; run list-cleanup-patterns.sh for the eligible set.
```

- [ ] **Step 3: Validate the lifecycle still passes and now references the loop**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
grep -q 'itk-incremental-refactor-loop' skills/itk-cleanup-pr-lifecycle/SKILL.md && echo "REFERENCES-LOOP: ok"
grep -q 'issue #3' skills/itk-cleanup-pr-lifecycle/SKILL.md && echo "STALE-PLACEHOLDER-REMAINS: FAIL" || echo "NO-STALE-PLACEHOLDER: ok"
```
Expected: `OK: all references resolve`, then `REFERENCES-LOOP: ok`, then `NO-STALE-PLACEHOLDER: ok`.

- [ ] **Step 4: Commit**

```bash
git add skills/itk-cleanup-pr-lifecycle/SKILL.md
git commit -m "ENH: itk-cleanup-pr-lifecycle step 3 delegates to itk-incremental-refactor-loop (issue #3)"
```

---

## Task 3: Retrofit `itk-declare-then-init` with a cross-class loop pointer

**Files:**
- Modify: `skills/itk-declare-then-init/SKILL.md`

**Interfaces:**
- Consumes: the loop skill from Task 1.
- Produces: a payload skill that points readers at the loop for driving all classes to completion, with all payload-specific content intact.

- [ ] **Step 1: Insert the loop pointer near the top**

In `skills/itk-declare-then-init/SKILL.md`, replace this exact block:

```
# ITK Declare-Then-Initialize Pattern Finder

## Quick reference
```

with:

```
# ITK Declare-Then-Initialize Pattern Finder

> **Looping across all pattern classes:** this skill fixes ONE pattern class per
> invocation. To drive every class to completion (one commit per class, until the
> finder is dry), run it as the payload of the incremental-refactor loop:
> `/itk-incremental-refactor-loop itk-declare-then-init`.

## Quick reference
```

- [ ] **Step 2: Verify the pointer was added and payload-specific content is intact**

Run:
```bash
f=skills/itk-declare-then-init/SKILL.md
grep -q 'itk-incremental-refactor-loop' "$f" && echo "POINTER: ok" || echo "POINTER: FAIL"
grep -q '## Pattern Classes' "$f" && echo "PATTERN-TABLE: ok" || echo "PATTERN-TABLE: FAIL"
grep -q '## Pitfalls' "$f" && echo "PITFALLS: ok" || echo "PITFALLS: FAIL"
grep -q 'N-Dekker Convention Reference' "$f" && echo "N-DEKKER: ok" || echo "N-DEKKER: FAIL"
```
Expected: all four print `ok`.

- [ ] **Step 3: Commit**

```bash
git add skills/itk-declare-then-init/SKILL.md
git commit -m "ENH: itk-declare-then-init points at itk-incremental-refactor-loop for cross-class looping (issue #3)"
```

---

## Task 4: Deploy + acceptance

**Files:**
- No repo files changed (symlink is machine-local state).

**Interfaces:**
- Consumes: all prior tasks.

- [ ] **Step 1: Deploy the loop skill (symlink, matching other itk-* skills)**

Run:
```bash
ln -sfn "$(pwd)/skills/itk-incremental-refactor-loop" "$HOME/.claude/skills/itk-incremental-refactor-loop"
ls -l "$HOME/.claude/skills/itk-incremental-refactor-loop"
```
Expected: a symlink pointing at `.../skills/itk-incremental-refactor-loop`.

- [ ] **Step 2: Acceptance — all three skills validate and cross-reference**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-incremental-refactor-loop/SKILL.md
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
grep -l 'itk-incremental-refactor-loop' skills/itk-cleanup-pr-lifecycle/SKILL.md skills/itk-declare-then-init/SKILL.md
```
Expected: both validators print `OK: all references resolve`; the grep lists both files.

- [ ] **Step 3: Dry-run trace (read-only)**

Read `skills/itk-incremental-refactor-loop/SKILL.md` top to bottom: confirm the 7-step loop, the termination guard, and the optional subagent-per-class mode are all present and internally consistent with the argument section. No commit.

- [ ] **Step 4: Report + gate**

Report to the user: loop skill added, lifecycle step 3 delegates to it, `itk-declare-then-init` points at it, validators green, skill deployed. Per `rules/pr-no-unsolicited.md`, do not push or open any PR without an explicit human request; ask how to land it (merge to main locally vs leave on branch).

---

## Self-Review

**Spec coverage:**
- Loop skill authored (7-step loop, termination guard, both modes) → Task 1. ✔
- Default mode (a) advisory + opt-in mode (b) subagent-per-class → Task 1 body. ✔
- `itk-cleanup-pr-lifecycle` step 3 delegates; no inline loop prose / no "issue #3" placeholder → Task 2. ✔
- `itk-declare-then-init` retrofit is additive (pointer added; table/pitfalls/N-Dekker intact) → Task 3. ✔
- Payload interface opaque; eligibility incl. script-based refactors → Task 1 argument section. ✔
- No new schema, no new scripts; validation reuses sibling validator → Tasks 1–4. ✔
- Deploy via symlink → Task 4. ✔

**Placeholder scan:** The loop `SKILL.md` and both edits are given in full; `<pattern-skill>`/`[scope]` are runtime arguments, not plan placeholders. No TBD/TODO. ✔

**Type consistency:** The skill name `itk-incremental-refactor-loop` is identical across Tasks 1–4 and inside all three SKILL.md files. The validator path `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh` is used identically throughout. ✔
