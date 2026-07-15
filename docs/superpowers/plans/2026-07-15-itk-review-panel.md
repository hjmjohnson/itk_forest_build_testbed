# itk-review-panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add an ITK-lens adversarial review-panel skill (agent-followed, read-only, advisory) that dispatches diverse lens-reviewers in parallel, verifies findings, and synthesizes a ranked report — and wire it into the cleanup lifecycle as a pre-PR review gate (step 7.5).

**Architecture:** `itk-review-panel` is an agent-followed coordination `SKILL.md` (no scripts). It computes a diff range, picks a complexity tier, dispatches N ITK-lens reviewer subagents concurrently (the Agent tool provides parallelism), adversarially verifies each finding, and synthesizes an advisory report. `itk-cleanup-pr-lifecycle` gains a step 7.5 that invokes it before the human PR gate.

**Tech Stack:** Markdown + YAML frontmatter (skills); validation via `validate-lifecycle-refs.sh`.

## Global Constraints

- **Avenue (a) only** — kit repo; no forest/downstream code.
- **Read-only + advisory** — the panel MUST NOT mutate the working tree, index, or HEAD; findings feed the human gate, never auto-apply.
- **Complexity-gated** — trivial diff → 1–2 lenses; large/structural → full 5-lens panel (don't over-review a one-liner).
- **Does NOT modify `gh-triage-pr`** — it is a documented optional future consumer only; the lifecycle is the wired consumer.
- **No new artifact type / no scripts** — agent-followed `SKILL.md`, v2 frontmatter.
- **Rules resolve at deployed `~/.claude/rules`.** Stage explicitly; commit prefix `ENH:`.

---

## File Structure

- `skills/itk-review-panel/SKILL.md` — CREATE: the ITK-lens adversarial review panel.
- `skills/itk-cleanup-pr-lifecycle/SKILL.md` — MODIFY: insert step 7.5 (review gate) between steps 7 and 8.

No new scripts; validation reuses `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh`.

---

## Task 1: Author `itk-review-panel/SKILL.md`

**Files:**
- Create: `skills/itk-review-panel/SKILL.md`

**Interfaces:**
- Produces: the `/itk-review-panel` trigger-discoverable review contract that Task 2 wires into the lifecycle.

- [ ] **Step 1: Write the file**

Create `skills/itk-review-panel/SKILL.md` with exactly this content:

````markdown
---
name: itk-review-panel
version: 1.0.0
purpose: Run a complexity-gated, ITK-lens adversarial review panel on a local diff — parallel lens-reviewers, adversarial verification, a ranked advisory report — before the PR is opened.
description: >-
  Read-only, advisory review panel for ITK changes. Dispatches diverse lens
  reviewers in parallel (correctness/C++ safety, ITK API & idiom conformance,
  rules/ compliance, downstream-break risk, test coverage), adversarially
  verifies each finding, and synthesizes a ranked report. Complexity-gated: a
  trivial diff gets 1-2 lenses, a large/structural diff gets the full panel.
  Pre-PR and local — complements (does not duplicate) gh-triage-pr's post-PR
  greptile round. Use to review local commits before opening an ITK PR. Trigger
  on: "itk-review-panel", "/itk-review-panel", "review panel", "ITK lens review",
  "adversarial review".
triggers:
  - itk-review-panel
  - /itk-review-panel
  - ITK lens review
  - review panel
user_invocable: true
cmd: false
argument_hint: "[<base>..<head>]"
contract:
  inputs:
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
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
  skills: []
  external_tools:
    - git
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

# ITK Review Panel

A **read-only, advisory** ITK-lens review of a local diff, run **before** the PR
is opened. Diverse lens-reviewers run in parallel, findings are adversarially
verified, and a ranked report is synthesized. Findings feed the human gate — they
are **never** auto-applied, and this skill **never mutates** the tree, index, or
HEAD (reviewers use `git show`/`git diff`/`git log`; a working copy of another
revision goes in a throwaway `git worktree`, never `HEAD`).

## Relationship to gh-triage-pr
This is **pre-PR and local**. `gh-triage-pr` is **post-PR** (its Phase 3 requests
an external `@greptileai` review on the open PR). They do not overlap — running
this panel first yields a cleaner diff, so greptile/human rounds are fewer. This
skill does NOT modify `gh-triage-pr`.

## Argument
`/itk-review-panel [<base>..<head>]` — default: the current branch vs its
merge-base with `upstream/main` (fall back to `origin/main`). Compute the range
with `git diff <base>..<head>` / `git log <base>..<head>`.

## 1. Complexity gate
Assess the diff and pick a tier (state which and why):

| Tier | Signal | Lenses |
|------|--------|--------|
| Trivial | one small mechanical change; no API/CMake/header/test edits | Correctness + rules/ compliance |
| Moderate | several files; logic changes; no API/CMake surface | + ITK API/idiom |
| Large/structural | many files, or touches public API / installed headers / exported CMake / tests | Full 5-lens panel |

Don't over-review a one-liner.

## 2. Lenses (one reviewer subagent each, in parallel)
Dispatch the selected lenses **concurrently** (superpowers:dispatching-parallel-agents),
each a READ-ONLY reviewer given the diff range and its single lens:

1. **Correctness / C++ safety** — does it do what it claims; UB, lifetime,
   iterator invalidation, sign/integer issues.
2. **ITK API / idiom conformance** — `itk::SizeValueType`/`IndexValueType`,
   `MakeFilled`/`Filled`, `New()`/smart pointers, `itk_add_test` patterns, and
   the **C++17-valid on BOTH ITKv5 and ITKv6** constraint (never require C++20+).
3. **rules/ compliance** — rules/code-comment-minimization.md (no over-comment /
   no before-after narration), rules/commit-attribution.md (no `Co-Authored-By`
   for AI), rules/pr-message-format.md, and for tests
   rules/pr-fixture-and-expected-values.md (fixtures exist; expected values from
   real data, not memory).
4. **Downstream-break risk** — changes to exported CMake / installed headers /
   public APIs consumers rely on; flag for the avenue-(b) forest sweep or
   `itk-test-cmake-changes-downstream`.
5. **Test coverage** — new/changed behavior exercised; tests assert real
   behavior; built+run locally (rules/pr-local-test-first.md).

## 3. Adversarial verify
Each surviving finding is checked by a skeptic subagent prompted to **refute**
it (default to "not a real issue" when uncertain). Only findings that survive
refutation enter the synthesis.

## 4. Synthesize
Emit a single ranked report, most-severe first: `file:line — <lens> — <concrete
violation / failure scenario>`, deduped across lenses, with the chosen complexity
tier stated at the top. The report is **advisory** — hand it to the human gate.

## Self-check
`bash ~/.claude/skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh ~/.claude/skills/itk-review-panel/SKILL.md`
must print `OK: all references resolve`.
````

- [ ] **Step 2: Validate references + frontmatter**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-review-panel/SKILL.md
python3 - <<'PY'
txt = open("skills/itk-review-panel/SKILL.md").read()
assert txt.startswith("---\n")
fm = txt.split("---\n",2)[1]
try:
    import yaml; d = yaml.safe_load(fm)
    assert d["name"] == "itk-review-panel"
    assert d["contract"]["side_effects"]["writes_to_repo"] is False
    assert d["contract"]["side_effects"]["modifies_working_tree"] is False
    print("frontmatter OK")
except ModuleNotFoundError:
    for k in ("name:","triggers:","contract:","dependencies:","deployment:"):
        assert k in fm, f"missing {k}"
    print("frontmatter OK (line-check fallback)")
PY
```
Expected: `OK: all references resolve`, then `frontmatter OK` (or fallback).

- [ ] **Step 3: Confirm the design invariants are present in the body**

Run:
```bash
f=skills/itk-review-panel/SKILL.md
grep -qi 'read-only'         "$f" && echo "READ-ONLY: ok"      || echo "READ-ONLY: FAIL"
grep -qi 'advisory'          "$f" && echo "ADVISORY: ok"       || echo "ADVISORY: FAIL"
grep -qi 'complexity gate'   "$f" && echo "COMPLEXITY-GATE: ok"|| echo "COMPLEXITY-GATE: FAIL"
grep -qi 'adversarial'       "$f" && echo "ADVERSARIAL: ok"    || echo "ADVERSARIAL: FAIL"
grep -qi 'gh-triage-pr'      "$f" && echo "TRIAGE-BOUNDARY: ok"|| echo "TRIAGE-BOUNDARY: FAIL"
c=$(grep -cE '^[0-9]+\. \*\*' "$f"); echo "lens count line-markers: $c (expect 5)"
```
Expected: all five `ok`, and the 5 lenses present.

- [ ] **Step 4: Commit**

```bash
git add skills/itk-review-panel/SKILL.md
git commit -m "ENH: Add itk-review-panel ITK-lens adversarial review skill (issue #7)"
```

---

## Task 2: Wire step 7.5 into `itk-cleanup-pr-lifecycle`

**Files:**
- Modify: `skills/itk-cleanup-pr-lifecycle/SKILL.md`

**Interfaces:**
- Consumes: `itk-review-panel` (Task 1).

- [ ] **Step 1: Insert step 7.5 between steps 7 and 8**

In `skills/itk-cleanup-pr-lifecycle/SKILL.md`, replace this exact block:

```
attribution per rules/commit-attribution.md (no `Co-Authored-By` for AI).

### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
```

with:

```
attribution per rules/commit-attribution.md (no `Co-Authored-By` for AI).

### 7.5 Review gate — ITK-lens panel (advisory)
Run `/itk-review-panel` on the local commits. Address — or consciously accept,
noting why — the surviving findings before the human PR gate. Advisory: it does
not open or block the PR by itself; it cleans the diff before reviewers/CI (and
gh-triage-pr's later greptile round) see it. Skip only for a trivial one-liner.

### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
```

- [ ] **Step 2: Validate + confirm the wiring**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
grep -q '### 7.5 Review gate' skills/itk-cleanup-pr-lifecycle/SKILL.md && echo "STEP-7.5: ok"
grep -q 'itk-review-panel' skills/itk-cleanup-pr-lifecycle/SKILL.md && echo "REFERENCES-PANEL: ok"
```
Expected: `OK: all references resolve`, then `STEP-7.5: ok`, `REFERENCES-PANEL: ok`.

- [ ] **Step 3: Commit**

```bash
git add skills/itk-cleanup-pr-lifecycle/SKILL.md
git commit -m "ENH: itk-cleanup-pr-lifecycle adds step 7.5 ITK-lens review gate (issue #7)"
```

---

## Task 3: Deploy + acceptance

**Files:** none (symlink is machine-local).

- [ ] **Step 1: Deploy the skill (symlink, matching other itk-* skills)**

Run:
```bash
ln -sfn "$(pwd)/skills/itk-review-panel" "$HOME/.claude/skills/itk-review-panel"
ls -l "$HOME/.claude/skills/itk-review-panel"
```
Expected: a symlink pointing at `.../skills/itk-review-panel`.

- [ ] **Step 2: Acceptance — both skills validate + cross-reference**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-review-panel/SKILL.md
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
grep -l 'itk-review-panel' skills/itk-review-panel/SKILL.md skills/itk-cleanup-pr-lifecycle/SKILL.md
```
Expected: both validators `OK: all references resolve`; the grep lists both files.

- [ ] **Step 3: Read-only invariant + dry-run trace**

Confirm the skill declares `writes_to_repo: false` and `modifies_working_tree:
false`, and that the body states reviewers never mutate HEAD/tree:
```bash
grep -E 'writes_to_repo: false|modifies_working_tree: false' skills/itk-review-panel/SKILL.md
grep -qi 'never.*mutate\|read-only' skills/itk-review-panel/SKILL.md && echo "READ-ONLY-INVARIANT: ok"
```
Then read the SKILL.md top to bottom: confirm the complexity gate, 5 lenses,
adversarial verify, and advisory synthesis are present and consistent. No commit.

- [ ] **Step 4: Report + gate**

Report: panel skill added, lifecycle wired at step 7.5, validators green, skill
deployed and read-only. Per `rules/pr-no-unsolicited.md`, do not push or open any
PR without an explicit human request; ask how to land it.

---

## Self-Review

**Spec coverage:**
- Agent-followed panel skill (not Workflow-JS) → Task 1. ✔
- 5 ITK lenses → Task 1 §2. ✔
- Complexity gate (trivial→large) → Task 1 §1. ✔
- Adversarial verify + advisory synthesis → Task 1 §3–4. ✔
- Read-only invariant → Task 1 frontmatter + body + Task 3 step 3. ✔
- Relationship to gh-triage-pr documented; gh-triage-pr NOT modified → Task 1 body; only 2 files in the whole plan. ✔
- Lifecycle step 7.5 wiring → Task 2. ✔
- Deploy via symlink → Task 3. ✔

**Placeholder scan:** full `itk-review-panel` SKILL.md and the lifecycle edit given; `<base>..<head>` are runtime arguments, not plan placeholders. No TBD/TODO. ✔

**Type consistency:** skill name `itk-review-panel` and the validator path used identically across Tasks 1–3; step marker `### 7.5 Review gate` spelled identically in Task 2 and its grep check. ✔
