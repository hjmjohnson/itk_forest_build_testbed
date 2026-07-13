"""gh-comment-cache — data models, cache opening, upserts, FTS search, and freeze logic.

This module is the Python interface for the ``gh-comment-cache`` skill's SQLite
cache.  It covers:

* Constants and frozen dataclasses (``Comment``, ``WatchedRepo``, ``QueryResult``)
* Helpers: ``_now_iso``, ``_body_sha256``, ``_get_gh_login``, ``_synthetic_workspace``
* ``_apply_migration`` — idempotent migration from ``001_init.sql``
* ``open_gh_cache`` — entry-point that opens (or creates) the global cache
* ``extract_mentions`` / ``_upsert_mentions`` — @mention extraction & persistence
* ``upsert_watched_repo``, ``upsert_pr_index``, ``upsert_raw_comment``
* ``freeze_sweep``, ``unfreeze_pr``
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from agent_skills.cache import CacheOpenResult, open_cache
from agent_skills.workspace import Workspace

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_NAME: str = "gh-comment-cache"
SKILL_VERSION: str = "1.0.0"
SCHEMA_VERSION: int = 1

#: Minimum token budget before the skill refuses to run an AI sub-task.
MIN_BUDGET: int = int(os.environ.get("GH_COMMENT_CACHE_MIN_BUDGET", "200"))

#: Number of days after close/merge before a PR is eligible for freezing.
FREEZE_COOLOFF_DAYS: int = 30

#: Absolute path to the migrations directory for this skill.
_MIGRATION_DIR: Path = Path(__file__).resolve().parent.parent.parent / "migrations"

# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WatchedRepo:
    """Row from ``raw_watched_repos``."""

    owner: str
    name: str
    source: str
    backfill_days: int
    added_at: str
    last_discovery_at: str | None = None


@dataclass(frozen=True)
class Comment:
    """Row from ``raw_comments``."""

    kind: str
    id: int
    repo_owner: str
    repo_name: str
    issue_number: int
    created_at: str
    updated_at: str
    author_login: str
    author_id: int
    body_md: str
    body_sha256: str
    payload: str
    fetched_at: str
    review_id: int | None = None
    in_reply_to_id: int | None = None
    author_assoc: str | None = None
    diff_hunk: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    original_commit_sha: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    side: str | None = None
    deleted_at: str | None = None


@dataclass
class QueryResult:
    """Result returned from a cache query operation."""

    rows: list = field(default_factory=list)
    cache_mode: str = "hit"
    synced_repos: list = field(default_factory=list)
    high_water_marks: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GhApiResponse:
    """Parsed response from ``gh api --include``."""

    status: int
    etag: str | None
    rate_remaining: int | None
    rate_reset: int | None
    body: str


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.datetime.now(datetime.UTC).isoformat()


def _body_sha256(body: str) -> str:
    """Return the SHA-256 hex digest of *body* (UTF-8 encoded)."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _get_gh_login() -> str:
    """Return the GitHub login for the authenticated ``gh`` CLI user."""
    result = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _synthetic_workspace(login: str) -> Workspace:
    """Return a synthetic, non-git ``Workspace`` keyed by *login*.

    The cache for this skill is global (per GitHub user) rather than
    per-repository, so we fabricate a stable workspace rooted at a
    well-known path that embeds the login name.
    """
    root = Path.home() / ".local" / "state" / "agent-skills" / SKILL_NAME / login
    return Workspace(
        normalized_root=root,
        upstream_url=f"github:user:{login}",
        origin_url=None,
        is_git=False,
    )


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def _apply_migration(conn) -> None:
    """Apply ``001_init.sql`` if the skill tables are not yet present.

    The migration is idempotent — safe to call on an already-migrated DB.
    """
    migration_file = _MIGRATION_DIR / "001_init.sql"
    sql = migration_file.read_text(encoding="utf-8")
    # Wrap in suppress so re-running on an existing schema is harmless.
    with contextlib.suppress(Exception):
        conn.executescript(sql)


# ---------------------------------------------------------------------------
# Cache entry-point
# ---------------------------------------------------------------------------


def open_gh_cache() -> CacheOpenResult:
    """Open (or create) the global gh-comment-cache SQLite database.

    Returns a :class:`~agent_skills.cache.CacheOpenResult` with an open
    connection and the path to the DB file.
    """
    login = _get_gh_login()
    workspace = _synthetic_workspace(login)
    result = open_cache(SKILL_NAME, SKILL_VERSION, workspace, schema_version=SCHEMA_VERSION)
    _apply_migration(result.connection)
    return result


# ---------------------------------------------------------------------------
# @mention extraction
# ---------------------------------------------------------------------------

# Matches a GitHub @mention that is NOT preceded by an alphanumeric char
# (to avoid matching email addresses like user@example.com).
_MENTION_RE = re.compile(r"(?<![a-zA-Z0-9])@([a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)")


def extract_mentions(body: str) -> set[str]:
    """Return the set of GitHub logins @mentioned in *body*.

    Email addresses are excluded: a match that is immediately followed by
    a ``.`` (domain part) is dropped.
    """
    mentions: set[str] = set()
    for m in _MENTION_RE.finditer(body):
        # Reject email-style patterns: @login.domain
        end = m.end()
        if end < len(body) and body[end] == ".":
            continue
        mentions.add(m.group(1))
    return mentions


def _upsert_mentions(conn, kind: str, comment_id: int, body: str) -> None:
    """Rebuild the ``derived_mentions`` rows for one comment."""
    conn.execute(
        "DELETE FROM derived_mentions WHERE comment_kind = ? AND comment_id = ?",
        (kind, comment_id),
    )
    logins = extract_mentions(body)
    if logins:
        conn.executemany(
            "INSERT INTO derived_mentions (comment_kind, comment_id, mentioned_login)"
            " VALUES (?, ?, ?)",
            [(kind, comment_id, login) for login in logins],
        )


# ---------------------------------------------------------------------------
# Source merging helper
# ---------------------------------------------------------------------------


def _merge_source(existing: str, incoming: str) -> str:
    """Return the merged source value.

    If *existing* and *incoming* are the same, return that value. Otherwise
    return ``'both'``.
    """
    if existing == incoming:
        return existing
    return "both"


# ---------------------------------------------------------------------------
# Upsert functions
# ---------------------------------------------------------------------------


def upsert_watched_repo(
    conn,
    owner: str,
    name: str,
    *,
    source: str,
    backfill_days: int,
) -> None:
    """Insert or update a row in ``raw_watched_repos``.

    Source merging: if the existing ``source`` differs from *source*, the
    stored value becomes ``'both'``.  ``backfill_days`` is kept at the
    maximum of the existing and incoming values.
    """
    existing = conn.execute(
        "SELECT source, backfill_days FROM raw_watched_repos WHERE owner = ? AND name = ?",
        (owner, name),
    ).fetchone()

    now = _now_iso()
    if existing is None:
        conn.execute(
            "INSERT INTO raw_watched_repos (owner, name, source, backfill_days, added_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (owner, name, source, backfill_days, now),
        )
    else:
        merged_source = _merge_source(existing["source"], source)
        merged_backfill = max(existing["backfill_days"], backfill_days)
        conn.execute(
            "UPDATE raw_watched_repos SET source = ?, backfill_days = ?"
            " WHERE owner = ? AND name = ?",
            (merged_source, merged_backfill, owner, name),
        )
    conn.commit()


def upsert_pr_index(
    conn,
    repo_owner: str,
    repo_name: str,
    number: int,
    is_pull: int,
    state: str,
    title: str,
    author_login: str,
    created_at: str,
    updated_at: str,
    closed_at: str | None,
    merged_at: str | None,
    i_authored: int,
    i_reviewed: int,
    i_mentioned: int,
) -> None:
    """Insert or update a row in ``raw_pr_index``.

    Attention flags (``i_authored``, ``i_reviewed``, ``i_mentioned``) are
    kept at the maximum of the stored and incoming values so they are never
    accidentally cleared by a partial update.
    """
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO raw_pr_index (
            repo_owner, repo_name, number, is_pull, state, title, author_login,
            created_at, updated_at, closed_at, merged_at,
            last_seen_at, i_authored, i_reviewed, i_mentioned
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (repo_owner, repo_name, number) DO UPDATE SET
            is_pull       = excluded.is_pull,
            state         = excluded.state,
            title         = excluded.title,
            author_login  = excluded.author_login,
            updated_at    = excluded.updated_at,
            closed_at     = excluded.closed_at,
            merged_at     = excluded.merged_at,
            last_seen_at  = excluded.last_seen_at,
            i_authored    = max(i_authored,  excluded.i_authored),
            i_reviewed    = max(i_reviewed,  excluded.i_reviewed),
            i_mentioned   = max(i_mentioned, excluded.i_mentioned)
        """,
        (
            repo_owner,
            repo_name,
            number,
            is_pull,
            state,
            title,
            author_login,
            created_at,
            updated_at,
            closed_at,
            merged_at,
            now,
            i_authored,
            i_reviewed,
            i_mentioned,
        ),
    )
    conn.commit()


def upsert_raw_comment(
    conn,
    kind: str,
    id: int,
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    review_id: int | None,
    in_reply_to_id: int | None,
    created_at: str,
    updated_at: str,
    author_login: str,
    author_id: int,
    author_assoc: str | None,
    body_md: str,
    payload: str,
    *,
    diff_hunk: str | None = None,
    file_path: str | None = None,
    commit_sha: str | None = None,
    original_commit_sha: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    side: str | None = None,
) -> None:
    """Insert or update a row in ``raw_comments``.

    On conflict the mutable fields (body, sha256, payload, timestamps) are
    updated.  After writing the row, ``derived_mentions`` is rebuilt via
    :func:`_upsert_mentions`.
    """
    now = _now_iso()
    sha = _body_sha256(body_md)
    conn.execute(
        """
        INSERT INTO raw_comments (
            kind, id, repo_owner, repo_name, issue_number,
            review_id, in_reply_to_id,
            created_at, updated_at,
            author_login, author_id, author_assoc,
            body_md, body_sha256,
            diff_hunk, file_path, commit_sha, original_commit_sha,
            start_line, end_line, side,
            payload, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (kind, id) DO UPDATE SET
            body_md     = excluded.body_md,
            body_sha256 = excluded.body_sha256,
            payload     = excluded.payload,
            fetched_at  = excluded.fetched_at,
            updated_at  = excluded.updated_at
        """,
        (
            kind,
            id,
            repo_owner,
            repo_name,
            issue_number,
            review_id,
            in_reply_to_id,
            created_at,
            updated_at,
            author_login,
            author_id,
            author_assoc,
            body_md,
            sha,
            diff_hunk,
            file_path,
            commit_sha,
            original_commit_sha,
            start_line,
            end_line,
            side,
            payload,
            now,
        ),
    )
    _upsert_mentions(conn, kind, id, body_md)
    conn.commit()


# ---------------------------------------------------------------------------
# Freeze logic
# ---------------------------------------------------------------------------


def freeze_sweep(conn) -> int:
    """Mark eligible closed/merged PRs as frozen.

    A PR is frozen when:
    * ``state`` is ``'closed'`` or ``'merged'``
    * ``closed_at`` is more than :data:`FREEZE_COOLOFF_DAYS` days ago
    * ``is_frozen = 0``

    Returns the number of rows updated.
    """
    cutoff = (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=FREEZE_COOLOFF_DAYS)
    ).isoformat()
    now = _now_iso()
    cursor = conn.execute(
        """
        UPDATE raw_pr_index
        SET    is_frozen = 1,
               frozen_at = ?
        WHERE  state IN ('closed', 'merged')
          AND  closed_at < ?
          AND  is_frozen = 0
        """,
        (now, cutoff),
    )
    conn.commit()
    return cursor.rowcount


def unfreeze_pr(conn, owner: str, name: str, number: int) -> None:
    """Clear the frozen flag for a single PR."""
    conn.execute(
        """
        UPDATE raw_pr_index
        SET    is_frozen = 0,
               frozen_at = NULL
        WHERE  repo_owner = ?
          AND  repo_name  = ?
          AND  number     = ?
        """,
        (owner, name, number),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# gh api subprocess wrapper (Task 5)
# ---------------------------------------------------------------------------


def _parse_include_response(raw: str) -> GhApiResponse:
    """Parse the output of ``gh api --include``.

    The format is: HTTP status line, headers, blank line, then JSON body.
    """
    # Split on first blank line to separate headers from body
    parts = raw.split("\n\n", 1)
    header_block = parts[0]
    body = parts[1] if len(parts) > 1 else ""

    lines = header_block.splitlines()

    # First line: "HTTP/2.0 200 OK" or similar
    status_line = lines[0] if lines else ""
    status = int(status_line.split()[1]) if len(status_line.split()) >= 2 else 0

    # Parse headers (case-insensitive)
    etag: str | None = None
    rate_remaining: int | None = None
    rate_reset: int | None = None

    for line in lines[1:]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_lower = key.strip().lower()
        value = value.strip()
        if key_lower == "etag":
            etag = value
        elif key_lower == "x-ratelimit-remaining":
            rate_remaining = int(value)
        elif key_lower == "x-ratelimit-reset":
            rate_reset = int(value)

    return GhApiResponse(
        status=status,
        etag=etag,
        rate_remaining=rate_remaining,
        rate_reset=rate_reset,
        body=body,
    )


def _check_rate_budget(resp: GhApiResponse, min_budget: int = MIN_BUDGET) -> None:
    """Raise ``RuntimeError`` if the remaining rate budget is too low."""
    if resp.rate_remaining is not None and resp.rate_remaining < min_budget:
        raise RuntimeError(
            f"GitHub API rate limit too low: {resp.rate_remaining} remaining "
            f"(minimum {min_budget}), resets at {resp.rate_reset}"
        )


def _gh_api_include(path: str, *, etag: str | None = None) -> GhApiResponse:
    """Run ``gh api --include <path>`` and return a parsed :class:`GhApiResponse`.

    If *etag* is provided, sends an ``If-None-Match`` header for conditional
    requests.  Raises ``RuntimeError`` on auth failure or non-zero exit.
    """
    cmd = ["gh", "api", "--include", path]
    if etag is not None:
        cmd.extend(["-H", f"If-None-Match: {etag}"])

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Check for auth failures
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if result.returncode != 0 and ("authentication" in stderr or "401" in str(result.stdout)):
            raise RuntimeError(f"GitHub authentication failure: {result.stderr}")
        raise RuntimeError(f"gh api failed (exit {result.returncode}): {result.stderr}")

    return _parse_include_response(result.stdout)


def _gh_api_paginate(path: str) -> list[dict]:
    """Run ``gh api --paginate <path>`` and return a list of dicts.

    The output may be multiple JSON arrays concatenated (``][``).
    We fix this by replacing ``]\\n[`` and ``][`` with ``,`` then parsing.
    """
    result = subprocess.run(
        ["gh", "api", "--paginate", path],
        capture_output=True,
        text=True,
        check=True,
    )
    text = result.stdout.strip()
    if not text:
        return []
    # Fix concatenated JSON arrays from pagination
    text = text.replace("]\n[", ",").replace("][", ",")
    return json.loads(text)


def _extract_issue_number(issue_url: str) -> int:
    """Extract the issue/PR number from a GitHub API URL.

    Example: ``https://api.github.com/repos/ISC/ITK/issues/6040`` → ``6040``
    """
    return int(issue_url.rstrip("/").rsplit("/", 1)[-1])


def parse_issue_comment(row: dict, owner: str, repo: str) -> dict:
    """Convert a JSON row from ``/repos/{o}/{r}/issues/comments`` to kwargs
    for :func:`upsert_raw_comment`."""
    return {
        "kind": "issue",
        "id": row["id"],
        "repo_owner": owner,
        "repo_name": repo,
        "issue_number": _extract_issue_number(row["issue_url"]),
        "review_id": None,
        "in_reply_to_id": None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "author_login": row["user"]["login"],
        "author_id": row["user"]["id"],
        "author_assoc": row.get("author_association"),
        "body_md": row.get("body", ""),
        "payload": json.dumps(row),
    }


def parse_review_comment(row: dict, owner: str, repo: str) -> dict:
    """Convert a JSON row from ``/repos/{o}/{r}/pulls/comments`` to kwargs
    for :func:`upsert_raw_comment`."""
    return {
        "kind": "review",
        "id": row["id"],
        "repo_owner": owner,
        "repo_name": repo,
        "issue_number": _extract_issue_number(row["pull_request_url"]),
        "review_id": row.get("pull_request_review_id"),
        "in_reply_to_id": row.get("in_reply_to_id"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "author_login": row["user"]["login"],
        "author_id": row["user"]["id"],
        "author_assoc": row.get("author_association"),
        "body_md": row.get("body", ""),
        "payload": json.dumps(row),
        "diff_hunk": row.get("diff_hunk"),
        "file_path": row.get("path"),
        "commit_sha": row.get("commit_id"),
        "original_commit_sha": row.get("original_commit_id"),
        "start_line": row.get("start_line"),
        "end_line": row.get("line"),
        "side": row.get("side"),
    }


# ---------------------------------------------------------------------------
# Sync engine (Task 6)
# ---------------------------------------------------------------------------

_STREAM_PATHS: dict[str, str] = {
    "issue_comments": "issues/comments",
    "review_comments": "pulls/comments",
}

_STREAM_PARSERS: dict[str, callable] = {
    "issue_comments": parse_issue_comment,
    "review_comments": parse_review_comment,
}


def _ensure_sync_state(conn, owner: str, name: str, stream: str) -> dict:
    """Ensure a ``raw_sync_state`` row exists for (*owner*, *name*, *stream*).

    Returns the row as a dict.
    """
    row = conn.execute(
        "SELECT * FROM raw_sync_state WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
        (owner, name, stream),
    ).fetchone()

    if row is not None:
        return dict(row)

    probe_url = (
        f"/repos/{owner}/{name}/{_STREAM_PATHS[stream]}?sort=updated&direction=desc&per_page=1"
    )
    conn.execute(
        "INSERT INTO raw_sync_state (repo_owner, repo_name, stream, probe_url) VALUES (?, ?, ?, ?)",
        (owner, name, stream, probe_url),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM raw_sync_state WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
        (owner, name, stream),
    ).fetchone()
    return dict(row)


def _compute_since(state: dict, backfill_days: int) -> str:
    """Compute the ``since`` parameter for a drain request.

    If initial backfill is not complete, floor to today minus *backfill_days*.
    Otherwise subtract 2 seconds from ``high_water`` for same-second tie epsilon.
    """
    if not state.get("initial_backfill_complete"):
        dt = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=backfill_days)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    hw = state["high_water"]
    dt = datetime.datetime.fromisoformat(hw.replace("Z", "+00:00"))
    dt -= datetime.timedelta(seconds=2)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_pr_index_from_comment(conn, parsed: dict) -> None:
    """Ensure a minimal ``raw_pr_index`` row exists for the comment's parent PR/issue."""
    owner = parsed["repo_owner"]
    name = parsed["repo_name"]
    number = parsed["issue_number"]

    existing = conn.execute(
        "SELECT 1 FROM raw_pr_index WHERE repo_owner = ? AND repo_name = ? AND number = ?",
        (owner, name, number),
    ).fetchone()

    if existing is not None:
        return

    now = _now_iso()
    conn.execute(
        """
        INSERT INTO raw_pr_index (
            repo_owner, repo_name, number, is_pull, state, title, author_login,
            created_at, updated_at, closed_at, merged_at,
            last_seen_at, i_authored, i_reviewed, i_mentioned
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner,
            name,
            number,
            1,
            "unknown",
            f"#{number}",
            "unknown",
            now,
            now,
            None,
            None,
            now,
            0,
            0,
            0,
        ),
    )
    conn.commit()


def discover_watched_repos(conn, *, gh_login: str | None = None) -> list[WatchedRepo]:
    """Discover repos by searching for PRs authored by or review-requested from *gh_login*.

    Runs ``gh search prs`` for both ``--author`` and ``--review-requested``,
    deduplicates, upserts into ``raw_watched_repos`` and ``raw_pr_index``.
    Returns the full list of watched repos.
    """
    if gh_login is None:
        gh_login = _get_gh_login()

    cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=90)).strftime(
        "%Y-%m-%d"
    )
    json_fields = "repository,number,state,updatedAt,title,author"

    # Search for authored PRs
    authored_result = subprocess.run(
        [
            "gh",
            "search",
            "prs",
            f"--author={gh_login}",
            f"--updated=>={cutoff}",
            "--state=all",
            f"--json={json_fields}",
            "--limit=200",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    authored_rows = json.loads(authored_result.stdout) if authored_result.stdout.strip() else []

    # Search for review-requested PRs
    review_result = subprocess.run(
        [
            "gh",
            "search",
            "prs",
            f"--review-requested={gh_login}",
            f"--updated=>={cutoff}",
            "--state=all",
            f"--json={json_fields}",
            "--limit=200",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    review_rows = json.loads(review_result.stdout) if review_result.stdout.strip() else []

    # Deduplicate by (owner, repo, number)
    seen: dict[tuple[str, str, int], dict] = {}
    for row in authored_rows:
        nwo = row["repository"]["nameWithOwner"]
        owner, name = nwo.split("/", 1)
        key = (owner, name, row["number"])
        if key not in seen:
            seen[key] = {**row, "_owner": owner, "_name": name, "_i_authored": 1, "_i_reviewed": 0}
        else:
            seen[key]["_i_authored"] = 1

    for row in review_rows:
        nwo = row["repository"]["nameWithOwner"]
        owner, name = nwo.split("/", 1)
        key = (owner, name, row["number"])
        if key not in seen:
            seen[key] = {**row, "_owner": owner, "_name": name, "_i_authored": 0, "_i_reviewed": 1}
        else:
            seen[key]["_i_reviewed"] = 1

    # Upsert repos and PRs
    repos_seen: set[tuple[str, str]] = set()
    for key, row in seen.items():
        owner, name, number = key
        if (owner, name) not in repos_seen:
            upsert_watched_repo(conn, owner, name, source="auto", backfill_days=90)
            repos_seen.add((owner, name))

        state_val = row.get("state", "OPEN").lower()
        updated = row.get("updatedAt", _now_iso())
        author = row.get("author", {}).get("login", "unknown") if row.get("author") else "unknown"
        upsert_pr_index(
            conn,
            repo_owner=owner,
            repo_name=name,
            number=number,
            is_pull=1,
            state=state_val,
            title=row.get("title", f"#{number}"),
            author_login=author,
            created_at=updated,
            updated_at=updated,
            closed_at=None,
            merged_at=None,
            i_authored=row.get("_i_authored", 0),
            i_reviewed=row.get("_i_reviewed", 0),
            i_mentioned=0,
        )

    return watched_repos(conn)


def sync_repo(conn, owner: str, name: str, *, force: bool = False) -> dict:
    """Sync comments for a single repo.

    For each stream (issue_comments, review_comments):
      Phase A — probe with conditional request (ETag).
      Phase B — paginated drain if new data detected.

    Returns a stats dict.
    """
    stats = {
        "probe_304_count": 0,
        "probe_200_count": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "requests_made": 0,
    }

    # Ensure the repo is in watched_repos
    repo_row = conn.execute(
        "SELECT * FROM raw_watched_repos WHERE owner = ? AND name = ?",
        (owner, name),
    ).fetchone()
    backfill_days = repo_row["backfill_days"] if repo_row else 90

    for stream, path_suffix in _STREAM_PATHS.items():
        state = _ensure_sync_state(conn, owner, name, stream)
        parser = _STREAM_PARSERS[stream]

        # Phase A: Probe
        try:
            probe_etag = state.get("probe_etag") if not force else None
            resp = _gh_api_include(state["probe_url"], etag=probe_etag)
            stats["requests_made"] += 1
            _check_rate_budget(resp)

            if resp.status == 304:
                stats["probe_304_count"] += 1
                conn.execute(
                    "UPDATE raw_sync_state SET last_probe_at = ?, last_status = ? "
                    "WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
                    (_now_iso(), "304_not_modified", owner, name, stream),
                )
                conn.commit()
                continue

            # 200 — save ETag, check if drain needed
            stats["probe_200_count"] += 1
            new_etag = resp.etag
            conn.execute(
                "UPDATE raw_sync_state SET probe_etag = ?, last_probe_at = ? "
                "WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
                (new_etag, _now_iso(), owner, name, stream),
            )
            conn.commit()

            # Check if newest updated_at > high_water
            probe_body = json.loads(resp.body) if resp.body.strip() else []
            if probe_body:
                newest_updated = probe_body[0].get("updated_at", "")
                hw = state["high_water"]
                if newest_updated <= hw and not force:
                    conn.execute(
                        "UPDATE raw_sync_state SET last_status = ? "
                        "WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
                        ("probe_no_new_data", owner, name, stream),
                    )
                    conn.commit()
                    continue

        except RuntimeError as exc:
            conn.execute(
                "UPDATE raw_sync_state SET last_status = ? "
                "WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
                (f"probe_error: {exc}", owner, name, stream),
            )
            conn.commit()
            continue

        # Phase B: Drain
        try:
            since = _compute_since(state, backfill_days)
            drain_url = (
                f"/repos/{owner}/{name}/{path_suffix}"
                f"?sort=updated&direction=asc&per_page=100&since={since}"
            )
            rows = _gh_api_paginate(drain_url)
            stats["requests_made"] += 1

            max_seen_updated = state["high_water"]
            for row in rows:
                parsed = parser(row, owner, name)
                _ensure_pr_index_from_comment(conn, parsed)

                # Check if the comment already exists
                existing = conn.execute(
                    "SELECT updated_at FROM raw_comments WHERE kind = ? AND id = ?",
                    (parsed["kind"], parsed["id"]),
                ).fetchone()

                upsert_raw_comment(conn, **parsed)

                if existing is None:
                    stats["rows_inserted"] += 1
                else:
                    stats["rows_updated"] += 1

                row_updated = parsed.get("updated_at", "")
                if row_updated > max_seen_updated:
                    max_seen_updated = row_updated

            # Update high_water and mark backfill complete
            conn.execute(
                "UPDATE raw_sync_state SET high_water = ?, initial_backfill_complete = 1, "
                "last_drain_at = ?, last_status = ? "
                "WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
                (max_seen_updated, _now_iso(), "drain_complete", owner, name, stream),
            )
            conn.commit()

        except RuntimeError as exc:
            conn.execute(
                "UPDATE raw_sync_state SET last_status = ? "
                "WHERE repo_owner = ? AND repo_name = ? AND stream = ?",
                (f"drain_error: {exc}", owner, name, stream),
            )
            conn.commit()

    return stats


# ---------------------------------------------------------------------------
# Query API (Task 7)
# ---------------------------------------------------------------------------


def _row_to_comment(row) -> Comment:
    """Convert a ``sqlite3.Row`` to a :class:`Comment` dataclass."""
    return Comment(
        kind=row["kind"],
        id=row["id"],
        repo_owner=row["repo_owner"],
        repo_name=row["repo_name"],
        issue_number=row["issue_number"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        author_login=row["author_login"],
        author_id=row["author_id"],
        body_md=row["body_md"],
        body_sha256=row["body_sha256"],
        payload=row["payload"],
        fetched_at=row["fetched_at"],
        review_id=row["review_id"],
        in_reply_to_id=row["in_reply_to_id"],
        author_assoc=row["author_assoc"],
        diff_hunk=row["diff_hunk"],
        file_path=row["file_path"],
        commit_sha=row["commit_sha"],
        original_commit_sha=row["original_commit_sha"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        side=row["side"],
        deleted_at=row["deleted_at"],
    )


def _build_repo_filter(
    repos: list[tuple[str, str]] | None,
) -> tuple[str, list]:
    """Build a SQL WHERE fragment for repo filtering.

    Returns ``(sql_fragment, params)`` where *sql_fragment* is either empty
    or starts with ``AND``.
    """
    if not repos:
        return ("", [])
    placeholders = ", ".join(["(?, ?)" for _ in repos])
    params = []
    for owner, name in repos:
        params.extend([owner, name])
    return (f"AND (rc.repo_owner, rc.repo_name) IN ({placeholders})", params)


def _high_water_marks(conn) -> dict[str, str]:
    """Return ``{owner/repo: max_high_water}`` from ``raw_sync_state``."""
    rows = conn.execute(
        "SELECT repo_owner, repo_name, MAX(high_water) as hw "
        "FROM raw_sync_state GROUP BY repo_owner, repo_name"
    ).fetchall()
    return {f"{r['repo_owner']}/{r['repo_name']}": r["hw"] for r in rows}


def list_comments_by_author(
    conn,
    author_login: str,
    repos: list[tuple[str, str]] | None = None,
    since: str | None = None,
    until: str | None = None,
    force_sync: bool = False,
) -> QueryResult:
    """Return comments authored by *author_login*."""
    repo_frag, repo_params = _build_repo_filter(repos)

    sql = f"SELECT rc.* FROM raw_comments rc WHERE rc.author_login = ? {repo_frag}"
    params: list = [author_login, *repo_params]

    if since:
        sql += " AND rc.updated_at >= ?"
        params.append(since)
    if until:
        sql += " AND rc.updated_at <= ?"
        params.append(until)

    sql += " ORDER BY rc.updated_at DESC"

    rows = conn.execute(sql, params).fetchall()
    return QueryResult(
        rows=[_row_to_comment(r) for r in rows],
        cache_mode="local_only",
        high_water_marks=_high_water_marks(conn),
    )


def list_comments_by_mention(
    conn,
    mentioned_login: str,
    repos: list[tuple[str, str]] | None = None,
    since: str | None = None,
    until: str | None = None,
    force_sync: bool = False,
) -> QueryResult:
    """Return comments that @mention *mentioned_login*."""
    repo_frag, repo_params = _build_repo_filter(repos)

    sql = (
        "SELECT rc.* FROM raw_comments rc "
        "JOIN derived_mentions dm ON dm.comment_kind = rc.kind AND dm.comment_id = rc.id "
        f"WHERE dm.mentioned_login = ? {repo_frag}"
    )
    params: list = [mentioned_login, *repo_params]

    if since:
        sql += " AND rc.updated_at >= ?"
        params.append(since)
    if until:
        sql += " AND rc.updated_at <= ?"
        params.append(until)

    sql += " ORDER BY rc.updated_at DESC"

    rows = conn.execute(sql, params).fetchall()
    return QueryResult(
        rows=[_row_to_comment(r) for r in rows],
        cache_mode="local_only",
        high_water_marks=_high_water_marks(conn),
    )


def list_comments_matching(
    conn,
    fts_query: str,
    repos: list[tuple[str, str]] | None = None,
    force_sync: bool = False,
) -> QueryResult:
    """Return comments matching *fts_query* via FTS5."""
    repo_frag, repo_params = _build_repo_filter(repos)

    sql = (
        "SELECT rc.* FROM raw_comments_fts fts "
        "JOIN raw_comments rc ON rc.rowid = fts.rowid "
        f"WHERE raw_comments_fts MATCH ? {repo_frag}"
        " ORDER BY rank"
    )
    params: list = [fts_query, *repo_params]

    rows = conn.execute(sql, params).fetchall()
    return QueryResult(
        rows=[_row_to_comment(r) for r in rows],
        cache_mode="local_only",
        high_water_marks=_high_water_marks(conn),
    )


def watched_repos(conn) -> list[WatchedRepo]:
    """Return all rows from ``raw_watched_repos``."""
    rows = conn.execute("SELECT * FROM raw_watched_repos").fetchall()
    return [
        WatchedRepo(
            owner=r["owner"],
            name=r["name"],
            source=r["source"],
            backfill_days=r["backfill_days"],
            added_at=r["added_at"],
            last_discovery_at=r["last_discovery_at"],
        )
        for r in rows
    ]


def ensure_fresh(conn, owner: str, repo: str, max_staleness: int = 900) -> None:
    """If the last drain is older than *max_staleness* seconds, trigger a sync."""
    row = conn.execute(
        "SELECT MIN(last_drain_at) as oldest_drain FROM raw_sync_state "
        "WHERE repo_owner = ? AND repo_name = ?",
        (owner, repo),
    ).fetchone()

    if row is None or row["oldest_drain"] is None:
        sync_repo(conn, owner, repo)
        return

    oldest = datetime.datetime.fromisoformat(row["oldest_drain"].replace("Z", "+00:00"))
    age = (datetime.datetime.now(datetime.UTC) - oldest).total_seconds()
    if age > max_staleness:
        sync_repo(conn, owner, repo)
