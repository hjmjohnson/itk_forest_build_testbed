#!/usr/bin/env python3
"""gh_cache_read.py — CLI wrapper for gh-comment-cache query operations.

Subcommands
-----------
by-author LOGIN [--repo OWNER/REPO]
    List comments authored by LOGIN.

by-mention LOGIN [--repo OWNER/REPO]
    List comments that @mention LOGIN.

search QUERY [--repo OWNER/REPO]
    Full-text search over comment bodies.

All subcommands read only from the local cache — no GitHub API calls are made.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_repos(repo_str: str | None) -> list[tuple[str, str]] | None:
    """Convert 'OWNER/REPO' to [(owner, name)], or return None if not given."""
    if repo_str is None:
        return None
    parts = repo_str.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        print(f"ERROR: expected OWNER/REPO, got {repo_str!r}", file=sys.stderr)
        sys.exit(1)
    return [(parts[0], parts[1])]


def _print_result(result) -> None:
    """Print the INFO banner and comment rows."""
    hw_parts = ", ".join(f"{repo}={ts}" for repo, ts in sorted(result.high_water_marks.items()))
    hw_str = hw_parts if hw_parts else "(none)"
    count = len(result.rows)

    print("INFO: Only local cache values used (no GitHub API calls).")
    print(f"      High-water marks: {hw_str}")
    print(f"      {count} comment(s) returned.")
    print()

    for comment in result.rows:
        label = "issue" if comment.kind == "issue" else comment.kind
        repo_str = f"{comment.repo_owner}/{comment.repo_name}"
        header = (
            f"[{label}#{comment.id}] {repo_str}#{comment.issue_number}"
            f" by {comment.author_login} ({comment.created_at})"
        )
        print(header)
        # Print up to 2 lines of body, indented
        body_lines = (comment.body_md or "").splitlines()
        preview = body_lines[:2]
        for line in preview:
            print(f"  {line}")
        if len(body_lines) > 2:
            print(f"  ... ({len(body_lines) - 2} more line(s))")
        print()


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_by_author(args: argparse.Namespace) -> None:
    """List comments authored by LOGIN."""
    from agent_skills.gh_cache import list_comments_by_author, open_gh_cache  # noqa: PLC0415

    repos = _parse_repos(args.repo)
    result_obj = open_gh_cache()
    conn = result_obj.connection
    try:
        result = list_comments_by_author(conn, args.login, repos=repos)
        _print_result(result)
    finally:
        conn.close()


def cmd_by_mention(args: argparse.Namespace) -> None:
    """List comments that @mention LOGIN."""
    from agent_skills.gh_cache import list_comments_by_mention, open_gh_cache  # noqa: PLC0415

    repos = _parse_repos(args.repo)
    result_obj = open_gh_cache()
    conn = result_obj.connection
    try:
        result = list_comments_by_mention(conn, args.login, repos=repos)
        _print_result(result)
    finally:
        conn.close()


def cmd_search(args: argparse.Namespace) -> None:
    """Full-text search over comment bodies."""
    from agent_skills.gh_cache import list_comments_matching, open_gh_cache  # noqa: PLC0415

    repos = _parse_repos(args.repo)
    result_obj = open_gh_cache()
    conn = result_obj.connection
    try:
        result = list_comments_matching(conn, args.query, repos=repos)
        _print_result(result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gh_cache_read",
        description="Query the local gh-comment-cache SQLite database (no network calls).",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # by-author
    p_author = sub.add_parser("by-author", help="List comments by a given author login.")
    p_author.add_argument("login", metavar="LOGIN", help="GitHub login to search for.")
    p_author.add_argument("--repo", metavar="OWNER/REPO", help="Restrict results to this repo.")

    # by-mention
    p_mention = sub.add_parser("by-mention", help="List comments that @mention a given login.")
    p_mention.add_argument("login", metavar="LOGIN", help="GitHub login to search for.")
    p_mention.add_argument("--repo", metavar="OWNER/REPO", help="Restrict results to this repo.")

    # search
    p_search = sub.add_parser("search", help="Full-text search over comment bodies.")
    p_search.add_argument("query", metavar="QUERY", help="FTS5 query string.")
    p_search.add_argument("--repo", metavar="OWNER/REPO", help="Restrict results to this repo.")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_SUBCOMMAND_MAP = {
    "by-author": cmd_by_author,
    "by-mention": cmd_by_mention,
    "search": cmd_search,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = _SUBCOMMAND_MAP[args.subcommand]
    handler(args)


if __name__ == "__main__":
    main()
