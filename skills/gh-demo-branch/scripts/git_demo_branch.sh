#!/usr/bin/env bash
# git_demo_branch.sh — assemble a `demo-<suffix>` staging branch on an hjmjohnson
# fork that aggregates the commits needed to make one build scenario green.
#
# A demo branch is NOT a PR: it is one possible future version of a project,
# based on the latest upstream main|master, that demonstrates inter-project
# reliability for a given FOREST_REFERENCE_SUFFIX. Several demo-* branches build
# different scenarios; they converge, then real PRs are cut.
#
# Usage:
#   git_demo_branch.sh init        <project> [suffix]
#   git_demo_branch.sh survey      <project> [suffix]
#   git_demo_branch.sh incorporate <project> <commit-ish> [suffix]
#   git_demo_branch.sh status      <project> [suffix]
#   git_demo_branch.sh push        <project> [suffix]
#   git_demo_branch.sh reconcile   <project>
#
#   <project>  component name; its upstream URL comes from versions.toml
#              (config.py get components.<project>.url) or $DEMO_UPSTREAM_URL.
#   suffix     defaults to $FOREST_REFERENCE_SUFFIX.
# Env: DEMO_FORK_OWNER (default hjmjohnson), DEMO_STAGING_DIR
#      (default ~/.cache/git-demo-branch), DEMO_UPSTREAM_URL (override).
set -uo pipefail

FORK_OWNER="${DEMO_FORK_OWNER:-hjmjohnson}"
STAGING="${DEMO_STAGING_DIR:-${HOME}/.cache/git-demo-branch}"
TESTBED="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." 2>/dev/null && pwd)"

# Diagnostics go to stderr so command-substituted helpers (prep) emit only data.
die(){ printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }
log(){ printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }

upstream_url(){ # project -> upstream git URL
  local p="$1"
  [ -n "${DEMO_UPSTREAM_URL:-}" ] && { echo "${DEMO_UPSTREAM_URL}"; return; }
  python3 "${TESTBED}/bin/config.py" get "components.${p}.url" 2>/dev/null \
    || die "no upstream URL for ${p} (set DEMO_UPSTREAM_URL or add to versions.toml)"
}
reponame(){ basename "$1" .git; }                       # url -> repo
fork_url(){ echo "https://github.com/${FORK_OWNER}/$(reponame "$1").git"; }
nwo(){ echo "${1#https://github.com/}" | sed 's/\.git$//'; }   # url -> owner/repo
suffix_or_env(){ echo "${1:-${FOREST_REFERENCE_SUFFIX:-}}"; }

# Materialize a private staging clone with `up` (upstream) + `fork` remotes.
prep(){
  local p="$1" up; up="$(upstream_url "$p")"
  local fk; fk="$(fork_url "$up")"
  local dir="${STAGING}/${p}"
  if [ ! -d "${dir}/.git" ]; then
    mkdir -p "${STAGING}"; log "clone ${up} -> ${dir}"
    git clone --quiet "${up}" "${dir}" || die "clone failed"
  fi
  git -C "${dir}" remote get-url up   >/dev/null 2>&1 || git -C "${dir}" remote add up   "${up}"
  git -C "${dir}" remote get-url fork >/dev/null 2>&1 || git -C "${dir}" remote add fork "${fk}"
  git -C "${dir}" remote set-url up "${up}"; git -C "${dir}" remote set-url fork "${fk}"
  git -C "${dir}" fetch --quiet up --prune 2>/dev/null
  git -C "${dir}" fetch --quiet fork --prune 2>/dev/null || true
  echo "${dir}"
}

up_default(){ # dir -> upstream default branch (main|master)
  git -C "$1" remote show up 2>/dev/null | sed -n 's/.*HEAD branch: //p' | head -1
}

cmd_init(){
  local p="$1" sfx; sfx="$(suffix_or_env "${2:-}")"; [ -n "${sfx}" ] || die "no suffix"
  local dir; dir="$(prep "$p")"; local def; def="$(up_default "$dir")"
  log "init demo-${sfx} off up/${def} in ${dir}"
  git -C "${dir}" checkout -B "demo-${sfx}" "up/${def}" --quiet
  echo "demo-${sfx} @ $(git -C "${dir}" rev-parse --short HEAD) (off up/${def})"
}

cmd_survey(){
  local p="$1" sfx; sfx="$(suffix_or_env "${2:-}")"
  local dir; dir="$(prep "$p")"; local up; up="$(upstream_url "$p")"; local owner_repo; owner_repo="$(nwo "$up")"
  echo "### open PRs on ${owner_repo} (priority starting points)"
  gh pr list --repo "${owner_repo}" --state open \
    --json number,title,headRefName,headRepositoryOwner \
    --jq '.[] | "  #\(.number) [\(.headRepositoryOwner.login):\(.headRefName)] \(.title)"' 2>/dev/null | head -40
  echo "### forks of ${owner_repo} (scan for existing fixes)"
  gh api "repos/${owner_repo}/forks?sort=newest&per_page=20" \
    --jq '.[] | "  \(.full_name)  (pushed \(.pushed_at[:10]))"' 2>/dev/null | head -20
  echo "### sibling demo-* branches on ${FORK_OWNER}/$(reponame "$up")"
  git -C "${dir}" for-each-ref --format='  %(refname:short)  %(objectname:short)' 'refs/remotes/fork/demo-*' 2>/dev/null
  [ -n "${sfx}" ] && echo "### (target branch: demo-${sfx})"
}

# Auto-incorporate a commit: cherry-pick onto demo-<suffix>; clean apply keeps
# it, conflict aborts and reports (per "auto-incorporate clean ones").
cmd_incorporate(){
  local p="$1" c="${2:?commit-ish}" sfx; sfx="$(suffix_or_env "${3:-}")"; [ -n "${sfx}" ] || die "no suffix"
  local dir; dir="$(prep "$p")"
  git -C "${dir}" rev-parse --verify --quiet "demo-${sfx}" >/dev/null \
    || die "demo-${sfx} not initialized; run: $0 init ${p} ${sfx}"
  git -C "${dir}" checkout "demo-${sfx}" --quiet
  local before; before="$(git -C "${dir}" rev-parse HEAD)"
  if git -C "${dir}" cherry-pick -x "${c}" >/tmp/_gdb_cp.log 2>&1; then
    echo "INCORPORATED ${c} -> demo-${sfx} ($(git -C "${dir}" rev-parse --short HEAD))"
  else
    git -C "${dir}" cherry-pick --abort 2>/dev/null
    git -C "${dir}" reset --hard "${before}" --quiet
    warn "SKIPPED ${c}: does not apply cleanly (conflict) — review manually"
    grep -iE 'conflict|error' /tmp/_gdb_cp.log | head -3
    return 1
  fi
}

cmd_status(){
  local p="$1" sfx; sfx="$(suffix_or_env "${2:-}")"; [ -n "${sfx}" ] || die "no suffix"
  local dir; dir="$(prep "$p")"; local def; def="$(up_default "$dir")"
  local ref=""   # prefer local working branch, else the pushed fork branch
  git -C "${dir}" rev-parse --verify --quiet "demo-${sfx}" >/dev/null && ref="demo-${sfx}"
  [ -z "${ref}" ] && git -C "${dir}" rev-parse --verify --quiet "fork/demo-${sfx}" >/dev/null && ref="fork/demo-${sfx}"
  [ -n "${ref}" ] || { warn "demo-${sfx} not found (local or on fork)"; return 0; }
  echo "${ref}: $(git -C "${dir}" rev-parse --short "${ref}")  |  up/${def}: $(git -C "${dir}" rev-parse --short up/${def})"
  echo "commits ahead of up/${def}:"
  git -C "${dir}" log --oneline "up/${def}..${ref}"
}

cmd_push(){
  local p="$1" sfx; sfx="$(suffix_or_env "${2:-}")"; [ -n "${sfx}" ] || die "no suffix"
  local dir; dir="$(prep "$p")"
  log "push demo-${sfx} -> fork (${FORK_OWNER})"
  git -C "${dir}" push --force-with-lease fork "demo-${sfx}:demo-${sfx}"
}

cmd_reconcile(){
  local p="$1"; local dir; dir="$(prep "$p")"
  local -a demos; mapfile -t demos < <(git -C "${dir}" for-each-ref --format='%(refname:short)' 'refs/remotes/fork/demo-*')
  echo "### demo-* branches: ${demos[*]:-(none)}"
  local i j
  for ((i=0;i<${#demos[@]};i++)); do for ((j=i+1;j<${#demos[@]};j++)); do
    echo "--- ${demos[i]} vs ${demos[j]} (range-diff) ---"
    git -C "${dir}" range-diff "up/$(up_default "$dir")" "${demos[i]}" "${demos[j]}" 2>/dev/null | head -12
  done; done
}

action="${1:-}"; shift || true
case "${action}" in
  init)        cmd_init "$@" ;;
  survey)      cmd_survey "$@" ;;
  incorporate) cmd_incorporate "$@" ;;
  status)      cmd_status "$@" ;;
  push)        cmd_push "$@" ;;
  reconcile)   cmd_reconcile "$@" ;;
  ""|-h|--help|help)
    sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown action '${action}' (init|survey|incorporate|status|push|reconcile)" ;;
esac
