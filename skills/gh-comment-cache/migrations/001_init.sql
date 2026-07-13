-- gh-comment-cache schema — skill-owned layout.
--
-- The framework's mandatory _meta, _workspace, and _sync_log tables are
-- installed automatically by agent_skills.cache.open_cache() and are not
-- repeated here.

-- =========================================================================
-- Layer 1: raw_* — exact bytes from GitHub. Never hand-edited.
-- =========================================================================

CREATE TABLE raw_watched_repos (
    owner           TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    source          TEXT    NOT NULL CHECK (source IN ('auto', 'manual', 'both')),
    backfill_days   INTEGER NOT NULL DEFAULT 90,
    added_at        TEXT    NOT NULL,
    last_discovery_at TEXT,
    PRIMARY KEY (owner, name)
);

CREATE TABLE raw_pr_index (
    repo_owner      TEXT    NOT NULL,
    repo_name       TEXT    NOT NULL,
    number          INTEGER NOT NULL,
    is_pull         INTEGER NOT NULL CHECK (is_pull IN (0, 1)),
    state           TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    author_login    TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    closed_at       TEXT,
    merged_at       TEXT,
    is_frozen       INTEGER NOT NULL DEFAULT 0 CHECK (is_frozen IN (0, 1)),
    frozen_at       TEXT,
    last_seen_at    TEXT    NOT NULL,
    i_authored      INTEGER NOT NULL DEFAULT 0,
    i_reviewed      INTEGER NOT NULL DEFAULT 0,
    i_mentioned     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (repo_owner, repo_name, number),
    FOREIGN KEY (repo_owner, repo_name)
        REFERENCES raw_watched_repos(owner, name)
);

CREATE INDEX idx_pr_index_frozen
    ON raw_pr_index (repo_owner, repo_name, is_frozen);
CREATE INDEX idx_pr_index_state_closed
    ON raw_pr_index (state, closed_at) WHERE is_frozen = 0;
CREATE INDEX idx_pr_index_attention
    ON raw_pr_index (i_authored, i_reviewed, i_mentioned);

CREATE TABLE raw_comments (
    kind            TEXT    NOT NULL CHECK (kind IN ('issue', 'review', 'review_body')),
    id              INTEGER NOT NULL,
    repo_owner      TEXT    NOT NULL,
    repo_name       TEXT    NOT NULL,
    issue_number    INTEGER NOT NULL,
    review_id       INTEGER,
    in_reply_to_id  INTEGER,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    author_login    TEXT    NOT NULL,
    author_id       INTEGER NOT NULL,
    author_assoc    TEXT,
    body_md         TEXT    NOT NULL,
    body_sha256     TEXT    NOT NULL,
    diff_hunk       TEXT,
    file_path       TEXT,
    commit_sha      TEXT,
    original_commit_sha TEXT,
    start_line      INTEGER,
    end_line        INTEGER,
    side            TEXT,
    payload         TEXT    NOT NULL,
    fetched_at      TEXT    NOT NULL,
    deleted_at      TEXT,
    PRIMARY KEY (kind, id),
    FOREIGN KEY (repo_owner, repo_name, issue_number)
        REFERENCES raw_pr_index(repo_owner, repo_name, number)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX idx_comments_repo_updated
    ON raw_comments (repo_owner, repo_name, updated_at);
CREATE INDEX idx_comments_pr
    ON raw_comments (repo_owner, repo_name, issue_number, kind, created_at);
CREATE INDEX idx_comments_author
    ON raw_comments (author_login, created_at);
CREATE INDEX idx_comments_author_repo
    ON raw_comments (author_login, repo_owner, repo_name);
CREATE INDEX idx_comments_live
    ON raw_comments (repo_owner, repo_name, issue_number)
    WHERE deleted_at IS NULL;

CREATE TABLE raw_sync_state (
    repo_owner      TEXT    NOT NULL,
    repo_name       TEXT    NOT NULL,
    stream          TEXT    NOT NULL CHECK (stream IN ('issue_comments', 'review_comments')),
    probe_url       TEXT    NOT NULL,
    probe_etag      TEXT,
    high_water      TEXT    NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    initial_backfill_complete INTEGER NOT NULL DEFAULT 0,
    last_probe_at   TEXT,
    last_drain_at   TEXT,
    last_status     TEXT,
    PRIMARY KEY (repo_owner, repo_name, stream),
    FOREIGN KEY (repo_owner, repo_name)
        REFERENCES raw_watched_repos(owner, name)
);

-- =========================================================================
-- Layer 2: derived_* — parsed from raw; deterministic; rebuildable.
-- =========================================================================

CREATE TABLE derived_mentions (
    comment_kind    TEXT    NOT NULL,
    comment_id      INTEGER NOT NULL,
    mentioned_login TEXT    NOT NULL,
    PRIMARY KEY (comment_kind, comment_id, mentioned_login),
    FOREIGN KEY (comment_kind, comment_id) REFERENCES raw_comments(kind, id) ON DELETE CASCADE
);
CREATE INDEX idx_mentions_login
    ON derived_mentions (mentioned_login, comment_kind);

CREATE VIRTUAL TABLE raw_comments_fts USING fts5(
    body_md,
    comment_kind UNINDEXED,
    comment_id UNINDEXED,
    content='raw_comments',
    content_rowid='rowid',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER raw_comments_ai AFTER INSERT ON raw_comments BEGIN
    INSERT INTO raw_comments_fts(rowid, body_md, comment_kind, comment_id)
    VALUES (new.rowid, new.body_md, new.kind, new.id);
END;
CREATE TRIGGER raw_comments_ad AFTER DELETE ON raw_comments BEGIN
    INSERT INTO raw_comments_fts(raw_comments_fts, rowid, body_md, comment_kind, comment_id)
    VALUES ('delete', old.rowid, old.body_md, old.kind, old.id);
END;
CREATE TRIGGER raw_comments_au AFTER UPDATE OF body_md ON raw_comments BEGIN
    INSERT INTO raw_comments_fts(raw_comments_fts, rowid, body_md, comment_kind, comment_id)
    VALUES ('delete', old.rowid, old.body_md, old.kind, old.id);
    INSERT INTO raw_comments_fts(rowid, body_md, comment_kind, comment_id)
    VALUES (new.rowid, new.body_md, new.kind, new.id);
END;

CREATE TABLE derived_sync_run_stats (
    sync_log_id     INTEGER PRIMARY KEY,
    repos_attempted INTEGER NOT NULL,
    repos_succeeded INTEGER NOT NULL,
    probe_304_count INTEGER NOT NULL,
    probe_200_count INTEGER NOT NULL,
    rows_inserted   INTEGER NOT NULL,
    rows_updated    INTEGER NOT NULL,
    requests_made   INTEGER NOT NULL,
    rate_limit_remaining_after INTEGER,
    FOREIGN KEY (sync_log_id) REFERENCES _sync_log(id) ON DELETE CASCADE
);

-- =========================================================================
-- Layer 3: ai_* — AI-generated labels. Discardable. v1 schema only.
-- =========================================================================

CREATE TABLE ai_classifications (
    comment_kind    TEXT    NOT NULL,
    comment_id      INTEGER NOT NULL,
    classifier_name TEXT    NOT NULL,
    label           TEXT    NOT NULL,
    confidence      REAL,
    rationale       TEXT,
    model           TEXT,
    body_sha256_at_classification TEXT NOT NULL,
    classified_at   TEXT    NOT NULL,
    PRIMARY KEY (comment_kind, comment_id, classifier_name, label),
    FOREIGN KEY (comment_kind, comment_id)
        REFERENCES raw_comments(kind, id) ON DELETE CASCADE
);
CREATE INDEX idx_classifications_classifier
    ON ai_classifications (classifier_name, label);
CREATE INDEX idx_classifications_stale
    ON ai_classifications (comment_kind, comment_id, body_sha256_at_classification);
