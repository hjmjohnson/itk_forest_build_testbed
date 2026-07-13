#!/usr/bin/env bash
# isolated-itk-worktree: create a self-contained ITK build/test sandbox in a git
# worktree at <main>/../<main-basename>-<name>-src, inheriting the primary
# checkout's committed-code-compliance hooks. Emits KEY=VALUE lines for the
# caller to consume; does NOT configure or build (the caller owns those so the
# long build can background, and pixi builds its own per-worktree environment).
set -euo pipefail

MAIN_REPO="${ITK_MAIN_REPO:-$HOME/src/ITK}"
UPSTREAM_REMOTE="${ITK_UPSTREAM_REMOTE:-upstream}"
UPSTREAM_SLUG="${ITK_UPSTREAM_SLUG:-InsightSoftwareConsortium/ITK}"

die() { echo "ERROR: $*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: setup-worktree.sh <PR#> | new:<branchname>"
ARG="$1"

cd "$MAIN_REPO" || die "main repo not found: $MAIN_REPO"
[ -d "$MAIN_REPO/.pixi" ] || die "no prebuilt pixi env at $MAIN_REPO/.pixi (run a build in the main checkout first)"

if [[ "$ARG" =~ ^new:(.+)$ ]]; then
  MODE=new
  BRANCH="${BASH_REMATCH[1]}"
  [ -n "$BRANCH" ] || die "empty branch name after 'new:'"
  WT_NAME="${BRANCH}"
elif [[ "$ARG" =~ ^[0-9]+$ ]]; then
  MODE=pr
  PR="$ARG"
  command -v gh >/dev/null || die "gh CLI required for PR checkout"
  BRANCH="$(gh pr view "$PR" --repo "$UPSTREAM_SLUG" --json headRefName -q .headRefName)" \
    || die "could not resolve head branch for PR #$PR"
  [ -n "$BRANCH" ] || die "PR #$PR has no head branch"
  WT_NAME="${PR}-${BRANCH}"
else
  die "first argument must be a PR number or new:<branchname> (got: '$ARG')"
fi

# Sibling layout: <main>/../<main-basename>-<name>-src. Keeps worktrees out of
# the primary's .git-tracked tree and gives each a stable path for CCACHE_BASEDIR.
WT_DIR="$(dirname "$MAIN_REPO")/$(basename "$MAIN_REPO")-${WT_NAME}-src"
[ -e "$WT_DIR" ] && die "worktree path already exists: $WT_DIR"

git fetch "$UPSTREAM_REMOTE" --prune

# 1. Create the worktree.
if [ "$MODE" = new ]; then
  git worktree add -b "$BRANCH" "$WT_DIR" "${UPSTREAM_REMOTE}/main"
else
  git worktree add --detach "$WT_DIR" "${UPSTREAM_REMOTE}/main"
fi

# 2. Inherit the primary checkout's commit-compliance hooks. A linked worktree's
#    default hooks dir is its own (empty) git-dir, so without this its commits
#    would skip pre-commit/KWStyle. core.hooksPath lives in shared config; set it
#    to the primary's hooks only when unset (primary already uses .git/hooks, so
#    this is a no-op for primary and makes every worktree inherit working hooks).
if [ -z "$(git config core.hooksPath || true)" ]; then
  git config core.hooksPath "$MAIN_REPO/.git/hooks"
fi

# 3. For PR mode, gh pr checkout inside the worktree wires up push tracking.
if [ "$MODE" = pr ]; then
  ( cd "$WT_DIR" && gh pr checkout "$PR" --repo "$UPSTREAM_SLUG" )
fi

# 4. Share .devlocal with the main checkout so TODO/scratch content is not
#    forked per-worktree; every worktree symlinks to the primary's .devlocal.
[ -e "$WT_DIR/.devlocal" ] || ln -s "$MAIN_REPO/.devlocal" "$WT_DIR/.devlocal"

echo "WORKTREE_DIR=$WT_DIR"
echo "WORKTREE_NAME=$WT_NAME"
echo "BRANCH=$BRANCH"
echo "MODE=$MODE"
# ccache normalizes absolute paths under this root to relative, so objects are
# shared across worktrees at different absolute paths. Export before configure/build.
echo "CCACHE_BASEDIR=$WT_DIR"
