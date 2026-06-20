#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LEVELS="prep-v5 mandatory legacy-remove future-legacy-remove"

_task_files() {  # $1 optional level filter
  local lvl="${1:-}"
  if [ -n "$lvl" ] && [ "$lvl" != "manual" ]; then
    ls "$HERE/tasks/$lvl"/*.sh 2>/dev/null
  elif [ "$lvl" = "manual" ]; then
    ls "$HERE/manual"/*.sh 2>/dev/null
  else
    ls "$HERE"/tasks/*/*.sh 2>/dev/null
  fi
}

_task_meta() {  # echoes "name<TAB>level<TAB>pattern<TAB>glob" by sourcing in a subshell
  local f="$1"
  ( TASK_NAME=""; TASK_LEVEL=""; GREP_PATTERN=""; MC_FILE_GLOB=""
    # shellcheck disable=SC1090
    MC_META_ONLY=1 source "$f" 2>/dev/null
    printf '%s\t%s\t%s\t%s\n' "$TASK_NAME" "$TASK_LEVEL" "$GREP_PATTERN" "${MC_FILE_GLOB:-}" )
}

_task_subject() {  # echoes the first line of a task's COMMIT_MSG (the recommendation)
  ( TASK_NAME=""; COMMIT_MSG=""
    # shellcheck disable=SC1090
    MC_META_ONLY=1 source "$1" 2>/dev/null
    printf '%s\n' "$COMMIT_MSG" | head -1 )
}

_task_code_aware() {  # 0 if the task defines MC_SUBST (comment/string-aware)
  ( MC_SUBST=()
    # shellcheck disable=SC1090
    MC_META_ONLY=1 source "$1" 2>/dev/null
    [ "${#MC_SUBST[@]}" -gt 0 ] )
}

_is_pending() {  # repo taskfile -> 0 if the task has REAL (non-comment) work
  local repo="$1" f="$2" p g
  IFS=$'\t' read -r _ _ p g < <(_task_meta "$f")
  # Split the glob without shell filename expansion (read never globs) so
  # '*.cmake' reaches git as a recursive pathspec, independent of the CWD.
  local globs=(); [ -n "$g" ] && read -ra globs <<< "$g"
  if [ "${#globs[@]}" -gt 0 ]; then
    git -C "$repo" grep -qE -- "$p" -- "${globs[@]}" ':!*ThirdParty/*' 2>/dev/null || return 1
  else
    git -C "$repo" grep -qE -- "$p" -- ':!*ThirdParty/*' 2>/dev/null || return 1
  fi
  # For comment/string-aware tasks, a naive match inside a comment or string is
  # not real work — confirm a genuine change via the comment-aware dry-run.
  if _task_code_aware "$f"; then
    bash "$f" --dry-run "$repo" 2>/dev/null | grep -q '^+++ ' || return 1
  fi
  return 0
}

# Report the migration base relative to the primary repo's primary branch
# (origin/HEAD -> origin/main). Migration results are only meaningful against
# the current primary branch; a stale checkout silently produces wrong work.
# Suppress with MC_NO_BASE_CHECK=1 when intentionally working off-primary.
_primary_branch_report() {
  [ "${MC_NO_BASE_CHECK:-0}" = "1" ] && return 0
  local path="${1:-$PWD}"
  git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  local primary
  primary="$(git -C "$path" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/@@')"
  if [ -z "$primary" ]; then
    if git -C "$path" rev-parse --verify -q origin/main >/dev/null; then primary="origin/main"
    elif git -C "$path" rev-parse --verify -q origin/master >/dev/null; then primary="origin/master"
    else
      printf '[itk-migrate] ⚠ base check: no origin primary branch found; results are NOT validated against a primary branch.\n' >&2
      return 0
    fi
  fi
  # Refresh the remote-tracking ref by default so the comparison is current;
  # --no-fetch / MC_NO_FETCH=1 skips it (e.g. offline).
  local freshness="as of last local fetch"
  if [ "${MC_NO_FETCH:-0}" = "1" ]; then
    freshness="--no-fetch; as of last local fetch"
  elif git -C "$path" fetch --quiet "${primary%%/*}" "${primary#*/}" 2>/dev/null; then
    freshness="just fetched"
  else
    freshness="fetch failed; as of last local fetch"
  fi
  local head_sha base_sha base_date counts behind ahead dirty
  head_sha="$(git -C "$path" rev-parse --short HEAD 2>/dev/null)"
  base_sha="$(git -C "$path" rev-parse --short "$primary" 2>/dev/null)"
  base_date="$(git -C "$path" log -1 --format=%cs "$primary" 2>/dev/null)"
  counts="$(git -C "$path" rev-list --left-right --count "$primary...HEAD" 2>/dev/null)"
  behind="$(printf '%s' "$counts" | awk '{print $1}')"; ahead="$(printf '%s' "$counts" | awk '{print $2}')"
  dirty="$(git -C "$path" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${behind:-0}" -gt 0 ] || [ "$head_sha" != "$base_sha" ]; then
    printf '[itk-migrate] ⚠ BASE WARNING: checkout is %s commit(s) BEHIND %s (and %s ahead).\n' "${behind:-?}" "$primary" "${ahead:-?}" >&2
    printf '[itk-migrate]     HEAD %s   %s %s (%s, %s)\n' "$head_sha" "$primary" "$base_sha" "$base_date" "$freshness" >&2
    printf '[itk-migrate]     Migration results are only valid against current %s. Fetch+rebase first,\n' "$primary" >&2
    printf '[itk-migrate]     or set MC_NO_BASE_CHECK=1 to work off-primary intentionally.\n' >&2
  else
    printf '[itk-migrate] base: HEAD %s == %s (%s, %s); %s uncommitted file(s).\n' "$head_sha" "$primary" "$base_date" "$freshness" "$dirty" >&2
  fi
  [ "${dirty:-0}" -gt 0 ] && printf '[itk-migrate]     note: %s uncommitted change(s) in the tree are part of the base being transformed.\n' "$dirty" >&2
  return 0
}

# Echo the last argument that is an existing directory (the task repo path), else PWD.
_repo_from_args() {
  local p="$PWD" a
  for a in "$@"; do [ -d "$a" ] && p="$a"; done
  printf '%s' "$p"
}

cmd="${1:-help}"; shift || true
# Strip global base-check flags from anywhere in the args.
_args=(); for a in "$@"; do
  case "$a" in
    --no-base-check) MC_NO_BASE_CHECK=1 ;;
    --no-fetch) MC_NO_FETCH=1 ;;
    --allow-dirty) export MC_ALLOW_DIRTY=1 ;;
    *) _args+=("$a") ;;
  esac
done
set -- "${_args[@]+"${_args[@]}"}"
case "$cmd" in
  list)
    lvl=""; [ "${1:-}" = "--level" ] && lvl="${2:-}"
    for f in $(_task_files "$lvl"); do
      IFS=$'\t' read -r n l _ _g < <(_task_meta "$f")
      printf '%-28s [%s]\n' "$n" "$l"
    done
    ;;
  status)
    path="${1:-$PWD}"
    _primary_branch_report "$path"
    for f in $(_task_files ""); do
      IFS=$'\t' read -r n _ _ _g < <(_task_meta "$f")
      _is_pending "$path" "$f" && printf '%-28s PENDING\n' "$n" || printf '%-28s clean\n' "$n"
    done
    ;;
  run)
    [ -n "${1:-}" ] || { echo "run: missing task name" >&2; exit 1; }
    name="$1"; shift
    f=""
    for x in $(_task_files ""); do
      IFS=$'\t' read -r n _ _ _g < <(_task_meta "$x")
      if [ "$n" = "$name" ]; then f="$x"; break; fi
    done
    [ -n "$f" ] || { echo "no such task: $name" >&2; exit 1; }
    _primary_branch_report "$(_repo_from_args "$@")"
    bash "$f" "$@"
    ;;
  level)
    lvl="$1"; shift
    build_check=""; passthru=()
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --build-check) build_check="$2"; shift 2 ;;
        *) passthru+=("$1"); shift ;;
      esac
    done
    _primary_branch_report "$(_repo_from_args "${passthru[@]+"${passthru[@]}"}")"
    for f in $(_task_files "$lvl"); do
      IFS=$'\t' read -r n _ _ _g < <(_task_meta "$f")
      printf '\n=== %s ===\n' "$n"
      bash "$f" "${passthru[@]}"; rc=$?
      # Exit 3 = the task needs a clean tree (a prior task staged changes).
      # Each task is one clean commit, so stop and let the human commit.
      if [ "$rc" -eq 3 ]; then
        printf '\n[itk-migrate] stopping at %s: commit the staged changes above as one\n' "$n" >&2
        printf '[itk-migrate] commit, then re-run "level %s" to continue.\n' "$lvl" >&2
        exit 3
      fi
      if [ -n "$build_check" ]; then
        printf '... build-check: %s\n' "$build_check"
        ( eval "$build_check" ) || { echo "build-check FAILED after $n; stopping." >&2; exit 1; }
      fi
    done
    ;;
  review)
    # Guided walkthrough: for each PENDING task, show the proposed change and
    # accept with Y (the default). On accept, apply + offer to commit as one
    # clean commit, then move to the next task. Reads answers from stdin.
    lvl=""; [ "${1:-}" = "--level" ] && { lvl="${2:-}"; shift 2; }
    path="$(_repo_from_args "$@")"
    _primary_branch_report "$path"
    _accept() { case "$1" in n|N|no|NO) return 1 ;; *) return 0 ;; esac; }  # empty/Enter = yes
    reviewed=0; applied=0
    for f in $(_task_files "$lvl"); do
      IFS=$'\t' read -r n _ _ _g < <(_task_meta "$f")
      _is_pending "$path" "$f" || continue
      reviewed=$((reviewed + 1))
      printf '\n========== %s  [%s] ==========\n' "$n" "$(_task_meta "$f" | cut -f2)" >&2
      printf 'Recommendation: %s\n\n' "$(_task_subject "$f")" >&2
      bash "$f" --dry-run "$path" 2>&1   # proposed change (preview)
      printf '\nApply "%s"? [Y/n/q] ' "$n" >&2
      read -r ans || ans=""
      case "$ans" in q|Q|quit) printf 'Stopped.\n' >&2; break ;; esac
      _accept "$ans" || { printf 'Skipped %s.\n' "$n" >&2; continue; }
      bash "$f" "$path"; rc=$?
      if [ "$rc" -eq 3 ]; then
        printf 'Cannot apply: working tree has uncommitted changes — commit them first.\n' >&2; break
      fi
      if git -C "$path" diff --cached --quiet; then
        printf 'No automatic change (manual review / comment-only); nothing staged.\n' >&2; continue
      fi
      applied=$((applied + 1))
      git -C "$path" diff --cached --stat >&2
      printf 'Commit as one clean commit? [Y/n] ' >&2
      read -r ans || ans=""
      if _accept "$ans"; then
        if git -C "$path" commit -F "$HERE/commit-messages/${n}.msg" >/dev/null 2>&1; then
          printf 'Committed %s: %s\n' "$n" "$(git -C "$path" log -1 --format='%h %s')" >&2
        else
          printf 'Commit failed (pre-commit hooks?); the change is staged — resolve and commit manually.\n' >&2; break
        fi
      else
        printf 'Left staged (commit before the next task can apply).\n' >&2; break
      fi
    done
    [ "$reviewed" -eq 0 ] && printf 'Nothing to review — all tasks clean%s.\n' "${lvl:+ at level $lvl}" >&2
    printf '\nReviewed %s task(s); applied %s.\n' "$reviewed" "$applied" >&2
    ;;
  *)
    cat <<EOF
itk-migrate.sh — semi-automated ITK v5.4.6 -> v6.1 migration driver
  list [--level L]                 list tasks
  status [path]                    show pending/clean per task
  review [--level L] [path]        guided walkthrough: preview each pending task,
                                   press Y to apply + commit, move to the next
  run <task> [--dry-run|--no-stage] [path]
  level <L> [--dry-run] [--build-check "cmd"] [path]
Levels: $LEVELS manual

status/run/level report the checkout vs the primary branch (origin/HEAD) and
warn when it is behind — migration results are only valid against current
origin/main. The primary branch is fetched first by default; pass --no-fetch
(or MC_NO_FETCH=1) to skip the fetch, or --no-base-check (MC_NO_BASE_CHECK=1)
to work off-primary intentionally.

An editing task refuses to run on a dirty working tree (commit/stash first) so
each task yields exactly one clean commit; level stops after the first task
that stages changes. Override with --allow-dirty (MC_ALLOW_DIRTY=1).
EOF
    ;;
esac
