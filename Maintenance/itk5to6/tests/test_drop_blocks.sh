#!/usr/bin/env bash
set -uo pipefail
export TOOLKIT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$TOOLKIT/tests/test_drop_blocks.py"
