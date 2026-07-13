#!/usr/bin/env bash
# Bootstrap a new Insight Journal paper repo from the official template and drop
# in the skill's pre-filled starters. Idempotent: refuses to clobber an existing
# non-empty target unless --force is given.
#
# Usage: new-paper.sh <target-dir> [--force]
# Env:   SKILL_DIR  (auto-detected from this script's location)
set -euo pipefail

SKILL_DIR="${SKILL_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TEMPLATE_URL="https://github.com/InsightSoftwareConsortium/InsightJournalTemplate"

TARGET="${1:?usage: new-paper.sh <target-dir> [--force]}"
FORCE="${2:-}"

if [[ -e "$TARGET" && -n "$(ls -A "$TARGET" 2>/dev/null)" && "$FORCE" != "--force" ]]; then
  echo "ERROR: $TARGET exists and is non-empty. Pass --force to proceed." >&2
  exit 1
fi

echo ">> cloning template into $TARGET"
git clone --depth 1 "$TEMPLATE_URL" "$TARGET"
rm -rf "$TARGET/.git"

echo ">> installing pre-filled starters (myst.yml, docs/index.md)"
mkdir -p "$TARGET/docs" "$TARGET/data" "$TARGET/scripts" "$TARGET/src"
cp "$SKILL_DIR/assets/myst.yml" "$TARGET/myst.yml"
cp "$SKILL_DIR/assets/index.md" "$TARGET/docs/index.md"
[[ -f "$TARGET/docs/references.bib" ]] || printf '' > "$TARGET/docs/references.bib"

echo ">> writing .gitignore for build artifacts"
cat > "$TARGET/.gitignore" <<'EOF'
_build/
_deps/
exports/
build/
.pixi/
*.meca.zip
EOF

echo ">> git init"
git -C "$TARGET" init -q
echo
echo "Done. Next:"
echo "  1. Edit $TARGET/myst.yml   (title, ORCID, repo, IJ id)"
echo "  2. Write   $TARGET/docs/index.md ; refs -> docs/references.bib"
echo "  3. Code -> src/ ; data -> data/ ; figure scripts -> scripts/"
echo "  4. Preview: (cd $TARGET && pixi run start)   or   myst build --typst"
