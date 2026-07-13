---
name: gh-comment-cache
version: 1.0.0
purpose: >-
  Local SQLite cache of GitHub issue and PR review comments with incremental
  sync, frozen-PR optimization, and write-through caching.
description: >-
  Caches GitHub issue comments and PR review comments locally in SQLite,
  treating GitHub as a write-through backing store. Optimized for read-heavy
  analytic workloads where closed PRs become static after a 30-day cooling-off
  period. Supports FTS5 full-text search, @mention indexing, and a
  classification substrate for AI-generated labels.

  Use this skill whenever the user asks to: sync their GitHub comment cache,
  add a repo to the watched set, query cached comments by author or mention,
  search comment text, check cache status, or refresh a frozen PR.

  Also trigger when the user says things like "cache my GitHub comments",
  "sync PR comments", "what did N-Dekker say about const in ITK",
  "search comments for coreguidelines", "show me all mentions of me",
  "add ITK to my comment cache", or "what's in the cache".
triggers:
  - gh-comment-cache
  - /gh-comment-cache
user_invocable: true
cmd: false
argument_hint: "sync | add-repo OWNER/REPO | remove-repo OWNER/REPO | refresh OWNER/REPO#N | status | by-author LOGIN | by-mention LOGIN | search QUERY"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: true
    writes_outside_repo_paths:
      - ~/.cache/agent-skills/gh-comment-cache/
    modifies_working_tree: false
    network_required: true
    git_required: false
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: true
    cache_root: ~/.cache/agent-skills/gh-comment-cache/
    schema_version: 1
    rebuildable: true
  derivation:
    has_ai_derived_layer: true
    derivation_version: 0
dependencies:
  skills: []
  external_tools:
    - gh
  python_packages: []
  scripts:
    - scripts/gh_cache_sync.py
    - scripts/gh_cache_read.py
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# gh-comment-cache — Local SQLite cache for GitHub comments

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
gh-comment-cache — Local SQLite cache for GitHub issue/PR comments

Usage:
  /gh-comment-cache sync                       Sync all watched repos
  /gh-comment-cache add-repo OWNER/REPO        Add repo to watch list
  /gh-comment-cache remove-repo OWNER/REPO     Remove repo from watch list
  /gh-comment-cache refresh OWNER/REPO#123     Unfreeze and re-sync one PR
  /gh-comment-cache status                     Show cache stats
  /gh-comment-cache by-author LOGIN            Comments by author
  /gh-comment-cache by-mention LOGIN           Comments mentioning user
  /gh-comment-cache search QUERY               Full-text search
```

Incrementally syncs GitHub issue comments and PR review comments into a local
SQLite database for fast, offline-capable read queries.

## Invocation

| Argument pattern | Script / action |
|---|---|
| `sync` | `gh_cache_sync.py sync` — freeze sweep + sync all watched repos |
| `sync --repo OWNER/REPO` | `gh_cache_sync.py sync --repo OWNER/REPO` — sync one repo |
| `sync --force` | `gh_cache_sync.py sync --force` — ignore ETag / high-water marks |
| `add-repo OWNER/REPO` | `gh_cache_sync.py add-repo OWNER/REPO` — add to watched set |
| `add-repo OWNER/REPO --backfill-days N` | `gh_cache_sync.py add-repo` with custom history window |
| `remove-repo OWNER/REPO` | `gh_cache_sync.py remove-repo OWNER/REPO` |
| `refresh OWNER/REPO#N` | `gh_cache_sync.py refresh OWNER/REPO#N` — unfreeze one PR |
| `status` | `gh_cache_sync.py status` — show stats, DB path, sync states |
| `by-author LOGIN` | `gh_cache_read.py by-author LOGIN` — comments by author |
| `by-author LOGIN --repo OWNER/REPO` | restrict results to one repo |
| `by-mention LOGIN` | `gh_cache_read.py by-mention LOGIN` — comments mentioning login |
| `by-mention LOGIN --repo OWNER/REPO` | restrict results to one repo |
| `search QUERY` | `gh_cache_read.py search QUERY` — FTS5 full-text search |
| `search QUERY --repo OWNER/REPO` | restrict FTS results to one repo |

## Library usage

The `agent_skills` modules used below are vendored under this skill's `lib/`
directory (add `<skill-dir>/lib` to `sys.path`, as the wrapper scripts do).

```python
from agent_skills.gh_cache import (
    open_gh_cache,
    upsert_watched_repo,
    sync_repo,
    freeze_sweep,
    unfreeze_pr,
    list_comments_by_author,
    list_comments_by_mention,
    list_comments_matching,
    watched_repos,
)

result = open_gh_cache()
conn = result.connection

# Add a repo and sync it
upsert_watched_repo(conn, "ISC", "ITK", source="manual", backfill_days=365)
freeze_sweep(conn)
stats = sync_repo(conn, "ISC", "ITK")
print(stats)

# Query
qr = list_comments_by_mention(conn, "hjmjohnson", repos=[("ISC", "ITK")])
for comment in qr.rows:
    print(comment.body_md[:80])

conn.close()
```

## force_sync behavioral triggers

The following trigger phrases cause the agent to run a sync before answering
the user's question:

- "cache my GitHub comments"
- "sync PR comments"
- "sync comment cache"
- "refresh the cache"
- "update comment cache"
- "pull latest comments"
- "add ITK to my comment cache"
- "add \<OWNER/REPO\> to the cache"

Read-only query phrases do **not** trigger a sync:

- "what did \<login\> say about \<topic\>"
- "search comments for \<term\>"
- "show me all mentions of me"
- "what's in the cache"
- "by-author \<login\>"
- "by-mention \<login\>"

## Cache layout (three-layer schema)

| Layer | Tables | Discardable? |
|---|---|---|
| `raw_*` | `raw_watched_repos`, `raw_pr_index`, `raw_comments`, `raw_sync_state`, `raw_comments_fts` | No |
| `derived_*` | `derived_mentions`, `derived_sync_run_stats` | No |
| `ai_*` | `ai_classifications` | Yes — `agent-skills cache rebuild gh-comment-cache` |

The DB lives at `~/.cache/agent-skills/gh-comment-cache/<workspace-fingerprint>/cache.sqlite`.

## Enhanced by

- **memsearch** — When installed, can recall prior analysis results and
  decisions from previous sessions. Falls back to cache-only queries
  when unavailable.
