#!/usr/bin/env bash
# Core library for itk5to6 migration task scripts. Source, then set the
# declarative globals and call run_text_substitution_task / run_regex_review_task.
# Never commits, branches, or runs gh.

mc_sed_bin() {
  if [ "$(uname -s)" = "Darwin" ] && command -v gsed >/dev/null 2>&1; then
    printf 'gsed\n'
  else
    printf 'sed\n'
  fi
}

mc_init() {
  MC_DRY_RUN=0; MC_STAGE=1; MC_REPO=""
  SED="$(mc_sed_bin)"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run) MC_DRY_RUN=1 ;;
      --no-stage) MC_STAGE=0 ;;
      --apply) MC_DRY_RUN=0 ;;
      -*) printf 'unknown flag: %s\n' "$1" >&2; return 1 ;;
      *) MC_REPO="$1" ;;
    esac
    shift
  done
  [ -n "$MC_REPO" ] || MC_REPO="$PWD"
  MC_REPO="$(cd "$MC_REPO" && pwd)"
  cd "$MC_REPO" || return 1
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    printf 'not a git work tree: %s\n' "$MC_REPO" >&2; return 1; }
  # toolkit dir for writing .msg files
  MC_TOOLKIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
}

mc_files_with() {
  if [ -n "${MC_FILE_GLOB:-}" ]; then
    # shellcheck disable=SC2086
    git grep -lE -- "$1" -- $MC_FILE_GLOB 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true
  else
    git grep -lE -- "$1" 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true
  fi
}

mc_apply_sed() {
  local expr="$1"; shift
  if "$SED" --version >/dev/null 2>&1; then
    "$SED" -i -e "$expr" "$@"          # GNU sed/gsed
  else
    "$SED" -i '' -e "$expr" "$@"       # BSD sed
  fi
}

mc_stage() {
  [ "$MC_STAGE" -eq 1 ] || return 0
  git add -- "$@"
}

mc_branch_guard() {
  local br; br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
  case "$br" in
    main|master)
      if [ -t 0 ]; then
        printf 'On branch %s. [c]reate working branch / [e]dit here / [a]bort? ' "$br" >&2
        read -r ans
        case "$ans" in
          c|C) printf 'Run:  git switch -c itk5to6-migration\nThen re-run.\n' >&2; return 1 ;;
          a|A) printf 'aborted\n' >&2; return 1 ;;
          *) return 0 ;;
        esac
      else
        printf 'WARNING: editing on %s (non-interactive); proceeding.\n' "$br" >&2
      fi
      ;;
  esac
  return 0
}

mc_emit_commit_message() {
  local task="$1"
  local out="$MC_TOOLKIT/commit-messages/${task}.msg"
  printf '%s\n' "$COMMIT_MSG" > "$out"
  printf '\n----- suggested commit message (also written to %s) -----\n' "$out"
  printf '%s\n' "$COMMIT_MSG"
  printf -- '----- the human reviews, validates (pre-commit), and commits -----\n'
}

run_text_substitution_task() {
  [ "${MC_META_ONLY:-0}" = "1" ] && return 0
  mc_branch_guard || return 1
  local files; files="$(mc_files_with "$GREP_PATTERN")"
  if [ -z "$files" ]; then
    printf '[%s] nothing to do (no %s)\n' "$TASK_NAME" "$GREP_PATTERN"
    return 0
  fi
  # shellcheck disable=SC2206
  local farr=(); while IFS= read -r f; do farr+=("$f"); done <<< "$files"
  if [ "$MC_DRY_RUN" -eq 1 ]; then
    printf '[%s] DRY RUN; would modify %d file(s):\n' "$TASK_NAME" "${#farr[@]}"
    local tmp expr
    for f in "${farr[@]}"; do
      tmp="$(mktemp)"; cp "$f" "$tmp"
      for expr in "${SED_EXPRS[@]}"; do mc_apply_sed "$expr" "$tmp"; done
      diff -u "$f" "$tmp" | "$SED" "s|$tmp|$f (proposed)|" || true
      rm -f "$tmp"
    done
    return 0
  fi
  local expr
  for expr in "${SED_EXPRS[@]}"; do mc_apply_sed "$expr" "${farr[@]}"; done
  mc_stage "${farr[@]}"
  printf '[%s] modified and staged %d file(s).\n' "$TASK_NAME" "${#farr[@]}"
  mc_emit_commit_message "$TASK_NAME"
  return 0
}

mc_report_only() {  # $1 = guidance string; uses GREP_PATTERN (honors MC_FILE_GLOB)
  [ "${MC_META_ONLY:-0}" = "1" ] && return 0
  local hits
  hits="$(git grep -nE -- "$GREP_PATTERN" ${MC_FILE_GLOB:+-- $MC_FILE_GLOB} 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true)"
  if [ -z "$hits" ]; then
    printf '[%s] nothing to do\n' "$TASK_NAME"
    return 0
  fi
  printf '[%s] manual review required:\n%s\n\nGUIDANCE: %s\n' "$TASK_NAME" "$hits" "$1"
  return 2
}

run_regex_review_task() {
  [ "${MC_META_ONLY:-0}" = "1" ] && return 0
  run_text_substitution_task || return $?
  [ "$MC_DRY_RUN" -eq 1 ] && return 0
  local residual
  if [ -n "${MC_FILE_GLOB:-}" ]; then
    # shellcheck disable=SC2086
    residual="$(git grep -nE -- "${RESIDUAL_PATTERN:-$GREP_PATTERN}" -- $MC_FILE_GLOB 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true)"
  else
    residual="$(git grep -nE -- "${RESIDUAL_PATTERN:-$GREP_PATTERN}" 2>/dev/null | grep -vE '(^|/)ThirdParty/' || true)"
  fi
  if [ -n "$residual" ]; then
    printf '\n[%s] WARNING: review these residual sites (regex could not fully transform):\n%s\n' "$TASK_NAME" "$residual"
    return 2
  fi
  return 0
}
