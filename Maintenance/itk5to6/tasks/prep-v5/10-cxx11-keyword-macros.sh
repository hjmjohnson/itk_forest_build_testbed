#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="cxx11-keyword-macros"; TASK_LEVEL="prep-v5"
GREP_PATTERN='ITK_(NULLPTR|OVERRIDE|FINAL|CONSTEXPR|NOEXCEPT|ALIGNAS|ALIGNOF|EXTERN_TEMPLATE|THREAD_LOCAL|DELETE_FUNCTION|NOEXCEPT_OR_THROW|HAS_CXX11_STATIC_ASSERT|HAS_CPP11_ALIGNAS)'
SED_EXPRS=(
  's/ITK_NOEXCEPT_OR_THROW/ITK_NOEXCEPT/g'
  's/ITK_HAS_CXX11_STATIC_ASSERT/ITK_COMPILER_CXX_STATIC_ASSERT/g'
  's/ITK_DELETE_FUNCTION/ITK_DELETED_FUNCTION/g'
  's/ITK_HAS_CPP11_ALIGNAS/ITK_COMPILER_CXX_ALIGNAS/g'
  's/ITK_ALIGNAS/alignas/g'
  's/ITK_ALIGNOF/alignof/g'
  's/ITK_CONSTEXPR/constexpr/g'
  's/ITK_EXTERN_TEMPLATE/extern/g'
  's/ITK_FINAL/final/g'
  's/ITK_NOEXCEPT_EXPR/noexcept/g'
  's/ITK_NOEXCEPT/noexcept/g'
  's/ITK_NULLPTR/nullptr/g'
  's/ITK_OVERRIDE/override/g'
  's/ITK_THREAD_LOCAL/thread_local/g'
)
COMMIT_MSG="STYLE: Replace deprecated ITK C++11 compatibility macros with keywords

ITK requires C++17, so the C++11-era portability macros (ITK_NULLPTR,
ITK_OVERRIDE, ITK_CONSTEXPR, ITK_NOEXCEPT, ITK_FINAL, ITK_ALIGNAS,
ITK_ALIGNOF, ITK_EXTERN_TEMPLATE, ITK_THREAD_LOCAL, ITK_DELETED_FUNCTION)
are unconditionally identical to their standard keywords. Using the
keywords directly removes a layer of indirection and matches modern ITK."
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_text_substitution_task
fi
