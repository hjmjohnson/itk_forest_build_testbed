#!/usr/bin/env python3
"""gh_cache_sync.py — CLI wrapper for gh-comment-cache sync operations.

Subcommands
-----------
sync         Sync all watched repos (or a single repo with --repo).
add-repo     Add a repo to the watched set.
remove-repo  Remove a repo from the watched set.
refresh      Unfreeze a specific PR so it will be re-synced.
status       Show watched repos, comment count, frozen count, DB path, last sync states.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_nwo(value: str) -> tuple[str, str]:
    """Parse 'OWNER/REPO' into (owner, name).  Exits on bad input."""
    parts = value.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        print(f"ERROR: expected OWNER/REPO, got {value!r}", file=sys.stderr)
        sys.exit(1)
    return parts[0], parts[1]


def _parse_pr_ref(value: str) -> tuple[str, str, int]:
    """Parse 'OWNER/REPO#NUMBER' into (owner, name, number).  Exits on bad input."""
    if "#" not in value:
        print(f"ERROR: expected OWNER/REPO#NUMBER, got {value!r}", file=sys.stderr)
        sys.exit(1)
    nwo, _, num_str = value.rpartition("#")
    try:
        number = int(num_str)
    except ValueError:
        print(f"ERROR: PR number must be an integer, got {num_str!r}", file=sys.stderr)
        sys.exit(1)
    owner, name = _parse_nwo(nwo)
    return owner, name, number


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_sync(args: argparse.Namespace) -> None:
    """Sync watched repos (or a single repo if --repo is given)."""
    from agent_skills.gh_cache import (  # noqa: PLC0415
        discover_watched_repos,
        freeze_sweep,
        open_gh_cache,
        sync_repo,
        upsert_watched_repo,
        watched_repos,
    )

    result = open_gh_cache()
    conn = result.connection

    try:
        # Always run freeze_sweep first
        frozen_count = freeze_sweep(conn)
        if frozen_count:
            print(f"Froze {frozen_count} newly-eligible PR(s).")

        if args.repo:
            owner, name = _parse_nwo(args.repo)
            # Ensure the repo is in the watched set
            upsert_watched_repo(conn, owner, name, source="manual", backfill_days=365)
            repos_to_sync = [(owner, name)]
        else:
            # Auto-discover then sync all
            discover_watched_repos(conn)
            repos_to_sync = [(r.owner, r.name) for r in watched_repos(conn)]

        if not repos_to_sync:
            print("No watched repos found.")
            return

        total_inserted = 0
        total_updated = 0
        total_requests = 0

        for owner, name in repos_to_sync:
            print(f"  Syncing {owner}/{name} ...", end=" ", flush=True)
            try:
                stats = sync_repo(conn, owner, name, force=args.force)
                inserted = stats.get("rows_inserted", 0)
                updated = stats.get("rows_updated", 0)
                requests = stats.get("requests_made", 0)
                frozen = stats.get("probe_304_count", 0)
                print(
                    f"+{inserted} new, ~{updated} updated, "
                    f"{requests} request(s), {frozen} 304(s)"
                )
                total_inserted += inserted
                total_updated += updated
                total_requests += requests
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")

        print(
            f"\nTotal: +{total_inserted} new, ~{total_updated} updated, "
            f"{total_requests} request(s) across {len(repos_to_sync)} repo(s)."
        )
    finally:
        conn.close()


def cmd_add_repo(args: argparse.Namespace) -> None:
    """Add a repo to the watched set."""
    from agent_skills.gh_cache import open_gh_cache, upsert_watched_repo  # noqa: PLC0415

    owner, name = _parse_nwo(args.repo)
    result = open_gh_cache()
    conn = result.connection
    try:
        upsert_watched_repo(conn, owner, name, source="manual", backfill_days=args.backfill_days)
        print(f"Added {owner}/{name} to watched repos (backfill_days={args.backfill_days}).")
    finally:
        conn.close()


def cmd_remove_repo(args: argparse.Namespace) -> None:
    """Remove a repo from the watched set (manual entries only)."""
    from agent_skills.gh_cache import open_gh_cache  # noqa: PLC0415

    owner, name = _parse_nwo(args.repo)
    result = open_gh_cache()
    conn = result.connection
    try:
        row = conn.execute(
            "SELECT source FROM raw_watched_repos WHERE owner = ? AND name = ?",
            (owner, name),
        ).fetchone()
        if row is None:
            print(f"{owner}/{name} is not in the watched set.")
            return

        source = row["source"]
        if source == "manual":
            conn.execute(
                "DELETE FROM raw_watched_repos WHERE owner = ? AND name = ?",
                (owner, name),
            )
            conn.commit()
            print(f"Removed {owner}/{name} from watched repos.")
        elif source == "both":
            conn.execute(
                "UPDATE raw_watched_repos SET source = 'auto' WHERE owner = ? AND name = ?",
                (owner, name),
            )
            conn.commit()
            print(
                f"{owner}/{name} was manually added AND auto-discovered. "
                "Removed manual flag; repo remains watched as auto-discovered."
            )
        else:
            print(
                f"{owner}/{name} is auto-discovered only. "
                "It will be removed from the watched set automatically when no "
                "longer discovered."
            )
    finally:
        conn.close()


def cmd_refresh(args: argparse.Namespace) -> None:
    """Unfreeze a PR so it will be re-synced on the next run."""
    from agent_skills.gh_cache import open_gh_cache, unfreeze_pr  # noqa: PLC0415

    owner, name, number = _parse_pr_ref(args.target)
    result = open_gh_cache()
    conn = result.connection
    try:
        unfreeze_pr(conn, owner, name, number)
        print(f"Unfroze {owner}/{name}#{number}. It will be re-synced on next sync run.")
    finally:
        conn.close()


def cmd_status(args: argparse.Namespace) -> None:
    """Show watched repos, comment counts, frozen PR count, DB path, and recent sync states."""
    from agent_skills.gh_cache import open_gh_cache, watched_repos  # noqa: PLC0415

    result = open_gh_cache()
    conn = result.connection
    try:
        print(f"DB path: {result.path}")
        print()

        repos = watched_repos(conn)
        print(f"Watched repos ({len(repos)}):")
        for repo in repos:
            print(
                f"  {repo.owner}/{repo.name}  source={repo.source}  "
                f"backfill_days={repo.backfill_days}"
            )

        total_comments = conn.execute("SELECT COUNT(*) FROM raw_comments").fetchone()[0]
        frozen_count = conn.execute(
            "SELECT COUNT(*) FROM raw_pr_index WHERE is_frozen = 1"
        ).fetchone()[0]
        total_prs = conn.execute("SELECT COUNT(*) FROM raw_pr_index").fetchone()[0]

        print()
        print(f"Comments cached: {total_comments}")
        print(f"PRs/Issues indexed: {total_prs}  (frozen: {frozen_count})")

        print()
        print("Last 10 sync states:")
        rows = conn.execute(
            "SELECT repo_owner, repo_name, stream, high_water, last_drain_at, last_status "
            "FROM raw_sync_state "
            "ORDER BY last_drain_at DESC NULLS LAST "
            "LIMIT 10"
        ).fetchall()
        if not rows:
            print("  (no sync states recorded yet)")
        else:
            for row in rows:
                print(
                    f"  {row['repo_owner']}/{row['repo_name']} [{row['stream']}] "
                    f"hw={row['high_water']}  drained={row['last_drain_at']}  "
                    f"status={row['last_status']}"
                )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gh_cache_sync",
        description="Manage the gh-comment-cache SQLite database.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # sync
    p_sync = sub.add_parser("sync", help="Sync watched repos.")
    p_sync.add_argument("--repo", metavar="OWNER/REPO", help="Sync only this repo.")
    p_sync.add_argument(
        "--force", action="store_true", help="Force full re-drain (ignore ETag / high-water)."
    )
    p_sync.add_argument(
        "--yes", action="store_true", help="Skip confirmation prompts (reserved for future use)."
    )

    # add-repo
    p_add = sub.add_parser("add-repo", help="Add a repo to the watched set.")
    p_add.add_argument("repo", metavar="OWNER/REPO")
    p_add.add_argument(
        "--backfill-days",
        type=int,
        default=365,
        metavar="N",
        help="Days of history to backfill on first sync (default: 365).",
    )

    # remove-repo
    p_rm = sub.add_parser("remove-repo", help="Remove a repo from the watched set.")
    p_rm.add_argument("repo", metavar="OWNER/REPO")

    # refresh
    p_refresh = sub.add_parser("refresh", help="Unfreeze a PR so it will be re-synced.")
    p_refresh.add_argument("target", metavar="OWNER/REPO#NUMBER")

    # status
    sub.add_parser("status", help="Show cache status.")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_SUBCOMMAND_MAP = {
    "sync": cmd_sync,
    "add-repo": cmd_add_repo,
    "remove-repo": cmd_remove_repo,
    "refresh": cmd_refresh,
    "status": cmd_status,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = _SUBCOMMAND_MAP[args.subcommand]
    handler(args)


if __name__ == "__main__":
    main()
