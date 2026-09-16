#!/usr/bin/env bash
# Phase 1 of itk-modernize-use-override: clang-tidy modernize-use-override over one build tree.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: override_sweep.sh --src DIR --build DIR [--fix] [--jobs N] [--exclude REGEX] [--llvm DIR]

  --src      source worktree (edits land here)
  --build    build tree containing compile_commands.json
  --fix      apply fixes (default: report only)
  --jobs     parallel clang-tidy jobs (default: CPU count)
  --exclude  path regex excluded from sources and headers (default: ThirdParty|_deps|-build/)
  --llvm     LLVM bin dir providing clang-tidy tools (default: first found on PATH or Homebrew)
Reports go to <build>/override-sweep/.
EOF
}

SRC="" BLD="" FIX=0 JOBS="" EXCLUDE='(ThirdParty|_deps|-build/|/KWStyle/)' LLVM=""
while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC=$2; shift 2 ;;
    --build) BLD=$2; shift 2 ;;
    --fix) FIX=1; shift ;;
    --jobs) JOBS=$2; shift 2 ;;
    --exclude) EXCLUDE=$2; shift 2 ;;
    --llvm) LLVM=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
[ -n "$SRC" ] && [ -n "$BLD" ] || { usage; exit 2; }
SRC=$(cd "$SRC" && pwd); BLD=$(cd "$BLD" && pwd)
[ -f "$BLD/compile_commands.json" ] || { echo "no compile_commands.json in $BLD (configure with -DCMAKE_EXPORT_COMPILE_COMMANDS=ON)" >&2; exit 1; }

if [ -z "$LLVM" ]; then
  if command -v run-clang-tidy >/dev/null 2>&1; then LLVM=$(dirname "$(command -v run-clang-tidy)")
  elif [ -x /opt/homebrew/opt/llvm/bin/run-clang-tidy ]; then LLVM=/opt/homebrew/opt/llvm/bin
  else echo "run-clang-tidy not found; pass --llvm" >&2; exit 1; fi
fi
if [ -z "$JOBS" ]; then JOBS=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4); fi

OUT="$BLD/override-sweep"; mkdir -p "$OUT"
CONFIG='{Checks: "-*,modernize-use-override", CheckOptions: {modernize-use-override.AllowOverrideAndFinal: false, modernize-use-override.IgnoreDestructors: false, modernize-use-override.IgnoreTemplateInstantiations: false}}'

echo "Repo: $(git -C "$SRC" remote get-url origin 2>/dev/null || echo "$SRC") ($(git -C "$SRC" rev-parse --short HEAD)) | Build: $BLD"
"$LLVM/run-clang-tidy" -p "$BLD" -clang-tidy-binary "$LLVM/clang-tidy" -j "$JOBS" -quiet \
  -config="$CONFIG" \
  -header-filter="^$SRC/.*" -exclude-header-filter=".*$EXCLUDE.*" \
  -source-filter="^$SRC/(?!.*$EXCLUDE).*" \
  -export-fixes "$OUT/fixes.yaml" > "$OUT/clang-tidy.log" 2>&1 || true

awk '/warning: .*\[modernize-use-override\]/' "$OUT/clang-tidy.log" | sort -u > "$OUT/warnings.txt"
awk '/Error while processing/' "$OUT/clang-tidy.log" | sort -u > "$OUT/unparsed-tus.txt"
echo "unique warnings: $(wc -l < "$OUT/warnings.txt" | tr -d ' ')"
echo "TUs clang-tidy could not parse: $(wc -l < "$OUT/unparsed-tus.txt" | tr -d ' ') (see $OUT/unparsed-tus.txt)"
awk -F: -v src="$SRC/" '{sub(src, "", $1); print $1}' "$OUT/warnings.txt" | sort | uniq -c | sort -rn > "$OUT/files.txt"

[ "$FIX" = 1 ] || { echo "report only; rerun with --fix to apply"; exit 0; }
[ -s "$OUT/fixes.yaml" ] || { echo "no fixes exported"; exit 0; }

rm -rf "$OUT/apply" && mkdir -p "$OUT/apply" && cp "$OUT/fixes.yaml" "$OUT/apply/"
"$LLVM/clang-apply-replacements" "$OUT/apply"

changed=$(git -C "$SRC" diff --name-only)
[ -n "$changed" ] || { echo "fixes applied no changes"; exit 0; }
for f in $changed; do
  perl -0pi -e '1 while s/\b(override|final)(\s+)\1\b/$1/g' "$SRC/$f"
done
if [ -f "$SRC/.clang-format" ]; then
  (cd "$SRC" && echo "$changed" | xargs "$LLVM/clang-format" -i)
fi
dups=$(cd "$SRC" && echo "$changed" | xargs perl -ne 'print "$ARGV:$.\n" if /\boverride\b.*\boverride\b/; close ARGV if eof')
[ -z "$dups" ] || { echo "duplicate override remains:" >&2; echo "$dups" >&2; exit 1; }
git -C "$SRC" diff --stat | tail -1
echo "review the diff, build, test, then commit"
