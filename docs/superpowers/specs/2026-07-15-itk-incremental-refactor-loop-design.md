# Design: `itk-incremental-refactor-loop` — a reusable "loop" skill

- **Date:** 2026-07-15
- **Repo:** `hjmjohnson/itk_forest_build_testbed` (kit repo), avenue **(a)** — ITK PR/issue management
- **Tracks:** issue #3 (Archon-learnings epic #1); consumed by `itk-cleanup-pr-lifecycle` (#2) step 3

## Problem

The "one pattern class per commit, until the detector is dry" loop — the
N-Dekker incremental methodology — is re-narrated in every incremental-refactor
skill (`itk-declare-then-init`, `itk-allocate-initialized`, `itk-sizetype-filled`,
`itk-convert-to-gtest`, the `detect.sh`/`transform.sh` family, …) and enforced
only by the model remembering it. `itk-cleanup-pr-lifecycle` step 3 currently
expresses the loop in prose as a placeholder, explicitly waiting for this skill.

## Decision

Encode the loop once as a **loop skill** — an ordinary `SKILL.md`
(`itk-incremental-refactor-loop`) that is the single canonical, referenceable
loop procedure. Same rationale as #2: the runtime is an interactive Claude
session and the artifact is a contract the agent follows, so a `SKILL.md` beats
any new YAML node type or executor (trigger discovery, deployment, validation,
v2 contract all come for free). Borrow Archon's *idea* (`loop { until;
fresh_context }`), not its format.

## The loop procedure (default mode — supervised, sequential)

`/itk-incremental-refactor-loop <pattern-skill> [scope]`

1. **Detect** — run the payload's detector over `[scope]`; capture the candidate
   set and count. The detector is whatever the payload's `SKILL.md` documents:
   `detect.sh` for the detect/transform family, or the dry-run of a finder
   script (e.g. `find_declare_then_init.py`) for script-based refactors. Treat
   the payload interface as **opaque** — read its `SKILL.md`, do not assume a
   uniform CLI.
2. **Pick ONE pattern class** — the smallest coherent unit the payload exposes:
   one `--pattern`, one `--varname`/`--vartype` filter, or one clang-tidy check.
3. **Transform just that class** — the payload's `transform.sh --apply` (or its
   documented clang-tidy / script command), scoped to that class only.
4. **Normalize** — `clang-format --style=file -i` on modified files.
5. **Verify** — the target compiles (build it), and every changed hunk is a true
   instance of the pattern (the payload's "Common mistakes" / pitfalls).
6. **Commit that class alone** — correct ITK prefix, one class per commit,
   `rules/pre-commit-mandatory.md` satisfied.
7. **Re-detect** — rerun step 1's detector in scope. If candidate sites remain,
   go to step 2. The loop ends when the detector reports **zero** sites
   (`NO_MATCHES_REMAIN`).

**Termination guard (no infinite loop):** if a class's transform leaves the
detector count unchanged (transformed nothing, e.g. all remaining hits are
forward-reference hazards or false positives), **stop and flag those sites for
manual review** instead of re-looping the same class.

## `fresh_context`

- **Default (a) — advisory.** The loop runs sequentially in the main session;
  begin each class from a clean slate. The per-commit boundary at step 6 is the
  natural context reset. No orchestration.
- **Opt-in (b) — subagent per class.** For large, fully-mechanical `--apply`
  sweeps where the transform is deterministic and hunk-review is low-risk,
  dispatch one subagent per pattern class (the Agent / dispatching-parallel-agents
  pattern); each subagent does steps 3–6 for its class and reports; the
  controller aggregates. Keeps the controller's context clean and isolates each
  class. **Not the default** — explicitly opt-in, restricted to `--apply`
  deterministic transforms, and still one-commit-per-class + build-verified.

## Frontmatter contract (v2, reused)

- `name: itk-incremental-refactor-loop`, `user_invocable: true`, `cmd: false`
- `argument_hint: "<pattern-skill> [scope]"`
- `dependencies.skills`: the payload skill is chosen at runtime. Eligible
  payloads are the **incremental-refactor skills** — the `detect.sh`/`transform.sh`
  family (enumerated by `list-cleanup-patterns.sh`) **plus** script-based
  multi-class refactors like `itk-declare-then-init`. Eligibility check: the
  named `skills/<pattern-skill>/` dir exists and documents a detect+transform
  interface; the loop reads that `SKILL.md` for the specifics.
- `contract.side_effects`: `modifies_working_tree: true`, `git_required: true`,
  `network_required: false`, `user_confirmation_required: false` (the loop does
  not open PRs — the lifecycle's human gate does).
- `contract.determinism: hybrid`.
- `deployment.tier: project`, `target_projects: [itk]`, `adapters: [claude-code]`.

## Integration (first delivery)

1. **`itk-cleanup-pr-lifecycle` step 3** — replace the inline loop prose with:
   *"delegate to `/itk-incremental-refactor-loop <pattern-skill> [scope]`"*.
2. **`itk-declare-then-init` retrofit (the proof)** — replace its per-class loop
   mechanics with a pointer to `itk-incremental-refactor-loop`. Keep all
   payload-specific knowledge (the pattern-class table, `--apply` behavior,
   forward-ref pitfalls, the N-Dekker convention reference) — only the generic
   loop mechanics move out.

## Out of scope

- Bulk retrofit of the other loopers (`itk-allocate-initialized`,
  `itk-sizetype-filled`, `itk-convert-to-gtest`, …) — a follow-up once the
  pattern is proven on `itk-declare-then-init`.
- The human PR gate and PR creation — that is the lifecycle (#2) / gate hooks (#4).
- Any mechanical loop executor — the loop is agent-supervised by design
  (build-verify + hunk review each class).

## Success criteria

1. `itk-cleanup-pr-lifecycle` step 3 references the loop skill; no inline loop
   prose remains there.
2. `itk-declare-then-init`'s loop mechanics are replaced by a reference to the
   loop skill; its payload-specific content is intact (pattern table, pitfalls,
   N-Dekker refs).
3. The loop skill documents both modes, defaults to (a), and states the
   termination guard.
4. The loop skill is deployed and trigger-discoverable; its skill/rule
   references validate (reuse the `validate-lifecycle-refs.sh` approach or an
   equivalent existence check).

## Risks

- **Retrofitting `itk-declare-then-init` drops nuance.** Mitigate: move only the
  generic loop mechanics; keep the pattern-class table, pitfalls, and N-Dekker
  convention verbatim.
- **Mode (b) autonomy vs. review discipline.** Mitigate: restrict (b) to
  `--apply` deterministic transforms; still require build-verify and one
  commit per class; hunk review stays a documented step even under (b).
