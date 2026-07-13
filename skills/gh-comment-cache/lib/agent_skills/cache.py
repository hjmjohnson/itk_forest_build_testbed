"""SQLite cache helpers (§5, Phase 1 skeleton).

Every cache DB managed by agent-skills must carry three meta tables:
`_meta`, `_workspace`, `_sync_log`. This module opens (or creates) a cache
file at the canonical location, installs the mandatory schema and pragmas,
and hands back a plain `sqlite3.Connection` for the skill to use.

Per-skill migrations live in `skills/<skill>/migrations/NNN_description.sql`;
they are applied in order, each bumping `_meta.schema_version`.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from agent_skills.workspace import Workspace

#: Mandatory PRAGMA statements set on every connection.
REQUIRED_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA mmap_size = 30000000000",
)

#: DDL for the mandatory meta tables. Applied on first open only.
META_DDL: str = """
CREATE TABLE IF NOT EXISTS _meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS _workspace (
    workspace_id     TEXT PRIMARY KEY,
    normalized_root  TEXT NOT NULL,
    upstream_url     TEXT,
    origin_url       TEXT,
    is_git           INTEGER NOT NULL,
    first_seen_at    TEXT NOT NULL,
    last_synced_at   TEXT
);

CREATE TABLE IF NOT EXISTS _sync_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    source_revision  TEXT,
    item_count       INTEGER,
    bytes_processed  INTEGER,
    success          INTEGER NOT NULL,
    error_message    TEXT
);
"""


def _cache_root() -> Path:
    """Return the OS-standard base for agent-skills caches."""
    override = os.environ.get("AGENT_SKILLS_CACHE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return (base / "agent-skills").resolve()


def cache_path(skill: str, workspace: Workspace) -> Path:
    """Return the canonical path for this skill+workspace's cache DB."""
    return _cache_root() / skill / workspace.fingerprint / "cache.sqlite"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


@dataclass(frozen=True)
class CacheOpenResult:
    """Returned by `open_cache` — includes both the connection and its path."""

    connection: sqlite3.Connection
    path: Path


def open_cache(
    skill: str,
    skill_version: str,
    workspace: Workspace,
    *,
    schema_version: int = 1,
    derivation_version: int = 0,
) -> CacheOpenResult:
    """Open (or create) the cache DB for `skill` + `workspace`.

    On a fresh database, this installs the required meta tables, sets the
    required pragmas, seeds `_meta` and `_workspace`, and returns a live
    connection. On an existing database it updates `_meta.last_accessed_at`.

    Phase 1 scaffold: does NOT yet apply per-skill migrations — that's added
    when the dir-file-index migration lands (§8 Phase 5).
    """
    path = cache_path(skill, workspace)
    path.parent.mkdir(parents=True, exist_ok=True)

    is_new = not path.exists()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for pragma in REQUIRED_PRAGMAS:
        conn.execute(pragma)

    if is_new:
        conn.executescript(META_DDL)
        now = _now_iso()
        conn.executemany(
            "INSERT INTO _meta (key, value) VALUES (?, ?)",
            [
                ("schema_version", str(schema_version)),
                ("derivation_version", str(derivation_version)),
                ("skill_name", skill),
                ("skill_version", skill_version),
                ("created_at", now),
                ("last_accessed_at", now),
            ],
        )
        conn.execute(
            """
            INSERT INTO _workspace (
                workspace_id, normalized_root, upstream_url, origin_url,
                is_git, first_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workspace.fingerprint,
                str(workspace.normalized_root),
                workspace.upstream_url,
                workspace.origin_url,
                1 if workspace.is_git else 0,
                now,
            ),
        )
        conn.commit()
    else:
        conn.execute(
            "UPDATE _meta SET value = ? WHERE key = 'last_accessed_at'",
            (_now_iso(),),
        )
        conn.commit()

    return CacheOpenResult(connection=conn, path=path)
