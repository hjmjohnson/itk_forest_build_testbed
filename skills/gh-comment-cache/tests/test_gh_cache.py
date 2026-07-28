"""Tests for lib/agent_skills/gh_cache.py — Tasks 2, 3, 4, and 7."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from agent_skills import gh_cache
from agent_skills.gh_cache import (
    Comment,
    QueryResult,
    WatchedRepo,
    _body_sha256,
    _merge_source,
    _now_iso,
    _synthetic_workspace,
    extract_mentions,
    freeze_sweep,
    list_comments_by_author,
    list_comments_by_mention,
    list_comments_matching,
    open_gh_cache,
    unfreeze_pr,
    upsert_pr_index,
    upsert_raw_comment,
    upsert_watched_repo,
    watched_repos,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_cache_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the cache root into a tmpdir for this test."""
    monkeypatch.setenv("AGENT_SKILLS_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path / "cache"


@pytest.fixture
def patched_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch _get_gh_login so tests don't call the real gh CLI."""
    monkeypatch.setattr(gh_cache, "_get_gh_login", lambda: "testuser")


@pytest.fixture
def conn(fake_cache_root: Path, patched_login):
    """Open a fresh gh cache connection for a single test."""
    result = open_gh_cache()
    yield result.connection
    result.connection.close()


# ---------------------------------------------------------------------------
# Task 2: Data models and cache opening
# ---------------------------------------------------------------------------


class TestConstants:
    def test_skill_name(self):
        assert gh_cache.SKILL_NAME == "gh-comment-cache"

    def test_skill_version(self):
        assert gh_cache.SKILL_VERSION == "1.0.0"

    def test_schema_version(self):
        assert gh_cache.SCHEMA_VERSION == 1

    def test_min_budget_default(self):
        assert gh_cache.MIN_BUDGET == 200

    def test_freeze_cooloff_days(self):
        assert gh_cache.FREEZE_COOLOFF_DAYS == 30

    def test_migration_dir_exists(self):
        assert gh_cache._MIGRATION_DIR.is_dir()

    def test_migration_file_exists(self):
        assert (gh_cache._MIGRATION_DIR / "001_init.sql").is_file()


class TestDataclasses:
    def test_watched_repo_constructor(self):
        repo = WatchedRepo(
            owner="octocat",
            name="hello-world",
            source="manual",
            backfill_days=90,
            added_at="2024-01-01T00:00:00+00:00",
        )
        assert repo.owner == "octocat"
        assert repo.last_discovery_at is None

    def test_comment_constructor(self):
        c = Comment(
            kind="issue",
            id=1,
            repo_owner="octocat",
            repo_name="hello-world",
            issue_number=42,
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
            author_login="bob",
            author_id=99,
            body_md="hello",
            body_sha256="abc",
            payload="{}",
            fetched_at="2024-01-01T00:00:00+00:00",
        )
        assert c.diff_hunk is None
        assert c.deleted_at is None

    def test_query_result_defaults(self):
        qr = QueryResult()
        assert qr.rows == []
        assert qr.cache_mode == "hit"
        assert qr.synced_repos == []
        assert qr.high_water_marks == {}

    def test_query_result_custom(self):
        qr = QueryResult(rows=[1, 2], cache_mode="miss")
        assert len(qr.rows) == 2
        assert qr.cache_mode == "miss"


class TestHelpers:
    def test_now_iso_returns_string(self):
        s = _now_iso()
        assert isinstance(s, str)
        assert "T" in s

    def test_body_sha256(self):
        import hashlib

        body = "Hello, world!"
        expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert _body_sha256(body) == expected

    def test_synthetic_workspace_not_git(self):
        ws = _synthetic_workspace("alice")
        assert ws.is_git is False
        assert "alice" in str(ws.normalized_root)

    def test_synthetic_workspace_upstream_url(self):
        ws = _synthetic_workspace("alice")
        assert ws.upstream_url == "github:user:alice"

    def test_synthetic_workspace_fingerprint_stable(self):
        ws1 = _synthetic_workspace("alice")
        ws2 = _synthetic_workspace("alice")
        assert ws1.fingerprint == ws2.fingerprint

    def test_synthetic_workspace_fingerprint_differs_by_login(self):
        ws_alice = _synthetic_workspace("alice")
        ws_bob = _synthetic_workspace("bob")
        assert ws_alice.fingerprint != ws_bob.fingerprint


class TestOpenGhCache:
    def test_creates_expected_tables(self, fake_cache_root: Path, patched_login):
        result = open_gh_cache()
        conn = result.connection
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        assert "raw_watched_repos" in tables
        assert "raw_pr_index" in tables
        assert "raw_comments" in tables
        assert "raw_sync_state" in tables
        assert "derived_mentions" in tables
        assert "derived_sync_run_stats" in tables
        assert "ai_classifications" in tables
        # framework tables
        assert "_meta" in tables
        assert "_workspace" in tables
        assert "_sync_log" in tables

    def test_idempotent_reopen(self, fake_cache_root: Path, patched_login):
        r1 = open_gh_cache()
        r1.connection.close()
        r2 = open_gh_cache()
        # Same path on second open
        assert r1.path == r2.path
        r2.connection.close()


# ---------------------------------------------------------------------------
# Task 3: Upsert functions and @mention extraction
# ---------------------------------------------------------------------------


class TestMentionExtraction:
    def test_basic_mention(self):
        assert extract_mentions("Thanks @alice!") == {"alice"}

    def test_email_not_extracted(self):
        assert extract_mentions("Contact me at user@example.com") == set()

    def test_trailing_punctuation(self):
        # Punctuation after the name should still yield the login
        mentions = extract_mentions("Ping @bob, can you review?")
        assert "bob" in mentions

    def test_multiple_mentions(self):
        result = extract_mentions("@alice and @bob should review")
        assert result == {"alice", "bob"}

    def test_no_mentions(self):
        assert extract_mentions("No mentions here.") == set()

    def test_single_char_login_not_matched(self):
        # GitHub logins must be at least 1 char; single char is valid
        result = extract_mentions("@a is valid")
        assert "a" in result

    def test_mention_at_start_of_string(self):
        result = extract_mentions("@carol please review")
        assert "carol" in result


# Helper to insert a watched repo dependency for tests that need one.
def _add_repo(conn, owner="octocat", name="hello-world"):
    upsert_watched_repo(conn, owner, name, source="manual", backfill_days=90)


def _add_pr(conn, owner="octocat", name="hello-world", number=1, state="open"):
    upsert_pr_index(
        conn,
        repo_owner=owner,
        repo_name=name,
        number=number,
        is_pull=1,
        state=state,
        title="Test PR",
        author_login="octocat",
        created_at="2024-01-01T00:00:00+00:00",
        updated_at="2024-01-01T00:00:00+00:00",
        closed_at=None,
        merged_at=None,
        i_authored=0,
        i_reviewed=0,
        i_mentioned=0,
    )


class TestUpsertWatchedRepo:
    def test_insert_manual(self, conn):
        upsert_watched_repo(conn, "octocat", "hello-world", source="manual", backfill_days=90)
        row = conn.execute(
            "SELECT * FROM raw_watched_repos WHERE owner='octocat' AND name='hello-world'"
        ).fetchone()
        assert row is not None
        assert row["source"] == "manual"
        assert row["backfill_days"] == 90

    def test_auto_then_manual_becomes_both(self, conn):
        upsert_watched_repo(conn, "octocat", "hello-world", source="auto", backfill_days=30)
        upsert_watched_repo(conn, "octocat", "hello-world", source="manual", backfill_days=90)
        row = conn.execute(
            "SELECT source, backfill_days FROM raw_watched_repos WHERE owner='octocat'"
        ).fetchone()
        assert row["source"] == "both"
        assert row["backfill_days"] == 90

    def test_max_backfill_days(self, conn):
        upsert_watched_repo(conn, "octocat", "hello-world", source="manual", backfill_days=60)
        upsert_watched_repo(conn, "octocat", "hello-world", source="manual", backfill_days=120)
        row = conn.execute(
            "SELECT backfill_days FROM raw_watched_repos WHERE owner='octocat'"
        ).fetchone()
        assert row["backfill_days"] == 120

    def test_same_source_stays(self, conn):
        upsert_watched_repo(conn, "octocat", "hello-world", source="auto", backfill_days=90)
        upsert_watched_repo(conn, "octocat", "hello-world", source="auto", backfill_days=90)
        row = conn.execute("SELECT source FROM raw_watched_repos WHERE owner='octocat'").fetchone()
        assert row["source"] == "auto"


class TestMergeSource:
    def test_same_returns_same(self):
        assert _merge_source("manual", "manual") == "manual"
        assert _merge_source("auto", "auto") == "auto"

    def test_different_returns_both(self):
        assert _merge_source("manual", "auto") == "both"
        assert _merge_source("auto", "manual") == "both"


class TestUpsertPrIndex:
    def test_basic_insert(self, conn):
        _add_repo(conn)
        _add_pr(conn)
        row = conn.execute(
            "SELECT * FROM raw_pr_index WHERE repo_owner='octocat' AND number=1"
        ).fetchone()
        assert row is not None
        assert row["title"] == "Test PR"
        assert row["state"] == "open"
        assert row["is_pull"] == 1

    def test_update_state(self, conn):
        _add_repo(conn)
        _add_pr(conn, state="open")
        _add_pr(conn, state="closed")
        row = conn.execute(
            "SELECT state FROM raw_pr_index WHERE repo_owner='octocat' AND number=1"
        ).fetchone()
        assert row["state"] == "closed"

    def test_attention_flags_max(self, conn):
        _add_repo(conn)
        upsert_pr_index(
            conn,
            repo_owner="octocat",
            repo_name="hello-world",
            number=1,
            is_pull=1,
            state="open",
            title="Test PR",
            author_login="octocat",
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
            closed_at=None,
            merged_at=None,
            i_authored=1,
            i_reviewed=0,
            i_mentioned=0,
        )
        upsert_pr_index(
            conn,
            repo_owner="octocat",
            repo_name="hello-world",
            number=1,
            is_pull=1,
            state="open",
            title="Test PR",
            author_login="octocat",
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
            closed_at=None,
            merged_at=None,
            i_authored=0,
            i_reviewed=1,
            i_mentioned=0,
        )
        row = conn.execute(
            "SELECT i_authored, i_reviewed FROM raw_pr_index WHERE number=1"
        ).fetchone()
        # Both flags should be 1 (max of old and new)
        assert row["i_authored"] == 1
        assert row["i_reviewed"] == 1


class TestUpsertComment:
    def test_basic_insert(self, conn):
        _add_repo(conn)
        _add_pr(conn)
        upsert_raw_comment(
            conn,
            "issue",
            101,
            "octocat",
            "hello-world",
            1,
            None,
            None,
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T00:00:00+00:00",
            "alice",
            1001,
            "CONTRIBUTOR",
            "Hello world!",
            "{}",
        )
        row = conn.execute("SELECT * FROM raw_comments WHERE kind='issue' AND id=101").fetchone()
        assert row is not None
        assert row["author_login"] == "alice"
        assert row["body_md"] == "Hello world!"

    def test_idempotent_triple_insert(self, conn):
        _add_repo(conn)
        _add_pr(conn)
        for _ in range(3):
            upsert_raw_comment(
                conn,
                "issue",
                101,
                "octocat",
                "hello-world",
                1,
                None,
                None,
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T00:00:00+00:00",
                "alice",
                1001,
                None,
                "Hello world!",
                "{}",
            )
        count = conn.execute("SELECT COUNT(*) FROM raw_comments").fetchone()[0]
        assert count == 1

    def test_edit_updates_body_and_sha256(self, conn):
        _add_repo(conn)
        _add_pr(conn)
        upsert_raw_comment(
            conn,
            "issue",
            101,
            "octocat",
            "hello-world",
            1,
            None,
            None,
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T00:00:00+00:00",
            "alice",
            1001,
            None,
            "Original body",
            "{}",
        )
        upsert_raw_comment(
            conn,
            "issue",
            101,
            "octocat",
            "hello-world",
            1,
            None,
            None,
            "2024-01-01T00:00:00+00:00",
            "2024-01-02T00:00:00+00:00",
            "alice",
            1001,
            None,
            "Edited body",
            "{}",
        )
        row = conn.execute("SELECT body_md, body_sha256 FROM raw_comments WHERE id=101").fetchone()
        assert row["body_md"] == "Edited body"
        assert row["body_sha256"] == _body_sha256("Edited body")

    def test_mentions_populated(self, conn):
        _add_repo(conn)
        _add_pr(conn)
        upsert_raw_comment(
            conn,
            "issue",
            101,
            "octocat",
            "hello-world",
            1,
            None,
            None,
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T00:00:00+00:00",
            "alice",
            1001,
            None,
            "Thanks @bob for the review!",
            "{}",
        )
        rows = conn.execute(
            "SELECT mentioned_login FROM derived_mentions WHERE comment_id=101"
        ).fetchall()
        logins = {r[0] for r in rows}
        assert "bob" in logins


# ---------------------------------------------------------------------------
# Task 4: FTS5 search and freeze logic
# ---------------------------------------------------------------------------


class TestFTS5:
    def _seed(self, conn):
        _add_repo(conn)
        _add_pr(conn)
        bodies = [
            (201, "The quick brown fox jumps"),
            (202, "Lazy dog sleeping"),
            (203, "SQLite FTS5 is powerful"),
        ]
        for comment_id, body in bodies:
            upsert_raw_comment(
                conn,
                "issue",
                comment_id,
                "octocat",
                "hello-world",
                1,
                None,
                None,
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T00:00:00+00:00",
                "alice",
                1001,
                None,
                body,
                "{}",
            )

    def test_fts_match_finds_correct_comment(self, conn):
        self._seed(conn)
        rows = conn.execute(
            """
            SELECT rc.id, rc.body_md
            FROM raw_comments_fts fts
            JOIN raw_comments rc ON rc.rowid = fts.rowid
            WHERE raw_comments_fts MATCH 'fox'
            """
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == 201

    def test_fts_no_match_returns_empty(self, conn):
        self._seed(conn)
        rows = conn.execute(
            """
            SELECT rc.id
            FROM raw_comments_fts fts
            JOIN raw_comments rc ON rc.rowid = fts.rowid
            WHERE raw_comments_fts MATCH 'unicorn'
            """
        ).fetchall()
        assert rows == []

    def test_body_edit_updates_fts_index(self, conn):
        self._seed(conn)
        # Update comment 201 body to something new
        upsert_raw_comment(
            conn,
            "issue",
            201,
            "octocat",
            "hello-world",
            1,
            None,
            None,
            "2024-01-01T00:00:00+00:00",
            "2024-01-02T00:00:00+00:00",
            "alice",
            1001,
            None,
            "Completely different content about elephants",
            "{}",
        )
        # Old term 'fox' should no longer match this comment
        rows_fox = conn.execute(
            """
            SELECT rc.id FROM raw_comments_fts fts
            JOIN raw_comments rc ON rc.rowid = fts.rowid
            WHERE raw_comments_fts MATCH 'fox'
            """
        ).fetchall()
        assert all(r["id"] != 201 for r in rows_fox)

        # New term 'elephant' should match
        rows_elephant = conn.execute(
            """
            SELECT rc.id FROM raw_comments_fts fts
            JOIN raw_comments rc ON rc.rowid = fts.rowid
            WHERE raw_comments_fts MATCH 'elephant'
            """
        ).fetchall()
        assert any(r["id"] == 201 for r in rows_elephant)


def _iso_days_ago(days: int) -> str:
    dt = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
    return dt.isoformat()


class TestFreeze:
    def _seed_pr(self, conn, number, state, days_ago=None, closed_at=None):
        _add_repo(conn)
        ca = (
            closed_at
            if closed_at is not None
            else (_iso_days_ago(days_ago) if days_ago is not None else None)
        )
        upsert_pr_index(
            conn,
            repo_owner="octocat",
            repo_name="hello-world",
            number=number,
            is_pull=1,
            state=state,
            title=f"PR {number}",
            author_login="octocat",
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
            closed_at=ca,
            merged_at=None,
            i_authored=0,
            i_reviewed=0,
            i_mentioned=0,
        )

    def test_freeze_sweep_old_closed(self, conn):
        self._seed_pr(conn, number=1, state="closed", days_ago=31)
        count = freeze_sweep(conn)
        assert count == 1
        row = conn.execute("SELECT is_frozen FROM raw_pr_index WHERE number=1").fetchone()
        assert row["is_frozen"] == 1

    def test_freeze_sweep_recent_closed_not_frozen(self, conn):
        self._seed_pr(conn, number=2, state="closed", days_ago=10)
        count = freeze_sweep(conn)
        assert count == 0
        row = conn.execute("SELECT is_frozen FROM raw_pr_index WHERE number=2").fetchone()
        assert row["is_frozen"] == 0

    def test_freeze_sweep_open_not_frozen(self, conn):
        self._seed_pr(conn, number=3, state="open", closed_at=None)
        count = freeze_sweep(conn)
        assert count == 0
        row = conn.execute("SELECT is_frozen FROM raw_pr_index WHERE number=3").fetchone()
        assert row["is_frozen"] == 0

    def test_second_sweep_is_noop(self, conn):
        self._seed_pr(conn, number=1, state="closed", days_ago=31)
        freeze_sweep(conn)
        count2 = freeze_sweep(conn)
        assert count2 == 0

    def test_unfreeze_reverses_freeze(self, conn):
        self._seed_pr(conn, number=1, state="closed", days_ago=31)
        freeze_sweep(conn)
        row_before = conn.execute("SELECT is_frozen FROM raw_pr_index WHERE number=1").fetchone()
        assert row_before["is_frozen"] == 1

        unfreeze_pr(conn, "octocat", "hello-world", 1)
        row_after = conn.execute(
            "SELECT is_frozen, frozen_at FROM raw_pr_index WHERE number=1"
        ).fetchone()
        assert row_after["is_frozen"] == 0
        assert row_after["frozen_at"] is None


# ---------------------------------------------------------------------------
# Task 7: Query API
# ---------------------------------------------------------------------------


class TestQueryAPI:
    """Tests for query functions: list_comments_by_author, list_comments_by_mention,
    list_comments_matching, watched_repos."""

    def _seed(self, conn):
        """Seed the database with 3 comments across 2 authors."""
        _add_repo(conn, owner="ISC", name="ITK")
        _add_pr(conn, owner="ISC", name="ITK", number=6040)

        # Comment 1001: N-Dekker, mentions hjmjohnson
        upsert_raw_comment(
            conn,
            "issue",
            1001,
            "ISC",
            "ITK",
            6040,
            None,
            None,
            "2026-03-01T00:00:00Z",
            "2026-03-15T00:00:00Z",
            "N-Dekker",
            42,
            "CONTRIBUTOR",
            "const correctness matters @hjmjohnson",
            "{}",
        )

        # Comment 1002: hjmjohnson, mentions N-Dekker
        upsert_raw_comment(
            conn,
            "issue",
            1002,
            "ISC",
            "ITK",
            6040,
            None,
            None,
            "2026-03-16T00:00:00Z",
            "2026-03-16T00:00:00Z",
            "hjmjohnson",
            99,
            "MEMBER",
            "Fixed in next commit @N-Dekker",
            "{}",
        )

        # Comment 1003: N-Dekker, no mentions
        upsert_raw_comment(
            conn,
            "issue",
            1003,
            "ISC",
            "ITK",
            6040,
            None,
            None,
            "2026-03-17T00:00:00Z",
            "2026-03-17T00:00:00Z",
            "N-Dekker",
            42,
            "CONTRIBUTOR",
            "cmake build is broken",
            "{}",
        )

    def test_list_by_author(self, conn):
        self._seed(conn)
        result = list_comments_by_author(conn, "N-Dekker")
        assert len(result.rows) == 2
        assert all(r.author_login == "N-Dekker" for r in result.rows)
        assert result.cache_mode == "local_only"

    def test_list_by_author_with_repo_filter(self, conn):
        self._seed(conn)
        result = list_comments_by_author(conn, "N-Dekker", repos=[("ISC", "ITK")])
        assert len(result.rows) == 2

        # Filter with a non-existent repo should return empty
        result2 = list_comments_by_author(conn, "N-Dekker", repos=[("OTHER", "REPO")])
        assert len(result2.rows) == 0

    def test_list_by_mention(self, conn):
        self._seed(conn)
        result = list_comments_by_mention(conn, "hjmjohnson")
        assert len(result.rows) == 1
        assert result.rows[0].id == 1001

    def test_list_matching_found(self, conn):
        self._seed(conn)
        result = list_comments_matching(conn, "const correctness")
        assert len(result.rows) == 1
        assert result.rows[0].id == 1001

    def test_list_matching_empty(self, conn):
        self._seed(conn)
        result = list_comments_matching(conn, "nonexistent")
        assert len(result.rows) == 0

    def test_watched_repos(self, conn):
        self._seed(conn)
        repos = watched_repos(conn)
        assert len(repos) >= 1
        owners = {r.owner for r in repos}
        assert "ISC" in owners
