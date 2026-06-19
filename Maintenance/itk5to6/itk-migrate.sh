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

cmd="${1:-help}"; shift || true
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
    for f in $(_task_files ""); do
      IFS=$'\t' read -r n _ p g < <(_task_meta "$f")
      if [ -n "$g" ]; then
        # shellcheck disable=SC2086
        git -C "$path" grep -qE -- "$p" -- $g ':!*ThirdParty/*' 2>/dev/null
      else
        git -C "$path" grep -qE -- "$p" -- ':!*ThirdParty/*' 2>/dev/null
      fi && printf '%-28s PENDING\n' "$n" || printf '%-28s clean\n' "$n"
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
    for f in $(_task_files "$lvl"); do
      IFS=$'\t' read -r n _ _ _g < <(_task_meta "$f")
      printf '\n=== %s ===\n' "$n"
      bash "$f" "${passthru[@]}" || true
      if [ -n "$build_check" ]; then
        printf '... build-check: %s\n' "$build_check"
        ( eval "$build_check" ) || { echo "build-check FAILED after $n; stopping." >&2; exit 1; }
      fi
    done
    ;;
  *)
    cat <<EOF
itk-migrate.sh — semi-automated ITK v5.4.6 -> v6.1 migration driver
  list [--level L]                 list tasks
  status [path]                    show pending/clean per task
  run <task> [--dry-run|--no-stage] [path]
  level <L> [--dry-run] [--build-check "cmd"] [path]
Levels: $LEVELS manual
EOF
    ;;
esac
