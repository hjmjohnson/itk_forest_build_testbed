#!/usr/bin/env bash
# Detect C-style casts (Type)expr that should become named C++ casts.
# Usage: detect.sh [repo-path]   (default: .)
# Boundary-aware: matches operator-preceded casts to type-looking targets,
# excludes ThirdParty/ and comment lines. Raw grep over all (ident) is too
# noisy; the clang AST matcher (google-readability-casting) is authoritative.
set -uo pipefail

REPO="${1:-.}"
cd "$REPO" || { echo "detect.sh: cannot cd to $REPO" >&2; exit 2; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "detect.sh: $REPO is not a git work tree" >&2; exit 2; }

# Cast must be preceded by an operator/punctuator that cannot end a declarator-id
# (drops function-param lists like operator++(int) and foo(unsigned int)).
# Cast target must look like a type: scalar keyword or a Type-suffixed identifier,
# optional const/sign qualifiers and a trailing '*'. Operand must be a value token.
PAT='(=|\(|,|<<|>>|\?|:|return)[[:space:]]*\(\s*(unsigned|signed|const)?\s*(unsigned|signed)?\s*(void|bool|char|short|int|long|float|double|size_t|ptrdiff_t|[A-Za-z_][A-Za-z0-9_]*(Type|ValueType|Pointer|PixelType|RealType|IdentifierType|Index|Offset))\s*\*?\s*\)\s*[A-Za-z_(][A-Za-z0-9_]'

# Pathspecs (quoted; glob-safe). Exclude ThirdParty and Examples doc-heavy text.
hits="$(git grep -nE "$PAT" -- \
        '*.cxx' '*.hxx' '*.h' '*.cpp' \
        ':!*ThirdParty*' ':!*/ThirdParty/*' ':!Examples/*' 2>/dev/null \
        | grep -vE ':[0-9]+:[[:space:]]*(//|\*|/\*)')"

if [ -n "$hits" ]; then
  printf '%s\n' "$hits"
fi

count="$(printf '%s' "$hits" | grep -c . )"
echo "----"
echo "C-style cast candidates: $count"
