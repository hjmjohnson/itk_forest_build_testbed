#!/usr/bin/env python3
"""ghtp_fetch.py — Fetch and classify all PR triage state.

Produces a JSON report with three priority buckets so the caller can
process them in the strict order: human > CI > AI review.

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

# AI review providers, keyed by bot login. Their comments carry findings that
# Phase 3 must act on, so they get their own bucket rather than being lumped in
# with infrastructure bots.
#
#   trigger      how a review is requested; "auto" means it reviews on push
#   rereview     comment that forces a fresh review of an already-reviewed head
#   detect_files repo files whose presence indicates the provider is configured
AI_REVIEW_PROVIDERS = {
    "greptile-apps[bot]": {
        "name": "greptile",
        "trigger": "@greptileai review this draft before I make it official",
        "rereview": "@greptileai review",
        "detect_files": [],
    },
    "coderabbitai[bot]": {
        "name": "coderabbit",
        "trigger": "auto",  # reviews automatically on push
        "rereview": "@coderabbitai full review",
        "detect_files": [".coderabbit.yaml", ".coderabbit.yml"],
    },
}

# Infrastructure bots that never carry review findings. Anything ending in
# "[bot]" that is in neither this set nor AI_REVIEW_PROVIDERS lands in
# "bot_unknown" so a new review bot cannot be silently ignored.
NON_BLOCKING_BOTS = {
    "github-actions[bot]",  # CI, surfaced via checks
    "codecov[bot]",
    "cla-bot[bot]",
    "stale[bot]",
    "dependabot[bot]",
    "renovate[bot]",
    "pre-commit-ci[bot]",
    "deepsource-autofix[bot]",
}


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
    """Return one of: 'human', 'ai_review', 'bot_other', 'bot_unknown'.

    An unrecognised bot is 'bot_unknown', not 'bot_other'. The two buckets are
    handled differently by the caller: 'bot_other' is documented as ignorable,
    while 'bot_unknown' means "a bot nobody has classified — look at it". A new
    review bot appearing in a repo must not disappear into the ignore pile.
    """
    if author_login in AI_REVIEW_PROVIDERS:
        return "ai_review"
    if author_login in NON_BLOCKING_BOTS:
        return "bot_other"
    if is_bot(author_login):
        return "bot_unknown"
    return "human"


# Normalised severity. Phase 3 acts on P1/P2 regardless of provider vocabulary.
CODERABBIT_SEVERITY_TO_PRIORITY = {
    "critical": "P1",
    "major": "P2",
    "minor": "P3",
    "trivial": "P3",
}


def parse_greptile_findings(body):
    """Extract findings from a greptile comment body.

    Greptile tags findings with P1/P2/P3 image badges.
    """
    findings = []
    # The badge is an <img> wrapped in an <a>, so the closing </a> sits between
    # the badge and the bold title. Without tolerating it, inline findings —
    # which is most of them — never match.
    pattern = re.compile(
        r'alt="(P[123])"[^>]*>\s*(?:</a>)?\s*\*\*([^*]+)\*\*',
        re.IGNORECASE,
    )
    for match in pattern.finditer(body or ""):
        findings.append(
            {"priority": match.group(1), "severity": match.group(1), "title": match.group(2).strip()}
        )
    return findings


def parse_coderabbit_findings(body):
    """Extract findings from a CodeRabbit comment body.

    CodeRabbit heads each finding with an italic badge row, e.g.

        _📐 Maintainability & Code Quality_ | _🟡 Minor_ | _⚡ Quick win_

        **Add the required Google-style docstring to the new test.**

    The severity word is mapped onto Greptile's P1/P2/P3 so the phase logic
    speaks one vocabulary.
    """
    body = body or ""
    findings = []
    pattern = re.compile(
        r"_[^_\n]*_\s*\|\s*_[^A-Za-z\n]*(Critical|Major|Minor|Trivial)_[^\n]*\n+\*\*([^*]+)\*\*",
        re.IGNORECASE,
    )
    for match in pattern.finditer(body):
        severity = match.group(1).lower()
        findings.append(
            {
                "priority": CODERABBIT_SEVERITY_TO_PRIORITY.get(severity, "P3"),
                "severity": severity,
                "title": match.group(2).strip(),
            }
        )
    return findings


def parse_coderabbit_signals(body):
    """Pull CodeRabbit's PR-level signals out of its walkthrough comment.

    Returns {"merge_risk": str|None, "failed_pre_merge_checks": [str]}. Both are
    PR-level verdicts with no Greptile equivalent: merge_risk is CodeRabbit's own
    blocking assessment, and a failed pre-merge check is a gate visible on the PR
    that Phase 4 should not silently pass over.
    """
    body = body or ""
    signals = {"merge_risk": None, "failed_pre_merge_checks": []}

    risk = re.search(r"\*\*Merge Risk:\*\*\s*_[^A-Za-z\n]*([A-Za-z]+)", body)
    if risk:
        signals["merge_risk"] = risk.group(1).strip()

    # Table rows look like: | Docstring Coverage | ⚠️ Warning | ... |
    for row in re.finditer(r"^\|\s*([^|\n]+?)\s*\|\s*[^|\n]*(?:Warning|Failed)[^|\n]*\|", body, re.M):
        name = row.group(1).strip()
        if name and not name.startswith(":") and name.lower() != "check name":
            signals["failed_pre_merge_checks"].append(name)
    return signals


def parse_findings(author_login, body):
    """Dispatch to the right provider parser."""
    provider = AI_REVIEW_PROVIDERS.get(author_login, {}).get("name")
    if provider == "greptile":
        return parse_greptile_findings(body)
    if provider == "coderabbit":
        return parse_coderabbit_findings(body)
    return []


def detect_configured_providers(owner, repo):
    """Report which providers the target repo has config files for.

    Queried against the repo being triaged rather than the working directory,
    which may be a different checkout entirely when triaging owner/repo#N.

    Presence is advisory: a provider can be installed org-wide with no in-repo
    config, so absence here does not mean it is inactive.
    """
    found = []
    for spec in AI_REVIEW_PROVIDERS.values():
        for path in spec["detect_files"]:
            result = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/contents/{path}", "--jq", ".name"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                found.append(spec["name"])
                break
    return found


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
    ai_review_comments = []
    bot_other_comments = []
    bot_unknown_comments = []
    ai_signals = {"merge_risk": None, "failed_pre_merge_checks": []}

    def bucket(kind, entry):
        if kind == "human":
            human_comments.append(entry)
        elif kind == "ai_review":
            ai_review_comments.append(entry)
        elif kind == "bot_unknown":
            bot_unknown_comments.append(entry)
        else:
            bot_other_comments.append(entry)

    def add_inline(c):
        login = c["user"]["login"]
        kind = classify_comment(login)
        entry = {
            "id": c["id"],
            "author": login,
            "kind": "inline",
            "path": c.get("path"),
            "line": c.get("line") or c.get("original_line"),
            "commit_id": c.get("commit_id"),
            "body": c.get("body", ""),
            "created_at": c.get("created_at"),
            "thread_state": thread_state.get(c["id"], {"is_resolved": None, "thread_id": None}),
        }
        if kind == "ai_review":
            entry["provider"] = AI_REVIEW_PROVIDERS[login]["name"]
            entry["findings"] = parse_findings(login, entry["body"])
        bucket(kind, entry)

    for c in inline:
        add_inline(c)

    def add_top_level(c, source):
        login = c["user"]["login"]
        kind = classify_comment(login)
        entry = {
            "id": c["id"],
            "author": login,
            "kind": source,
            "path": None,
            "line": None,
            "body": c.get("body", ""),
            "created_at": c.get("created_at"),
            "thread_state": {"is_resolved": None, "thread_id": None},
        }
        if kind == "ai_review":
            entry["provider"] = AI_REVIEW_PROVIDERS[login]["name"]
            entry["findings"] = parse_findings(login, entry["body"])
            if entry["provider"] == "coderabbit":
                found = parse_coderabbit_signals(entry["body"])
                if found["merge_risk"]:
                    ai_signals["merge_risk"] = found["merge_risk"]
                for name in found["failed_pre_merge_checks"]:
                    if name not in ai_signals["failed_pre_merge_checks"]:
                        ai_signals["failed_pre_merge_checks"].append(name)
        bucket(kind, entry)

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

    # 9. AI-review findings still open. An inline finding whose thread is
    # resolved is done; top-level findings have no thread, so they stay listed.
    unresolved_ai_findings = []
    for c in ai_review_comments:
        if (c.get("thread_state") or {}).get("is_resolved"):
            continue
        for f in c.get("findings", []):
            unresolved_ai_findings.append(
                {
                    "provider": c["provider"],
                    "priority": f["priority"],
                    "severity": f["severity"],
                    "title": f["title"],
                    "path": c.get("path"),
                    "line": c.get("line"),
                    "comment_id": c["id"],
                }
            )
    blocking_ai_findings = [f for f in unresolved_ai_findings if f["priority"] in ("P1", "P2")]

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
        "phase_3_ai_review": {
            "providers_seen": sorted({c["provider"] for c in ai_review_comments}),
            "providers_configured_in_repo": detect_configured_providers(owner, repo),
            "total_comments": len(ai_review_comments),
            "unresolved_findings": unresolved_ai_findings,
            "blocking_findings": blocking_ai_findings,
            "merge_risk": ai_signals["merge_risk"],
            "failed_pre_merge_checks": ai_signals["failed_pre_merge_checks"],
            "comments": ai_review_comments,
        },
        # Retained so callers written against the greptile-only report keep working.
        "phase_3_greptile": {
            "total_comments": len([c for c in ai_review_comments if c["provider"] == "greptile"]),
            "comments": [c for c in ai_review_comments if c["provider"] == "greptile"],
        },
        "bot_other": {
            "total": len(bot_other_comments),
            "comments": bot_other_comments,
        },
        # Bots matching no known provider or infra bot. NOT safe to ignore:
        # inspect these, then add them to AI_REVIEW_PROVIDERS or NON_BLOCKING_BOTS.
        "bot_unknown": {
            "total": len(bot_unknown_comments),
            "logins": sorted({c["author"] for c in bot_unknown_comments}),
            "comments": bot_unknown_comments,
        },
    }

    indent = 2 if args.pretty else None
    print(json.dumps(report, indent=indent, default=str))


if __name__ == "__main__":
    main()
