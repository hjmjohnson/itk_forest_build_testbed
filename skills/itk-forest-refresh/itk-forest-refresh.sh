#!/usr/bin/env bash
# itk-forest-refresh [all|v5|v6] -- bring ITK and every downstream consumer to
# their latest tip, build any requested in-flight-PR integration branches,
# wire them into versions.toml, then repoint ITK and warm the ccache build.
#
#   v6  -> itk-main forest,          ITK on upstream/main
#   v5  -> itk-release-5.4 forest,   ITK on upstream/release-5.4
#   all -> both (default)
#
# Reads skills/itk-forest-refresh/integration-requests.toml for any downstream
# PR integration that is currently requested (see that file's header for the
# format). Nothing listed there = a plain float to upstream default branches,
# which is bin/refresh-forest.sh's existing job; this script's own value is:
#   1. building/updating a PR integration branch per requested consumer,
#      SHARED between v5 and v6 by default (per docs/integration-branches.md),
#   2. wiring it into versions.toml [scenarios.<suffix>.<Name>],
#   3. then calling the existing refresh/repoint/build primitives so the
#      forest(s) actually pick it up.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
cd "${ROOT}"
# shellcheck disable=SC1091
. "${ROOT}/bin/platform.sh"

TARGET="${1:-all}"
REQ_FILE="${HERE}/integration-requests.toml"
SET_SCENARIO="${HERE}/lib/set_scenario.py"
VERSIONS="${ROOT}/versions.toml"

log(){ printf '%s\n' "$*"; }
die(){ echo "itk-forest-refresh: $*" >&2; exit 1; }

case "${TARGET}" in
  v6)  SUFFIXES=(itk-main) ;;
  v5)  SUFFIXES=(itk-release-5.4) ;;
  all) SUFFIXES=(itk-main itk-release-5.4) ;;
  *) die "usage: itk-forest-refresh [all|v5|v6]" ;;
esac
suffix_to_itk_ref(){ [ "$1" = itk-main ] && echo upstream/main || echo upstream/release-5.4; }
suffix_to_v(){ [ "$1" = itk-main ] && echo v6 || echo v5; }

REPOS="${FOREST_GIT_REPOS:-${ROOT}/forest_git_repos}"

# ---- fork-remote detection -------------------------------------------------
# Fork remote names are inconsistent across clones (hjfork / hj / hjmjohnson);
# pick the first remote whose URL points at the hjmjohnson account.
fork_remote(){
  local repo="$1" r url
  for r in $(git -C "${repo}" remote 2>/dev/null); do
    url="$(git -C "${repo}" remote get-url "${r}" 2>/dev/null)"
    case "${url}" in *hjmjohnson/*|*hjmjohnson:*) echo "${r}"; return 0 ;; esac
  done
  return 1
}
fork_url(){ git -C "$1" remote get-url "$(fork_remote "$1")" 2>/dev/null; }

repo_base(){
  local repo="$1" b
  b="$(git -C "${repo}" symbolic-ref --short -q refs/remotes/origin/HEAD || true)"
  [ -n "${b}" ] && { echo "${b}"; return; }
  for b in origin/main origin/master; do
    git -C "${repo}" show-ref --verify --quiet "refs/remotes/${b}" && { echo "${b}"; return; }
  done
}

# Build/refresh a shared PR-integration branch in a central clone: reset to
# the latest default branch, merge each requested PR head (--no-ff), push to
# the fork. Returns 0 and prints "url|branch" on success.
build_integration_branch(){
  local repo="$1" branch="$2"; shift 2
  local prs=("$@")
  git -C "${repo}" fetch origin --prune --quiet || { echo "fetch origin failed" >&2; return 1; }
  local base; base="$(repo_base "${repo}")"
  [ -n "${base}" ] || { echo "no default branch" >&2; return 1; }
  local fork; fork="$(fork_remote "${repo}")" || { echo "no hjmjohnson fork remote" >&2; return 1; }
  git -C "${repo}" checkout -f -B "${branch}" "${base}" --quiet || { echo "checkout ${base} failed" >&2; return 1; }
  local pr num
  for pr in "${prs[@]}"; do
    num="${pr##*/}"
    git -C "${repo}" fetch origin "pull/${num}/head" --quiet \
      || { echo "fetch PR ${num} failed" >&2; return 1; }
    # "ENH:" prefix: some consumers (ITK itself) enforce a commit-msg hook
    # requiring one of BUG:/COMP:/DOC:/ENH:/PERF:/STYLE:/WIP:; harmless on
    # repos with no such hook.
    git -C "${repo}" merge --no-ff --quiet -m "ENH: Integrate PR #${num} for forest testing" FETCH_HEAD \
      || { git -C "${repo}" merge --abort 2>/dev/null; echo "merge PR ${num} conflicts" >&2; return 1; }
  done
  git -C "${repo}" push --force-with-lease "${fork}" "${branch}:${branch}" --quiet \
    || { echo "push to ${fork} failed" >&2; return 1; }
  echo "$(git -C "${repo}" remote get-url "${fork}")|${branch}"
}

# ---- 1. requested ITK-side integration (rare; see integration-requests.toml) ----
ITK_REPO="${REPOS}/ITK"
declare -A ITK_REF_FOR
for suf in "${SUFFIXES[@]}"; do
  v="$(suffix_to_v "${suf}")"
  prs_py="$("${FOREST_PYTHON:-python3}" - "${REQ_FILE}" "${v}" <<'PY'
import sys, tomllib
path, v = sys.argv[1], sys.argv[2]
try:
    with open(path, "rb") as f:
        data = tomllib.load(f)
except FileNotFoundError:
    sys.exit(0)
for p in (data.get("itk", {}).get(v, {}) or {}).get("prs", []):
    print(p)
PY
)"
  if [ -n "${prs_py}" ]; then
    log "ITK (${suf}): building itk-forest-integration-${suf} with: ${prs_py}"
    mapfile -t prs <<<"${prs_py}"
    out="$(build_integration_branch "${ITK_REPO}" "itk-forest-integration-${suf}" "${prs[@]}")" \
      || die "ITK integration branch failed for ${suf}: ${out}"
    fork="$(fork_remote "${ITK_REPO}")"
    ITK_REF_FOR["${suf}"]="${fork}/itk-forest-integration-${suf}"
  else
    ITK_REF_FOR["${suf}"]="$(suffix_to_itk_ref "${suf}")"
  fi
done

# ---- 2. requested downstream integration, shared across v5/v6 by default ----
downstream_py="$("${FOREST_PYTHON:-python3}" - "${REQ_FILE}" <<'PY'
import sys, tomllib
path = sys.argv[1]
try:
    with open(path, "rb") as f:
        data = tomllib.load(f)
except FileNotFoundError:
    sys.exit(0)
for name, spec in (data.get("downstream") or {}).items():
    prs = ",".join(spec.get("prs", []))
    forests = ",".join(spec.get("forests", ["itk-main", "itk-release-5.4"]))
    print(f"{name}|{prs}|{forests}")
PY
)"

if [ -n "${downstream_py}" ]; then
  while IFS='|' read -r name prs forests; do
    [ -n "${name}" ] || continue
    repo="${REPOS}/${name}"
    [ -d "${repo}/.git" ] || { log "${name}: no central clone (skip integration)"; continue; }
    IFS=',' read -ra pr_arr <<<"${prs}"
    IFS=',' read -ra forest_arr <<<"${forests}"
    # only build/wire for forests actually in scope this run
    wanted=()
    for f in "${forest_arr[@]}"; do
      for suf in "${SUFFIXES[@]}"; do [ "${f}" = "${suf}" ] && wanted+=("${suf}"); done
    done
    [ ${#wanted[@]} -gt 0 ] || continue
    log "${name}: building shared itk-forest-integration branch with PRs: ${prs}"
    result="$(build_integration_branch "${repo}" "itk-forest-integration" "${pr_arr[@]}")" \
      || { log "${name}: integration branch FAILED: ${result}"; continue; }
    url="${result%%|*}" branch="${result##*|}"
    for suf in "${wanted[@]}"; do
      "${FOREST_PYTHON:-python3}" "${SET_SCENARIO}" "${VERSIONS}" "${suf}" "${name}" "${url}" "${branch}"
    done
  done <<<"${downstream_py}"
else
  log "no downstream integration requested (integration-requests.toml empty/absent)"
fi

# ---- 3. float every other downstream worktree to latest, per forest ---------
for suf in "${SUFFIXES[@]}"; do
  log "## refresh ${suf}"
  FOREST_REFERENCE_SUFFIX="${suf}" APPLY=1 bash "${ROOT}/bin/refresh-forest.sh"
done

# ---- 4. repoint + build ITK, per forest --------------------------------------
for suf in "${SUFFIXES[@]}"; do
  log "## ITK ${suf} -> ${ITK_REF_FOR[${suf}]}"
  FOREST_REFERENCE_SUFFIX="${suf}" ITK_REF="${ITK_REF_FOR[${suf}]}" \
    bash "${ROOT}/bin/setup-itk-downstream-testbed.sh" repoint-itk || die "repoint-itk failed for ${suf}"
  FOREST_REFERENCE_SUFFIX="${suf}" pixi run build-ITK \
    || log "## ITK build FAILED for ${suf} -- see output above"
  forest_dir="$(FOREST_REFERENCE_SUFFIX="${suf}" bash "${ROOT}/bin/setup-itk-downstream-testbed.sh" --print-forest 2>/dev/null)"
  [ -n "${forest_dir}" ] || forest_dir="${ROOT}/build_forest-${suf}"
  git -C "${forest_dir}/ITK" log -1 --format="${suf} ITK now %h %s" 2>/dev/null
done

log "ALLDONE"
