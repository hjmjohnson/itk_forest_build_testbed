# Design: `itk-review-panel` — ITK-lens adversarial review panel

- **Date:** 2026-07-15
- **Repo:** `hjmjohnson/itk_forest_build_testbed` (kit repo), avenue **(a)**
- **Tracks:** issue #7 (Archon-learnings epic #1 — final sub-issue)

## Problem

There is no ITK-aware pre-PR review. The kit has no review skill — only the
built-in `/code-review` and superpowers' generic template (lenses: scalability /
security / testing). Neither knows ITK's `rules/` (comment-minimization,
commit-attribution, pr-message-format, fixture-and-expected-values) or ITK C++
idioms (sizetype, `MakeFilled`, the C++17-valid-on-both-ITKv5-and-ITKv6
constraint, downstream-break risk). And `itk-cleanup-pr-lifecycle` jumps from
step 7 (finalize commits) straight to step 8 (human PR gate) with **no review in
between**.

## Decision

A **`itk-review-panel`** skill — agent-followed (like #2–#6), NOT a Workflow-JS
script. It dispatches N reviewer subagents (each an ITK lens) via the Agent tool
(real parallelism), adversarially verifies findings, and synthesizes an advisory
report.

### Why not the Workflow tool

Parallel review + adversarial-verify is the Workflow tool's canonical example,
but that tool requires explicit **ultracode opt-in** and is background/token-heavy
— wrong for a review that should run **routinely**, including as a lifecycle step
on every cleanup PR. An agent-followed panel dispatches reviewer subagents with
no opt-in gate and works in any interactive session.

## Relationship to `gh-triage-pr` (reviewed in planning)

`gh-triage-pr` is **post-PR triage**: Phase 1 human comments → Phase 2 CI →
Phase 3 `@greptileai` draft review (external bot, on the open PR) → Phase 4
recommend-ready. `itk-review-panel` is **pre-PR, local, ITK-lens** — it runs
*before the PR exists*.

- **No duplication.** Greptile is external / generic / post-PR; the panel is
  local / ITK-rule-aware / pre-PR. Different stage, different lens set.
- **Synergistic.** Running the ITK-lens panel before opening the PR yields a
  cleaner diff, so greptile and human reviewers see fewer issues — reducing the
  "noisy, context-dependent" greptile rounds `gh-triage-pr`'s own docs warn
  about. This serves its "minimize wasted effort" philosophy and the
  `pr-local-test-first` "don't burn CI cycles" ethos.
- **Wiring boundary.** The lifecycle (#2) is the wired consumer (new step 7.5).
  `gh-triage-pr` is an *optional future* second consumer (re-run the panel on the
  updated diff before a force-push during triage) — but **#7 does NOT modify
  `gh-triage-pr`** (avoids scope creep; noted as a follow-up).

## The panel

**Invocation:** `/itk-review-panel [<base>..<head>]` (default: the current
branch vs its upstream/merge-base).

### Lenses (ITK-specific)

1. **Correctness / C++ safety** — does the change do what it claims; UB,
   lifetime, iterator invalidation, integer/sign issues.
2. **ITK API / idiom conformance** — `itk::SizeValueType`/`IndexValueType`,
   `MakeFilled`/`Filled`, `itk_add_test` patterns, smart-pointer/`New()` usage,
   and the **C++17-valid-on-both-ITKv5-and-ITKv6** constraint (never require
   C++20+).
3. **`rules/` compliance** — comment-minimization (no over-comment / no
   before-after narration), commit-attribution (no `Co-Authored-By` for AI),
   pr-message-format, and (for tests) pr-fixture-and-expected-values (fixtures
   exist; expected values verified from real data, not memory).
4. **Downstream-break risk** — does it change exported CMake / installed headers
   / public APIs that consumers rely on? Flag for the avenue-(b) forest sweep or
   `itk-test-cmake-changes-downstream`.
5. **Test coverage** — are new/changed behaviors exercised; do tests assert real
   behavior; is the test built+run locally (pr-local-test-first)?

### Complexity gate (Archon's smart-review)

Scale the panel to the diff:

- **Trivial** (tiny mechanical diff, few files, no API/CMake/test changes) →
  1–2 lenses (correctness + rules).
- **Moderate** → correctness + idiom + rules.
- **Large / structural** (many files, or touches API/CMake/headers/tests) → the
  full 5-lens panel.

State which tier was chosen and why (so a small cleanup isn't over-reviewed).

### Adversarial verify + synthesize

Each lens's findings are independently verified by a skeptic subagent (prompted
to refute; default to "not a real issue" if uncertain) before surviving into the
synthesis. Findings are **advisory** — they feed the human gate, never
auto-apply. Output: a ranked, deduped list (most-severe first) with file:line and
a concrete failure/violation for each, plus the chosen complexity tier.

## Companion edit — lifecycle step 7.5

`itk-cleanup-pr-lifecycle/SKILL.md` gains a step between 7 and 8:

> **### 7.5 Review gate — ITK-lens panel (advisory)**
> Run `/itk-review-panel` on the local commits. Address (or consciously accept,
> noting why) surviving findings before proceeding to the human PR gate. This is
> advisory — it does not open or block the PR by itself; it improves the diff
> before reviewers/CI see it.

(Existing steps 8–9 renumber-in-prose is unnecessary — they keep their numbers;
7.5 slots between.)

## Validation / testing

`itk-review-panel` is an agent-followed coordination skill (prose, no scripts).
Validation reuses `validate-lifecycle-refs.sh` (referenced skills/rules resolve).
The parallel dispatch and the reviews themselves are runtime behavior (like the
lifecycle's own gates), out of scope for a unit check.

## Out of scope

- A Workflow-JS orchestrator (ultracode-gated; wrong for a routine gate).
- Modifying `gh-triage-pr` (optional future second consumer; not touched here).
- Auto-applying findings (advisory only).
- Replacing `/code-review` or greptile (complementary, ITK-specific niche).

## Success criteria

1. `/itk-review-panel` dispatches lens-reviewers in parallel, adversarially
   verifies, and emits a ranked advisory report with the chosen complexity tier.
2. The complexity gate visibly scales the panel (trivial diff → few lenses; large
   → full panel).
3. Findings are advisory (never auto-applied) and feed the human gate.
4. `itk-cleanup-pr-lifecycle` invokes the panel at step 7.5 before the human PR
   gate; the spec's non-duplication-with-gh-triage-pr boundary is documented in
   the skill.
5. References validate; `itk-review-panel` is deployed and trigger-discoverable.

## Risks

- **Over-review of trivial diffs** — mitigated by the complexity gate (a
  one-line mechanical fix gets 1–2 lenses, not five).
- **Agent adherence / false confidence** — findings are advisory and
  adversarially verified; the human gate remains the authority.
- **Token cost of N reviewers** — bounded by the complexity gate; far cheaper
  than a burned CI/greptile round on an avoidable issue.
