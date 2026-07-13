#!/usr/bin/env python3
"""unified_search.py — Cross-source search across GitHub comments and
Discourse posts using the shared gh-comment-cache SQLite DB.

Usage:
    unified_search.py search "VTK license"
    unified_search.py search "SPDX" --source discourse
    unified_search.py search "ccache" --source github --author hjmjohnson
    unified_search.py by-author dzenanz
    unified_search.py by-author thewtex --source discourse
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _open_db():
    """Open the gh-comment-cache DB."""
    cache_root = Path.home() / ".cache" / "agent-skills" / "gh-comment-cache"
    for p in cache_root.rglob("cache.sqlite"):
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        return conn, p

    print("ERROR: gh-comment-cache DB not found.", file=sys.stderr)
    sys.exit(1)


def _has_discourse(conn) -> bool:
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    return "raw_discourse_posts" in tables


def cmd_search(args: argparse.Namespace) -> None:
    conn, db_path = _open_db()
    query = args.query
    source = args.source
    author = args.author
    limit = args.limit

    results = []

    # GitHub search (subquery approach — FTS5 content-sync tables
    # don't support JOIN+snippet reliably)
    if source in (None, "github"):
        sql = """
            SELECT rc.kind, rc.id, rc.repo_owner, rc.repo_name,
                   rc.issue_number, rc.author_login, rc.created_at,
                   substr(rc.body_md, 1, 200) as snippet
            FROM raw_comments rc
            WHERE rc.rowid IN (
                SELECT rowid FROM raw_comments_fts WHERE body_md MATCH ?
            )
        """
        params = [query]
        if author:
            sql += " AND rc.author_login = ?"
            params.append(author)
        sql += " ORDER BY rc.created_at DESC LIMIT ?"
        params.append(limit)

        for row in conn.execute(sql, params):
            repo = f"{row['repo_owner']}/{row['repo_name']}"
            results.append(
                {
                    "source": "github",
                    "origin": repo,
                    "thread_id": row["issue_number"],
                    "author": row["author_login"],
                    "date": row["created_at"][:10],
                    "snippet": row["snippet"],
                    "url": f"https://github.com/{repo}/{'issues' if row['kind'] == 'issue' else 'pull'}/{row['issue_number']}#issuecomment-{row['id']}",
                }
            )

    # Discourse search
    if source in (None, "discourse") and _has_discourse(conn):
        sql = """
            SELECT dp.id, dp.topic_id, dp.author_username, dp.created_at,
                   dt.title, dt.slug, dp.site_url,
                   substr(dp.body_md, 1, 200) as snippet
            FROM raw_discourse_posts dp
            LEFT JOIN raw_discourse_topics dt ON dt.site_url = dp.site_url AND dt.id = dp.topic_id
            WHERE dp.rowid IN (
                SELECT rowid FROM raw_discourse_fts WHERE body_md MATCH ?
            )
        """
        params = [query]
        if author:
            sql += " AND dp.author_username = ?"
            params.append(author)
        sql += " ORDER BY dp.created_at DESC LIMIT ?"
        params.append(limit)

        for row in conn.execute(sql, params):
            results.append(
                {
                    "source": "discourse",
                    "origin": row["site_url"],
                    "thread_id": row["topic_id"],
                    "thread_title": row["title"],
                    "author": row["author_username"],
                    "date": row["created_at"][:10],
                    "snippet": row["snippet"],
                    "url": f"{row['site_url']}/t/{row['slug']}/{row['topic_id']}",
                }
            )

    # Sort combined results by date descending
    results.sort(key=lambda r: r["date"], reverse=True)

    print(f"Found {len(results)} result(s) for '{query}'")
    if source:
        print(f"  (filtered to source={source})")
    print()

    for r in results:
        tag = f"[{r['source']}]"
        title = r.get("thread_title", f"#{r['thread_id']}")
        print(f"{tag:12s} {r['date']}  {r['author']:20s}  {title[:50]}")
        print(f"             {r['snippet'][:120]}")
        print(f"             {r['url']}")
        print()

    conn.close()


def cmd_by_author(args: argparse.Namespace) -> None:
    conn, db_path = _open_db()
    login = args.login
    source = args.source
    limit = args.limit

    count_gh = 0
    count_disc = 0

    if source in (None, "github"):
        count_gh = conn.execute(
            "SELECT count(*) FROM raw_comments WHERE author_login = ?", (login,)
        ).fetchone()[0]

    if source in (None, "discourse") and _has_discourse(conn):
        count_disc = conn.execute(
            "SELECT count(*) FROM raw_discourse_posts WHERE author_username = ?", (login,)
        ).fetchone()[0]

    print(f"Author: {login}")
    if source in (None, "github"):
        print(f"  GitHub comments: {count_gh}")
    if source in (None, "discourse"):
        print(f"  Discourse posts: {count_disc}")
    print(f"  Total: {count_gh + count_disc}")
    print()

    # Show recent posts
    results = []

    if source in (None, "github"):
        for row in conn.execute(
            """SELECT kind, id, repo_owner, repo_name, issue_number,
                      created_at, substr(body_md, 1, 100) as preview
               FROM raw_comments WHERE author_login = ?
               ORDER BY created_at DESC LIMIT ?""",
            (login, limit),
        ):
            results.append(
                {
                    "source": "github",
                    "date": row["created_at"][:10],
                    "preview": row["preview"].replace("\n", " ")[:80],
                    "ref": f"{row['repo_owner']}/{row['repo_name']}#{row['issue_number']}",
                }
            )

    if source in (None, "discourse") and _has_discourse(conn):
        for row in conn.execute(
            """SELECT dp.id, dp.topic_id, dp.created_at,
                      substr(dp.body_md, 1, 100) as preview,
                      dt.title
               FROM raw_discourse_posts dp
               LEFT JOIN raw_discourse_topics dt ON dt.site_url = dp.site_url AND dt.id = dp.topic_id
               WHERE dp.author_username = ?
               ORDER BY dp.created_at DESC LIMIT ?""",
            (login, limit),
        ):
            results.append(
                {
                    "source": "discourse",
                    "date": row["created_at"][:10],
                    "preview": row["preview"].replace("\n", " ")[:80],
                    "ref": (row["title"] or f"topic #{row['topic_id']}")[:50],
                }
            )

    results.sort(key=lambda r: r["date"], reverse=True)
    for r in results[:limit]:
        tag = f"[{r['source']}]"
        print(f"  {tag:12s} {r['date']}  {r['ref']}")
        print(f"               {r['preview']}")
        print()

    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified cross-source search")
    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", help="Full-text search across all sources")
    p_search.add_argument("query", help="Search query (FTS5 syntax)")
    p_search.add_argument("--source", choices=["github", "discourse"], help="Limit to one source")
    p_search.add_argument("--author", help="Filter by author")
    p_search.add_argument("--limit", type=int, default=20, help="Max results per source")

    p_author = sub.add_parser("by-author", help="Show posts by author across sources")
    p_author.add_argument("login", help="Username/login")
    p_author.add_argument("--source", choices=["github", "discourse"])
    p_author.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0

    {"search": cmd_search, "by-author": cmd_by_author}[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
