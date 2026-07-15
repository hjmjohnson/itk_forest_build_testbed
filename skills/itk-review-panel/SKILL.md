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
