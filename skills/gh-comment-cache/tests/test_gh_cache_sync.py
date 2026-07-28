"""Tests for gh-comment-cache sync engine — Tasks 5, 6, and 7."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agent_skills import gh_cache
from agent_skills.gh_cache import (
    GhApiResponse,
    _check_rate_budget,
    _extract_issue_number,
    _parse_include_response,
    discover_watched_repos,
    open_gh_cache,
    parse_issue_comment,
    parse_review_comment,
    sync_repo,
    upsert_watched_repo,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures" / "gh_api"


@pytest.fixture
def fake_cache_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the cache root into a tmpdir for this test."""
    monkeypatch.setenv("AGENT_SKILLS_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path / "cache"


@pytest.fixture
def gh_login(monkeypatch: pytest.MonkeyPatch) -> str:
    """Monkeypatch _get_gh_login so tests don't call the real gh CLI."""
    login = "hjmjohnson"
    monkeypatch.setattr(gh_cache, "_get_gh_login", lambda: login)
    return login


@pytest.fixture
def db(fake_cache_root: Path, gh_login: str):
    """Open a fresh gh cache connection for a single test."""
    result = open_gh_cache()
    yield result.connection
    result.connection.close()


# ---------------------------------------------------------------------------
# Task 5: gh api wrapper and response parsing
# ---------------------------------------------------------------------------


class TestGhApiWrapper:
    def test_parse_304_response(self):
        raw = (FIXTURES / "probe_304.txt").read_text()
        resp = _parse_include_response(raw)
        assert resp.status == 304
        assert resp.etag == '"abc123"'
        assert resp.rate_remaining == 4990
        assert resp.body.strip() == ""

    def test_parse_200_response(self):
        raw = (FIXTURES / "probe_200.txt").read_text()
        resp = _parse_include_response(raw)
        assert resp.status == 200
        assert resp.etag == '"def456"'
        assert resp.rate_remaining == 4989
        body = json.loads(resp.body)
        assert isinstance(body, list)
        assert body[0]["id"] == 99999
        assert body[0]["user"]["login"] == "N-Dekker"


class TestParseComment:
    def test_parse_issue_comment(self):
        raw = (FIXTURES / "probe_200.txt").read_text()
        resp = _parse_include_response(raw)
        rows = json.loads(resp.body)
        parsed = parse_issue_comment(rows[0], "ISC", "ITK")
        assert parsed["kind"] == "issue"
        assert parsed["id"] == 99999
        assert parsed["issue_number"] == 6040
        assert parsed["author_login"] == "N-Dekker"
        assert parsed["body_md"] == "Please review @hjmjohnson"
        assert parsed["repo_owner"] == "ISC"
        assert parsed["repo_name"] == "ITK"

    def test_extract_issue_number(self):
        url = "https://api.github.com/repos/ISC/ITK/issues/6040"
        assert _extract_issue_number(url) == 6040

    def test_parse_review_comment(self):
        row = {
            "id": 55555,
            "pull_request_url": "https://api.github.com/repos/ISC/ITK/pulls/6040",
            "pull_request_review_id": 777,
            "in_reply_to_id": 444,
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-04-10T00:00:00Z",
            "user": {"login": "reviewer", "id": 88},
            "author_association": "MEMBER",
            "body": "Looks good",
            "diff_hunk": "@@ -10,3 +10,4 @@",
            "path": "src/main.cpp",
            "commit_id": "abc123",
            "original_commit_id": "def456",
            "start_line": 10,
            "line": 12,
            "side": "RIGHT",
        }
        parsed = parse_review_comment(row, "ISC", "ITK")
        assert parsed["kind"] == "review"
        assert parsed["id"] == 55555
        assert parsed["issue_number"] == 6040
        assert parsed["review_id"] == 777
        assert parsed["in_reply_to_id"] == 444
        assert parsed["diff_hunk"] == "@@ -10,3 +10,4 @@"
        assert parsed["file_path"] == "src/main.cpp"
        assert parsed["commit_sha"] == "abc123"
        assert parsed["original_commit_sha"] == "def456"
        assert parsed["start_line"] == 10
        assert parsed["end_line"] == 12
        assert parsed["side"] == "RIGHT"


class TestRateLimitProtection:
    def test_low_budget_raises(self):
        raw = (FIXTURES / "rate_limited.txt").read_text()
        resp = _parse_include_response(raw)
        with pytest.raises(RuntimeError, match="rate limit too low"):
            _check_rate_budget(resp, min_budget=200)

    def test_sufficient_budget_passes(self):
        raw = (FIXTURES / "probe_200.txt").read_text()
        resp = _parse_include_response(raw)
        # Should not raise — 4989 remaining is well above 200
        _check_rate_budget(resp, min_budget=200)

    def test_none_rate_remaining_passes(self):
        resp = GhApiResponse(status=200, etag=None, rate_remaining=None, rate_reset=None, body="")
        # Should not raise when rate_remaining is None
        _check_rate_budget(resp, min_budget=200)


# ---------------------------------------------------------------------------
# Task 6: Sync engine tests
# ---------------------------------------------------------------------------


class TestDiscoverWatchedRepos:
    def test_discover_persists_repos(self, db, monkeypatch):
        fixture_data = (FIXTURES / "search_prs_author.json").read_text()

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.stdout = fixture_data
            result.stderr = ""
            result.returncode = 0
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)
        repos = discover_watched_repos(db, gh_login="hjmjohnson")

        assert len(repos) >= 1
        owners = {r.owner for r in repos}
        assert "ISC" in owners

        # PR should be indexed
        row = db.execute(
            "SELECT * FROM raw_pr_index WHERE repo_owner='ISC' AND repo_name='ITK' AND number=6040"
        ).fetchone()
        assert row is not None
        assert row["title"] == "Fix const issue"


class TestSyncRepo:
    def _setup_repo(self, db):
        """Add a watched repo for testing."""
        upsert_watched_repo(db, "ISC", "ITK", source="auto", backfill_days=90)

    def test_probe_304_no_drain(self, db, monkeypatch):
        self._setup_repo(db)
        raw_304 = (FIXTURES / "probe_304.txt").read_text()

        def fake_include(path, *, etag=None):
            return _parse_include_response(raw_304)

        paginate_called = False

        def fake_paginate(path):
            nonlocal paginate_called
            paginate_called = True
            return []

        monkeypatch.setattr("agent_skills.gh_cache._gh_api_include", fake_include)
        monkeypatch.setattr("agent_skills.gh_cache._gh_api_paginate", fake_paginate)

        stats = sync_repo(db, "ISC", "ITK")
        assert stats["probe_304_count"] >= 1
        assert not paginate_called

    def test_probe_200_triggers_drain(self, db, monkeypatch):
        self._setup_repo(db)
        raw_200 = (FIXTURES / "probe_200.txt").read_text()
        drain_data = json.loads((FIXTURES / "drain_page1.json").read_text())

        def fake_include(path, *, etag=None):
            return _parse_include_response(raw_200)

        def fake_paginate(path):
            # Only return issue comment data for the issue_comments stream
            if "issues/comments" in path:
                return drain_data
            return []

        monkeypatch.setattr("agent_skills.gh_cache._gh_api_include", fake_include)
        monkeypatch.setattr("agent_skills.gh_cache._gh_api_paginate", fake_paginate)

        stats = sync_repo(db, "ISC", "ITK")
        assert stats["probe_200_count"] >= 1

        # Comments should be in the DB
        comments = db.execute(
            "SELECT * FROM raw_comments WHERE repo_owner='ISC' AND repo_name='ITK'"
        ).fetchall()
        assert len(comments) >= 2

        # Check specific comment
        c = db.execute("SELECT * FROM raw_comments WHERE id=99999").fetchone()
        assert c is not None
        assert c["author_login"] == "N-Dekker"

    def test_high_water_advances(self, db, monkeypatch):
        self._setup_repo(db)
        raw_200 = (FIXTURES / "probe_200.txt").read_text()
        drain_data = json.loads((FIXTURES / "drain_page1.json").read_text())

        def fake_include(path, *, etag=None):
            return _parse_include_response(raw_200)

        def fake_paginate(path):
            if "issues/comments" in path:
                return drain_data
            return []

        monkeypatch.setattr("agent_skills.gh_cache._gh_api_include", fake_include)
        monkeypatch.setattr("agent_skills.gh_cache._gh_api_paginate", fake_paginate)

        sync_repo(db, "ISC", "ITK")

        # Check that high_water advanced and backfill is complete
        row = db.execute(
            "SELECT high_water, initial_backfill_complete FROM raw_sync_state "
            "WHERE repo_owner='ISC' AND repo_name='ITK' AND stream='issue_comments'"
        ).fetchone()
        assert row is not None
        assert row["high_water"] > "1970-01-01"
        assert row["initial_backfill_complete"] == 1
