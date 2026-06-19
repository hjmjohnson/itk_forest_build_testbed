#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="cmake-blockend-cruft"; TASK_LEVEL="prep-v5"
MC_FILE_GLOB='*.cmake CMakeLists.txt'
GREP_PATTERN='\b(else|endif|endforeach|endfunction|endmacro|endwhile)\s*\([^)]+\)'
# GNU BRE: \(…\|…\) is alternation, group 1 captures the command name, ([^)]*) matches and drops the argument list.
SED_EXPRS=('s/\b\(else\|endif\|endforeach\|endfunction\|endmacro\|endwhile\)[[:space:]]*([^)]*)/\1()/g')
COMMIT_MSG="STYLE: Drop block-end command arguments (else(x)->else())

CMake ignores arguments to block-end commands (else, endif, endforeach,
endfunction, endmacro, endwhile). The arguments duplicate the opening
condition, drift over time, and add noise. Removing them is idiomatic
modern CMake."
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_text_substitution_task
fi
