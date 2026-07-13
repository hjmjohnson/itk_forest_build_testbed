#!/usr/bin/env python3
"""ghtp_reply.py — Reply to a PR inline comment and optionally resolve the thread.

Posts an in-thread reply (so the reviewer gets notified and the thread
visually shows a response), then optionally uses GraphQL to mark the
thread as resolved. REST alone cannot resolve threads — you need
GraphQL's resolveReviewThread mutation.

Usage:
    python3 ghtp_reply.py \\
        --owner OWNER --repo REPO --num NNNN \\
        --comment-id 12345 \\
        --body "Fixed in abc1234 — renamed section to 12a."
        [--resolve]

Requires: gh CLI (authenticated), python3.
"""

import argparse
import json
import subprocess
import sys


def gh(args):
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def post_reply(owner, repo, num, comment_id, body):
    """POST /repos/{owner}/{repo}/pulls/{num}/comments/{id}/replies."""
    out = gh(
        [
            "api",
            "-X",
            "POST",
            f"repos/{owner}/{repo}/pulls/{num}/comments/{comment_id}/replies",
            "-f",
            f"body={body}",
        ]
    )
    return json.loads(out)


def lookup_thread_id(owner, repo, num, comment_id):
    """Find the review thread ID that contains a given comment database ID."""
    query = """
    query($owner: String!, $repo: String!, $num: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $num) {
          reviewThreads(first: 100) {
            nodes {
              id
              comments(first: 50) {
                nodes { databaseId }
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
    threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    for thread in threads:
        for c in thread["comments"]["nodes"]:
            if c["databaseId"] == comment_id:
                return thread["id"]
    return None


def resolve_thread(thread_id):
    """Mutation to resolve a review thread via GraphQL."""
    mutation = """
    mutation($threadId: ID!) {
      resolveReviewThread(input: {threadId: $threadId}) {
        thread { id isResolved }
      }
    }
    """
    out = gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={mutation}",
            "-F",
            f"threadId={thread_id}",
        ]
    )
    return json.loads(out)


def main():
    parser = argparse.ArgumentParser(description="Reply to a PR comment and optionally resolve")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--num", required=True, type=int)
    parser.add_argument("--comment-id", required=True, type=int)
    parser.add_argument("--body", required=True, help="Reply body (markdown)")
    parser.add_argument(
        "--resolve", action="store_true", help="Also resolve the thread after replying"
    )
    args = parser.parse_args()

    # 1. Post the reply
    try:
        reply = post_reply(args.owner, args.repo, args.num, args.comment_id, args.body)
        print(f"Reply posted: {reply.get('html_url', 'ok')}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: failed to post reply: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Optionally resolve the thread
    if args.resolve:
        try:
            thread_id = lookup_thread_id(args.owner, args.repo, args.num, args.comment_id)
            if not thread_id:
                print(f"WARN: could not find thread for comment {args.comment_id}", file=sys.stderr)
                sys.exit(0)
            result = resolve_thread(thread_id)
            is_resolved = (
                result.get("data", {})
                .get("resolveReviewThread", {})
                .get("thread", {})
                .get("isResolved")
            )
            if is_resolved:
                print(f"Thread {thread_id} resolved.", file=sys.stderr)
            else:
                print(f"WARN: resolve returned non-resolved state: {result}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: failed to resolve thread: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
