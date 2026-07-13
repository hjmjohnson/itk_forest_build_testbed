#!/usr/bin/env python3
"""discourse_cache_sync.py — Sync Discourse topics and posts into the
gh-comment-cache SQLite DB for unified cross-source search.

Subcommands
-----------
add-site URL [--name NAME]
    Register a Discourse site for syncing.

sync [--site URL] [--full]
    Incremental sync of topics and posts. With --full, re-fetches everything.

sync-topic TOPIC_ID [--site URL]
    Fetch/refresh a single topic and all its posts.

status
    Show registered sites, topic/post counts, and sync state.

The Discourse JSON API is public (read-only, no auth needed for public sites).
Rate limit: 60 requests/minute for anonymous access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# HTML-to-plaintext converter for FTS indexing
# ---------------------------------------------------------------------------


class _HTMLStripper(HTMLParser):
    """Minimal HTML→plaintext converter for Discourse 'cooked' HTML."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def html_to_text(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_json(url: str, retries: int = 3, delay: float = 1.0) -> dict:
    """Fetch JSON from a URL with retries and rate-limit awareness."""
    for attempt in range(retries):
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code == 429:
                wait = float(e.headers.get("Retry-After", delay * (attempt + 1)))
                print(f"  Rate limited, waiting {wait:.0f}s...", file=sys.stderr)
                time.sleep(wait)
            elif e.code in (502, 503, 504):
                time.sleep(delay * (attempt + 1))
            else:
                raise
        except (URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


def _extract_mentions(text: str) -> list[str]:
    """Extract @mentions from text."""
    return re.findall(r"@(\w+)", text)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _open_db():
    """Open the gh-comment-cache DB and apply the Discourse migration."""
    import sqlite3

    db_path = None
    cache_root = Path.home() / ".cache" / "agent-skills" / "gh-comment-cache"
    for p in cache_root.rglob("cache.sqlite"):
        db_path = p
        break

    if db_path is None:
        print(
            "ERROR: gh-comment-cache DB not found. Run gh-comment-cache sync first.",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    # Apply discourse migration if needed
    migration_file = Path(__file__).parent.parent / "migrations" / "002_discourse.sql"
    if migration_file.exists():
        # Check if tables already exist
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "raw_discourse_sites" not in tables:
            print("Applying Discourse schema migration...")
            conn.executescript(migration_file.read_text())
            conn.commit()

    return conn, db_path


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_add_site(args: argparse.Namespace) -> None:
    conn, db_path = _open_db()
    url = args.url.rstrip("/")
    name = args.name or url.split("//")[-1]

    conn.execute(
        "INSERT OR REPLACE INTO raw_discourse_sites (base_url, site_name, added_at) VALUES (?, ?, ?)",
        (url, name, _now_iso()),
    )

    # Fetch and cache categories
    try:
        data = _fetch_json(f"{url}/categories.json")
        cats = data.get("category_list", {}).get("categories", [])
        for cat in cats:
            conn.execute(
                """INSERT OR REPLACE INTO raw_discourse_categories
                   (site_url, id, name, slug, topic_count, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (url, cat["id"], cat["name"], cat["slug"], cat.get("topic_count", 0), _now_iso()),
            )
        print(f"Added {url} with {len(cats)} categories")
    except Exception as e:
        print(f"Added {url} (categories fetch failed: {e})")

    conn.commit()
    conn.close()


def cmd_sync(args: argparse.Namespace) -> None:
    conn, db_path = _open_db()

    sites = conn.execute("SELECT base_url, site_name FROM raw_discourse_sites").fetchall()
    if not sites:
        print("No Discourse sites registered. Use: discourse-cache add-site URL")
        conn.close()
        return

    for site in sites:
        if args.site and site["base_url"] != args.site:
            continue
        _sync_site(conn, site["base_url"], site["site_name"], full=args.full)

    conn.close()


def _sync_site(conn, base_url: str, site_name: str, full: bool = False) -> None:
    """Sync topics and posts from a Discourse site."""
    print(f"Syncing {site_name} ({base_url})...")

    # Get sync state
    row = conn.execute(
        "SELECT high_water, last_page FROM raw_discourse_sync_state WHERE site_url=? AND stream='latest_topics'",
        (base_url,),
    ).fetchone()

    if row and not full:
        high_water = row["high_water"]
        start_page = 0  # Always start from page 0 for latest
    else:
        high_water = "1970-01-01T00:00:00Z"
        start_page = 0
        conn.execute(
            """INSERT OR REPLACE INTO raw_discourse_sync_state
               (site_url, stream, high_water, last_page, initial_backfill_complete)
               VALUES (?, 'latest_topics', ?, 0, 0)""",
            (base_url, high_water),
        )

    new_high_water = high_water
    topics_upserted = 0
    posts_upserted = 0
    page = start_page

    while True:
        try:
            data = _fetch_json(f"{base_url}/latest.json?page={page}&order=activity")
        except Exception as e:
            print(f"  Page {page} failed: {e}")
            break

        topics = data.get("topic_list", {}).get("topics", [])
        if not topics:
            break

        reached_old = False
        for t in topics:
            last_posted = t.get("last_posted_at", t.get("created_at", ""))

            # For incremental sync, stop when we reach topics older than high_water
            if not full and last_posted <= high_water:
                reached_old = True
                break

            if last_posted > new_high_water:
                new_high_water = last_posted

            tags_json = json.dumps(
                [tag["name"] if isinstance(tag, dict) else tag for tag in (t.get("tags") or [])]
            )

            conn.execute(
                """INSERT OR REPLACE INTO raw_discourse_topics
                   (site_url, id, title, slug, category_id, tags, author_username,
                    posts_count, views, like_count, created_at, last_posted_at,
                    closed, archived, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    base_url,
                    t["id"],
                    t["title"],
                    t["slug"],
                    t.get("category_id"),
                    tags_json,
                    t.get("last_poster_username", "unknown"),
                    t.get("posts_count", 0),
                    t.get("views", 0),
                    t.get("like_count", 0),
                    t.get("created_at", ""),
                    last_posted,
                    int(t.get("closed", False)),
                    int(t.get("archived", False)),
                    _now_iso(),
                ),
            )
            topics_upserted += 1

            # Fetch posts for this topic
            posts_upserted += _sync_topic_posts(conn, base_url, t["id"])

        conn.commit()

        if reached_old or len(topics) < 30:
            break

        page += 1
        time.sleep(0.5)  # Rate limit courtesy

    # Update sync state
    conn.execute(
        """UPDATE raw_discourse_sync_state
           SET high_water=?, last_page=?, last_sync_at=?, last_status='ok',
               initial_backfill_complete=1
           WHERE site_url=? AND stream='latest_topics'""",
        (new_high_water, page, _now_iso(), base_url),
    )
    conn.execute(
        "UPDATE raw_discourse_sites SET last_sync_at=? WHERE base_url=?",
        (_now_iso(), base_url),
    )
    conn.commit()

    print(f"  {topics_upserted} topics, {posts_upserted} posts synced")


def _sync_topic_posts(conn, base_url: str, topic_id: int) -> int:
    """Fetch ALL posts for a topic, including paginated ones.

    Discourse returns ~20 posts in the initial /t/{id}.json response,
    plus a `stream` array with every post ID. Remaining posts are
    fetched in batches via /t/{id}/posts.json?post_ids[]=...
    """
    try:
        data = _fetch_json(f"{base_url}/t/{topic_id}.json")
    except Exception as e:
        print(f"  Topic {topic_id} fetch failed: {e}", file=sys.stderr)
        return 0

    post_stream = data.get("post_stream", {})
    initial_posts = post_stream.get("posts", [])
    all_stream_ids = post_stream.get("stream", [])

    # Collect all posts — start with what we got in the initial response
    all_posts = list(initial_posts)
    fetched_ids = {p["id"] for p in initial_posts}

    # Fetch remaining posts in batches of 20
    missing_ids = [pid for pid in all_stream_ids if pid not in fetched_ids]
    batch_size = 20
    for i in range(0, len(missing_ids), batch_size):
        batch = missing_ids[i : i + batch_size]
        params = "&".join(f"post_ids[]={pid}" for pid in batch)
        try:
            batch_data = _fetch_json(f"{base_url}/t/{topic_id}/posts.json?{params}")
            batch_posts = batch_data.get("post_stream", {}).get("posts", [])
            all_posts.extend(batch_posts)
            time.sleep(0.3)  # Rate limit courtesy
        except Exception as e:
            print(f"  Topic {topic_id} batch fetch failed: {e}", file=sys.stderr)
            break

    count = 0
    for p in all_posts:
        cooked = p.get("cooked", "")
        plain = html_to_text(cooked)
        sha = _sha256(plain)

        conn.execute(
            """INSERT OR REPLACE INTO raw_discourse_posts
               (site_url, id, topic_id, post_number, author_username,
                reply_to_post_number, created_at, updated_at,
                body_cooked, body_md, body_sha256, like_count, reads,
                payload, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                base_url,
                p["id"],
                topic_id,
                p["post_number"],
                p.get("username", "unknown"),
                p.get("reply_to_post_number"),
                p.get("created_at", ""),
                p.get("updated_at", ""),
                cooked,
                plain,
                sha,
                p.get("like_count", 0),
                p.get("reads", 0),
                json.dumps(p),
                _now_iso(),
            ),
        )

        # Extract mentions
        for mention in _extract_mentions(plain):
            conn.execute(
                """INSERT OR IGNORE INTO derived_discourse_mentions
                   (site_url, post_id, mentioned_username) VALUES (?, ?, ?)""",
                (base_url, p["id"], mention),
            )

        count += 1

    time.sleep(0.3)  # Rate limit courtesy
    return count


def cmd_sync_topic(args: argparse.Namespace) -> None:
    conn, db_path = _open_db()
    site = args.site or _default_site(conn)
    if not site:
        print("ERROR: No site registered or --site not specified", file=sys.stderr)
        sys.exit(1)

    count = _sync_topic_posts(conn, site, args.topic_id)
    conn.commit()
    conn.close()
    print(f"Synced {count} posts for topic {args.topic_id}")


def cmd_status(args: argparse.Namespace) -> None:
    conn, db_path = _open_db()

    print(f"Database: {db_path}")
    print()

    sites = conn.execute("SELECT * FROM raw_discourse_sites").fetchall()
    if not sites:
        print("No Discourse sites registered.")
        conn.close()
        return

    for site in sites:
        topic_count = conn.execute(
            "SELECT count(*) FROM raw_discourse_topics WHERE site_url=?",
            (site["base_url"],),
        ).fetchone()[0]
        post_count = conn.execute(
            "SELECT count(*) FROM raw_discourse_posts WHERE site_url=?",
            (site["base_url"],),
        ).fetchone()[0]
        mention_count = conn.execute(
            "SELECT count(*) FROM derived_discourse_mentions WHERE site_url=?",
            (site["base_url"],),
        ).fetchone()[0]

        print(f"Site: {site['site_name']} ({site['base_url']})")
        print(f"  Topics: {topic_count}")
        print(f"  Posts:  {post_count}")
        print(f"  Mentions: {mention_count}")
        print(f"  Last sync: {site['last_sync_at'] or 'never'}")

    # Cross-source totals
    gh_count = conn.execute("SELECT count(*) FROM raw_comments").fetchone()[0]
    print("\nCross-source totals:")
    print(f"  GitHub comments: {gh_count}")
    disc_count = conn.execute("SELECT count(*) FROM raw_discourse_posts").fetchone()[0]
    print(f"  Discourse posts: {disc_count}")
    print(f"  Combined:        {gh_count + disc_count}")

    conn.close()


def _default_site(conn) -> str | None:
    row = conn.execute("SELECT base_url FROM raw_discourse_sites LIMIT 1").fetchone()
    return row["base_url"] if row else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Discourse topics/posts into gh-comment-cache DB"
    )
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add-site", help="Register a Discourse site")
    p_add.add_argument("url", help="Discourse base URL (e.g. https://discourse.itk.org)")
    p_add.add_argument("--name", help="Friendly name for the site")

    p_sync = sub.add_parser("sync", help="Sync topics and posts")
    p_sync.add_argument("--site", help="Only sync this site URL")
    p_sync.add_argument("--full", action="store_true", help="Full re-sync (ignore high-water)")

    p_topic = sub.add_parser("sync-topic", help="Sync a single topic")
    p_topic.add_argument("topic_id", type=int, help="Discourse topic ID")
    p_topic.add_argument("--site", help="Site URL (default: first registered)")

    p_status = sub.add_parser("status", help="Show sync status")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0

    {
        "add-site": cmd_add_site,
        "sync": cmd_sync,
        "sync-topic": cmd_sync_topic,
        "status": cmd_status,
    }[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
