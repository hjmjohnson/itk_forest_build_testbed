# Design: `pr_gate.py` — structural enforcement of the PR/pre-commit gates

- **Date:** 2026-07-15
- **Epic tracked in:** `hjmjohnson/itk_forest_build_testbed` (kit repo), avenue **(a)**
- **Code lands in:** `~/src/agent-skills/` (home of the `pr-*`/`pre-commit-mandatory` rules and the FERPA hooks) + global `~/.claude/settings.json`
- **Tracks:** issue #4 (Archon-learnings epic #1)

## Problem

The gates that `itk-cleanup-pr-lifecycle` (#2) and the `rules/` encode are today
*documented steps the agent must remember*: `pre-commit-mandatory`,
`pr-always-draft`, `pr-no-unsolicited`. `pr-no-unsolicited` exists **because that
advisory failed** (16 simultaneous upstream PRs). A step in a `SKILL.md` cannot
stop an accidental skip; only a harness hook can.

## What a hook can and cannot enforce

A Claude Code PreToolUse hook sees the *tool command and repo state*, not the
*conversation*. That bounds what "structural" means here:

| Gate | Enforcement | Mechanism |
|---|---|---|
| `pre-commit-mandatory` | **Full** | `git push` denied unless a "pre-commit passed at `<HEAD-sha>`" marker exists for the current HEAD (no-op where there is no `.pre-commit-config.yaml`). |
| `pr-always-draft` | **Full** | `gh pr create` denied unless `--draft` is present. |
| `pr-no-unsolicited` | **Partial (hardening)** | `gh pr create` denied unless a fresh approval marker for the current repo+branch exists. Kills the *accidental skip*; a determined agent could still write the marker — that residual is inherent (a hook cannot verify conversational consent). |
| FERPA confirmation | **Already done** | `ferpa-pre-hook.py` already blocks PII egress on `gh`/`git push`/`curl`. Out of scope. |

## Architecture

**One Python module** `~/src/agent-skills/bin/pr_gate.py` with three CLI modes:

- `pr_gate.py hook` — the PreToolUse hook. Reads the hook JSON on stdin, inspects
  the `Bash` command, emits an allow/deny decision (mirroring
  `ferpa-pre-hook.py`'s I/O contract). **Fail-open**: any exception, unparseable
  input, or unrelated command → allow (emit nothing / exit 0).
- `pr_gate.py approve [--reason TEXT]` — records the PR approval marker for the
  current repo+branch. The lifecycle skill runs this *after* the human says yes.
- `pr_gate.py record-precommit` — runs `pre-commit run --all-files`; on success
  records the pre-commit marker for the current HEAD sha. The lifecycle skill
  runs this at its pre-commit gate.

**State** lives in `~/.local/state/agent-skills/pr-gate/` (per skill-framework
convention; `chmod 700` dir). Keys:

- approval: `approved-<key>` where `key = sha256(repo_root + "\0" + branch)[:16]`;
  file mtime gives the TTL (`PR_GATE_APPROVAL_TTL_MIN`, default 60).
- pre-commit: `precommit-<key>-<HEAD-sha>` (existence = passed on that exact tree).

### Hook decision logic (`pr_gate.py hook`)

Given the Bash `command` string and the session `cwd`:

1. If the command contains a `git push` invocation (parsed, not substring-naive —
   tolerate env prefixes, `&&`, quoting):
   - Resolve `repo_root` and `HEAD` via `git -C <cwd>`.
   - If `<repo_root>/.pre-commit-config.yaml` is absent → **allow** (the
     `PRE_COMMIT_ALLOW_NO_CONFIG` case: kit repo, release-5.4).
   - Else if a `precommit-<key>-<HEAD>` marker exists → **allow**; otherwise
     **deny** with: *"pre-commit-mandatory: run `pr_gate.py record-precommit`
     against this exact HEAD before pushing."*
   - Also deny if the HEAD commit subject starts with `fixup!`/`squash!`.
2. If the command contains a `gh pr create` invocation:
   - If neither `--draft` nor `-d` present → **deny** with: *"pr-always-draft:
     add --draft."*
   - Else if no fresh `approved-<key>` marker (within TTL) → **deny** with:
     *"pr-no-unsolicited: no recorded human approval for <branch>. After the
     human authorizes THIS PR, run `pr_gate.py approve`."*
3. Otherwise → **allow**.

Deny is emitted in the same JSON shape `ferpa-pre-hook.py` uses (to be read from
that file during implementation, not guessed).

### Wiring

Append a second `command` hook to the existing PreToolUse `Bash` matcher in
`~/.claude/settings.json`, after `ferpa-pre-hook.py`:
`python3 /home/johnsonhj/src/agent-skills/bin/pr_gate.py hook`. Both run; either
denying blocks. Applied via the `update-config` skill (the sanctioned path for
settings edits). Takes effect on the next session start.

### Lifecycle wiring (kit repo)

`itk-cleanup-pr-lifecycle/SKILL.md` is updated so the recorded actions exist:

- **Step 5 (pre-commit gate):** after `pre-commit run --all-files` is clean, run
  `pr_gate.py record-precommit` (records the HEAD marker so step-9-era pushes pass).
- **Step 8 (human gate):** after the explicit human "yes", run `pr_gate.py approve`.
- **Step 9:** `gh pr create --draft …` now satisfies both hook checks.

## Testing

`pr_gate.py hook` is pure-ish: feed synthetic PreToolUse JSON on stdin, assert
the decision. Cases (a temp git repo fixture drives the repo-state ones):

- unrelated command (`ls -la`) → allow
- malformed / empty stdin → allow (fail-open)
- `git push` in repo with no `.pre-commit-config.yaml` → allow
- `git push` in repo WITH config, no marker → deny
- `git push` after `record-precommit` (marker present, HEAD matches) → allow
- `git push` after a new commit (HEAD moved, marker stale) → deny
- `gh pr create` without `--draft` → deny
- `gh pr create --draft` without approval marker → deny
- `gh pr create --draft` after `approve` (fresh marker) → allow
- `gh pr create --draft` with an expired marker (mtime beyond TTL) → deny
- `approve` then `record-precommit` write the expected marker files

## Out of scope

- FERPA gate (already enforced by `ferpa-pre-hook.py`).
- Enforcing conversational consent beyond the approval marker (a hook cannot).
- Retrofitting gates into skills other than `itk-cleanup-pr-lifecycle`.
- Any change to how the human's own terminal behaves — hooks only intercept
  Claude Code's tool calls, never the user's manual `git`/`gh`.

## Success criteria

1. `pr_gate.py hook` denies: `git push` without a matching pre-commit marker (in
   a config'd repo), `gh pr create` without `--draft`, and `gh pr create --draft`
   without a fresh approval marker — and allows all the negative/unrelated cases.
2. Fail-open verified: malformed input and unrelated commands always allow.
3. `approve` / `record-precommit` write markers the hook then honors.
4. Wired into `~/.claude/settings.json` alongside FERPA (idempotently, via
   update-config); FERPA hook untouched.
5. `itk-cleanup-pr-lifecycle` records the markers at steps 5 and 8.
6. All test cases pass locally.

## Risks

- **A global Bash hook is high-blast-radius.** Mitigate: fail-open on every error;
  touch only `git push` / `gh pr create`; every other command returns allow
  immediately. Tests assert the allow-by-default behavior explicitly.
- **Marker forgeability.** Inherent to the partial-enforcement tier; documented,
  not hidden. The goal is killing accidental skips, not defeating a rogue agent.
- **Latency.** The hook never runs `pre-commit` itself (marker check only), so it
  adds negligible time; `record-precommit` bears the cost, once, at the gate.
