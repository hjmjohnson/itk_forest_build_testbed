---
name: gh-triage-pr
version: 1.0.0
purpose: 'Triage one or more GitHub pull requests in a strict priority order: (1) address human reviewer comments first, (2) fix CI failures second, (3) request and address a @greptileai draft review third — only after all draft CI builds are green, (4) finally recommend marking the PR ready for review.'
description: >-
  Triage one or more GitHub pull requests in a strict priority order:
  (1) address human reviewer comments first, (2) fix CI failures second,
  (3) request and address a @greptileai draft review third — only after
  all draft CI builds are green, (4) finally recommend marking the PR
  ready for review. Use this skill whenever the user says: "gh-triage-PR",
  "gh-triage-PR #NNNN", "gh-triage-PR my", "gh-triage-PR all-draft",
  "triage PR", "triage my PRs", "triage all drafts", "clean up my PRs",
  "what's left on PR X", "address reviewer feedback", "finish PR X", or
  "make PR X ready for review". Strongly prefers fixup commits into the
  commit that introduced each concern (via git commit --fixup + git
  rebase --autosquash), replies to individual inline comments so the
  GitHub "Resolved" status is visible, resolves threads via GraphQL when
  a reply is posted, and always re-checks the PR title and body for
  accuracy after the final set of fixups.
triggers:
  - gh-triage-pr
  - /gh-triage-pr
user_invocable: true
cmd: false
argument_hint: "#NNN | owner/repo#NNN | my | all-draft"
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

# gh-triage-PR: Progressive PR Triage Workflow

Triage open pull requests in a deterministic priority order. The goal is
to get a PR from "draft with concerns" to "ready for review, all threads
resolved" with minimum wasted effort — don't ask bots for another round
of review until the humans and CI are happy, and never leave a force-push
without also replying to the threads that motivated it.

## Quick reference (print when invoked without arguments)

If the user invokes `/gh-triage-pr` with no arguments or an ambiguous
request, print this usage hint and ask what they'd like to triage:

```
gh-triage-pr — Progressive PR triage (humans → CI → greptile → ready)

Usage:
  /gh-triage-pr #6040              Triage one PR (current repo)
  /gh-triage-pr 6040               Same (bare number)
  /gh-triage-pr owner/repo#6040    Triage a PR in another repo
  /gh-triage-pr my                 All your open PRs (draft + ready)
  /gh-triage-pr all-draft          All your draft PRs only

Phases (strict order — do not skip):
  1. Human comments    Address reviewer feedback, fixup commits
  2. CI failures       Fix red checks on HEAD
  3. Greptile review   Request @greptileai review, address P1/P2
  4. Metadata + ready  Check title/body, recommend gh pr ready
```

## When to use

| User says | Action |
|-----------|--------|
| `gh-triage-PR #6040` | Triage that one PR |
| `gh-triage-PR 6040` | Same (accept bare number) |
| `gh-triage-PR owner/repo#6040` | Triage in a non-current repo |
| `gh-triage-PR my` | Triage all PRs authored by current user (draft and ready) |
| `gh-triage-PR all-draft` | Triage all **draft** PRs authored by current user |
| "triage my PRs" | Same as `my` |
| "what's left on PR 6040?" | Single-PR triage, report only (no edits) |

## Priority order (strict — do not reorder)

These four phases are deterministic. Do not advance a phase until the
prior phase is fully clean. This is the whole point of the skill —
greptile's review is noisy and context-dependent, so we only ask for it
after humans and CI are settled.

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1  HUMAN COMMENTS     (highest priority)              │
│          All reviewer feedback from real users.             │
│          Blockers: CHANGES_REQUESTED, unresolved threads.   │
├─────────────────────────────────────────────────────────────┤
│ Phase 2  CI FAILURES                                        │
│          Red checks on the current HEAD commit.             │
│          Do not proceed to Phase 3 with any red check.      │
├─────────────────────────────────────────────────────────────┤
│ Phase 3  GREPTILE DRAFT REVIEW                              │
│          Post "@greptileai review this draft before I make  │
│          it official" and wait for its response. Address    │
│          every P1/P2 finding. Iterate until clean.          │
├─────────────────────────────────────────────────────────────┤
│ Phase 4  PR METADATA + READY-FOR-REVIEW RECOMMENDATION      │
│          Re-read PR title + body + final diff. Recommend    │
│          `gh pr ready` if everything is clean. DO NOT run   │
│          `gh pr ready` automatically — always recommend.    │
└─────────────────────────────────────────────────────────────┘
```

## Fix strategy — commit hygiene matters

When addressing a reviewer comment, **strongly prefer fixing the commit
that introduced the concern**. A PR with one logical commit per feature
is far easier to review, bisect, and revert than one with a trailing
garbage heap of "address review feedback" commits.

### When to fixup vs. add a new commit

| Situation | Strategy |
|-----------|----------|
| Reviewer found a bug/typo/style issue in code the PR introduced | **Fixup** into the commit that added that line |
| Reviewer found a bug in code the PR *touched* (via `git blame`) | **Fixup** into the commit that touched it |
| Reviewer asked for a new test / docs / feature unrelated to existing commits | **New commit** (can be prefixed `[review]` or similar) |
| Reviewer requested a rename/refactor that spans multiple commits in the PR | **New commit** (squashing across commits loses bisectability) |

When in doubt, prefer fixup.

### The fixup procedure

```bash
# 1. Identify the commit that introduced the concern
#    If the comment is inline on a specific line:
ORIG_SHA=$(git blame -L "${LINE},${LINE}" -- "${FILE}" | awk '{print $1}')

# 2. Verify that SHA is part of the current PR branch
git branch --contains "${ORIG_SHA}" | grep -q "${PR_BRANCH}" \
  || { echo "WARNING: ${ORIG_SHA} is not in this PR"; exit 1; }

# 3. Make the edit, then stage
git add "${FILE}"

# 4. Create a fixup commit targeting the original
git commit --fixup="${ORIG_SHA}"

# 5. After all fixups for this PR are created, autosquash in one pass
git -c sequence.editor=: rebase -i --autosquash "${MERGE_BASE}"
#   sequence.editor=: makes the rebase non-interactive (accepts the
#   auto-generated todo list without prompting)

# 6. ★ MANDATORY GATE — re-run hooks against the rewritten tree.
#    --no-verify in step 4 only suppresses kw-commit-msg for the
#    transient "fixup!" subject; the post-autosquash tree has NOT
#    been validated by content hooks (clang-format, gersemi, etc.).
#    See ~/.claude/rules/pre-commit-mandatory.md.
pre-commit run --all-files
#    Exit 0 required. If "files were modified by this hook":
#       git add -u
#       git commit --fixup="${ORIG_SHA}" --no-verify
#       git -c sequence.editor=: rebase -i --autosquash "${MERGE_BASE}"
#       pre-commit run --all-files          # loop until exit 0
#    Only the release-5.4 case (no .pre-commit-config.yaml) may skip
#    this gate; verify with: test ! -f .pre-commit-config.yaml.

# 7. Force-push (ONLY if step 6 reported all hooks Passed).
git push --force-with-lease origin "${PR_BRANCH}"
```

**Critical:** always use `--force-with-lease`, never `--force`. It
prevents clobbering upstream commits if someone else pushed to your
branch while you were working.

### Separate force-pushes for rebase vs. content

Never mix a rebase onto the base branch and PR-content changes in one
force-push. GitHub's per-push "compare" link is the reviewer's main
tool for seeing what changed since their last review; a push that both
rebases and edits makes that range diff useless (it drowns the real
changes in upstream churn). Requested verbatim by a reviewer on ITK
PR #6614: *"when force-pushing, can you keep plain rebase on main as a
separate force-push? That makes it easy to just look at the
PR-specific changes. When a rebase is mixed in, catching those
PR-changes is harder."*

The ordering when both are needed:

```bash
# Push 1 — rebase only (reviewers skip this one)
git fetch upstream "$BASE_REF"
git rebase "upstream/${BASE_REF}"
git push --force-with-lease origin "${PR_BRANCH}"

# Push 2 — content only, on the already-rebased branch
#   (fixup commits + autosquash + pre-commit gate per the procedure above)
git push --force-with-lease origin "${PR_BRANCH}"
```

If content fixups are already committed locally when a rebase becomes
necessary, still split: complete the autosquash on the OLD base, push
(content-only), then rebase and push again (rebase-only). Either order
is fine — one concern per force-push is the invariant. When both
pushes land close together, leave a one-line PR comment naming which
push is which, e.g. *"first force-push = plain rebase on main; second =
review fixes only."*

**Verify before pushing content:** GitHub's per-push compare
(`compare/<old-head>..<new-head>`) shows only the patch's changes iff
the merge base did not move. Gate the content push on:

```bash
[ "$(git merge-base "origin/${PR_BRANCH}" "upstream/${BASE_REF}")" = \
  "$(git merge-base HEAD "upstream/${BASE_REF}")" ] \
  || echo "STOP: base moved — this push would mix rebase into the compare"
```

**Repairing an already-mixed push:** when a force-push has already
combined a rebase with content changes (or a reviewer is staring at a
noisy compare link), post the patch-only delta as a `git range-diff`
in a PR comment — it pairs old and new commits and shows only how each
patch itself changed (`=` means identical):

```bash
OLD=<previous-head-sha>; NEW=<current-head-sha>; N=<PR commit count>
git range-diff "${OLD}~${N}..${OLD}" "${NEW}~${N}..${NEW}"
# post inside a ```diff fence via gh pr comment --body-file
```

Example: ITK PR #6614's mixed push `deddbb8..f25689d` range-diffs to
one include swap in commit 1 and `=` for commit 2 — the entire review
burden of that force-push, recovered after the fact.

**Critical:** never push without step 6 passing. The PR #6154 push
that landed a clang-format failure (HEAD `2e30d89c`, 2026-04-28) is
the canonical violation — the perl rename of `randgen` →
`randomNumberEngine` widened multiple function signatures past 120
columns, which clang-format silently re-wraps. Without step 6, the
push tip drifts from style and CI's pre-commit job fails. The user
has flagged this as *completely unacceptable*; treat the gate as
non-negotiable.

### Replying to comments and resolving threads

After the fixup is pushed, reply to each inline comment **in-thread**
(not as a top-level PR comment). This makes the GitHub UI show the
thread as having a reply and allows you to resolve it, which visually
declutters the PR review page.

The reply body should reference the fix commit and briefly explain what
was done. Example reply bodies:

- `Fixed in 5b418a8 — renamed section to \`### 12a.\` and corrected the mislabeled \`14a/14b/14c\` siblings.`
- `Addressed in the amended commit — added the missing \`typename\` keyword.`
- `Intentional — see commit message; the \`const\` here prevents accidental mutation in the lambda capture.` *(for push-back responses when the reviewer was wrong)*

After replying, resolve the thread via GraphQL (REST has no resolve
endpoint). See `scripts/ghtp_reply.py` which handles both in one call.

### Format of PR bodies, comments, and greptile-review summaries

**All text posted to GitHub must follow `~/.claude/rules/pr-message-format.md`.**
Inline review replies via `ghtp_reply.py` are usually one-liners and don't
need the full template, but PR bodies (`gh pr create --body` /
`gh pr edit --body`), top-level PR comments (`gh pr comment --body`), and
status summaries (e.g., the WIP-blocker comment posted at the end of Phase 4)
must lead with a 1-3 line visible summary and sequester all longer analysis,
status tables, root-cause walkthroughs, and merge-order discussion inside
collapsed `<details>` blocks. Provenance, file/SHA references for future
Claude sessions, and structured task metadata go inside HTML comments
(`<!-- ... -->`), which are stripped from rendered Markdown but survive
`gh pr view --json body`.

The minimum template:

```markdown
1-3 line summary — what changed + why. Inline links to related PRs/issues.

<details>
<summary>Root cause</summary>

[Long-form analysis here, hidden by default.]

</details>

<details>
<summary>Status table / merge order</summary>

[Tables and AI-generated walk-throughs here.]

</details>

<!--
provenance: claude-code session YYYY-MM-DD
key_facts: <structured data for future Claude sessions>
related_files: <paths and line numbers>
post_merge_action: <what the user should do next>
-->
```

The visible portion above the first `<details>` should be readable in
under 10 seconds. Anything that requires the reviewer to act on (a
"this PR is blocked on #X" call-out, a `WIP:` rationale) stays visible;
anything that's only context for those who want the deep dive gets
collapsed.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/ghtp_list_targets.sh` | Parse `$ARG` into a list of `owner/repo#num` targets |
| `scripts/ghtp_fetch.py` | Fetch all PR state (comments, reviews, CI, metadata) and classify |
| `scripts/ghtp_reply.py` | Post an inline reply to a comment and resolve the thread via GraphQL |

All scripts require the `gh` CLI (authenticated) and Python 3.

## Procedure (run for each target PR)

### Step 0 — Resolve targets

```bash
# Accept: #NNNN, NNNN, owner/repo#NNNN, my, all-draft
bash scripts/ghtp_list_targets.sh "$ARG"
# Outputs one "owner/repo NUM" per line
```

### Step 0.5 — Rebase onto upstream/main (MANDATORY)

Before any triage work, verify the PR branch is current with the
upstream target branch. Stale branches accumulate unrelated commits
in the PR diff, confuse CI, and make review impossible.

```bash
# Determine the upstream remote (the PR's base repo, not the fork)
UPSTREAM=$(gh pr view "$NUM" --repo "$OWNER/$REPO" \
  --json baseRepository --jq '.baseRepository.owner.login + "/" + .baseRepository.name')
BASE_REF=$(gh pr view "$NUM" --repo "$OWNER/$REPO" --json baseRefName --jq .baseRefName)

# Fetch upstream target branch
git fetch upstream "$BASE_REF"

# Check how far behind
BEHIND=$(git rev-list --count "HEAD..upstream/${BASE_REF}")
if [ "$BEHIND" -gt 0 ]; then
  echo "Branch is $BEHIND commits behind upstream/${BASE_REF} — rebasing..."
  git rebase "upstream/${BASE_REF}"
  git push --force-with-lease origin "$PR_BRANCH"
  echo "Rebase complete. CI will re-run on the new HEAD."
fi

# Also verify the commit count is sane — if the PR has more commits
# than expected, the branch likely contains already-merged work
EXPECTED_UNIQUE=$(git rev-list --count "upstream/${BASE_REF}..HEAD")
echo "Commits unique to this PR: $EXPECTED_UNIQUE"
```

**Why this matters:** When a fork's `main` is behind upstream `main`,
branches created from the fork's stale `main` carry all the commits
that upstream has already merged. The PR diff shows dozens of unrelated
changes. Rebasing onto `upstream/main` drops the already-merged commits
(they produce empty diffs during rebase) and leaves only the PR's
actual work.

**Always target `upstream/main`** (the canonical repo), not
`origin/main` (the fork). The fork's `main` may itself be behind.

**Push the pure rebase by itself, before any content changes.** The
Step 0.5 force-push must contain ONLY the rebase onto the new base —
no fixups, no edits. Reviewers can then dismiss that push at a glance
(GitHub shows it as "force-pushed" with an empty/mechanical range
diff) and read the later content-only force-push in isolation. See
"Separate force-pushes for rebase vs. content" below.

### Step 1 — Fetch and classify

```bash
python3 scripts/ghtp_fetch.py --owner "$OWNER" --repo "$REPO" --num "$NUM"
```

This prints a JSON report with three buckets:
- `human_comments` — real-user comments, grouped by thread; each has
  `is_resolved`, `commit_line_blame` (if inline), and a `priority` hint
- `ci_failures` — non-success checks on the HEAD commit
- `greptile_findings` — greptile review findings (parsed from its
  markdown body), tagged P1/P2/P3 where greptile has indicated

Also fetches the PR title, body, draft/ready state, and commit list.

### Step 2 — Phase 1: address human comments

For each unresolved human thread:

1. Read the comment body and the file+line it refers to.
2. Run `git blame` on that line to find the introducing SHA.
3. If the SHA is part of the PR branch, plan a fixup into that commit.
   If not (comment is on pre-existing code), plan a new commit.
4. Make the edit.
5. `git commit --fixup=<sha>` (or normal `git commit` for new-concern).
6. Reply to the thread via `ghtp_reply.py --resolve`.

**Do not rebase or force-push after each individual fix.** Collect all
the fixups first, then do one autosquash rebase + force-push at the end
of Phase 1. This keeps the force-push count low and avoids CI thrash.

### Step 3 — Phase 2: fix CI failures (with retry loop)

After Phase 1's force-push, wait for CI to re-run, then:

1. Fetch the latest check runs on the new HEAD.
2. For each failing check, read the log and identify the root cause.
3. Classify the failure:
   - **Real failure** (compile error, test failure) → fix using the same
     fixup pattern as Phase 1, force-push.
   - **Known flake** → trigger rerun without code changes.
4. Force-push once at the end of Phase 2 (if code fixes were needed).

Use `gh run view <run-id> --log-failed` to pull just the failing lines.

**CI retry loop (maximum 3 attempts):**

After each force-push or rerun trigger, poll CI status. Use the
ralph-loop skill (`/loop 5m`) to check every 5 minutes, or poll
manually:

```bash
gh pr checks "$NUM" --repo "$OWNER/$REPO"
```

For each retry iteration:
1. If all checks green → Phase 2 complete, advance to Phase 3.
2. If failure is a known flake → `gh run rerun <run-id> --failed`
   and increment retry counter.
3. If failure is a real code issue → fix, force-push, reset retry counter.
4. If retry counter reaches 3 with the same flake → stop and report
   to the user. The failure may be a genuine infrastructure issue.

**Known ITK CI flakes** (safe to retry):
- **Any Azure DevOps pipeline** exit code 255 with 0 failures on CDash →
  dashboard script `ci_completed_successfully` in `itk_common.cmake:628`
  treats any compiler warning as a fatal error. Affected pipelines:
  `ITK.Linux`, `ITK.Linux.Python`, `ITK.macOS`, `ITK.macOS.Python`,
  `ITK.Windows`, `ITK.Windows.Python`. All are safe to retry.
- `ARMBUILD-*` exit code 255 with "100% tests passed, 0 tests failed" →
  same dashboard script cause (ExternalData warnings counted)
- `CDash` check shows "fail" but hasn't indexed results yet → stale
  status; wait or re-check later
- `pre-commit` pyupgrade crash on Python 3.14 → fixed by PR #6046;
  if still seen, the fix hasn't merged yet
- `Pixi-Cxx` download timeout (92 bytes received for InsightData tarball) →
  transient GitHub release download failure

**How to verify a flake vs real failure:**
```bash
# Check CDash for actual test results (bypasses dashboard script noise)
curl -s "https://open.cdash.org/api/v1/index.php?project=Insight&filtercount=1&showfilters=1&field1=revision&compare1=61&value1=<COMMIT_SHA>" | \
  python3 -c "import json,sys; [print(f'{b[\"buildname\"]}: err={b[\"compilation\"][\"error\"]} fail={b[\"test\"][\"fail\"]} pass={b[\"test\"][\"pass\"]}') for bg in json.load(sys.stdin).get('buildgroups',[]) for b in bg.get('builds',[])]"
```
If CDash shows 0 compile errors and 0 test failures but the GitHub check
is red, it's a flake.

**Rerunning CI — by platform:**

| Platform | Rerun method |
|----------|-------------|
| **GitHub Actions** (ARMBUILD, Pixi, pre-commit, spell, lint) | `gh run rerun <run-id> --failed` |
| **Azure DevOps** (ITK.Linux, ITK.Windows, ITK.macOS, + Python variants) | Post `/azp run <pipeline-name>` as a PR comment |

**Azure DevOps `/azp` commands:**
```bash
# Rerun a specific Azure pipeline via PR comment:
gh pr comment "$NUM" --repo "$OWNER/$REPO" --body "/azp run ITK.Linux"
gh pr comment "$NUM" --repo "$OWNER/$REPO" --body "/azp run ITK.macOS.Python"
gh pr comment "$NUM" --repo "$OWNER/$REPO" --body "/azp run ITK.Windows"

# Rerun all Azure pipelines:
gh pr comment "$NUM" --repo "$OWNER/$REPO" --body "/azp run"
```

The `/azp` bot is configured on InsightSoftwareConsortium/ITK and
responds to PR comments. Pipeline names must match exactly (case-
sensitive). Common pipeline names:
- `ITK.Linux`, `ITK.Linux.Python`
- `ITK.macOS`, `ITK.macOS.Python`
- `ITK.Windows`, `ITK.Windows.Python`
- `ITK.Batch`

**When to comment on flakes:** If a flake blocks Phase 2 advancement,
post a brief PR comment explaining the failure is a known flake before
re-triggering. This prevents reviewers from thinking the PR has real
issues.

### Step 4 — Phase 3: greptile draft review

Only after Phase 1 and Phase 2 are fully clean.

**Pre-check: Greptile availability**

Before requesting a review, verify Greptile is reachable:

```bash
# Check if GREPTILE_API_KEY is set
if [ "$GREPTILE_API_KEY" = "SKIP" ]; then
    echo "Greptile review skipped (GREPTILE_API_KEY=SKIP)"
    # Advance directly to Phase 4
fi

if [ -z "$GREPTILE_API_KEY" ]; then
    echo "⚠ GREPTILE_API_KEY not set. Cannot run local review."
    echo ""
    echo "To configure:"
    echo "  1. Sign up at https://greptile.com"
    echo "  2. Get API key from https://app.greptile.com/settings/api"
    echo "  3. Add to ~/.zshrc: export GREPTILE_API_KEY=\"your-key\""
    echo "  4. Restart Claude Code"
    echo ""
    echo "To permanently skip: export GREPTILE_API_KEY=\"SKIP\""
    echo ""
    echo "Falling back to GitHub @greptileai bot comment..."
fi
```

**If `GREPTILE_API_KEY=SKIP`:** Skip Phase 3 entirely. Advance to Phase 4.

**If `GREPTILE_API_KEY` is set and MCP tools available:** Use the
`trigger_code_review` MCP tool for a local review before posting to GitHub.
This is faster and doesn't create noise on the PR.

**If MCP tools are not available:** Fall back to the GitHub bot approach:

1. Post the review-request comment:
   ```bash
   gh pr comment "$NUM" --repo "$OWNER/$REPO" \
     --body "@greptileai review this draft before I make it official"
   ```
2. Wait for greptile to respond (typically 1-3 minutes). Poll via
   `ghtp_fetch.py` until the response arrives.

**Handling findings (both local and GitHub approaches):**

3. Address each P1/P2 finding using the same fixup pattern.
4. Reply to each greptile inline comment in-thread (greptile threads
   can be resolved the same way as human threads).
5. **ITK style conformance is always in scope** — fix naming, include
   order, assertion quality, `using` vs `typedef`, etc. regardless of
   Greptile priority level.
6. **Non-trivial or out-of-scope suggestions** (algorithm restructuring,
   new features, API redesign) → present to user for manual decision:
   ```
   Greptile suggests (P2): "<suggestion>"
   This appears out of scope for this PR. Options:
     1. Skip (recommended)
     2. Address as follow-up PR
     3. Implement now
   ```
7. If greptile flags a false positive, reply with a brief justification
   — do not force a fix just to silence it.
8. Iterate: force-push, request another greptile review, address new
   findings, until greptile reports clean or only has P3/nitpicks you
   choose to accept.

### Step 5 — Phase 4: PR metadata and ready-for-review

1. Re-read the PR title. Does it still accurately describe the final
   diff after all the fixups? If not, update via
   `gh pr edit "$NUM" --title "..."`.
2. Re-read the PR body. Same check. Update if needed. **Any rewrite
   must follow the format in `~/.claude/rules/pr-message-format.md`
   and the "Format of PR bodies, comments, and greptile-review
   summaries" section above** — short visible summary, long-form
   analysis inside `<details>`, machine-readable provenance inside
   HTML comments. If the existing body is a pre-format wall of text,
   take the opportunity to retroactively reformat it.
3. Verify all threads are resolved (`ghtp_fetch.py` will show any
   stragglers).
4. Verify CI is green on the current HEAD.
5. **Recommend** marking ready for review:
   ```
   All phases clean. Recommend:
     gh pr ready $NUM --repo $OWNER/$REPO
   Run this when you're ready. Not run automatically.
   ```
   Do **not** run `gh pr ready` yourself. The user wants the final
   promotion to be a manual act.

## Batch mode (`my` / `all-draft`)

When the argument is `my` or `all-draft`, iterate over the target list
and run the full procedure for each. Between PRs:

- Print a short divider with the PR number and title
- Keep a running summary of what was done per PR
- At the end, print a final table:

  ```
  PR    | Phase reached        | Result
  ------|----------------------|------------------------------
  #6040 | Phase 4 (metadata)   | Ready-for-review recommended
  #6027 | Phase 1 (human)      | 2 threads still need a human reply
  #6035 | Phase 2 (CI)         | macOS build failing, needs fix
  ```

Batch mode should **not** auto-advance past any phase with unresolved
blockers — per-PR, stop where the blocker is, summarize, and move on
to the next PR. Return to blocked PRs only after finishing the easy
ones.

## Pre-flight checks before any edits

Before making any commit in the PR branch:

1. **Confirm you're on the right branch**:
   `git branch --show-current` should match the PR's `headRefName`.
2. **Confirm working tree is clean**:
   `git status --porcelain` should be empty.
3. **Confirm branch is up to date with remote**:
   `git fetch origin $PR_BRANCH && git status -sb`. If behind, rebase
   first.
4. **Verify pre-commit hooks are functional** (MANDATORY):
   ```bash
   pre-commit run --files .pre-commit-config.yaml
   ```
   This only checks the hooks themselves load. The **separate gate that
   validates the actual tree** runs after autosquash and before push —
   see step 6 in the fixup procedure above and
   `~/.claude/rules/pre-commit-mandatory.md`. Do not conflate the two.

   If this fails, **stop and diagnose** — do not bypass hooks:
   - Missing hooks → `./Utilities/SetupForDevelopment.sh`
   - `ModuleNotFoundError: No module named '_opcode'` →
     `rm -rf .pixi/envs/pre-commit && pixi install -e pre-commit`
   - `core.hooksPath` mismatch →
     `git config --unset-all core.hooksPath && bash Utilities/GitSetup/setup-precommit`
   - KWStyle crash (missing libc++) →
     `git config hooks.KWStyle false` (KWStyle is checked in CI)
   - pyupgrade crash on Python 3.14 →
     `pre-commit clean` (stale cache; see PR #6046)

   **Never use `--no-verify` or `-c core.hooksPath=/dev/null`** except
   for the one known exception:

   **Exception: `fixup!` commits with kw-commit-msg hook.**
   ITK's kw-commit-msg hook rejects commit messages that don't start
   with a standard prefix (BUG:/COMP:/DOC:/ENH:/PERF:/STYLE:). The
   `fixup!` prefix used by `git commit --fixup=<sha>` is inherently
   temporary — it will be squashed away by `git rebase --autosquash`.
   Use `--no-verify` **only** for the fixup commit itself:
   ```bash
   git commit --fixup=<sha> --no-verify
   ```
   The final rebased commit retains its original valid prefix and will
   pass the hook normally.

   For all other hook failures, require human intervention to fix the
   dev environment.

5. **Check Greptile API availability** (for Phase 3):
   - If `$GREPTILE_API_KEY` is set and not `SKIP` → Greptile available
   - If `$GREPTILE_API_KEY` is `SKIP` → Phase 3 will be skipped
   - If unset → warn user with setup instructions (see Phase 3 details)

## Bot classification

Treat these bots as non-blocking (skip unless explicitly asked):

- `greptile-apps[bot]` — handled explicitly in Phase 3
- `github-actions[bot]` — CI status, surfaced in Phase 2
- `codecov[bot]` — coverage comments, informational only
- `dependabot[bot]`, `renovate[bot]` — usually not on your PRs
- `cla-bot[bot]`, `stale[bot]` — process bots, ignore

Everything else with `user.type == "User"` is a human and belongs in
Phase 1.

## Quality checks after triage

Before reporting success on a PR:

- [ ] All human threads marked resolved on GitHub
- [ ] CI is green on the HEAD commit
- [ ] Greptile review posted and all P1/P2 findings addressed
- [ ] PR title still accurate
- [ ] PR body still accurate
- [ ] Commit history is clean (no `fixup!` commits remain — autosquash ran)
- [ ] No `--force` pushes (only `--force-with-lease`)
- [ ] **`pre-commit run --all-files` exited 0 against the pushed HEAD** (or branch is `release-5.4` with no `.pre-commit-config.yaml`). See `~/.claude/rules/pre-commit-mandatory.md`.

## Discourse search for context

When investigating CI failures or reviewer comments in ITK PRs, also
search the ITK Discourse forum for prior discussion and context.
See the `itk-discourse-search` rule for search patterns and endpoints.

```bash
# Quick search for a topic related to the current PR's concern
curl -s "https://discourse.itk.org/search.json?q=QUERY" | \
  python3 -c "import json,sys; [print(f'  [{t[\"id\"]}] {t[\"title\"]}') for t in json.load(sys.stdin).get('topics',[])]"
```

If Discourse has a relevant thread, link it in the PR comment or
thread reply for cross-reference.

## Enhanced by

- **pr-review-toolkit** — When installed, can dispatch specialized review
  agents (code-reviewer, silent-failure-hunter, type-design-analyzer)
  for deeper analysis. Falls back to inline review when unavailable.
