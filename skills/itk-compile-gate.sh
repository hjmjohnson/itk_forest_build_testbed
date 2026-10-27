#!/usr/bin/env bash
# Warning-fatal compile gate for the ITK modernization transforms.
#
# Compiles each translation unit -fsyntax-only using the REAL compile command
# from an existing ninja build graph, plus a fatal warning set that catches the
# dead-code regressions these transforms can introduce (orphaned type aliases,
# set-but-unused locals). A plain syntax-only gate misses these; GCC's
# -Wunused-local-typedefs and the report_build_diagnostics.py dashboards that
# treat warnings as fatal reject what a Clang-only local check passes.
#
# ccache is disabled for the gate: a cache hit replays a stale object without
# re-running the compiler, so a freshly-introduced warning never appears (this
# is why the PR #608 dead-typedef regression passed macOS CI but failed GCC).
#
# Usage:
#   itk-compile-gate.sh <build-dir> <src.cxx|hdr.h|hdr.hxx> [...]
#   itk-compile-gate.sh <build-dir> --changed <repo>   # gate files changed vs HEAD
# A header is gated through up to 8 translation units that include it.
#
# Apply the transform in place first, then run this against the touched TUs.
# Exit 0 only if every gated TU compiles clean with no fatal warning.
set -uo pipefail

[ "$#" -ge 2 ] || { echo "usage: $0 <build-dir> <src.cxx|hdr.h>... | <build-dir> --changed <repo>" >&2; exit 2; }

BUILD="$1"; shift
[ -f "$BUILD/build.ninja" ] || { echo "not a ninja build dir: $BUILD" >&2; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$HERE/itk-init-over-assign/lib${PYTHONPATH:+:$PYTHONPATH}"

INPUTS=()
REPO=""
if [ "${1:-}" = "--changed" ]; then
    REPO="$(cd "${2:-.}" && pwd)"
    while IFS= read -r p; do
        [ -n "$p" ] && INPUTS+=("$REPO/$p")
    done < <(git -C "$REPO" diff --name-only HEAD -- '*.cxx' '*.cpp' '*.cc' '*.h' '*.hxx')
    [ "${#INPUTS[@]}" -gt 0 ] || { echo "no changed C++ files vs HEAD"; exit 0; }
else
    for f in "$@"; do
        case "$f" in /*) INPUTS+=("$f") ;; *) INPUTS+=("$PWD/$f") ;; esac
    done
fi

HAS_HEADER=0
for f in "${INPUTS[@]}"; do
    case "$f" in *.h|*.hxx) HAS_HEADER=1 ;; esac
done

TUS=()
if [ "$HAS_HEADER" -eq 1 ]; then
    [ -n "$REPO" ] || REPO="$(git -C "$(dirname "${INPUTS[0]}")" rev-parse --show-toplevel)" \
        || { echo "cannot find repo root for ${INPUTS[0]}" >&2; exit 2; }
    [ -f "$BUILD/compile_commands.json" ] || { echo "no compile_commands.json in $BUILD" >&2; exit 2; }
    expand_err="$(mktemp)"
    while IFS= read -r t; do
        [ -n "$t" ] && TUS+=("$t")
    done < <(python3 -m ioa.gate --expand --graph "$BUILD" --repo-root "$REPO" "${INPUTS[@]}" 2>"$expand_err")
    DEAD="$(cat "$expand_err")"; rm -f "$expand_err"
else
    TUS=("${INPUTS[@]}")
    DEAD=""
fi

# Warning sets differ by compiler family: -Wunused-local-typedefs is GCC,
# -Wunused-local-typedef (no 's') is Clang. Passing the wrong spelling to the
# other compiler errors, so select by the compile command's compiler token.
gcc_warnflags="-fsyntax-only -Wunused-local-typedefs -Werror=unused-local-typedefs -Wunused-but-set-variable -Werror=unused-but-set-variable -Wunused-variable -Werror=unused-variable"
clang_warnflags="-fsyntax-only -Wunused-local-typedef -Werror=unused-local-typedef -Wunused-but-set-variable -Werror=unused-but-set-variable -Wunused-variable -Werror=unused-variable"

fail=0
gated=0
for src in "${TUS[@]}"; do
    base="$(basename "$src")"
    obj="$(ninja -C "$BUILD" -t targets all 2>/dev/null | grep -E "/${base}\.o:" | head -1 | cut -d: -f1)"
    if [ -z "$obj" ]; then
        echo "SKIP  $base (no object in build graph)"
        continue
    fi
    cmd="$(ninja -C "$BUILD" -t commands "$obj" 2>/dev/null | tail -1)"
    [ -n "$cmd" ] || { echo "SKIP  $base (no compile command)"; continue; }

    if echo "$cmd" | grep -q clang; then wf="$clang_warnflags"; else wf="$gcc_warnflags"; fi

    # Drop object-output and dependency-generation flags; -fsyntax-only writes
    # nothing. Insert the fatal warning set before the -c source argument.
    cmd2="$(echo "$cmd" | sed -E \
        -e 's#-o +[^ ]+\.o##' \
        -e 's# -M[TQF] +[^ ]+##g' -e 's# -M[DM]?( |$)# #g' \
        -e "s#-c +#${wf//#/\\#} -c #")"

    gated=$((gated+1))
    out="$(cd "$BUILD" && CCACHE_DISABLE=1 bash -c "$cmd2" 2>&1)"; rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "OK    $base"
    else
        echo "FAIL  $base"
        echo "$out" | grep -iE "error|warning" | head -8 | sed 's/^/        /'
        fail=1
    fi
done

if [ -n "$DEAD" ]; then
    echo "$DEAD" | sed 's/^/FAIL  /'
    fail=1
fi

echo "----------------------------------------"
echo "gated: $gated  result: $([ "$fail" -eq 0 ] && echo PASS || echo FAIL)"
exit "$fail"
