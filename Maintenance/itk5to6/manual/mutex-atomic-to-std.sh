#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="mutex-atomic-to-std"; TASK_LEVEL="manual"
GREP_PATTERN='itk::(SimpleFastMutexLock|FastMutexLock|MutexLock|AtomicInt)'
RESIDUAL_PATTERN='itk::(SimpleFastMutexLock|FastMutexLock|MutexLock|AtomicInt)'
SED_EXPRS=(
  's/itk::SimpleFastMutexLock/std::mutex/g'
  's/itk::FastMutexLock/std::mutex/g'
  's/itk::MutexLock/std::mutex/g'
  's/itk::AtomicInt<\([^>]*\)>/std::atomic<\1>/g'
)
read -r -d '' COMMIT_MSG <<'EOF' || true
ENH: Replace ITK mutex/atomic types with C++11 std equivalents (ITKv5→v6)

Renames itk::SimpleFastMutexLock, itk::FastMutexLock, and
itk::MutexLock to std::mutex; replaces itk::AtomicInt<T>
with std::atomic<T>.

Manual follow-up required:
- Replace #include "itkSimpleFastMutexLock.h",
  #include "itkFastMutexLock.h", and #include "itkMutexLock.h"
  with #include <mutex>.
- Replace #include "itkAtomicInt.h" with #include <atomic>.
- MutexLock::Lock()/Unlock() map to std::mutex::lock()/unlock();
  prefer std::lock_guard<std::mutex> for RAII ownership.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
