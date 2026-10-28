#!/usr/bin/env bash
# Collapse a full-buffer ImageRegionIterator loop whose only statement is
# it.Set(<loop-invariant expr>) into image->FillBuffer(<expr>). Every other
# candidate loop is left alone and reported. Dry-run by default; --apply to
# write. Never commits. --manifest <path> (with --apply) clang-formats the
# edits and writes an itk-helpers manifest, skipped loops included;
# --graph <dir> is accepted for the common CLI. Files come from git grep, so
# only tracked files are edited; --tracked-only and --all-files are accepted.
set -uo pipefail

APPLY=0
REPO="."
MANIFEST=""
while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1 ;;
        --manifest) MANIFEST="${2:-}"; shift ;;
        --graph) shift ;;
        --llvm-bin) export IOA_LLVM_BIN="${2:-}"; shift ;;
        --tracked-only|--all-files) ;;
        *) REPO="$1" ;;
    esac
    shift
done
case "$MANIFEST" in
    ""|/*) ;;
    *) MANIFEST="$PWD/$MANIFEST" ;;
esac
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
. "$HERE/../../lib/detect-common.sh"

itk_detect_init "$REPO"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
SKIPS="$WORK/skips.tsv"
: > "$SKIPS"

FILES="$(git grep -lE 'IsAtEnd' -- "${ITK_DETECT_SOURCES[@]}" "${ITK_DETECT_EXCLUDES[@]}" 2>/dev/null || true)"

# Rewrite every file into $WORK first, so a failure part way leaves the tree untouched.
changed=0
EDITED=()
while IFS= read -r f; do
    [ -n "$f" ] || continue
    out="$WORK/new.$((changed + 1))"
    "$PY" "$HERE/fill_loops.py" "$f" "$out" --rel "$f" --skips "$SKIPS" || exit 1
    if ! cmp -s "$f" "$out"; then
        changed=$((changed + 1))
        EDITED+=("$f")
    fi
done <<< "$FILES"

PAIRS=()
i=0
for f in ${EDITED[@]+"${EDITED[@]}"}; do
    i=$((i + 1))
    if [ "$APPLY" -eq 1 ]; then
        cp "$f" "$WORK/orig.$i"
        PAIRS+=("$WORK/orig.$i=$f")
        cp "$WORK/new.$i" "$f"
        echo "APPLIED: $f"
    else
        echo "WOULD EDIT: $f"
    fi
done

while IFS="$(printf '\t')" read -r rel a _ _ note; do
    [ -n "$rel" ] && echo "SKIPPED: $rel:$a $note"
done < "$SKIPS"

if [ "$APPLY" -eq 1 ] && [ -n "$MANIFEST" ]; then
    "$PY" "$HERE/../../lib/manifest_from_diff.py" --repo . --cls fillbuffer-over-iterate \
        --manifest "$MANIFEST" --skips "$SKIPS" ${PAIRS[@]+"${PAIRS[@]}"} || exit 1
fi

echo "---"
echo "files_changed: $changed  skipped_loops: $(grep -c . "$SKIPS")  (apply=$APPLY)"
[ "$APPLY" -eq 1 ] || echo "dry-run; re-run with --apply to write"
