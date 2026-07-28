#!/usr/bin/env bash
# Detect C-style casts (Type)expr that should become named C++ casts.
# Usage: detect.sh [repo-path]   (default: .)
# Boundary-aware: matches operator-preceded casts to type-looking targets,
# excludes comment lines. Raw grep over all (ident) is too noisy; the clang AST
# matcher (google-readability-casting) is authoritative.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"

# Cast must be preceded by an operator/punctuator that cannot end a declarator-id
# (drops function-param lists like operator++(int) and foo(unsigned int)).
# Cast target must look like a type: scalar keyword or a Type-suffixed identifier,
# optional const/sign qualifiers and a trailing '*'. Operand must be a value token.
PATTERN='(=|\(|,|<<|>>|\?|:|return)[[:space:]]*\(\s*(unsigned|signed|const)?\s*(unsigned|signed)?\s*(void|bool|char|short|int|long|float|double|size_t|ptrdiff_t|[A-Za-z_][A-Za-z0-9_]*(Type|ValueType|Pointer|PixelType|RealType|IdentifierType|Index|Offset))\s*\*?\s*\)\s*[A-Za-z_(][A-Za-z0-9_]'

itk_detect_init "${1:-.}"

# Examples/ is prose-heavy and generates noise disproportionate to its value.
hits="$(itk_detect_grep "$PATTERN" "${ITK_DETECT_SOURCES[@]}" ':(exclude)Examples/*' \
        | grep -vE ':[0-9]+:[[:space:]]*(//|\*|/\*)')" || true
[ -n "$hits" ] && printf '%s\n' "$hits"

itk_detect_report "$(itk_detect_count "$hits")"
