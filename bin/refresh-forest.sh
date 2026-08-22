#!/usr/bin/env bash
# Advance every consumer worktree in a forest to its current upstream tip.
#
# `checkout` is create-only -- checkout_one() returns "present (skip)" the moment
# <forest>/<name>/.git exists -- so a forest built weeks ago keeps building the
# sources it was created with. This is the missing verb: bring an EXISTING forest
# to latest without discarding the per-forest patch commits it carries.
#
#   FOREST_REFERENCE_SUFFIX=itk-main bash bin/refresh-forest.sh          # dry run
#   FOREST_REFERENCE_SUFFIX=itk-main APPLY=1 bash bin/refresh-forest.sh  # do it
#   ... APPLY=1 bash bin/refresh-forest.sh ANTs elastix                  # subset
#
# Target ref per component, highest precedence first:
#   1. versions.toml [scenarios.<suffix>.<name>]  -> that fork branch
#   2. [subbuild.Plastimatch] fork_ref            -> the ITKv6-support fork tip
#   3. the central clone's default branch         -> origin/HEAD (else main/master)
#
# Local commits are REBASED onto the target, never dropped. A worktree that is
# dirty, or whose rebase conflicts, is left untouched and reported -- refreshing
# must never be the reason a forest loses work.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "${HERE}/platform.sh"
ROOT="$(npath "$(cd "${HERE}/.." && pwd)")"
SUFFIX="${FOREST_REFERENCE_SUFFIX:-}"
# The engine is the authority on the forest name (it applies BUILD_FOREST_ROOT,
# the suffix, absolute-vs-relative resolution and native-path conversion);
# recomputing it here drifted on Windows, where the default root is absolute.
FOREST="${FOREST:-$(bash "${HERE}/setup-itk-downstream-testbed.sh" --print-forest)}"
REPOS="$(npath "${FOREST_GIT_REPOS:-${ROOT}/forest_git_repos}")"
APPLY="${APPLY:-0}"

# shellcheck disable=SC1091
. "${ROOT}/bin/platform.sh"
# shellcheck disable=SC2086
cfg(){ "${FOREST_PYTHON}" ${FOREST_PYTHON_PRE} "${ROOT}/bin/config.py" "$@" 2>/dev/null; }
log(){ printf '%s\n' "$*"; }
say(){ printf '  %-24s %s\n' "$1" "$2"; }

[ -d "${FOREST}" ] || { echo "no such forest: ${FOREST}" >&2; exit 1; }
log "Forest: ${FOREST}   (APPLY=${APPLY})"

PLM_FORK_REMOTE="$(cfg get subbuild.Plastimatch.fork_remote)"
PLM_FORK_REF="$(cfg get subbuild.Plastimatch.fork_ref)"

# origin/HEAD, falling back to origin/main then origin/master.
repo_base(){
  local repo="$1" b
  b="$(git -C "${repo}" symbolic-ref --short -q refs/remotes/origin/HEAD || true)"
  [ -n "${b}" ] && { echo "${b}"; return; }
  for b in origin/main origin/master; do
    git -C "${repo}" show-ref --verify --quiet "refs/remotes/${b}" && { echo "${b}"; return; }
  done
}

names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  for d in "${FOREST}"/*/; do
    [ -e "${d}.git" ] && names+=("$(basename "${d}")")
  done
fi

skipped=() moved=() current=()

for name in "${names[@]}"; do
  dest="${FOREST}/${name}"; repo="${REPOS}/${name}"
  # ITK is the ref UNDER TEST, not a consumer to float. Its ref comes from
  # ITK_REF/repoint-itk; a default-branch rebase would drag a release-5.4 forest
  # onto main and silently answer a question nobody asked.
  [ "${name}" = ITK ] && { say "${name}" "ref under test -- use repoint-itk (skip)"; continue; }
  [ -e "${dest}/.git" ] || { say "${name}" "not checked out (skip)"; continue; }
  [ -d "${repo}/.git" ] || { say "${name}" "no central clone (skip)"; continue; }

  if [ -n "$(git -C "${dest}" status --porcelain --untracked-files=no)" ]; then
    say "${name}" "DIRTY -- left untouched"; skipped+=("${name}:dirty"); continue
  fi

  git -C "${repo}" fetch --all --tags --prune --quiet 2>/dev/null

  # Resolve the target this component should sit on.
  target=""; label=""
  ov="$([ -n "${SUFFIX}" ] && cfg scenario "${SUFFIX}" "${name}")"
  if [ -n "${ov}" ]; then
    IFS='|' read -r ov_url ov_branch <<<"${ov}"
    if git -C "${repo}" fetch --force "${ov_url}" "${ov_branch}:refs/demo/${name}-${ov_branch}" --quiet; then
      target="refs/demo/${name}-${ov_branch}"; label="scenario ${ov_branch}"
    else
      say "${name}" "scenario fetch failed (skip)"; skipped+=("${name}:scenario-fetch"); continue
    fi
  elif [ "${name}" = Plastimatch ] && [ -n "${PLM_FORK_REF}" ]; then
    git -C "${repo}" fetch "${PLM_FORK_REMOTE}" "${PLM_FORK_REF}" --quiet 2>/dev/null
    target="${PLM_FORK_REMOTE}/${PLM_FORK_REF}"; label="fork ${PLM_FORK_REF}"
  else
    target="$(repo_base "${repo}")"; label="${target}"
    [ -n "${target}" ] || { say "${name}" "no default branch (skip)"; skipped+=("${name}:no-base"); continue; }
  fi

  old="$(git -C "${dest}" rev-parse --short HEAD)"
  new="$(git -C "${repo}" rev-parse --short "${target}" 2>/dev/null)"
  ahead="$(git -C "${dest}" rev-list --count "${target}"..HEAD 2>/dev/null || echo 0)"
  behind="$(git -C "${dest}" rev-list --count "HEAD..${target}" 2>/dev/null || echo 0)"

  if [ "${behind}" = 0 ]; then
    say "${name}" "current at ${old} (${label}${ahead:+, +${ahead} local})"; current+=("${name}"); continue
  fi

  if [ "${APPLY}" != 1 ]; then
    say "${name}" "would advance ${old} -> ${new} (+${behind}) [${label}${ahead:+, replay ${ahead} local}]"
    moved+=("${name}"); continue
  fi

  if git -C "${dest}" rebase "${target}" --quiet 2>/dev/null; then
    say "${name}" "advanced ${old} -> $(git -C "${dest}" rev-parse --short HEAD) (${label})"
    moved+=("${name}")
  else
    git -C "${dest}" rebase --abort 2>/dev/null
    say "${name}" "REBASE CONFLICT -- left at ${old}"; skipped+=("${name}:conflict")
  fi
done

log ""
log "advanced: ${#moved[@]}   already current: ${#current[@]}   skipped: ${#skipped[@]}"
[ ${#skipped[@]} -gt 0 ] && log "skipped: ${skipped[*]}"
[ "${APPLY}" = 1 ] && cfg manifest "${FOREST}" >/dev/null 2>&1
exit 0
