# Design: `itk-cleanup-pr-lifecycle` — a composite "lifecycle" skill

- **Date:** 2026-07-15
- **Repo:** `hjmjohnson/itk_forest_build_testbed` (kit repo), avenue **(a)** — ITK PR/issue management
- **Tracks:** issue #2 (first concrete deliverable of the Archon-learnings epic #1)

## Problem

Multi-skill chains are re-derived in prose every session. A routine ITK
*cleanup PR* — pick a mechanical pattern, fix every site one class at a time,
verify, satisfy the pre-commit and PR gates, open a draft — is not encoded
anywhere as a single unit. Its steps live scattered across `itk-start-worktree`,
the ~20 detect/transform pattern skills, and the `rules/` policies. Each session
the agent reconstructs the ordering and the gates from memory, which is slow and
error-prone (the `pr-no-unsolicited` rule exists because a gate was once missed).

## Decision

Encode the chain as **one new skill of a "lifecycle" kind** — an ordinary
`SKILL.md` whose body is an ordered checklist and whose steps are invocations of
existing skills and named rule-gates. This is not a new artifact type and not a
new runtime.

### Why not a YAML/JS workflow engine

The runtime is *only* an interactive Claude session, and the artifact is *a
contract the agent follows*. Under those two constraints a YAML file or a JS
`Workflow` script buys nothing over a `SKILL.md`: in all three the "executor" is
the same agent reading the same text. A `SKILL.md` is strictly better because it
already gets trigger-based discovery, symlink deployment, `doctor` validation,
and the v2 contract — machinery a parallel YAML system would have to rebuild.
Borrow Archon's *ideas* (explicit ordered steps, loop-until-dry, human gates),
not its format. (Confirmed decisions: end at draft-PR **1(a)**; no new framework
schema **2(a)**.)

## The lifecycle

**Invocation:** `/itk-cleanup-pr-lifecycle <pattern-skill> [scope]`

One parameterized wrapper, not 20 near-duplicates. The lifecycle is the
invariant scaffold; `<pattern-skill>` is the payload plugged in at the transform
step (e.g. `itk-container-size-to-empty`, `itk-declare-then-init`,
`itk-emplace-back-construct`, …). `[scope]` optionally narrows the target (a
module path, or a `--varname`/`--vartype` filter the pattern skill accepts).

`<pattern-skill>` is validated against the detect/transform family — skills under
`skills/itk-*` that expose a `detect.sh` (and usually a `transform.sh`). No
argument → print the list of eligible pattern skills and stop.

### Steps (each backed by an existing skill or a named rule)

| # | Step | Backed by | Gate? |
|---|------|-----------|-------|
| 1 | Create isolated sandbox: new branch off `upstream/main`, hooks inherited, CI build dir pre-warming | `itk-start-worktree new:<branch>` | — |
| 2 | Detect candidate sites for `<pattern-skill>` within `[scope]` | pattern skill `detect.sh` | — |
| 3 | Transform **one pattern class at a time, looping until detect is dry**, committing per class | pattern skill `transform.sh` + the loop pattern of issue #3 | — |
| 4 | Verify: re-detect (0 sites left in scope) + build + eyeball every hunk | pattern skill "Verification" section | — |
| 5 | Run `pre-commit run --all-files`; on auto-fixes, stage + re-fixup + re-run until exit 0 | `rules/pre-commit-mandatory.md` | **GATE** |
| 6 | Build + run the touched code locally (compile at minimum; `ctest -R` if tests touched) | `rules/pr-local-test-first.md` | — |
| 7 | Finalize commits: correct prefix (`COMP:`/`STYLE:`/`ENH:`), minimal comments, attribution | `rules/commit-attribution.md`, `rules/code-comment-minimization.md` | — |
| 8 | Summarize the change set, then ask *"open a single draft PR?"* and **wait for an explicit yes** | `rules/pr-no-unsolicited.md` | **HUMAN GATE** |
| 9 | `gh pr create --draft --body-file …` (body per format rule) | `rules/pr-always-draft.md`, `rules/pr-message-format.md`, `rules/gh-body-file-for-long-text.md` | — |

### How steps invoke sub-skills

The lifecycle body names each sub-skill; at that step the agent reads and follows
the referenced `SKILL.md` (or runs its scripts directly, e.g. `detect.sh` /
`transform.sh`). The lifecycle does **not** copy sub-skill procedure inline — it
references, so sub-skills stay the single source of truth and the lifecycle stays
a thin ordering + gating layer.

### Loop-until-dry (step 3)

Until issue #3 lands a reusable loop construct, the lifecycle expresses the loop
in prose: *"re-run `detect.sh`; while candidate sites remain in scope, transform
the next single pattern class, verify it compiles, and commit before moving to
the next class."* This preserves the N-Dekker incremental per-commit discipline.
When #3 lands, step 3 delegates to it.

### Gate representation

Gates (steps 5 and 8) are explicit **STOP** steps that cite their governing rule
and state the exit condition. In this agent-followed-contract model they are
steps the agent must not skip. Making them *structurally* enforced (a hook that
blocks `gh pr create` without a recorded approval, or `git push` without a green
`pre-commit`) is issue **#4**'s scope, not this one. #2's job is only to stop the
re-derivation and make the gates un-missable in the checklist.

## Frontmatter contract (v2, reused as-is)

Composition is expressed with the *existing* `dependencies.skills` field — no new
schema. Key fields:

- `name: itk-cleanup-pr-lifecycle`, `user_invocable: true`, `cmd: false`
- `argument_hint: "<pattern-skill> [scope]"`
- `dependencies.skills:` `[itk-start-worktree, itk-container-size-to-empty,
  itk-declare-then-init, …]` — the composed skills (or a note that the payload
  skill is chosen at runtime from the detect/transform family).
- `contract.side_effects`: `modifies_working_tree: true`, `git_required: true`,
  `network_required: true` (gh/PR), `user_confirmation_required: true` (step 8).
- `contract.determinism: hybrid` (deterministic scripts + agent-followed ordering).
- `deployment.tier: project`, `target_projects: [itk]`, `adapters: [claude-code]`.

A `kind: lifecycle` marker is **not** added to the required schema (decision
2(a)). If a lightweight, optional convention is wanted later to distinguish
lifecycle skills in listings, it can be a non-breaking optional field — out of
scope here.

## Out of scope

- **Forest / downstream validation** (avenue b). A pure cleanup PR builds ITK
  (and maybe one consumer); a full forest sweep is a separate avenue-(b) concern.
- **Post-PR review handling** — `gh-triage-pr` runs on a different time horizon
  (after CI churns) and stays a separate invocation. Lifecycle ends at step 9.
- **Structural gate enforcement** — issue #4.
- **A reusable loop construct** — issue #3; approximated in prose here.
- **The general "what is a workflow" format question** — deliberately not
  answered; this deliverable proves the pattern with one concrete skill and lets
  the general shape fall out of the concrete case.

## Success criteria

1. `/itk-cleanup-pr-lifecycle itk-container-size-to-empty` drives a real cleanup
   from empty branch to opened draft PR without the agent re-deriving the order
   or skipping a gate.
2. Swapping the payload (`itk-declare-then-init`, etc.) requires *no* change to
   the lifecycle skill.
3. `agent-skills doctor` reports the new skill valid.
4. Every gate (5, 8) halts as specified; step 8 never proceeds without an
   explicit human "yes".

## Risks / open questions

- **Agent adherence.** An agent-followed contract is only as good as the agent's
  discipline; this is the residual risk #4 exists to close. Acceptable for #2.
- **Payload skill surface varies.** Some cleanups are clang-tidy-driven, some are
  `detect.sh`/`transform.sh`, some (e.g. `itk-declare-then-init`) take a
  sub-pattern argument. The lifecycle must treat the payload's interface as
  opaque and defer to its `SKILL.md` rather than assume a uniform CLI.
- **Commit-prefix choice** (`COMP:` vs `STYLE:` vs `ENH:`) is pattern-dependent;
  step 7 delegates the choice to the payload skill's guidance / ITK convention.
