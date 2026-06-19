#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
for s in itk-migrate-v6 itk-drop-version; do
  f="$TOOLKIT/skills/$s/SKILL.md"
  assert_file_contains "$f" "name: $s"
  assert_file_contains "$f" "user_invocable"
  assert_file_contains "$f" "user_confirmation_required"
done
echo "PASS test_skills"
