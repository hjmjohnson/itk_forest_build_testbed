-- Discourse integration — extends the gh-comment-cache DB with Discourse
-- topic and post tables, enabling cross-source queries via UNION ALL
-- on the FTS5 tables.
--
-- Discourse data model:
--   Site -> Categories -> Topics -> Posts
--   A Topic is like an Issue/PR; a Post is like a Comment.

-- =========================================================================
-- Layer 1: raw_* — exact data from Discourse JSON API.
-- =========================================================================

CREATE TABLE IF NOT EXISTS raw_discourse_sites (
    base_url        TEXT    PRIMARY KEY,    -- e.g. 'https://discourse.itk.org'
    site_name       TEXT    NOT NULL,       -- e.g. 'ITK Discourse'
    added_at        TEXT    NOT NULL,
    last_sync_at    TEXT
);

CREATE TABLE IF NOT EXISTS raw_discourse_categories (
    site_url        TEXT    NOT NULL,
    id              INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    slug            TEXT    NOT NULL,
    topic_count     INTEGER NOT NULL DEFAULT 0,
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (site_url, id),
    FOREIGN KEY (site_url) REFERENCES raw_discourse_sites(base_url)
);

CREATE TABLE IF NOT EXISTS raw_discourse_topics (
    site_url        TEXT    NOT NULL,
    id              INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    slug            TEXT    NOT NULL,
    category_id     INTEGER,
    tags            TEXT,                   -- JSON array of tag names
    author_username TEXT    NOT NULL,
    posts_count     INTEGER NOT NULL DEFAULT 0,
    views           INTEGER NOT NULL DEFAULT 0,
    like_count      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    last_posted_at  TEXT,
    closed          INTEGER NOT NULL DEFAULT 0,
    archived        INTEGER NOT NULL DEFAULT 0,
    is_frozen       INTEGER NOT NULL DEFAULT 0,
    frozen_at       TEXT,
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (site_url, id),
    FOREIGN KEY (site_url) REFERENCES raw_discourse_sites(base_url)
);

CREATE INDEX IF NOT EXISTS idx_discourse_topics_last_posted
    ON raw_discourse_topics (site_url, last_posted_at);
CREATE INDEX IF NOT EXISTS idx_discourse_topics_category
    ON raw_discourse_topics (site_url, category_id);
CREATE INDEX IF NOT EXISTS idx_discourse_topics_frozen
    ON raw_discourse_topics (site_url, is_frozen);

CREATE TABLE IF NOT EXISTS raw_discourse_posts (
    site_url        TEXT    NOT NULL,
    id              INTEGER NOT NULL,
    topic_id        INTEGER NOT NULL,
    post_number     INTEGER NOT NULL,
    author_username TEXT    NOT NULL,
    reply_to_post_number INTEGER,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    body_cooked     TEXT    NOT NULL,       -- HTML rendered by Discourse
    body_md         TEXT    NOT NULL,       -- Stripped to plain text for FTS
    body_sha256     TEXT    NOT NULL,
    like_count      INTEGER NOT NULL DEFAULT 0,
    reads           INTEGER NOT NULL DEFAULT 0,
    payload         TEXT    NOT NULL,       -- Full JSON for future use
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (site_url, id),
    FOREIGN KEY (site_url, topic_id)
        REFERENCES raw_discourse_topics(site_url, id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_discourse_posts_topic
    ON raw_discourse_posts (site_url, topic_id, post_number);
CREATE INDEX IF NOT EXISTS idx_discourse_posts_author
    ON raw_discourse_posts (author_username, created_at);
CREATE INDEX IF NOT EXISTS idx_discourse_posts_updated
    ON raw_discourse_posts (site_url, updated_at);

CREATE TABLE IF NOT EXISTS raw_discourse_sync_state (
    site_url        TEXT    NOT NULL,
    stream          TEXT    NOT NULL CHECK (stream IN ('latest_topics', 'topic_posts')),
    high_water      TEXT    NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    -- For latest_topics: last page fully drained
    last_page       INTEGER NOT NULL DEFAULT 0,
    initial_backfill_complete INTEGER NOT NULL DEFAULT 0,
    last_sync_at    TEXT,
    last_status     TEXT,
    PRIMARY KEY (site_url, stream),
    FOREIGN KEY (site_url) REFERENCES raw_discourse_sites(base_url)
);

-- =========================================================================
-- Layer 2: derived_* — parsed from raw; deterministic.
-- =========================================================================

CREATE TABLE IF NOT EXISTS derived_discourse_mentions (
    site_url        TEXT    NOT NULL,
    post_id         INTEGER NOT NULL,
    mentioned_username TEXT  NOT NULL,
    PRIMARY KEY (site_url, post_id, mentioned_username),
    FOREIGN KEY (site_url, post_id)
        REFERENCES raw_discourse_posts(site_url, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_discourse_mentions_user
    ON derived_discourse_mentions (mentioned_username);

-- FTS5 for Discourse posts — same tokenizer as GitHub comments for
-- consistent cross-source search behavior.
CREATE VIRTUAL TABLE IF NOT EXISTS raw_discourse_fts USING fts5(
    body_md,
    site_url UNINDEXED,
    post_id UNINDEXED,
    topic_id UNINDEXED,
    content='raw_discourse_posts',
    content_rowid='rowid',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS raw_discourse_posts_ai AFTER INSERT ON raw_discourse_posts BEGIN
    INSERT INTO raw_discourse_fts(rowid, body_md, site_url, post_id, topic_id)
    VALUES (new.rowid, new.body_md, new.site_url, new.id, new.topic_id);
END;
CREATE TRIGGER IF NOT EXISTS raw_discourse_posts_ad AFTER DELETE ON raw_discourse_posts BEGIN
    INSERT INTO raw_discourse_fts(raw_discourse_fts, rowid, body_md, site_url, post_id, topic_id)
    VALUES ('delete', old.rowid, old.body_md, old.site_url, old.id, old.topic_id);
END;
CREATE TRIGGER IF NOT EXISTS raw_discourse_posts_au AFTER UPDATE OF body_md ON raw_discourse_posts BEGIN
    INSERT INTO raw_discourse_fts(raw_discourse_fts, rowid, body_md, site_url, post_id, topic_id)
    VALUES ('delete', old.rowid, old.body_md, old.site_url, old.id, old.topic_id);
    INSERT INTO raw_discourse_fts(rowid, body_md, site_url, post_id, topic_id)
    VALUES (new.rowid, new.body_md, new.site_url, new.id, new.topic_id);
END;

-- =========================================================================
-- Cross-source search view — unifies GitHub and Discourse FTS results.
-- =========================================================================

CREATE VIEW IF NOT EXISTS v_unified_search AS
SELECT
    'github' AS source,
    rc.repo_owner || '/' || rc.repo_name AS origin,
    rc.issue_number AS thread_id,
    pi.title AS thread_title,
    rc.kind AS post_type,
    rc.id AS post_id,
    rc.author_login AS author,
    rc.created_at,
    rc.body_md,
    'https://github.com/' || rc.repo_owner || '/' || rc.repo_name ||
        CASE WHEN rc.kind = 'issue'
            THEN '/issues/' ELSE '/pull/' END ||
        rc.issue_number || '#issuecomment-' || rc.id AS url
FROM raw_comments rc
LEFT JOIN raw_pr_index pi
    ON pi.repo_owner = rc.repo_owner
    AND pi.repo_name = rc.repo_name
    AND pi.number = rc.issue_number

UNION ALL

SELECT
    'discourse' AS source,
    dp.site_url AS origin,
    dp.topic_id AS thread_id,
    dt.title AS thread_title,
    'post' AS post_type,
    dp.id AS post_id,
    dp.author_username AS author,
    dp.created_at,
    dp.body_md,
    dp.site_url || '/t/' || dt.slug || '/' || dt.id ||
        '/' || dp.post_number AS url
FROM raw_discourse_posts dp
LEFT JOIN raw_discourse_topics dt
    ON dt.site_url = dp.site_url
    AND dt.id = dp.topic_id;
