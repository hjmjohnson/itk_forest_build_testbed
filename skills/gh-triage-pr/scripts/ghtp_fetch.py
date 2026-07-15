#!/usr/bin/env python3
"""ghtp_fetch.py — Fetch and classify all PR triage state.

Produces a JSON report with three priority buckets so the caller can
process them in the strict order: human > CI > greptile.

Usage:
    python3 ghtp_fetch.py --owner OWNER --repo REPO --num NNNN
    python3 ghtp_fetch.py --owner OWNER --repo REPO --num NNNN --pretty

Requires: gh (authenticated), python3.
"""

import argparse
import json
import re
import subprocess
import sys

# Bot logins that are non-blocking (not surfaced in human_comments)
NON_BLOCKING_BOTS = {
    "greptile-apps[bot]",  # handled in its own bucket
    "github-actions[bot]",  # CI, surfaced via checks
    "codecov[bot]",
    "cla-bot[bot]",
    "stale[bot]",
    "dependabot[bot]",
    "renovate[bot]",
}

GREPTILE_LOGIN = "greptile-apps[bot]"


def gh(args, check=True):
    """Run gh CLI and return stdout (string)."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def gh_json(args):
    return json.loads(gh(args))


def gh_api(path, method="GET", jq=None):
    """Run gh api and return parsed JSON (or raw string if jq was used)."""
    cmd = ["api", "-X", method, path]
    if jq:
        cmd.extend(["--jq", jq])
    out = gh(cmd)
    if jq:
        # jq --jq prints NDJSON or raw values; caller decides what to do
        return out
    return json.loads(out) if out.strip() else None


def fetch_pr_metadata(owner, repo, num):
    """PR-level fields: title, body, draft, headRefName, baseRefName, state."""
    return gh_json(
        [
            "pr",
            "view",
            str(num),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "number,title,body,isDraft,state,headRefName,headRefOid,baseRefName,author",
        ]
    )


def fetch_reviews(owner, repo, num):
    """Top-level reviews (APPROVED / CHANGES_REQUESTED / COMMENTED)."""
    return gh_json(
        [
            "api",
            f"repos/{owner}/{repo}/pulls/{num}/reviews",
        ]
    )


def fetch_inline_comments(owner, repo, num):
    """Inline review comments (tied to specific files/lines)."""
    # Paginate through all comments
    return gh_json(
        [
            "api",
            "--paginate",
            f"repos/{owner}/{repo}/pulls/{num}/comments",
        ]
    )


def fetch_issue_comments(owner, repo, num):
    """Top-level PR comments (the ones posted on the Conversation tab)."""
    return gh_json(
        [
            "api",
            "--paginate",
            f"repos/{owner}/{repo}/issues/{num}/comments",
        ]
    )


def fetch_check_runs(owner, repo, sha):
    """CI check runs on the given SHA."""
    data = gh_json(
        [
            "api",
            f"repos/{owner}/{repo}/commits/{sha}/check-runs",
        ]
    )
    return data.get("check_runs", [])


def fetch_review_threads_graphql(owner, repo, num):
    """Fetch review threads via GraphQL to get isResolved state.

    REST API does not expose thread resolution state — only GraphQL does.
    Returns a dict mapping comment_id -> {is_resolved, thread_id}.
    """
    query = """
    query($owner: String!, $repo: String!, $num: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $num) {
          reviewThreads(first: 100) {
            nodes {
              id
              isResolved
              isOutdated
              comments(first: 50) {
                nodes {
                  databaseId
                  author { login }
                }
              }
            }
          }
        }
      }
    }
    """
    out = gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"num={num}",
        ]
    )
    data = json.loads(out)
    threads = (
        data.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )

    comment_map = {}
    for thread in threads:
        tid = thread["id"]
        is_resolved = thread["isResolved"]
        is_outdated = thread["isOutdated"]
        for comment in thread["comments"]["nodes"]:
            db_id = comment["databaseId"]
            if db_id is not None:
                comment_map[db_id] = {
                    "thread_id": tid,
                    "is_resolved": is_resolved,
                    "is_outdated": is_outdated,
                }
    return comment_map


def is_bot(login):
    return login.endswith("[bot]")


def classify_comment(author_login):
    """Return one of: 'human', 'greptile', 'bot_other'."""
    if author_login == GREPTILE_LOGIN:
        return "greptile"
    if is_bot(author_login):
        return "bot_other"
    return "human"


def parse_greptile_findings(body):
    """Extract structured findings from a greptile comment body.

    Greptile tags findings with P1/P2/P3 badges. This returns a list of
    {priority, title} dicts — the full body is still retained elsewhere.
    """
    findings = []
    # Matches <img alt="P1"> or <img alt="P2"> or <img alt="P3">
    pattern = re.compile(
        r'alt="(P[123])"[^>]*>\s*\*\*([^*]+)\*\*',
        re.IGNORECASE,
    )
    for match in pattern.finditer(body or ""):
        findings.append({"priority": match.group(1), "title": match.group(2).strip()})
    return findings


def mark_addressed(comments, addressed_set):
    """Tag each comment with addressed_locally (True if its id is in the
    locally-recorded addressed set). Returns the same list."""
    for c in comments:
        c["addressed_locally"] = str(c.get("id")) in addressed_set
    return comments


def count_unresolved_inline(comments):
    """Human inline comments that are neither resolved upstream nor addressed locally."""
    return sum(
        1
        for c in comments
        if c.get("kind") == "inline"
        and c.get("thread_state", {}).get("is_resolved") is False
        and not c.get("addressed_locally", False)
    )


def main():
    parser = argparse.ArgumentParser(description="Fetch PR triage state")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--num", required=True, type=int)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    owner, repo, num = args.owner, args.repo, args.num

    # 1. PR metadata
    meta = fetch_pr_metadata(owner, repo, num)
    head_sha = meta["headRefOid"]

    # 2. All comments
    reviews = fetch_reviews(owner, repo, num)
    inline = fetch_inline_comments(owner, repo, num)
    issue_comments = fetch_issue_comments(owner, repo, num)

    # 3. Thread resolution state (GraphQL)
    try:
        thread_state = fetch_review_threads_graphql(owner, repo, num)
    except Exception as e:
        print(f"WARN: could not fetch thread state via GraphQL: {e}", file=sys.stderr)
        thread_state = {}

    # 4. CI check runs
    checks = fetch_check_runs(owner, repo, head_sha)

    # 5. Classify and bucket
    human_comments = []
    greptile_comments = []
    bot_other_comments = []

    def add_inline(c):
        kind = classify_comment(c["user"]["login"])
        entry = {
            "id": c["id"],
            "author": c["user"]["login"],
            "kind": "inline",
            "path": c.get("path"),
            "line": c.get("line") or c.get("original_line"),
            "commit_id": c.get("commit_id"),
            "body": c.get("body", ""),
            "created_at": c.get("created_at"),
            "thread_state": thread_state.get(c["id"], {"is_resolved": None, "thread_id": None}),
        }
        if kind == "human":
            human_comments.append(entry)
        elif kind == "greptile":
            greptile_comments.append(entry)
        else:
            bot_other_comments.append(entry)

    for c in inline:
        add_inline(c)

    def add_top_level(c, source):
        kind = classify_comment(c["user"]["login"])
        entry = {
            "id": c["id"],
            "author": c["user"]["login"],
            "kind": source,
            "path": None,
            "line": None,
            "body": c.get("body", ""),
            "created_at": c.get("created_at"),
            "thread_state": {"is_resolved": None, "thread_id": None},
        }
        if kind == "human":
            human_comments.append(entry)
        elif kind == "greptile":
            # Greptile top-level comments contain its finding list
            entry["findings"] = parse_greptile_findings(c.get("body", ""))
            greptile_comments.append(entry)
        else:
            bot_other_comments.append(entry)

    for c in issue_comments:
        add_top_level(c, "issue_comment")

    for r in reviews:
        if r.get("body"):
            add_top_level(
                {
                    "id": r["id"],
                    "user": r["user"],
                    "body": r["body"],
                    "created_at": r.get("submitted_at"),
                },
                source=f"review_{r.get('state', 'COMMENTED').lower()}",
            )

    # Locally-recorded addressed concerns (best-effort; never break fetch).
    addressed_local = set()
    try:
        import os as _os
        import subprocess as _sp

        _pw = _os.path.expanduser("~/.claude/skills/gh-comment-cache/scripts/pr_workstate.py")
        if _os.path.exists(_pw):
            _r = _sp.run(
                [sys.executable, _pw, "addressed", f"{owner}/{repo}", str(num)],
                capture_output=True, text=True, timeout=15,
            )
            addressed_local = {ln.strip() for ln in _r.stdout.splitlines() if ln.strip()}
    except Exception:
        addressed_local = set()
    mark_addressed(human_comments, addressed_local)

    # 6. CI summary
    ci_failures = [
        {
            "name": c["name"],
            "conclusion": c["conclusion"],
            "status": c["status"],
            "details_url": c.get("details_url"),
            "output_title": (c.get("output") or {}).get("title"),
        }
        for c in checks
        if c.get("conclusion") not in (None, "success", "neutral", "skipped")
    ]
    ci_pending = [c["name"] for c in checks if c.get("status") in ("queued", "in_progress")]
    ci_green = not ci_failures and not ci_pending

    # 7. Unresolved human count (blocks Phase 3)
    unresolved_human_inline = count_unresolved_inline(human_comments)

    # 8. Latest CHANGES_REQUESTED review that hasn't been superseded
    changes_requested = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]

    report = {
        "pr": {
            "owner": owner,
            "repo": repo,
            "number": num,
            "title": meta["title"],
            "body": meta.get("body", ""),
            "is_draft": meta["isDraft"],
            "state": meta["state"],
            "head_sha": head_sha,
            "head_ref": meta["headRefName"],
            "base_ref": meta["baseRefName"],
            "author": meta["author"]["login"],
            "url": f"https://github.com/{owner}/{repo}/pull/{num}",
        },
        "phase_1_human": {
            "total": len(human_comments),
            "unresolved_inline": unresolved_human_inline,
            "changes_requested_reviews": len(changes_requested),
            "comments": human_comments,
        },
        "phase_2_ci": {
            "green": ci_green,
            "failures": ci_failures,
            "pending": ci_pending,
        },
        "phase_3_greptile": {
            "total_comments": len(greptile_comments),
            "comments": greptile_comments,
        },
        "bot_other": {
            "total": len(bot_other_comments),
            "comments": bot_other_comments,
        },
    }

    indent = 2 if args.pretty else None
    print(json.dumps(report, indent=indent, default=str))


if __name__ == "__main__":
    main()
