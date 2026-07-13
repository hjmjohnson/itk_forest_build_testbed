---
name: gh-issue-audit
version: 1.0.0
purpose: >-
  Audit all open issues in a GitHub repository to find ones that are already
  completed (merged fix, maintainer confirmed) or actively in-flight (open PR),
  and report them without modifying anything unless the user explicitly requests closures.
description: >-
  Use when the user wants to find open GitHub issues that are already resolved or
  have active work in progress. Triggers on: "audit open issues", "find completed
  issues", "which issues are already fixed", "find stale issues that are done",
  "cross-reference issues with PRs", "find issues with merged fixes", or any
  request to identify closed-but-still-open issues in a repo.
triggers:
  - gh-issue-audit
  - /gh-issue-audit
user_invocable: true
cmd: false
argument_hint: "OWNER/REPO [--close-confirmed]"
contract:
  inputs:
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: true
    writes_outside_repo_paths:
      - /tmp/gh_issue_audit_<repo>.json
    modifies_working_tree: false
    network_required: true
    git_required: false
    user_confirmation_required: true
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: true
    derivation_version: 1
dependencies:
  skills: []
  external_tools:
    - gh
    - python3
    - curl
  python_packages: []
  scripts: []
deployment:
  tier: shared
  target_projects: []
  needs_loader_dir: false
  adapters:
    - claude-code
---

# gh-issue-audit

Audit all open issues in a GitHub repository to identify ones already resolved
or actively in-flight, using parallel per-issue investigation.

## Quick Reference

```
/gh-issue-audit OWNER/REPO              # Report only (safe, no writes)
/gh-issue-audit OWNER/REPO --close-confirmed  # Report + close high-confidence completed
```

## Step 1 — Resolve the target repo

Parse the argument. Accept:
- `OWNER/REPO` (e.g. `InsightSoftwareConsortium/ITK`)
- A GitHub URL (extract `owner/repo` from it)
- No argument: use `gh repo view --json nameWithOwner --jq .nameWithOwner` in cwd

Store as `$REPO`.

## Step 2 — Pre-fetch all open issues to disk

Fetch once; reuse for all parallel investigations.

```bash
REPO="InsightSoftwareConsortium/ITK"
OUTFILE="/tmp/gh_issue_audit_$(echo $REPO | tr '/' '_').json"

gh issue list --repo "$REPO" --state open --limit 500 \
  --json number,title,body,labels,createdAt,updatedAt,url,assignees \
  > "$OUTFILE"

python3 -c "import json; issues=json.load(open('$OUTFILE')); print(f'{len(issues)} open issues')"
```

If the repo has >500 open issues, paginate:
```bash
gh issue list --repo "$REPO" --state open --limit 500 --json number,title,body,labels,createdAt,updatedAt,url,assignees > "$OUTFILE"
# gh does not support --page; use GraphQL cursor pagination if needed beyond 500
```

## Step 3 — Investigate each issue in parallel (Workflow)

Launch a Workflow that reads `$OUTFILE` and fans out one agent per issue.

### Per-issue agent prompt

For each issue `#N` with title `T`:

```
Investigate $REPO issue #N: "T"
URL: https://github.com/$REPO/issues/N
Body (first 600 chars): ...

Run in sequence:

1. Search for PRs referencing this issue:
   gh pr list --repo $REPO --state all --limit 20 --search "#N" \
     --json number,title,state,mergedAt,url,isDraft

2. Check git log (if local clone exists):
   git -C /path/to/clone log --oneline --since="12 months ago" --all \
     --grep="#N" | head -5

3. Read last 3 comments for resolution signals:
   gh issue view N --repo $REPO --json comments | \
     python3 -c "import json,sys; d=json.load(sys.stdin); \
       [print(c['author']['login']+': '+c['body'][:300]) \
        for c in d.get('comments',[])[-3:]]"

4. Search Discourse (ITK / NAMIC projects only):
   curl -s "https://discourse.itk.org/search.json?q=%23N" | \
     python3 -c "import json,sys; \
       [print(t['title']) for t in json.load(sys.stdin).get('topics',[])[:3]]"

Classify as:
- completed/high:   merged PR with explicit "Closes #N"/"Fixes #N"/"Resolves #N",
                    OR maintainer commented the issue is resolved
- completed/medium: merged PR closely related by topic/timing, no explicit keyword
- in_flight/high:   open (non-merged) PR explicitly referencing #N
- in_flight/medium: recently opened draft PR or branch addressing this by topic
- open:             no evidence of active work — default when uncertain
- unclear:          conflicting signals

Return JSON: {issue_number, status, confidence, evidence, linked_prs, recommendation}
```

### Workflow schema (per issue)

```json
{
  "issue_number": 123,
  "status": "completed|in_flight|open|unclear",
  "confidence": "high|medium|low",
  "evidence": "PR #456 merged 2026-06-12, body contains 'Closes #123'",
  "linked_prs": ["#456"],
  "recommendation": "Close issue — fixed by merged PR #456"
}
```

## Step 4 — Synthesize and report

Group results into four buckets:

| Bucket | Criteria |
|--------|----------|
| **Close immediately** | `completed` + `high` confidence |
| **Verify then close** | `completed` + `medium` confidence |
| **In-flight** | `in_flight` (any confidence) |
| **Still open** | `open` or `unclear` — omit from report |

Print a Markdown report with:

```markdown
# Issue Audit — OWNER/REPO
**Date:** YYYY-MM-DD   **Issues audited:** N

## Close Immediately (High Confidence) — K issues
| # | Title | Evidence | Linked PRs |
|---|-------|----------|------------|
| [#NNN](url) | title | merged PR #M closed it | #M |

## Verify Then Close (Medium Confidence) — K issues
| # | Title | Evidence | Linked PRs |
|---|-------|----------|------------|

## In-Flight (Active Work) — K issues
| # | Title | Evidence | Active PRs |
|---|-------|----------|------------|

## Recommendations
- Add `Closes #NNN` keywords to PR bodies (N issues missed auto-close)
- ...
```

## Step 5 — Optional closure (only with --close-confirmed)

If `--close-confirmed` was passed **and** the user confirms interactively:

```bash
for issue in $HIGH_CONFIDENCE_COMPLETED_ISSUES; do
  gh issue close $issue --repo $REPO \
    --comment "Resolved by merged PR $LINKED_PR. Closing — the PR lacked a 'Closes #$issue' keyword so GitHub did not auto-close."
done
```

**Never close medium-confidence issues without an additional explicit per-issue confirmation.**

Without `--close-confirmed`, print a summary of what *would* be closed and ask:
> "Found N high-confidence completed issues. Run with `--close-confirmed` or confirm to close them now."

## Classification rules

### Completed — high confidence signals
- PR body/title contains `closes #N`, `fixes #N`, `resolves #N` (case-insensitive)
- PR was merged AND issue was opened/updated the same week as the merge
- A maintainer or issue-author commented "fixed in …" or "closing as resolved"
- GitHub `stateReason` is already `COMPLETED` (issue already closed)

### Completed — medium confidence signals
- Merged PR title closely matches issue title, merged within 30 days of issue update
- No explicit close keyword but discussion in PR body clearly addresses the issue

### In-flight signals
- Open (not merged) PR with `#N` in title, body, or `gh pr list --search "#N"` result
- Issue has an `assignee` added within the last 90 days
- Recent comment by a contributor saying "working on this" or "PR coming"

### Ignore / open signals
- PR is closed (not merged) — the fix was abandoned
- PR is >6 months old with no activity — likely stalled
- Only bot comments (Dependabot, Codecov, etc.)

## Discourse cross-reference

For ITK and related NAMIC projects, search Discourse in parallel with the
GitHub investigation. Many design decisions and workarounds live only in
Discourse threads, not in PR bodies.

```bash
curl -s "https://discourse.itk.org/search.json?q=%23ISSUE_NUMBER" | \
  python3 -c "import json,sys; d=json.load(sys.stdin);
  [print(f'  [{t[\"id\"]}] {t[\"title\"]}  https://discourse.itk.org/t/{t[\"slug\"]}/{t[\"id\"]}')
   for t in d.get('topics', [])[:3]]"
```

See the `itk-discourse-search` rule for full API details and operators.

## Scale guidance

| Issue count | Strategy |
|-------------|----------|
| ≤ 50        | One agent per issue, fully parallel |
| 51–300      | Workflow pipeline, ~16 concurrent |
| > 300       | Paginate fetch; run two workflow batches |

The Workflow harness caps at 16 concurrent agents automatically — pass
all issues to `pipeline()` and let the harness manage throughput.

## Common pitfalls

- **Missing `Closes` keyword** — most common reason an issue stays open after
  its fix merges. Report a count in recommendations.
- **PR number ≠ issue number** — `gh pr list --search "#N"` matches both;
  verify the result is a PR (has `mergedAt`) not another issue.
- **Closed PRs (not merged)** — a closed-but-not-merged PR means the fix was
  abandoned. Do not classify as completed.
- **Draft PRs** — classify as `in_flight/medium`, not completed.
- **Issue already closed** — `gh issue list --state open` should exclude these,
  but double-check with `gh issue view N --json state` if unsure.
