#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBDIR="$SCRIPT_DIR/../lib"
TASK_NAME="drop-itk-v5"

# Detect --apply BEFORE mc_init — mc_init resets MC_DRY_RUN=0 unconditionally
case " $* " in *" --apply "*) APPLY=1 ;; *) APPLY=0 ;; esac

# shellcheck source=../lib/migrate_common.sh
source "$LIBDIR/migrate_common.sh"
mc_init "$@"
mc_branch_guard || exit 1

mapfile -t FILES < <(
  # || true: git grep exits non-zero when no files match; pipefail-safe
  git -C "$MC_REPO" grep -lE -- 'ITK_VERSION_MAJOR|__has_include' 2>/dev/null \
    | grep -vE '(^|/)ThirdParty/' || true
)

if [[ ${#FILES[@]} -eq 0 ]]; then
  printf '[%s] nothing to do\n' "$TASK_NAME"
  exit 0
fi

ABS_FILES=()
for f in "${FILES[@]}"; do
  ABS_FILES+=("$MC_REPO/$f")
done

DROP_ARGS=(--floor-major 6 --map "$LIBDIR/header_version_map.tsv")
[[ $APPLY -eq 1 ]] && DROP_ARGS+=(--apply)

python3 "$LIBDIR/drop_blocks.py" "${DROP_ARGS[@]}" "${ABS_FILES[@]}"
PY_EXIT=$?

if [[ $APPLY -eq 1 && $PY_EXIT -ne 1 ]]; then
  mc_stage "${ABS_FILES[@]}" || { echo "[${TASK_NAME}] staging failed" >&2; exit 1; }
  COMMIT_MSG="ENH: Drop pre-ITKv6 compatibility branches

Removes #if ITK_VERSION_MAJOR < 6 (and equivalent __has_include) dead
branches now that the build floor is ITKv6.1. Ambiguous blocks were left
intact and reported for manual review."
  mc_emit_commit_message "$TASK_NAME"
fi

exit "$PY_EXIT"
