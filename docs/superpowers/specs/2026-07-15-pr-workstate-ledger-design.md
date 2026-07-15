# Design: PR/issue work-state ledger (durable, extends gh-comment-cache)

- **Date:** 2026-07-15
- **Repo:** `hjmjohnson/itk_forest_build_testbed` (kit repo), avenue **(a)**
- **Tracks:** issue #5 (Archon-learnings epic #1)

## Problem

There is no single place that answers, across the PR tools I run, "for PR #N,
what's my *work-state*" — which skill last touched it, what the gate decision
was, and which reviewer concerns *I've already addressed* (so `gh-triage-pr`
doesn't re-surface resolved ones each run). That state is **session-authored**:
not a GitHub fact, not derivable from raw data.

Most adjacent state already exists and is NOT rebuilt here: `gh-comment-cache`
caches the PR index + comments (SQLite, 3-layer, workspace-keyed); `gh-issue-summary`
derives outstanding reviewer requests on demand; #4's `pr_gate` persists gate
markers. #5 adds only the thin **work-state** layer on top.

## Decision

Extend the `gh-comment-cache` skill with a small work-state layer, but store it
in a **separate durable SQLite DB**, not in the cache DB.

### Why durable, not a cache-DB migration

`gh-comment-cache`'s DB lives under `~/.cache` (`cache_path()` →
`XDG_CACHE_HOME`/`~/.cache`), which `agent-skills cache clear` wipes. Work-state
is durable memory that must survive a cache clear. So it lives in
`~/.local/state/agent-skills/gh-comment-cache/workstate-<workspace-fp>.sqlite`
(dir `0700`), keyed by the **same** `workspace.py` fingerprint as the cache —
reusing the identity without touching the shared `cache.py` or risking data loss.
Override for tests: `PR_WORKSTATE_DIR`.

## Deliverable

A `pr_workstate.py` script under `skills/gh-comment-cache/scripts/`, its own
schema (applied on open — plain `CREATE TABLE IF NOT EXISTS`, no cache-meta
machinery needed), and a `gh-triage-pr` wiring that records addressed concerns.

### Schema (durable DB)

```sql
CREATE TABLE IF NOT EXISTS pr_workstate (
    repo_owner   TEXT NOT NULL,
    repo_name    TEXT NOT NULL,
    number       INTEGER NOT NULL,
    status       TEXT,          -- e.g. in-progress | gated | pushed | merged
    last_skill   TEXT,          -- which skill last touched it
    gate_state   TEXT,          -- e.g. precommit-ok | approved | none
    local_verdict TEXT,         -- last local build/test verdict, free text
    updated_at   TEXT NOT NULL, -- ISO8601 (caller passes; no Date.now in scripts)
    PRIMARY KEY (repo_owner, repo_name, number)
);
CREATE TABLE IF NOT EXISTS pr_concern_state (
    repo_owner   TEXT NOT NULL,
    repo_name    TEXT NOT NULL,
    number       INTEGER NOT NULL,
    comment_id   TEXT NOT NULL, -- GitHub review-comment id
    addressed    INTEGER NOT NULL DEFAULT 1 CHECK (addressed IN (0,1)),
    by_skill     TEXT,
    at           TEXT NOT NULL,
    PRIMARY KEY (repo_owner, repo_name, number, comment_id)
);
```

### CLI

- `pr_workstate.py set <owner/repo> <number> [--status S] [--skill X] [--gate G] [--verdict V]`
  — upsert a `pr_workstate` row (only provided fields change).
- `pr_workstate.py concern <owner/repo> <number> <comment_id> --by <skill> [--reopen]`
  — upsert a `pr_concern_state` row (`--reopen` sets `addressed=0`).
- `pr_workstate.py addressed <owner/repo> <number>`
  — print the addressed `comment_id`s (one per line) so a fetcher can skip them.
- `pr_workstate.py workqueue [--repo <owner/repo>]`
  — join the durable work-state against `gh-comment-cache`'s `raw_pr_index`
    (opened read-only at `cache_path("gh-comment-cache", ws)`; degrade
    gracefully to work-state-only rows if the cache DB is absent). Prints a
    table: `#`, title, state, `last_skill`, `gate_state`, `addressed/…`.

Keying uses `workspace.identify(cwd).fingerprint` (imported from the sibling
`gh-comment-cache/lib/agent_skills/workspace.py`).

### Consumer wiring (the proof) — `gh-triage-pr`

- After `ghtp_reply.py` successfully replies to / resolves an inline reviewer
  comment, it records the concern:
  `pr_workstate.py concern <repo> <pr> <comment_id> --by gh-triage-pr`.
- `ghtp_fetch.py` (which lists outstanding concerns) consults
  `pr_workstate.py addressed <repo> <pr>` and marks/skips already-addressed
  comment ids, so a re-run doesn't re-surface concerns already handled locally.

This is the single most concrete win: not re-triaging concerns I already
addressed. (Lifecycle `set`-ing status/gate is a later follow-up, not in #5.)

## Testing

`pr_workstate.py` is a pure-ish sqlite CLI — drive it with a temp
`PR_WORKSTATE_DIR` and a temp cache DB:

- `set` then re-`set` a subset of fields → row upserts, untouched fields persist.
- `concern … ` then `addressed` → lists the id; `--reopen` removes it.
- `workqueue` with a seeded `raw_pr_index` cache DB → joins title/state; with no
  cache DB → degrades to work-state-only rows (no crash).
- Unknown repo/number → empty, exit 0.
- Durable DB survives a simulated cache clear (it's in `PR_WORKSTATE_DIR`, not the
  cache path).

## Out of scope

- Any modification to `cache.py` or the shared 3-layer cache semantics.
- Syncing/reconciling work-state against GitHub's live "resolved" status (local
  record complements, does not mirror, GitHub).
- Lifecycle (#2) status/gate recording and #6 fan-out integration (later).
- A GUI; `workqueue` is a plain text table.

## Success criteria

1. `pr_workstate.py` `set`/`concern`/`addressed`/`workqueue` all work against a
   durable DB under `~/.local/state/agent-skills/gh-comment-cache/`.
2. The durable DB is unaffected by `agent-skills cache clear` (different tree).
3. `workqueue` joins the gh-comment-cache PR index when present and degrades
   gracefully when absent.
4. `gh-triage-pr` records addressed concerns on reply and skips them on re-fetch.
5. All tests pass locally.

## Risks

- **Staleness / drift** — my "addressed" record can diverge from GitHub if a
  thread is reopened upstream. Mitigation: `--reopen`, and `gh-triage-pr` still
  reads GitHub's live resolved status; the local record is an optimization, not
  the source of truth.
- **Two DBs to reason about** (cache vs durable). Mitigation: same workspace
  fingerprint keys both; `workqueue` is the single joined view.
