#!/usr/bin/env bash
# Refresh the vendored agent_skills modules from the canonical agent-skills repo.
#
#   vendor-sync.sh [<agent-skills-repo>]   default: ~/src/agent-skills
#   vendor-sync.sh --check [<repo>]        exit 1 if any vendored file has drifted
#
# The testbed is a relocatable kit: it must run with no agent-skills checkout
# present, so these modules are vendored rather than imported. That makes the
# canonical copy in agent-skills the single source of truth and this copy a
# generated artifact. gh_cache.py is NOT synced — it carries a deliberate
# one-line divergence (its _MIGRATION_DIR resolves inside this skill).
set -uo pipefail

VENDORED=(cache.py workspace.py)

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="$here/agent_skills"

check=0
if [ "${1:-}" = "--check" ]; then check=1; shift; fi
src_repo="${1:-$HOME/src/agent-skills}"
src="$src_repo/lib/agent_skills"

if [ ! -d "$src" ]; then
    echo "vendor-sync: no agent-skills checkout at $src_repo" >&2
    [ "$check" -eq 1 ] && exit 0   # nothing to compare against; not a failure
    exit 2
fi

rc=0
for f in "${VENDORED[@]}"; do
    if [ "$check" -eq 1 ]; then
        if ! diff -q "$src/$f" "$dest/$f" >/dev/null 2>&1; then
            echo "DRIFTED: $f"
            diff -u "$src/$f" "$dest/$f" | head -20
            rc=1
        fi
    else
        cp "$src/$f" "$dest/$f"
        echo "synced: $f"
    fi
done

if [ "$check" -eq 1 ]; then
    [ "$rc" -eq 0 ] && echo "OK: vendored modules match $src_repo"
fi
exit "$rc"
