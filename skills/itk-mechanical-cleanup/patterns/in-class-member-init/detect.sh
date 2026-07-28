#!/usr/bin/env bash
# Detect uninitialized non-static data members (m_Foo;) in class headers.
# Flags members with no in-class initializer; skips static/=/{/reference.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../../lib/detect-common.sh"

# Member-decl pattern: indented   <type> m_Name[opt-array] ;   [opt-comment]
# Excludes lines with '=' or '{' (already initialized) and '&' (reference).
PAT='^[[:space:]]+[A-Za-z_][A-Za-z0-9_:<>,* ]*[ *]m_[A-Za-z0-9_]+(\[[^]]*\])?[[:space:]]*;[[:space:]]*(//.*)?$'
# Statement keywords that masquerade as a "type" (return m_X; etc.) — not decls.
# Matched after the "path:lineno:" prefix git grep emits.
STMT=':[[:space:]]*(return|delete|throw|co_return)\b'

itk_detect_init "${1:-.}"

# Headers only: a member declaration cannot appear outside a class definition.
hits="$(itk_detect_grep "$PAT" "${ITK_DETECT_HEADERS[@]}" \
        | grep -vE '\bstatic\b' \
        | grep -vE '&[[:space:]]*m_' \
        | grep -vE "$STMT")" || true
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")"
