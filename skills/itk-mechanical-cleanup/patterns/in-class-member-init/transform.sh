#!/usr/bin/env bash
# Append '{}' before the trailing ';' of uninitialized non-static members.
# Safe bare-{} case only; never touches constructors. Dry-run by default;
# --apply to write. Never commits. Re-run clang-format + build afterward.
set -uo pipefail

APPLY=0
REPO="."
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    *) REPO="$a" ;;
  esac
done

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
while IFS= read -r f; do
  [ -n "$f" ] || continue
  # Insert {} before the ; on matching lines lacking static/=/{/&.
  # Preserve an optional trailing comment.
  out=$(awk -v pat="$PAT" '
    {
      line=$0
      if (line ~ pat && line !~ /static/ && line !~ /=/ && line !~ /\{/ && line !~ /&[ \t]*m_/ \
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
      printf '%s\n' "$out" > "$f"
      echo "APPLIED: $f"
    else
      echo "WOULD EDIT: $f"
    fi
  fi
done <<< "$FILES"

echo "---"
echo "files_changed: $changed  (apply=$APPLY)"
[ "$APPLY" -eq 1 ] || echo "dry-run; re-run with --apply to write"
