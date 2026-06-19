#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="spatialobject-space"; TASK_LEVEL="manual"
GREP_PATTERN='AddSpatialObject|RemoveSpatialObject|ScenePointer'
RESIDUAL_PATTERN='AddSpatialObject|RemoveSpatialObject|ScenePointer'
SED_EXPRS=(
  's/AddSpatialObject/AddChild/g'
  's/RemoveSpatialObject/RemoveChild/g'
  's/ScenePointer/GroupPointer/g'
)
read -r -d '' COMMIT_MSG <<'EOF' || true
ENH: Rename SpatialObject scene-graph API to child-based names (ITKv5→v6)

Mechanically renames the low-risk SpatialObject API:
  AddSpatialObject  → AddChild
  RemoveSpatialObject → RemoveChild
  ScenePointer      → GroupPointer

Manual follow-up required (NOT auto-renamed — per-call-site judgment needed):
- GetObjects() → GetChildren(): GetObjects is too generic (exists in VTK/Qt/
  other libs); inspect each call site and rename only SpatialObject uses.
- IsInside(pt) must become either IsInsideInObjectSpace(pt) or
  IsInsideInWorldSpace(pt) depending on which coordinate space the
  point is expressed in at each call site.
- ComputeMyBoundingBox() must become Update() followed by
  GetMyBoundingBoxInObjectSpace() or GetMyBoundingBoxInWorldSpace().
- Review each call site and choose the correct space variant.
  See the ITKv5 SpatialObject migration guide for details.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
