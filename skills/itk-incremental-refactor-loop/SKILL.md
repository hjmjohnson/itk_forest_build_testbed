---
name: itk-incremental-refactor-loop
version: 1.0.0
purpose: Drive a mechanical ITK refactor one pattern class at a time until the payload's detector is dry, committing per class (N-Dekker incremental methodology), with an optional subagent-per-class mode for large mechanical sweeps.
description: >-
  Reusable incremental-refactor loop: given a payload refactor skill, detect
  candidate sites, then repeatedly pick ONE pattern class, transform just that
  class, verify it compiles, review the hunks, and commit that class alone —
  until the payload's detector reports zero sites. Preserves one-class-per-commit
  discipline. Eligible payloads are itk-mechanical-cleanup's fourteen patterns
  plus script-based refactors like itk-declare-then-init. Use when
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
argument_hint: "<payload> [scope]"
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
    - itk-mechanical-cleanup
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

`/itk-incremental-refactor-loop <payload> [scope]`

- `<payload>` — the refactor to apply. Two forms, both emitted by
  `~/.claude/skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh`:
  `itk-mechanical-cleanup:<pattern>` for the fourteen detect.sh/transform.sh
  patterns, or a bare skill name for a script-based multi-class refactor such
  as `itk-declare-then-init`. Treat the payload interface as **opaque** — read
  `itk-mechanical-cleanup/patterns/<pattern>/PATTERN.md` (or the skill's
  `SKILL.md`) for how it detects, enumerates pattern classes, and applies one
  class. No argument → print the eligible set and stop.
- `[scope]` — optional narrowing passed through to the payload (a module path,
  or a payload-specific filter like `--varname size`).

## The loop (default: supervised, sequential)

1. **Detect** — run the payload's detector over `[scope]` (its `detect.sh`, or a
   finder-script dry-run). Record the candidate count. Every `detect.sh` ends on
   a `----` rule and one `match_count: <N>` line — that N is the count, and a
   clean tree is `match_count: 0` with exit 0 (exit 2 means the scan could not
   run). See `itk-mechanical-cleanup/lib/detect-common.sh`.
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
