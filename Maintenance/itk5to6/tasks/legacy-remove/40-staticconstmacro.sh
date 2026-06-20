#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="staticconstmacro"; TASK_LEVEL="legacy-remove"
MC_FILE_GLOB='*.h *.hxx *.hpp *.txx *.cxx *.cpp *.cc *.c'
GREP_PATTERN='itkStaticConstMacro'
RESIDUAL_PATTERN='itkStaticConstMacro *\('
SED_EXPRS=('s/itkStaticConstMacro *( *\([^,]*\),[ \_s]*\([^,]*\),[ \_s]*\([^)]*\)) */static constexpr \2 \1 = \3/g')
read -r -d '' COMMIT_MSG <<'EOF' || true
STYLE: Replace itkStaticConstMacro with static constexpr

The 'itkStaticConstMacro(name, type, value)' macro expands to
'static const type name = value', which is a C++03 pattern. Modern
C++ prefers 'static constexpr type name = value', which ensures the
value is a compile-time constant and avoids ODR issues with
out-of-class definitions. The macro is removed when ITK_LEGACY_REMOVE
is ON.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
