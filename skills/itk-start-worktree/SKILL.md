---
name: itk-start-worktree
version: 1.0.0
purpose: Create a self-contained ITK git-worktree sandbox (sibling dir <main>-<name>-src) for working a PR or a new branch in isolation, inheriting the primary checkout's commit-compliance hooks and pre-warming its own build dir.
description: >-
  Create an isolated ITK sandbox: a git worktree at
  <main>/../<main-basename>-<name>-src (where <name> is <PR#>-<branch> or the
  bare new branch), inheriting the primary checkout's pre-commit/KWStyle hooks,
  with the PR or new branch checked out and a CI build dir (its own pixi env)
  configured and pre-warming in the background. The session then works only
  inside that worktree so concurrent Claude work elsewhere cannot contaminate
  it. Use when starting focused work on one ITK PR or one new ITK branch and
  you want a clean, self-contained build/test sandbox.
  Trigger on: "itk-start-worktree", "/itk-start-worktree",
  "isolated ITK worktree", "ITK sandbox worktree", "work PR in a worktree".
triggers:
  - itk-start-worktree
  - /itk-start-worktree
user_invocable: true
cmd: false
argument_hint: "<PR#> | new:<branchname>"
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
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: false
  determinism: deterministic
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
    - gh
    - pixi
  python_packages: []
  scripts:
    - setup-worktree.sh
deployment:
  tier: always
  target_projects:
    - /home/johnsonhj/src/ITK
  needs_loader_dir: true
  adapters:
    - claude-code
---

# Isolated ITK Worktree Sandbox

## Overview

Spin up a **self-contained ITK sandbox** for one task: a git worktree at
`<main>/../<main-basename>-<name>-src` (a sibling of the primary clone) that
inherits the primary checkout's commit-compliance hooks (pre-commit/KWStyle)
and builds in its own `build/` with its own pixi env. The session `cd`s in and
works *only* there, so unrelated Claude actions in other checkouts cannot
contaminate this task and vice-versa.

`<name>` is `<PR#>-<headBranch>` for a PR, or the bare `<branch>` for a new
branch. So primary clone `~/src/ITK` + `new:remove-fem-module` →
`~/src/ITK-remove-fem-module-src`.

## Required argument

The first argument is **mandatory** and must be exactly one of:

| Argument | Meaning |
|----------|---------|
| `<PR#>` (digits) | Check out that upstream PR's head branch |
| `new:<branchname>` | Create `<branchname>` from `upstream/main` |

No argument → stop and ask which PR# or `new:<branch>` to use. Do not guess.

## Procedure

Run from `/home/johnsonhj/src/ITK` (the main checkout that owns `.pixi`).

### 1. Create the worktree + inherit hooks (steps 1–3)

```bash
~/.claude/skills/itk-start-worktree/setup-worktree.sh "<ARG>"
```

The script (fails loudly if the target dir exists) does:
- `git fetch upstream --prune`
- `git worktree add` (new branch off `upstream/main`, or detached for PR mode)
- guarantees `core.hooksPath` → the primary's `.git/hooks` (only sets it when
  unset). A linked worktree otherwise defaults to its own empty git-dir hooks
  and would skip pre-commit/KWStyle; this makes it inherit the primary's
  already-installed, working hooks. KWStyle/rebase/blame config is shared via
  `.git/config`, so the worktree is a full peer with no SetupForDevelopment
  re-run and no per-worktree hook download.
- for a PR, `gh pr checkout <PR#>` *inside* the worktree (wires push tracking)
- symlinks `<WORKTREE_DIR>/.devlocal` → `<MAIN_REPO>/.devlocal`. `.devlocal` is
  per-project scratch (`hj-todo`'s `todo.md`, plans, hints), not per-worktree;
  a symlink keeps every worktree reading/writing the same shared TODO and
  scratch content as the main checkout instead of forking a stale copy.

It prints `WORKTREE_DIR=…`, `WORKTREE_NAME=…`, `BRANCH=…`, and
`CCACHE_BASEDIR=…` (equal to `WORKTREE_DIR`). Capture `WORKTREE_DIR`,
`WORKTREE_NAME`, and `CCACHE_BASEDIR`.

> No `.pixi` is shared in. `pixi run configure-ci` (step 3) builds the
> worktree its own env — cheap, since pixi hardlinks packages from the global
> cache rather than re-downloading.

### 2. Enter the sandbox (step 4)

```bash
cd <WORKTREE_DIR>
```

All later commands run here. Do **not** operate on the main checkout again
for this task.

### 3. Configure, then pre-warm the build in the background (step 5)

Export `CCACHE_BASEDIR` (the value the script emitted, = `<WORKTREE_DIR>`)
first, so ccache rewrites this worktree's absolute build paths to relative and
shares cached objects with builds at other worktree locations:

```bash
export CCACHE_BASEDIR=<WORKTREE_DIR>
pixi run configure-ci
```

When configure succeeds, launch the long build detached (use the Bash tool's
**background** mode so the session stays interactive). Keep `CCACHE_BASEDIR`
exported in the build shell too:

```bash
CCACHE_BASEDIR=<WORKTREE_DIR> nice -19 pixi run build-ci >/dev/null 2>&1   # run_in_background: true
```

ccache is global, so this reuses cached objects from other ITK builds. The
build readies `build/` for `pixi run test-ci -R <regex>` later.

### 4. Register the worktree with Serena

If the `mcp__serena__*` tools are available (load via ToolSearch if deferred),
call `activate_project` with `<WORKTREE_DIR>` so Serena indexes this checkout
under its own project entry:

```
mcp__serena__activate_project({ "project": "<WORKTREE_DIR>" })
```

Each worktree is a distinct path, so Serena treats it as a separate project
from the main `ITK` entry and needs its own activation — it does not inherit
the main checkout's index. Do this once per worktree, right after creation;
the dedicated session launched in step 5 below can also re-activate it if
Serena's active project has since changed.

### 5. Hand off a dedicated session (step 7)

The worktree is a self-contained sandbox; the cleanest way to work it is a
**separate Claude session rooted in that directory**, named canonically after
the worktree. The `claude` CLI sets a session display name with `-n/--name`
(shown in the prompt box, `/resume` picker, and terminal title). There is no
agent tool to rename the *current* session, so do not claim it was renamed —
instead hand the user the exact command to launch the dedicated one.

The canonical session name **is** `<WORKTREE_NAME>` (i.e. `<PR#>-<branch>` for a
PR, or the bare `<branch>` for a new branch).

## Final report

End the report with the worktree dir, branch, the background `build-ci` task id
(when configure succeeded), and — as the closing lines — a copy-pasteable
launch block:

```
Worktree created, start a new session by:

    cd <WORKTREE_DIR> && export CCACHE_BASEDIR=<WORKTREE_DIR> && claude --name <WORKTREE_NAME>
```

Substitute the real absolute `<WORKTREE_DIR>` and `<WORKTREE_NAME>` so the line
is runnable verbatim. If configure or build failed, say so above this block and
still print the launch line (the dedicated session is where the failure gets
worked) — do not omit it.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Running `pixi run` from main after setup | `cd <WORKTREE_DIR>` first; the sandbox is the worktree. |
| Running `SetupForDevelopment.sh` in the worktree | Redundant: hooks/config are inherited. Its `pre-commit-install` even refuses under `core.hooksPath`. The script handles compliance. |
| Blocking the session on `build-ci` | Run it backgrounded; configure-ci is foreground, build-ci is not. |
| Claiming the session was renamed | The agent cannot rename it; surface the value for the user to set. |
| Reusing an existing worktree name | Script aborts if the dir exists; remove the old one or pick a new branch. |

## Teardown (when the task is done)

```bash
cd /home/johnsonhj/src/ITK
git worktree remove --force ../ITK-<WORKTREE_NAME>-src
# delete the local branch too if it was a throwaway new: branch
```

`.devlocal` is a symlink to the main checkout, so removal never deletes shared
TODO/scratch content — nothing to back up before teardown.
