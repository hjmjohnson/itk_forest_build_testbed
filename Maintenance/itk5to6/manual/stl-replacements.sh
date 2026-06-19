#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../lib" && pwd)/migrate_common.sh"
TASK_NAME="stl-replacements"; TASK_LEVEL="manual"
GREP_PATTERN='itksys::hash_map|mpl::(EnableIf|IsSame|IsBaseOf|IsConvertible)'
RESIDUAL_PATTERN='itksys::hash_map|mpl::(EnableIf|IsSame|IsBaseOf|IsConvertible)'
SED_EXPRS=(
  's/itksys::hash_map/std::unordered_map/g'
  's/mpl::EnableIf/std::enable_if_t/g'
  's/mpl::IsSame/std::is_same/g'
  's/mpl::IsBaseOf/std::is_base_of/g'
  's/mpl::IsConvertible/std::is_convertible/g'
)
read -r -d '' COMMIT_MSG <<'EOF' || true
ENH: Replace ITK/itksys type-trait and hash_map with C++11/14 STL (ITKv5→v6)

Replaces itksys::hash_map with std::unordered_map and itk::mpl type
traits (EnableIf, IsSame, IsBaseOf, IsConvertible) with their
standard-library equivalents.

Manual follow-up required:
- Replace #include "itkHashMap.h" / itksys hash headers with
  #include <unordered_map>.
- Replace #include "itkMPLContainers.h" / itkEnableIf.h etc. with
  #include <type_traits>.
- itksys::hash_map provides defined iteration order; std::unordered_map
  does not — review algorithms that assume ordered traversal.
- mpl::EnableIf<C,T>::Type → std::enable_if_t<C::value,T> (note
  ::value accessor difference).
- mpl::IsSame<A,B>, mpl::IsBaseOf<A,B>, mpl::IsConvertible<A,B> were
  boolean-valued; the std equivalents need ::value in boolean contexts —
  prefer the C++17 _v aliases (std::is_same_v<A,B>, std::is_base_of_v<A,B>,
  std::is_convertible_v<A,B>). Manual review needed where the type was
  used directly as a bool.
EOF
if [ "${MC_META_ONLY:-0}" != "1" ]; then
  mc_init "$@"
  run_regex_review_task
fi
