#!/usr/bin/env bash
# ghtp_list_targets.sh — Parse a gh-triage-PR argument into a list of targets.
#
# Accepted inputs:
#   #NNNN            -> current repo, that PR
#   NNNN             -> current repo, that PR
#   owner/repo#NNNN  -> specific repo
#   my               -> all open PRs authored by current user
#   all-draft        -> all open DRAFT PRs authored by current user
#
# Output: one line per target, "owner/repo NUM" (space-separated).

set -euo pipefail

ARG="${1:-}"
if [[ -z "$ARG" ]]; then
    echo "Usage: $0 <#NNNN|NNNN|owner/repo#NNNN|my|all-draft>" >&2
    exit 1
fi

current_repo() {
    # Resolve owner/repo for the current directory. Fail loudly if not a gh repo.
    gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || {
        echo "ERROR: not in a GitHub repo (gh repo view failed)" >&2
        exit 1
    }
}

case "$ARG" in
    my)
        # All open PRs authored by the current user (draft and ready).
        gh search prs --author "@me" --state open --json number,repository \
            --jq '.[] | "\(.repository.nameWithOwner) \(.number)"'
        ;;

    all-draft)
        # All open DRAFT PRs authored by the current user.
        gh search prs --author "@me" --state open --draft --json number,repository \
            --jq '.[] | "\(.repository.nameWithOwner) \(.number)"'
        ;;

    */*#*)
        # owner/repo#NNNN form
        repo="${ARG%#*}"
        num="${ARG#*#}"
        echo "$repo $num"
        ;;

    \#*)
        # #NNNN in current repo
        num="${ARG#\#}"
        repo="$(current_repo)"
        echo "$repo $num"
        ;;

    [0-9]*)
        # bare NNNN in current repo
        repo="$(current_repo)"
        echo "$repo $ARG"
        ;;

    *)
        echo "ERROR: unrecognized argument: $ARG" >&2
        exit 1
        ;;
esac
