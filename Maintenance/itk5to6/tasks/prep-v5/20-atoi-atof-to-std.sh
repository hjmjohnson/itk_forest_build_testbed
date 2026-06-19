#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="atoi-atof-to-std"; TASK_LEVEL="prep-v5"
GREP_PATTERN='\b(atoi|atof) *\('
SED_EXPRS=('s/\batoi *(/std::stoi(/g' 's/\batof *(/std::stod(/g')
RESIDUAL_PATTERN='\b(atoi|atof) *\('
COMMIT_MSG="ENH: Replace atoi/atof with std::stoi/std::stod

std::stoi/std::stod throw std::invalid_argument on malformed input
instead of silently returning 0, surfacing parse errors that atoi/atof
hide. Requires <string>. Review call sites that relied on the silent-0
behavior."
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
