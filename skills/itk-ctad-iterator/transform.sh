#!/usr/bin/env bash
# Delete redundant explicit template args on single-line image-iterator
# constructions so C++17 CTAD deduces them. DRY-RUN by default; --apply writes.
# Never commits. Multi-line constructions are skipped (edit by hand).
set -uo pipefail

REPO="."
APPLY=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    *) REPO="$a" ;;
  esac
done

ITERS='ImageRegionConstIteratorWithIndex|ImageRegionIteratorWithIndex|ImageRegionConstIterator|ImageRegionIterator|ImageScanlineConstIterator|ImageScanlineIterator|ImageRegionRange|ImageBufferRange'
PATTERN="(${ITERS})<[^>;]+>[[:space:]]*\("

cd "$REPO" 2>/dev/null || { echo "no such repo: $REPO" >&2; exit 2; }

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  files=$(git grep -lE "$PATTERN" -- '*.hxx' '*.cxx' ':(exclude)*ThirdParty/*' 2>/dev/null)
else
  files=$(grep -rlE --include='*.hxx' --include='*.cxx' "$PATTERN" . 2>/dev/null \
          | grep -v '/ThirdParty/')
fi

[ -z "$files" ] && { echo "no candidate files"; exit 0; }

# Balanced-bracket delete of <...> immediately before '(' for the closed set.
# Operates per file via python for correctness with nested templates.
changed=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  out=$(APPLY="$APPLY" ITERS="$ITERS" python3 - "$f" <<'PY'
import os, re, sys
f = sys.argv[1]
iters = os.environ["ITERS"].split("|")
apply = os.environ["APPLY"] == "1"
name_re = re.compile(r'\b(' + "|".join(iters) + r')<')
src = open(f, encoding="utf-8", errors="surrogateescape").read()
lines = src.split("\n")
ndel = 0
newlines = []
for ln, line in enumerate(lines, 1):
    res = []
    i = 0
    out = line
    changed_line = False
    while True:
        m = name_re.search(out, i)
        if not m:
            break
        lt = m.end() - 1          # index of '<'
        depth = 0
        j = lt
        ok = False
        while j < len(out):
            c = out[j]
            if c == '<':
                depth += 1
            elif c == '>':
                depth -= 1
                if depth == 0:
                    ok = True
                    break
            j += 1
        if not ok:                # template args span lines -> skip
            i = m.end()
            continue
        k = j + 1
        while k < len(out) and out[k] in " \t":
            k += 1
        if k < len(out) and out[k] == '(':   # construction site
            out = out[:lt] + out[j+1:]
            ndel += 1
            changed_line = True
            i = lt
        else:
            i = m.end()
    if changed_line:
        print(f"{f}:{ln}: - {line.strip()}")
        print(f"{f}:{ln}: + {out.strip()}")
    newlines.append(out)
if apply and ndel:
    open(f, "w", encoding="utf-8", errors="surrogateescape").write("\n".join(newlines))
print(f"__DEL__ {ndel}")
PY
)
  n=$(printf '%s\n' "$out" | sed -n 's/^__DEL__ //p')
  printf '%s\n' "$out" | grep -v '^__DEL__'
  changed=$(( changed + ${n:-0} ))
done <<< "$files"

echo "----"
if [ "$APPLY" -eq 1 ]; then
  echo "applied deletions: $changed   (run clang-format + build to verify CTAD)"
else
  echo "dry-run deletions: $changed   (re-run with --apply to write)"
fi
