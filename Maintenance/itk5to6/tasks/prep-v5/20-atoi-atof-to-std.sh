#!/usr/bin/env bash
set -uo pipefail
source "$(cd "$(dirname "$0")/../../lib" && pwd)/migrate_common.sh"
TASK_NAME="atoi-atof-to-std"; TASK_LEVEL="prep-v5"
MC_FILE_GLOB='*.h *.hxx *.hpp *.txx *.cxx *.cpp *.cc *.c'
GREP_PATTERN='\b(atoi|atof) *\('
# Comment/string-aware (Python re) so doc comments and string literals that
# mention atoi/atof are never rewritten. Residual occurrences (e.g. in
# comments) are surfaced below for manual review.
# (?<![\w:]) avoids matching inside identifiers or other namespaces; optional
# std:: is consumed so an already-qualified std::atoi becomes std::stoi (not
# std::std::stoi).
MC_SUBST=('(?<![\w:])(?:std::)?atoi(\s*)\(' 'std::stoi\1(' '(?<![\w:])(?:std::)?atof(\s*)\(' 'std::stod\1(')
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
