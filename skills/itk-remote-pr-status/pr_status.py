#!/usr/bin/env python3
"""Collect CI and review status for all open hjmjohnson PRs across ITK remote modules."""

import json
import os
import subprocess
import sys


def run(cmd, **kwargs):
    """Run a command and return stdout, or empty string on failure."""
    try:
        return subprocess.check_output(
            cmd, text=True, stderr=subprocess.DEVNULL, timeout=30, **kwargs
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def get_repo(module_dir):
    """Extract owner/repo from git remote URL."""
    url = run(["git", "-C", module_dir, "remote", "get-url", "origin"])
    if not url:
        return None
    for prefix in ["git@github.com:", "https://github.com/"]:
        if url.startswith(prefix):
            url = url[len(prefix) :]
    return url.rstrip(".git")


def get_pr_status(repo):
    """Get open PRs by hjmjohnson with full status."""
    raw = run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--author",
            "hjmjohnson",
            "--repo",
            repo,
            "--json",
            "number,title,headRefName,reviewDecision,assignees,reviewRequests,url",
        ]
    )
    if not raw:
        return []

    prs = json.loads(raw)
    results = []

    for pr in prs:
        pr_num = pr["number"]

        # Get check rollup
        rollup_raw = run(
            ["gh", "pr", "view", str(pr_num), "--repo", repo, "--json", "statusCheckRollup"]
        )
        checks = json.loads(rollup_raw).get("statusCheckRollup", []) if rollup_raw else []

        passed = sum(1 for c in checks if c.get("conclusion") == "SUCCESS")
        failed = sum(1 for c in checks if c.get("conclusion") == "FAILURE")
        pending = sum(1 for c in checks if c.get("status") != "COMPLETED")
        skipped = sum(1 for c in checks if c.get("conclusion") in ("SKIPPED", "CANCELLED"))
        total = len(checks)

        failed_names = sorted(set(c["name"] for c in checks if c.get("conclusion") == "FAILURE"))

        if failed == 0 and pending == 0 and passed > 0:
            status = "ALL_PASS"
        elif pending > 0 and failed == 0:
            status = "PENDING"
        elif failed > 0 and pending > 0:
            status = "FAIL_AND_PENDING"
        elif failed > 0:
            status = "FAILING"
        else:
            status = "UNKNOWN"

        # Review status
        review_decision = pr.get("reviewDecision", "")
        assignees = [a.get("login", "") for a in pr.get("assignees", [])]
        reviewers = [r.get("login", "") for r in pr.get("reviewRequests", [])]

        results.append(
            {
                "repo": repo,
                "number": pr_num,
                "title": pr["title"],
                "branch": pr["headRefName"],
                "url": pr["url"],
                "status": status,
                "passed": passed,
                "failed": failed,
                "pending": pending,
                "skipped": skipped,
                "total": total,
                "failed_checks": failed_names,
                "review_decision": review_decision,
                "assignees": assignees,
                "reviewers": reviewers,
            }
        )

    return results


def main():
    base = os.environ.get("REMOTE_MODULES_DIR", os.path.expanduser("~/src/REMOTE_MODULES"))

    all_results = []
    for entry in sorted(os.listdir(base)):
        module_dir = os.path.join(base, entry)
        if not os.path.isdir(os.path.join(module_dir, ".git")):
            continue

        repo = get_repo(module_dir)
        if not repo:
            continue

        prs = get_pr_status(repo)
        for pr in prs:
            pr["module"] = entry
            all_results.append(pr)

    json.dump(all_results, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
