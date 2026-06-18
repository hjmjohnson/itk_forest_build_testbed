#!/usr/bin/env bash
# Materialize every Slicer extension source tree for code search.
#
# Reads the ExtensionsIndex descriptors checked out at FOREST/SlicerExtensions
# (each <name>.json carries scm_url + scm_revision), deep-clones each repo into
# forest_git_repos/SlicerExt-<name>, and adds a git worktree at
# FOREST/SlicerExtensions-src/<name>. Deep clones (full history) per kit policy;
# worktrees share the central object store so re-materializing is cheap.
#
# Usage:  checkout-slicer-extensions.sh [name...]      (default: all descriptors)
# Env:    FOREST_REFERENCE_SUFFIX  select build_forest-<suffix>
#         INCLUDE_ARCHIVE=1        also clone SlicerExtensions/ARCHIVE/*.json
#         JOBS=N                   parallel clones (default: nproc)
#         FOREST, FOREST_GIT_REPOS, BUILD_FOREST_ROOT  as in setup script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTBED="${TESTBED:-$(dirname "${SCRIPT_DIR}")}"
CONFIG_SH="${TESTBED}/config.sh"
if [ ! -f "${CONFIG_SH}" ] && command -v python3 >/dev/null 2>&1; then
  python3 "${SCRIPT_DIR}/config.py" generate >/dev/null 2>&1 || true
fi
# shellcheck disable=SC1090
[ -f "${CONFIG_SH}" ] && . "${CONFIG_SH}"

REPOS="${FOREST_GIT_REPOS:-${TESTBED}/forest_git_repos}"
BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT:-build_forest}"
[ -n "${FOREST_REFERENCE_SUFFIX:-}" ] && BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT}-${FOREST_REFERENCE_SUFFIX}"
case "${BUILD_FOREST_ROOT}" in
  /*) FOREST="${FOREST:-${BUILD_FOREST_ROOT}}" ;;
  *)  FOREST="${FOREST:-${TESTBED}/${BUILD_FOREST_ROOT}}" ;;
esac
JOBS="${JOBS:-$( (command -v nproc >/dev/null && nproc) || sysctl -n hw.ncpu 2>/dev/null || echo 4)}"

INDEX="${FOREST}/SlicerExtensions"
DEST_BASE="${FOREST}/SlicerExtensions-src"

log(){ printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

# Internal per-repo worker invoked by xargs.
if [ "${1:-}" = "__one" ]; then
  name="$2"; url="$3"; rev="${4:-HEAD}"
  repo="${REPOS}/SlicerExt-${name}"
  dest="${DEST_BASE}/${name}"
  branch="slicerext-${name}${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
  export GIT_TERMINAL_PROMPT=0
  if [ -d "${repo}/.git" ]; then
    git -C "${repo}" fetch --quiet --all --prune 2>/dev/null || true
  else
    git clone --quiet "${url}" "${repo}" || { warn "${name}: clone failed (${url})"; exit 0; }
  fi
  git -C "${repo}" worktree prune 2>/dev/null || true
  [ -e "${dest}/.git" ] && { log "${name}: worktree present (skip)"; exit 0; }
  start=""
  for cand in "origin/${rev}" "${rev}"; do
    git -C "${repo}" rev-parse --verify --quiet "${cand}^{commit}" >/dev/null 2>&1 && { start="${cand}"; break; }
  done
  if [ -z "${start}" ]; then
    start="$(git -C "${repo}" rev-parse --verify --quiet origin/main >/dev/null 2>&1 && echo origin/main || echo origin/master)"
  fi
  if git -C "${repo}" show-ref --verify --quiet "refs/heads/${branch}"; then
    git -C "${repo}" worktree add --quiet "${dest}" "${branch}" \
      && log "${name}: worktree (existing branch ${branch})" || warn "${name}: worktree failed"
  else
    git -C "${repo}" worktree add --quiet -b "${branch}" "${dest}" "${start}" \
      && log "${name}: worktree (branch ${branch} off ${start})" || warn "${name}: worktree failed (${start})"
  fi
  exit 0
fi

command -v git >/dev/null || die "missing tool: git"
[ -d "${INDEX}" ] || die "ExtensionsIndex not checked out at ${INDEX} — run: pixi run checkout SlicerExtensions"
mkdir -p "${DEST_BASE}"

mapfile -t manifest < <(
  python3 - "${INDEX}" "${INCLUDE_ARCHIVE:-0}" "$@" <<'PY'
import json, glob, os, sys
index, include_archive = sys.argv[1], sys.argv[2] == "1"
wanted = set(sys.argv[3:])
paths = glob.glob(os.path.join(index, "*.json"))
if include_archive:
    paths += glob.glob(os.path.join(index, "ARCHIVE", "*.json"))
rows = {}
for p in paths:
    name = os.path.splitext(os.path.basename(p))[0]
    if wanted and name not in wanted:
        continue
    try:
        d = json.load(open(p))
    except Exception:
        continue
    if d.get("scm", "git") != "git":
        continue
    url = d.get("scm_url")
    if not url:
        continue
    rows[name] = (name, url, d.get("scm_revision") or "HEAD")
for name in sorted(rows):
    print("\t".join(rows[name]))
PY
)

[ "${#manifest[@]}" -gt 0 ] || die "no matching extension descriptors found"
log "TESTBED=${TESTBED}  FOREST=${FOREST}  JOBS=${JOBS}  extensions=${#manifest[@]}"

# Each TSV line splits on whitespace into name/url/rev positional args.
printf '%s\n' "${manifest[@]}" \
  | xargs -P "${JOBS}" -L1 bash -c 'exec "$0" __one "$@"' "${BASH_SOURCE[0]}"

log "done: $(find "${DEST_BASE}" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ') extension worktrees under ${DEST_BASE}"
