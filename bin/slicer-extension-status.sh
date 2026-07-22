#!/usr/bin/env bash
# Real pass/fail status for every Slicer extension built in a forest.
#
#   FOREST_REFERENCE_SUFFIX=itk-main bash bin/slicer-extension-status.sh
#   ... bash bin/slicer-extension-status.sh --tsv         # machine-readable
#
# WHY THIS EXISTS
# ---------------
# The extensions SuperBuild cannot report failure. Each extension is built by a
# wrapper script whose non-zero result is discarded:
#
#     -- build_<Ext>_wrapper_script: Ignoring result '255'
#     [N/M] Completed '<Ext>'
#
# so `ninja` exits 0 and every extension reads as "Completed" even when its
# inner build produced hundreds of errors. That is correct for the upstream
# dashboard driver -- one broken extension must not abort a nightly, because
# each result is submitted to CDash separately -- but this forest has no CDash
# consumer, so the failures went nowhere and the build reported a false green.
#
# Ground truth is the per-extension output/error files the wrapper leaves in the
# extensions build dir. This script reads those, never the SuperBuild exit code.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
SUFFIX="${FOREST_REFERENCE_SUFFIX:-}"
FOREST="${BUILD_FOREST_ROOT:-${ROOT}/build_forest${SUFFIX:+-${SUFFIX}}}"
BUILD="${FOREST}/SlicerExtensions/build"
TSV=0; [ "${1:-}" = "--tsv" ] && TSV=1

[ -d "${BUILD}" ] || { echo "no extensions build dir: ${BUILD}" >&2; exit 1; }

pass=0; fail=0; unbuilt=0
rows=()

shopt -s nullglob
for out in "${BUILD}"/build_*output.txt; do
  base="$(basename "${out}")"; ext="${base#build_}"; ext="${ext%output.txt}"
  err="${BUILD}/build_${ext}_error.txt"

  # CTest writes an authoritative "<N> Compiler errors" line per phase. The
  # FIRST is the extension build; a SECOND (when present) is the packaging
  # phase, whose count is CPack otool/install_name_tool bundle-fixup noise.
  # Taking the last would report a clean build as broken.
  n="$(grep -oE '^ *[0-9]+ Compiler errors' "${out}" 2>/dev/null | head -1 | grep -oE '[0-9]+' || true)"
  if [ -z "${n}" ]; then
    n="$(grep -oE '[0-9]+ build error\(s\)' "${err}" 2>/dev/null | head -1 | grep -oE '[0-9]+' || true)"
  fi
  [ -z "${n}" ] && n=0

  # A configure-step failure produces no compiler-error count at all, so look
  # for the stamp ninja reports as FAILED (e.g. Plastimatch-configure).
  cfgfail=0
  grep -qE 'Configuring incomplete, errors occurred|FAILED: .*-configure' "${out}" 2>/dev/null && cfgfail=1

  pkgonly=0
  if [ "${n}" -eq 0 ] && [ "${cfgfail}" -eq 0 ] \
     && grep -qE 'otool: can.t open file|install_name_tool: can.t open file' "${out}" 2>/dev/null; then
    pkgonly=1
  fi

  if [ "${cfgfail}" -eq 1 ]; then
    status=CONFIG-FAIL; fail=$((fail+1))
    first="$(grep -m1 -B0 -E 'Configuring incomplete|FAILED: .*-configure' "${out}" | cut -c1-90)"
  elif [ "${n}" -gt 0 ] 2>/dev/null; then
    status=BUILD-FAIL; fail=$((fail+1))
    first="$(grep -m1 -E '(^|[^-])error:' "${out}" 2>/dev/null | cut -c1-90)"
  elif [ "${pkgonly}" -eq 1 ]; then
    status=pass-pkgwarn; pass=$((pass+1))
    first="built ok; CPack bundle fixup errors (not a build failure)"
  else
    status=pass; pass=$((pass+1)); first=""
  fi
  rows+=("${ext}"$'\t'"${status}"$'\t'"${n}"$'\t'"${first}")
done
shopt -u nullglob

# Extensions that were requested but produced no output file never built at all
# -- a descriptor that failed to configure or clone. Silent otherwise.
descdir="${FOREST}/SlicerExtensions-descriptions"
if [ -d "${descdir}" ]; then
  for d in "${descdir}"/*.json; do
    [ -e "${d}" ] || continue
    e="$(basename "${d}" .json)"
    [ -f "${BUILD}/build_${e}output.txt" ] && continue
    rows+=("${e}"$'\t'"NOT-BUILT"$'\t'"-"$'\t'"no output file")
    unbuilt=$((unbuilt+1))
  done
fi

if [ "${TSV}" = 1 ]; then
  printf '%s\n' "${rows[@]}" | sort
else
  printf '%-38s %-10s %8s  %s\n' EXTENSION STATUS ERRORS "FIRST ERROR"
  printf '%s\n' "${rows[@]}" | sort -t$'\t' -k2,2 -k1,1 \
    | awk -F'\t' '{printf "%-38s %-10s %8s  %s\n", $1, $2, $3, $4}'
  echo
  printf 'requested=%d  pass=%d  FAIL=%d  NOT-BUILT=%d\n' \
    "$((pass+fail+unbuilt))" "${pass}" "${fail}" "${unbuilt}"
fi

[ "${fail}" -eq 0 ] && [ "${unbuilt}" -eq 0 ]
