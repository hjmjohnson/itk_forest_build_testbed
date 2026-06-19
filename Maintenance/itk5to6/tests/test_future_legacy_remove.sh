#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/helpers.sh"
T="$TOOLKIT/tasks/future-legacy-remove"
repo="$(mk_fixture_repo)"; cd "$repo"
printf 'using X = CoordRepType; using Y = InputCoordRepType;\n' > a.h; git add a.h >/dev/null
bash "$T/10-coordrep-to-coordinate.sh" "$repo" >/dev/null
assert_file_contains a.h "CoordinateType"
assert_file_contains a.h "InputCoordinateType"
assert_file_not_contains a.h "CoordRepType"
echo "PASS test_future_legacy_remove"
