#!/usr/bin/env bash
# Warning-fatal syntax gate for the ITK modernization transforms.
#
# Thin wrapper over `python3 -m ioa.gate`: headers expand to up to 8 including
# translation units, each compiled -fsyntax-only with its real command from the
# build's compile_commands.json plus a fatal warning set, ccache disabled.
#
# Usage:
#   itk-compile-gate.sh <build-dir> <src.cxx|hdr.h|hdr.hxx> [...]
#   itk-compile-gate.sh <build-dir> --changed <repo>   # gate files changed vs HEAD
# Exit 0 only if every gated TU compiles clean.
set -uo pipefail

[ "$#" -ge 2 ] || { echo "usage: $0 <build-dir> <file>... | <build-dir> --changed <repo>" >&2; exit 2; }

BUILD="$1"; shift
[ -f "$BUILD/compile_commands.json" ] || { echo "no compile_commands.json in $BUILD" >&2; exit 2; }
BUILD="$(cd "$BUILD" && pwd)"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$HERE/itk-init-over-assign/lib${PYTHONPATH:+:$PYTHONPATH}"
PY="${CONDA_PREFIX:+$CONDA_PREFIX/bin/}python3"

INPUTS=()
if [ "${1:-}" = "--changed" ]; then
    ROOT="$(cd "${2:-.}" && pwd)"
    while IFS= read -r p; do
        [ -n "$p" ] && INPUTS+=("$ROOT/$p")
    done < <(git -C "$ROOT" diff --name-only HEAD -- '*.cxx' '*.cpp' '*.cc' '*.h' '*.hxx')
    if [ "${#INPUTS[@]}" -eq 0 ]; then
        echo "no changed C++ TUs vs HEAD"
        exit 0
    fi
else
    for f in "$@"; do
        case "$f" in /*) INPUTS+=("$f") ;; *) INPUTS+=("$PWD/$f") ;; esac
    done
    ROOT="$(dirname "${INPUTS[0]}")"
    while [ "$ROOT" != "/" ] && [ ! -e "$ROOT/.git" ]; do ROOT="$(dirname "$ROOT")"; done
    [ -e "$ROOT/.git" ] || { echo "no repo root above ${INPUTS[0]}" >&2; exit 2; }
fi

exec "$PY" -m ioa.gate --graph "$BUILD" --repo-root "$ROOT" "${INPUTS[@]}"
