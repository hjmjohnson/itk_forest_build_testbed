#!/usr/bin/env bash
# Assert every skill/rule referenced by a lifecycle SKILL.md exists on disk.
#   validate-lifecycle-refs.sh <path-to-SKILL.md>
# Checks: (1) each cited rules/<name>.md exists under the deployed rules dir (CLAUDE_RULES_DIR or ~/.claude/rules);
#         (2) the itk-start-worktree skill dir exists;
#         (3) at least one eligible payload skill is listed.
# Prints a MISSING: line per failure; exit 1 if any, else 0.
set -uo pipefail
skill_md="${1:?usage: validate-lifecycle-refs.sh <SKILL.md>}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skills_root="$(dirname "$here")"
rc=0

# (1) cited rules resolve at the deployed rules dir (not this repo — rules/ is gitignored here)
rules_dir="${CLAUDE_RULES_DIR:-$HOME/.claude/rules}"
while IFS= read -r rulepath; do
  name="${rulepath#rules/}"
  [ -f "$rules_dir/$name" ] || { echo "MISSING: $rulepath (looked in $rules_dir)"; rc=1; }
done < <(grep -oE 'rules/[a-z0-9-]+\.md' "$skill_md" | sort -u)

# (2) fixed sub-skill
if grep -q 'itk-start-worktree' "$skill_md"; then
  [ -d "$skills_root/itk-start-worktree" ] || { echo "MISSING: skills/itk-start-worktree"; rc=1; }
fi

# (3) at least one payload
if ! bash "$here/list-cleanup-patterns.sh" >/dev/null 2>&1; then
  echo "MISSING: no eligible payload skills (no itk-*/detect.sh found)"; rc=1
fi

[ "$rc" -eq 0 ] && echo "OK: all references resolve"
exit "$rc"
