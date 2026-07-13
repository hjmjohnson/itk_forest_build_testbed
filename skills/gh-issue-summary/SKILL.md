---
name: gh-issue-summary
version: 1.0.0
purpose: Generates a comprehensive SummaryReport.md of all open GitHub PRs and Issues authored by the current user, covering the last month of activity.
description: >-
  Generates a comprehensive SummaryReport.md of all open GitHub PRs and Issues authored by the
  current user, covering the last month of activity. Fetches comment threads to identify
  outstanding reviewer requests, unanswered pings, design decisions, and merge dependencies.
  Writes a local SummaryReport.md with prioritized action items and recommendations, and saves
  detailed notes for complex issues into an issues/ subdirectory.

  Use this skill whenever the user asks to: summarize their open PRs or issues, create a monthly
  GitHub activity report, identify what needs attention across their repositories, find outstanding
  reviewer comments, review their GitHub backlog, or generate a status report of in-flight work.
  Also trigger when the user says things like "what do I need to do on GitHub", "catch me up on
  my PRs", "what comments are waiting for me", or "make a report of my open work".
triggers:
  - gh-issue-summary
  - /gh-issue-summary
user_invocable: true
cmd: false
argument_hint: "[--repo OWNER/REPO] [--days N]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
    network_required: true
    git_required: false
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
  external_tools: []
  python_packages: []
  scripts: []
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# GitHub PR & Issue Summary Skill

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
gh-issue-summary — Summarize all your open GitHub PRs and Issues

Usage:
  /gh-issue-summary                        All open PRs/issues (last 30 days)
  /gh-issue-summary --repo InsightSoftwareConsortium/ITK   One repo only
  /gh-issue-summary --days 7               Last 7 days of activity
```

Generate a `SummaryReport.md` (and supporting `issues/` notes) that surfaces every open PR and
Issue the current user owns, extracts outstanding actions from comment threads, and recommends
concrete next steps.

---

## Step 1: Authenticate and identify the user

```bash
gh api user --jq '.login'
```

Store the login as `$GHUSER`. All searches use `--author $GHUSER`.

---

## Step 2: Gather all open PRs and Issues

Run both searches in parallel. Use `@me` for portability (works even if login differs):

```bash
# Open PRs
gh search prs --author @me --state open --limit 100 \
  --json number,title,repository,url,createdAt,updatedAt,isDraft,commentsCount

# Open Issues (excludes PRs)
gh search issues --author @me --state open --limit 100 \
  --json number,title,repository,url,createdAt,updatedAt,commentsCount
```

**Available JSON fields for `gh search prs/issues`** (note: fewer fields than `gh pr list`):
- `number`, `title`, `repository` (contains `name`, `nameWithOwner`), `url`
- `createdAt`, `updatedAt`, `isDraft` (PRs only), `commentsCount`
- NOT available: `reviewDecision`, `reviews`, `body` — fetch those per-item in Step 3

---

## Step 3: Fetch comment threads and PR metadata

For any PR or Issue where `commentsCount > 0`, fetch the full comment thread **and** (for PRs)
the head commit timestamp. Run fetches in parallel where possible:

```bash
# PR: comments + review status + head push time + inline review threads
gh pr view NUMBER --repo OWNER/REPO \
  --json number,title,body,comments,reviews,headRefName,updatedAt \
  --jq '{number,title,headRefName,comments:.comments,reviews:.reviews}'

# PR head commit pushed time (tells you when code last changed)
gh api repos/OWNER/REPO/pulls/NUMBER \
  --jq '{pushedAt: .head.repo.pushed_at, headSha: .head.sha, headRef: .head.ref}'

# Inline review thread comments (separate from issue comments)
gh api repos/OWNER/REPO/pulls/NUMBER/comments \
  --jq '[.[] | {id,user:.user.login,body,path,position,created_at}]'

# Issue comments
gh issue view NUMBER --repo OWNER/REPO \
  --json number,title,body,comments \
  --jq '{number,title,comments:.comments}'
```

**Prioritize items updated within the last 30 days.** For older items with comments, fetch
selectively — focus on those where the last comment is not from you (i.e., someone is waiting
on a response).

### Step 3a: Detect @mentions

Check GitHub notifications for items where you were directly mentioned:

```bash
gh api notifications --jq '[.[] | select(.reason == "mention") |
  {repo: .repository.full_name, subject: .subject.title,
   url: .subject.url, updatedAt: .updated_at}]'
```

Surface any `@mention` items at the **top** of Outstanding Actions in the report, above all
other items. A direct mention requires a response even if the PR/issue isn't otherwise active.

---

## Step 4: Identify outstanding actions

### Step 4a: Temporal cross-check — avoid false positives

Before classifying any comment as "outstanding", compare the comment's `created_at` timestamp
against the PR's `pushedAt` (the most recent push to the head branch):

```
comment.created_at  <  PR.pushedAt  →  comment PREDATES the latest push
                                        → the requested change may already be in the branch
                                        → VERIFY before flagging as outstanding
```

For any reviewer comment that predates the latest push:

1. **Identify what was asked** — extract the specific symbol, function, or file mentioned.
2. **Check the branch** — search the actual PR branch for the mentioned code:
   ```bash
   gh api repos/OWNER/REPO/contents/PATH/TO/FILE?ref=HEAD_SHA \
     --jq '.content' | base64 -d | grep -n "symbol_or_function_name"
   ```
   Empty result = the change was made. Non-empty = still present, truly outstanding.
3. **For inline review threads** — `position != null` means the commented line is still in the
   diff context, but does NOT mean the code is still there. Always verify via file content.
4. **Classify accordingly**:
   - Change already made → mark as **"Addressed — thread not resolved"** and suggest the user
     click "Resolve conversation" in the GitHub UI, or leave a brief reply confirming the fix.
   - Change not yet made → mark as **Code change required** as normal.

### Step 4b: Classify outstanding actions

For each comment thread, classify what action (if any) is needed:

| Signal | Classification |
|--------|----------------|
| Direct `@mention` of you | **@mention — response required** (top priority) |
| Reviewer asks you to change code / remove commits | **Code change required** |
| Reviewer asks a question you haven't answered | **Response needed** |
| Comment predates latest push AND code is already fixed | **Addressed — resolve thread** |
| You pinged someone who hasn't replied | **Awaiting response** |
| Design/architecture decision raised without resolution | **Decision needed** |
| PR depends on another PR merging first | **Blocked / dependency** |
| PR is DRAFT with no blocker | **Promote to ready** |
| No comments, no activity in >30 days | **Needs follow-up** |

Also note **merge order dependencies** if a PR's body or comments mention "depends on #NNN".

### Step 4c: Suggest resolution text for addressed-but-open threads

For every thread classified as **"Addressed — resolve thread"**, generate a ready-to-post
reply the user can copy-paste to close the loop:

> "Done — removed in <commit SHA short> / addressed in the latest push (<date>).
>  Marking this resolved."

Include the suggestion in the `SummaryReport.md` Outstanding Actions section under the item.

---

## Step 5: Write SummaryReport.md

Write to `SummaryReport.md` in the **current working directory**. Use this structure:

```markdown
# GitHub Activity Summary — <username>
**Period:** Last month (<date range>)
**Generated:** <today's date>
**Scope:** All open PRs and Issues authored by <username>

---

## @Mentions Requiring Response
[Items where you were directly @mentioned — always shown first, even if otherwise low priority]

For each mention:
- **Where:** repo/PR or issue link
- **Who mentioned you:** @username
- **What they said** (quote)
- **Suggested reply** or action

---

## Outstanding Actions — High Priority
[Items with specific reviewer requests or blocking issues, each as its own ### section]

For each item:
- **What was asked** (quote the reviewer comment briefly)
- **Recommendation** with concrete next step

---

## Already Addressed — Threads to Close
[Comments that predate the latest push AND whose requested change is verified gone from the branch]

For each item:
- **Thread:** repo/PR#NNN — reviewer name — original request (brief quote)
- **Evidence:** file/function not found on branch `<headRef>` as of `<pushedAt>`
- **Suggested reply to post:**
  > "Done — addressed in the <date> push. Marking resolved."

---

## Open PRs — Recent (<current month>/<prior month>)
[Table: PR link | title | repo | status | comment count]
[Merge order dependencies as a numbered list if present]

---

## Open PRs — Older / Long-running
[Table: repo | PR | title | age | recommendation]

---

## Open Issues — Active
[Table: repo | issue | title | created | status]

---

## Open Issues — Long-standing / Backlog
[Table: repo | issue | title | age | recommendation]

---

## Recommendations
### Immediate (this week)
### Short-term (this month)
### Medium-term (next quarter)
```

---

## Step 6: Capture detailed notes for complex issues

For any issue or PR where:
- The comment thread is long (>3 substantive comments), OR
- A non-trivial patch or design alternative was discussed, OR
- Multiple PRs are cross-referenced

…write a dedicated file to `issues/<REPO>-<NUMBER>-<slug>.md` containing:
- Full problem description
- History of attempts/PRs
- Each reviewer's concern and your response
- The patch or alternative if one exists
- A recommended path forward with checkboxes

Update `SummaryReport.md` to link to these files from the relevant sections.

---

## Handling large result sets

If there are >20 PRs or >30 issues, batch the comment fetches into groups of 5–10 to avoid
hitting rate limits. The `gh` CLI uses your token's rate limit; a short pause is rarely needed
but if you see 403 errors, add `sleep 1` between batches.

---

## Tips for good recommendations

- **Be specific**: "Rebase and remove the first two commits" beats "update the PR".
- **Use merge order**: if PR A depends on B, say so and list them in order.
- **Close stale items**: PRs >2 years old with no activity should be flagged for closing unless
  there's a clear reason to keep them.
- **Note abandoned upstreams**: if the original maintainer hasn't responded in >6 months and
  community is asking for a fork, recommend forking.
- **Surface bot reviews**: Greptile, Codecov, and similar bots often leave actionable P2/P3
  findings — mention them but distinguish from human reviewer requests.

## Discourse cross-reference

For ITK and related NAMIC projects, also search the Discourse forum
when building the summary report. Community discussion often provides
context that GitHub issues lack — design rationale, user-reported
workarounds, and release feedback.

```bash
# Search Discourse for topics related to open issues
curl -s "https://discourse.itk.org/search.json?q=QUERY+after:2025-01-01" | \
  python3 -c "import json,sys; [print(f'  [{t[\"id\"]}] {t[\"title\"]}') for t in json.load(sys.stdin).get('topics',[])]"
```

When a Discourse thread is relevant to a GitHub issue or PR, note it
in the summary with a direct link. See the `itk-discourse-search`
rule for full API details and search operators.

## Enhanced by

- **memsearch** — When installed, can recall prior analysis results and
  decisions from previous sessions. Falls back to cache-only queries
  when unavailable.
