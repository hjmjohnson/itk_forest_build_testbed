#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="coordrep-to-coordinate"; TASK_LEVEL="future-legacy-remove"
GREP_PATTERN='CoordRepType'
SED_EXPRS=(
  's/ImagePointCoordRepType/ImagePointCoordinateType/g'
  's/InputCoordRepType/InputCoordinateType/g'
  's/OutputCoordRepType/OutputCoordinateType/g'
  's/CoordRepType/CoordinateType/g'
)
read -r -d '' COMMIT_MSG <<'EOF' || true
STYLE: CoordRepType -> CoordinateType code readability

For the sake of code readability, a new 'CoordinateType' alias is added for
each nested 'CoordRepType' alias. The old 'CoordRepType' aliases will still be
available with ITK 6.0, but it is recommended to use 'CoordinateType' instead.
The 'CoordRepType' aliases will be removed when 'ITK_FUTURE_LEGACY_REMOVE' is
enabled. Similarly, 'InputCoordinateType', 'OutputCoordinateType', and
'ImagePointCoordinateType' replace 'InputCoordRepType', 'OutputCoordRepType',
and 'ImagePointCoordRepType', respectively.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_text_substitution_task
fi
