#!/usr/bin/env bash
# Shared test helpers. No external test framework required.
TOOLKIT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export TOOLKIT

mk_fixture_repo() {
  local d
  d="$(mktemp -d "${TMPDIR:-/tmp}/itk5to6-fixture.XXXXXX")"
  git -C "$d" init -q
  git -C "$d" config user.name  "itk5to6 test"
  git -C "$d" config user.email "itk5to6@example.invalid"
  git -C "$d" config commit.gpgsign false
  printf '%s\n' "$d"
}

_fail() { printf 'ASSERT FAIL: %s\n' "$*" >&2; exit 1; }

assert_eq() {
  local expected="$1" actual="$2" msg="${3:-}"
  if [ "$expected" != "$actual" ]; then
    printf 'expected: %s\nactual:   %s\n' "$expected" "$actual" >&2
    _fail "${msg:-assert_eq}"
  fi
}

assert_file_contains() {
  grep -qF -- "$2" "$1" || _fail "file $1 missing: $2"
}
assert_file_not_contains() {
  if grep -qF -- "$2" "$1"; then _fail "file $1 unexpectedly contains: $2"; fi
}

assert_exit_code() {
  local expected="$1"; shift
  local rc=0
  "$@" >/dev/null 2>&1 || rc=$?
  assert_eq "$expected" "$rc" "exit code of: $*"
}

assert_staged() {
  git diff --cached --name-only | grep -qx -- "$1" || _fail "not staged: $1"
}
