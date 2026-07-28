#!/usr/bin/env bash
# Flag ImageRegion[Const]IteratorWithIndex declarations whose enclosing file
# never reads the index (.GetIndex / .GetIndexInternal) -> drop-WithIndex
# candidates. Review-gated: files with both a decl AND a GetIndex call are
# reported as REVIEW (may mix index-using and index-free iterators).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../../lib/detect-common.sh"

# Declaration sites: "...IteratorWithIndex<...> name(" or "= ...IteratorWithIndex<...>;"
DECL_RE='ImageRegion(Const)?IteratorWithIndex<'

itk_detect_init "${1:-.}"

# Drop doc-comment cross-reference lines.
hits="$(itk_detect_grep "$DECL_RE" "${ITK_DETECT_SOURCES[@]}" \
        | grep -vE '\\sa|^\S+:[0-9]+:[[:space:]]*\*|^\S+:[0-9]+:[[:space:]]*//')" || true

decls=0
candidate=0
review=0
seen_files=""

while IFS= read -r line; do
    [ -n "$line" ] || continue
    decls=$((decls + 1))
    file="${line%%:*}"
    echo "$line"
    case " ${seen_files} " in
        *" ${file} "*) continue ;;
    esac
    seen_files="${seen_files} ${file}"
    printf '    -> '
    if git grep -qE '\.GetIndex(Internal)?\(' -- "$file"; then
        echo "REVIEW (file also calls GetIndex; check per-variable)"
        review=$((review + 1))
    else
        echo "CANDIDATE (no GetIndex in file)"
        candidate=$((candidate + 1))
    fi
done <<< "$hits"

echo
itk_detect_report "$decls" \
    "CANDIDATE files (no GetIndex, safe to rewrite): ${candidate}" \
    "REVIEW files (mixed; manual per-variable check): ${review}"
