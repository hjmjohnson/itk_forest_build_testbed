---
name: itk-cleanup-pr-lifecycle
version: 1.0.0
purpose: Drive an ITK mechanical-cleanup change from an empty branch to an opened draft PR by ordering, gating, and looping over an existing detect/transform cleanup skill and the pr-* rule gates.
description: >-
  Run a full ITK cleanup-PR lifecycle for one mechanical pattern: create an
  isolated worktree, detect and transform every site of a chosen cleanup skill
  one class at a time until dry, verify, pass the pre-commit and local-test
  gates, then stop at an explicit human gate before opening a single draft PR.
  Parameterized by the cleanup pattern skill (the payload); one lifecycle wraps
  every current and future detect/transform skill. Use when applying a
  mechanical cleanup (container-size-to-empty, declare-then-init, emplace-back,
  etc.) to ITK and shipping it as a draft PR. Trigger on:
  "itk-cleanup-pr-lifecycle", "/itk-cleanup-pr-lifecycle", "cleanup PR
  lifecycle", "run a cleanup to PR".
triggers:
  - itk-cleanup-pr-lifecycle
  - /itk-cleanup-pr-lifecycle
  - cleanup PR lifecycle
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
    - itk-start-worktree
    # payload cleanup skill is chosen at runtime from the detect/transform
    # family; run list-cleanup-patterns.sh for the eligible set.
  external_tools:
    - git
    - gh
    - pixi
    - pre-commit
  python_packages: []
  scripts:
    - list-cleanup-patterns.sh
    - validate-lifecycle-refs.sh
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Cleanup PR Lifecycle

Order, gate, and loop over existing skills to take ONE mechanical cleanup from an
empty branch to an opened draft PR. This skill is a thin wrapper: at each step it
defers to the referenced skill's own `SKILL.md` (the single source of truth) — it
never re-implements their procedure.

## Argument

`/itk-cleanup-pr-lifecycle <pattern-skill> [scope]`

- `<pattern-skill>` — the cleanup skill to apply (the payload), e.g.
  `itk-container-size-to-empty`. Must be one of the eligible detect/transform
  skills. **No argument → run `list-cleanup-patterns.sh`, print the eligible set,
  and stop.**
- `[scope]` — optional narrowing passed through to the payload: a module path
  (e.g. `Modules/Core/Common`) or a payload-specific filter (e.g.
  `--varname size`). Treat the payload's interface as opaque; read its
  `SKILL.md` for the flags it accepts.

Validate the argument:

```bash
bash "$(dirname "$0")/list-cleanup-patterns.sh" | grep -qx "<pattern-skill>" \
  || { echo "not an eligible cleanup pattern; choose one of:"; \
       bash "$(dirname "$0")/list-cleanup-patterns.sh"; exit 2; }
```

## Steps

Follow in order. Do not skip a **GATE**. State the repo/branch you are acting on
before each consequential command.

### 1. Isolated sandbox
Create a fresh worktree on a new branch off `upstream/main`:
`/itk-start-worktree new:cleanup-<pattern-skill>`
Work only inside the printed `WORKTREE_DIR` for the rest of the lifecycle.

### 2. Detect
Run the payload's detector to get the candidate sites within `[scope]`:
`bash skills/<pattern-skill>/detect.sh <WORKTREE_DIR>`

### 3. Transform — one class at a time, loop until dry
Apply the payload's transform, then re-detect; while candidate sites remain in
scope, transform the **next single pattern class**, confirm it compiles, and
**commit before moving to the next class** (N-Dekker incremental per-commit).
Use the payload's `transform.sh --apply` (or its documented clang-tidy command).
Re-run step 2's detector after each class; the loop ends when it reports zero
sites in scope. (When issue #3's reusable loop construct lands, delegate to it.)

### 4. Verify
`bash skills/<pattern-skill>/detect.sh <WORKTREE_DIR>` shows 0 sites in scope,
the target builds (`pixi run build-ITK`), and `git diff` shows every changed
site is a true instance of the pattern (per the payload's "Common mistakes").

### 5. GATE — pre-commit (rules/pre-commit-mandatory.md)
Run `pre-commit run --all-files`. If any hook reports "files were modified",
stage the fixes, fold them into the relevant commit (`git commit --fixup` +
`git -c sequence.editor=: rebase -i --autosquash upstream/main`), and re-run.
**Do not proceed until exit code is 0.**

### 6. Local test (rules/pr-local-test-first.md)
Build the touched code (minimum: it compiles). If the change touched or added
tests, run them: `ctest --test-dir <build> -V -R '<regex>'`. Fix before
proceeding.

### 7. Finalize commits
Ensure each commit has the correct ITK prefix (`STYLE:`/`COMP:`/`ENH:` per the
payload's guidance), minimal comments (rules/code-comment-minimization.md), and
attribution per rules/commit-attribution.md (no `Co-Authored-By` for AI).

### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
Summarize the change set (pattern, modules touched, commit count) to the user
and ask: *"Local work is complete and tested. Shall I open a single draft PR?"*
**Wait for an explicit human "yes". Never proceed on assumption.**

### 9. Open the draft PR
Only after the human yes: author the body in a file and open a draft
(rules/pr-always-draft.md, rules/pr-message-format.md,
rules/gh-body-file-for-long-text.md):

```bash
gh pr create --draft --repo InsightSoftwareConsortium/ITK --base main \
  --head <fork>:cleanup-<pattern-skill> --title "<PREFIX>: <summary>" \
  --body-file <body.md>
```

## Ends here
Post-PR review handling (reviewer comments, CI, greptile, marking ready) is a
separate `/gh-triage-pr` invocation on a later time horizon — not part of this
lifecycle.

## Self-check
`bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md`
must print `OK: all references resolve`.
