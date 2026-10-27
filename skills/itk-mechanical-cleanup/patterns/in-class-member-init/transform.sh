#!/usr/bin/env bash
# Append '{}' before the trailing ';' of uninitialized non-static members.
# Safe bare-{} case only; never touches constructors or smart-pointer members.
# Dry-run by default; --apply to write. Never commits. Re-run clang-format +
# build afterward. --manifest <path> (with --apply) clang-formats the edits and
# writes a member-default-init manifest; --graph <dir> is accepted for the
# common CLI.
set -uo pipefail

APPLY=0
REPO="."
MANIFEST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --manifest) MANIFEST="${2:-}"; shift ;;
    --graph) shift ;;
    *) REPO="$1" ;;
  esac
  shift
done
case "$MANIFEST" in
  ""|/*) ;;
  *) MANIFEST="$PWD/$MANIFEST" ;;
esac
HELPER="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../lib" && pwd)/manifest_from_diff.py"

PAT='^[[:space:]]+[A-Za-z_][A-Za-z0-9_:<>,* ]*[ *]m_[A-Za-z0-9_]+(\[[^]]*\])?[[:space:]]*;[[:space:]]*(//.*)?$'

cd "$REPO" || { echo "cannot cd to $REPO" >&2; exit 2; }

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  FILES=$(git grep -lE "$PAT" -- '*.h' '*.hxx' \
            ':(exclude)*ThirdParty/*' ':(exclude)*/ThirdParty/*' 2>/dev/null)
else
  FILES=$(grep -rlE "$PAT" --include='*.h' --include='*.hxx' . 2>/dev/null \
          | grep -v '/ThirdParty/')
fi

changed=0
SAVED=""
PAIRS=()
if [ "$APPLY" -eq 1 ] && [ -n "$MANIFEST" ]; then
  SAVED=$(mktemp -d)
  trap 'rm -rf "$SAVED"' EXIT
fi
while IFS= read -r f; do
  [ -n "$f" ] || continue
  # Insert {} before the ; on matching lines lacking static/=/{/&.
  # Preserve an optional trailing comment.
  out=$(awk -v pat="$PAT" '
    {
      line=$0
      type=line
      sub(/m_[A-Za-z0-9_]+.*$/, "", type)
      if (line ~ pat && line !~ /static/ && line !~ /=/ && line !~ /\{/ && line !~ /&[ \t]*m_/ \
          && type !~ /Pointer|unique_ptr|shared_ptr/ \
          && line !~ /^[ \t]*(return|delete|throw|co_return)[ \t]/) {
        # split off a trailing // comment
        cmt=""
        body=line
        i=index(body, "//")
        if (i>0) { cmt=substr(body, i); body=substr(body, 1, i-1) }
        # append {} before the last ;
        sub(/;[ \t]*$/, "{};", body)
        if (cmt!="") body=body " " cmt
        print body
        next
      }
      print line
    }' "$f")
  if [ "$out" != "$(cat "$f")" ]; then
    changed=$((changed+1))
    if [ "$APPLY" -eq 1 ]; then
      if [ -n "$SAVED" ]; then
        cp "$f" "$SAVED/$changed"
        PAIRS+=("$SAVED/$changed=$f")
      fi
      printf '%s\n' "$out" > "$f"
      echo "APPLIED: $f"
    else
      echo "WOULD EDIT: $f"
    fi
  fi
done <<< "$FILES"

if [ -n "$SAVED" ]; then
  "${PYTHON:-python3}" "$HELPER" --repo . --cls in-class-member-init --kind member-default-init --manifest "$MANIFEST" \
    ${PAIRS[@]+"${PAIRS[@]}"} || exit 1
fi

echo "---"
echo "files_changed: $changed  (apply=$APPLY)"
[ "$APPLY" -eq 1 ] || echo "dry-run; re-run with --apply to write"
