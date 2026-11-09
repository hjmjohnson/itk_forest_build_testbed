#!/usr/bin/env bash
# Build every downstream against the ITK ref under test and record PASS/FAIL
# by artifact (not exit code). With RUN_CTEST=1, also run each built target's
# ctest suite, keep its history, and score REGRESS when a test fails that is
# not an accepted failure. Continues past failures.
#   pixi run bash bin/run-matrix.sh               # build-only (default)
#   RUN_CTEST=1 pixi run bash bin/run-matrix.sh   # build + test + REGRESS scoring
#   bin/run-matrix.sh --list-targets|--list-deferred|--check-artifact <X>|--ctest-dir <X>
#   bin/run-matrix.sh --run-ctest <X>|--record-baseline <X>|--ctest-history [<X>]
#
# Slicer note: Slicer never consumes the system ITK. It always builds a
# dedicated Slicer-vendored ITK branch (hjmjohnson/ITK @ slicer-itk-<...>) via
# -DSlicer_ITK_GIT_TAG=<branch>. See docs/slicer-itk-policy.md.
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "${BIN_DIR}")"            # repo root = parent of bin/
ENG="${BIN_DIR}/setup-itk-downstream-testbed.sh"
# Artifact filenames and the conda env layout differ per platform; platform.sh
# is the single authority for both (see docs/windows.md).
. "${BIN_DIR}/platform.sh"
# The engine is the single authority on the forest name; ask it rather than
# recomputing the composition here and risking drift.
# No `set -e` here (the matrix continues past build failures), so an engine that
# dies must be caught explicitly: an empty FOREST would root LOGDIR at "/logs"
# and build the whole matrix at "/".
FOREST="${FOREST:-$(bash "${ENG}" --print-forest)}" || exit 1
[ -n "${FOREST}" ] || { echo "run-matrix: engine could not resolve the forest name" >&2; exit 1; }
export FOREST
LOG_TAG="${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
# Put the pixi env's cmake/ninja ahead of any system one (system cmake 3.26.6 is
# too old for Slicer's >=3.28 requirement). This is NOT equivalent to `pixi run`:
# the compilers ($CC/$CXX) and the ccache hash policy come from the activation
# env, not from PATH. Run under `pixi run`; the engine enforces it.
# A conda env's executables are in bin/ on Unix but in the env root +
# Library/bin + Scripts on Windows, so ask platform.sh rather than hardcoding
# bin/ (which simply does not exist on win-64 and made this a silent no-op).
# upath: $PATH is colon-separated, so entries must be shell form, not "C:/...".
while IFS= read -r _d; do
  [ -d "${_d}" ] && PATH="$(upath "${_d}"):$PATH"
done < <(pixi_env_bindirs "${ROOT}/.pixi/envs/default")
TB="${FOREST}"
LOGDIR="${FOREST}/logs"
case "${1:-}" in
  --list-targets|--list-deferred|--check-artifact|--ctest-dir|--ctest-history|--record-baseline) : ;;
  *) mkdir -p "${LOGDIR}" ;;
esac
SUMMARY=""
RUNSLONG_PENDING="${LOGDIR}/.runslong-pending${LOG_TAG}"

# --- ctest layer -----------------------------------------------------------
# Tests are expensive; bound each target's wall-clock and allow scope/skip:
#   RUN_CTEST=1             also run tests (default: 0, build-only)
#   CTEST_JOBS=N            parallel test jobs (default: ncpu/2, min 2)
#   CTEST_TIMEOUT=S         per-test timeout seconds (default 300)
#   CTEST_TIMEOUT_<target>=S  per-test timeout for one target (SphinxExamples: 60)
#   SPHINX_RUN_GUI_TESTS=1  also run SphinxExamples that open interactive windows
#   CTEST_RUNS_LONG_JOBS=N / CTEST_RUNS_LONG_TIMEOUT=S  second pass for RUNS_LONG tests (3, 3600)
#   CTEST_RUNS_LONG_BACKGROUND=0  run that pass in place instead of niced beside the next builds
#   CTEST_RUNS_LONG_NICE=N  nice level of the background RUNS_LONG pass (10)
#   ITK_CTEST_KEEP_FOREIGN_WRAPPING=1  run ITK's tests with consumers' wrapping left in its package
#   CTEST_TARGET_TIMEOUT=S  overall per-target wall-clock cap (default 1800)
#   CTEST_INCLUDE=regex     only run tests matching it (ctest -R) to scope long suites
# Scheduling: after ITK, independent targets build side by side.
#   MATRIX_PARALLEL=N       targets building at once (default 3; 1 = serial)
#   MATRIX_MAX_LOAD=N       start a target only while fewer than N cores are busy (default ncpu)
#   MATRIX_START_SPACING=S  seconds between target starts, for a new build to register (default 180)
#   MATRIX_TARGETS="A B"    run only these targets (default: all)
#   JOBS=N                  build jobs per target (default ncpu*1.5/MATRIX_PARALLEL when parallel)
RUN_CTEST="${RUN_CTEST:-0}"
# Slicer extension self-tests stay off independently of RUN_CTEST: the extension
# dashboard driver's own ctest_test launches Slicer.app per extension, and a crash
# there leaves a modal macOS dialog that blocks an unattended build. The engine
# reads SLICER_EXT_RUN_TESTS, but the per-extension args files are regenerated
# during the BUILD, so the flag must be live in this process's environment --
# not only inside configure_one. SLICER_EXT_RUN_TESTS=1 opts back in (attended).
export SLICER_EXT_RUN_TESTS="${SLICER_EXT_RUN_TESTS:-0}"
if [ "${SLICER_EXT_RUN_TESTS}" = 1 ]; then
  export run_extension_ctest_with_test=TRUE
else
  export run_extension_ctest_with_test=FALSE
fi
export run_extension_ctest_with_packages="${run_extension_ctest_with_packages:-FALSE}"
export run_extension_ctest_submit=FALSE
_ncpu(){ nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4; }
CTEST_JOBS="${CTEST_JOBS:-$(( $(_ncpu) / 2 ))}"; [ "${CTEST_JOBS}" -lt 2 ] && CTEST_JOBS=2
CTEST_TIMEOUT="${CTEST_TIMEOUT:-300}"
CTEST_TARGET_TIMEOUT="${CTEST_TARGET_TIMEOUT:-1800}"

# Build tree for a target: nested layout (<name>/build, mirrors the engine's
# build_dir()) with a fallback to the legacy flat <name>-build.
bdir(){
  # FOREST_BUILD_DIR_<name> moves a build out of the forest, as the engine's
  # build_dir() does; Windows hands the name over uppercased.
  local v="FOREST_BUILD_DIR_${1//[^A-Za-z0-9_]/_}" u d
  u="${v^^}"
  if [ -n "${!v:-}" ]; then npath "${!v}"; return; fi
  if [ -n "${!u:-}" ]; then npath "${!u}"; return; fi
  if [ "${FOREST_OS}" = windows ] && [ "$1" = Slicer ] && [ "${FOREST_SUBST_DRIVE:-S:}" != none ]; then
    echo "${FOREST_SUBST_DRIVE:-S:}/b"; return
  fi
  d="${TB}/${1}/build"
  [ -d "${d}" ] || { [ -d "${TB}/${1}-build" ] && d="${TB}/${1}-build"; }
  echo "${d}"
}

# Build dir that holds CTestTestfile.cmake for a target (inner build for
# SuperBuilds); empty if no test harness is present.
ctest_dir(){
  local n="$1" d
  case "$n" in
    BRAINSTools) d="$(bdir BRAINSTools)/BRAINSTools-Release-EPRelease-build" ;;
    Slicer)      d="$(bdir Slicer)/Slicer-build" ;;
    *)           d="$(bdir "$n")" ;;
  esac
  [ -f "${d}/CTestTestfile.cmake" ] && { echo "${d}"; return; }
  find "$(bdir "$n")" -maxdepth 4 -name CTestTestfile.cmake -print 2>/dev/null \
    | head -1 | xargs -r dirname
}

# --- ctest history and REGRESS scoring ---------------------------------------
# Each run keeps logs/ctest-history/<target><tag>-<stamp>.{log,failed} and adds a
# row to logs/ctest-results<tag>.tsv. Accepted failures live in the kit, so they
# are reviewed and versioned: ctest-baselines/<forest>/<target>.failures (one test
# name per line; an empty file means every test must pass). Without that file the
# previous run's failures are the reference. A failing test outside the reference
# is a regression.
HISTDIR="${LOGDIR}/ctest-history"
RESULTS_TSV="${LOGDIR}/ctest-results${LOG_TAG}.tsv"
baseline_file(){ echo "${ROOT}/ctest-baselines/$(basename "${FOREST}")/${1}.failures"; }

# Failing test names from a ctest log's "The following tests FAILED:" section.
ctest_failed_tests(){
  sed -n '/The following tests FAILED:/,$p' "$1" \
    | sed -nE 's/^[[:space:]]*[0-9]+ - ([^ ]+) \(.*/\1/p' | sort -u
}

# Record one run in the history; echo the scoring suffix for its token.
record_ctest_run(){
  local n="$1" log="$2" passed="$3" total="$4" stamp ref refsrc new fixed sha
  stamp="$(date +%Y%m%d_%H%M%S)"
  mkdir -p "${HISTDIR}"
  local hist="${HISTDIR}/${n}${LOG_TAG}-${stamp}"
  cp "${log}" "${hist}.log"
  ctest_failed_tests "${log}" >"${hist}.failed"
  if [ -f "$(baseline_file "$n")" ]; then
    ref="$(grep -v '^#' "$(baseline_file "$n")" | sed '/^[[:space:]]*$/d' | sort -u)"; refsrc=baseline
  else
    local prev; prev="$(ls -1 "${HISTDIR}/${n}${LOG_TAG}-"*.failed 2>/dev/null | grep -v "${stamp}" | tail -1)"
    if [ -n "${prev}" ]; then ref="$(sort -u "${prev}")"; refsrc=previous; else ref=""; refsrc=none; fi
  fi
  new="$(comm -13 <(printf '%s\n' "${ref}" | sed '/^$/d') "${hist}.failed" | sed '/^$/d' | wc -l | tr -d ' ')"
  fixed="$(comm -23 <(printf '%s\n' "${ref}" | sed '/^$/d') "${hist}.failed" | sed '/^$/d' | wc -l | tr -d ' ')"
  [ "${refsrc}" = none ] && new=0
  sha="$(git -C "${FOREST}/ITK" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
  [ -f "${RESULTS_TSV}" ] || printf 'stamp\ttarget\titk_sha\tpassed\ttotal\tnew_failures\tfixed\treference\tlog\n' >"${RESULTS_TSV}"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "${stamp}" "${n}" "${sha}" "${passed}" "${total}" \
    "${new}" "${fixed}" "${refsrc}" "${hist}.log" >>"${RESULTS_TSV}"
  local suffix=""
  [ "${new}" -gt 0 ] && suffix=" new-fail:${new}"
  [ "${fixed}" -gt 0 ] && suffix="${suffix} fixed:${fixed}"
  [ "${refsrc}" = none ] && suffix="${suffix} (no reference yet)"
  echo "${suffix}"
}

# Run the test suite for $1; echo a compact token:
#   T:142/150 (8 of 150 failed) | T:0/0:no-tests | T:skip:no-harness | T:timeout
#   followed by " new-fail:N" (regressions) and " fixed:M" when the reference says so,
#   and " notrun:K" when K tests had no executable (scored FAIL).
run_ctest(){
  local n="$1" d log line failed total inc=()
  d="$(ctest_dir "$n")"
  [ -n "$d" ] || { echo "T:skip:no-harness"; return; }
  log="${LOGDIR}/ctest-${n}${LOG_TAG}.log"
  [ -n "${CTEST_INCLUDE:-}" ] && inc=(-R "${CTEST_INCLUDE}")
  # SphinxExamples registers its Python examples as bare
  # `${Python3_EXECUTABLE} Code.py` with no ctest ENVIRONMENT, so `import itk`
  # resolves only from sys.path. Point it at the wrapping tree of the ITK
  # under test, or the tests would silently exercise some other itk.
  local envp=() _itkpy exc=() _gui _tvar="CTEST_TIMEOUT_${n}" tmo
  tmo="${!_tvar:-${CTEST_TIMEOUT}}"
  if [ "$n" = SphinxExamples ]; then
    _itkpy="$(bdir ITK)/Wrapping/Generators/Python"
    [ -d "${_itkpy}/itk" ] || { echo "T:skip:itk-python-missing"; return; }
    envp=(env "PYTHONPATH=${_itkpy}${PYTHONPATH:+:${PYTHONPATH}}")
    # Display examples block until a person closes their window.
    tmo="${!_tvar:-60}"
    if [ "${SPHINX_RUN_GUI_TESTS:-0}" != 1 ]; then
      ctest --test-dir "$d" --show-only=json-v1 >"${LOGDIR}/ctest-${n}${LOG_TAG}.json" 2>/dev/null
      _gui="$("${FOREST_PYTHON:-python3}" "${BIN_DIR}/sphinx-gui-tests.py" "${LOGDIR}/ctest-${n}${LOG_TAG}.json")" \
        || { echo "T:skip:gui-filter-failed"; return; }
      [ -n "${_gui}" ] && exc=(-E "${_gui}")
    fi
  fi
  # Consumers built against ITK's build tree install their wrapping into ITK's
  # Python package; ITK's whole-package tests must not see it.
  local _quar="" _cfg _m
  if [ "$n" = ITK ] && [ "${ITK_CTEST_KEEP_FOREIGN_WRAPPING:-0}" != 1 ]; then
    _cfg="$(bdir ITK)/Wrapping/Generators/Python/itk/Configuration"
    _quar="${LOGDIR}/itk-wrap-quarantine"
    mkdir -p "${_quar}"
    for _m in $("${FOREST_PYTHON:-python3}" "${BIN_DIR}/itk-foreign-wrapping.py" "${FOREST}/ITK" "$(bdir ITK)" 2>/dev/null); do
      mv -f "${_cfg}/${_m}Config.py" "${_quar}/" 2>/dev/null
      mv -f "${_cfg}/${_m}_snake_case.py" "${_quar}/" 2>/dev/null
    done
  fi
  local _long="${log%.log}-runslong.log" rc
  rm -f "${_long}" "${_long}.rc"
  timeout "${CTEST_TARGET_TIMEOUT}" "${envp[@]}" \
    ctest --test-dir "$d" -j"${CTEST_JOBS}" --timeout "${tmo}" -LE RUNS_LONG \
      --output-on-failure "${inc[@]}" "${exc[@]}" >"$log" 2>&1
  rc=$?
  # No RUNS_LONG test imports itk, so consumers may reclaim the package now.
  if [ -n "${_quar}" ]; then
    mv -f "${_quar}"/*.py "${_cfg}/" 2>/dev/null
  fi
  [ "${rc}" -eq 124 ] && { echo "T:timeout"; return; }
  # RUNS_LONG tests run few at a time with a long timeout, so machine load does
  # not turn them into timeouts; by default niced in the background so the
  # downstream builds proceed, and folded in by finish_runslong.
  local runlong=(timeout "${CTEST_TARGET_TIMEOUT}" "${envp[@]}"
    ctest --test-dir "$d" -j"${CTEST_RUNS_LONG_JOBS:-3}" --timeout "${CTEST_RUNS_LONG_TIMEOUT:-3600}" -L RUNS_LONG
    --output-on-failure "${inc[@]}" "${exc[@]}")
  if [ "${CTEST_RUNS_LONG_BACKGROUND:-1}" = 1 ] && [ -n "$(ctest --test-dir "$d" -N -L RUNS_LONG "${inc[@]}" "${exc[@]}" 2>/dev/null | grep -E '^ +Test +#')" ]; then
    ( nice -n "${CTEST_RUNS_LONG_NICE:-10}" "${runlong[@]}" >"${_long}" 2>&1; echo $? >"${_long}.rc" ) \
      </dev/null >/dev/null 2>&1 &
    echo "${n}" >>"${RUNSLONG_PENDING}"
    echo "$(ctest_tally "$log" | awk '{print "T:" $2-$1 "/" $2}') runslong:pending"
    return
  fi
  "${runlong[@]}" >"${_long}" 2>&1
  [ $? -eq 124 ] && { echo "T:timeout"; return; }
  ctest_result "$n" "$log" "${_long}"
}

# "<failed> <total>" summed over the ctest logs given.
ctest_tally(){
  local f line failed=0 total=0
  for f in "$@"; do
    [ -f "$f" ] || continue
    line="$(grep -E 'tests passed,.*tests failed out of' "$f" | tail -1)"
    [ -n "$line" ] || continue
    failed=$((failed + $(echo "$line" | sed -E 's/.* ([0-9]+) tests failed.*/\1/')))
    total=$((total + $(echo "$line" | sed -E 's/.* out of ([0-9]+).*/\1/')))
  done
  echo "${failed} ${total}"
}

# Fold the RUNS_LONG log into the main log and score both passes as one run.
ctest_result(){
  local n="$1" log="$2" long="$3" failed total
  read -r failed total <<<"$(ctest_tally "$log" "$long")"
  [ -f "${long}" ] && cat "${long}" >>"$log"
  if [ "${total}" -eq 0 ]; then
    grep -qE 'No tests were found' "$log" && { echo "T:0/0:no-tests"; return; }
    echo "T:unknown"; return
  fi
  local notrun; notrun="$(grep -E '\*\*\*Not Run' "$log" | grep -cv '(Disabled)')"
  echo "T:$((total - failed))/${total}$(record_ctest_run "$n" "$log" "$((total - failed))" "${total}")$([ "${notrun}" -gt 0 ] && echo " notrun:${notrun}")"
}

# Summary line for a built target's test token: a test that never ran (missing
# executable) proves nothing, so it scores FAIL even when no reference flags it.
ctest_summary_line(){
  local n="$1" tstat="$2"
  if [[ "${tstat}" == *notrun:* ]]; then printf 'FAIL  %-20s %s' "${n}" "${tstat} (tests not run)"
  elif [[ "${tstat}" == *new-fail:* ]]; then printf 'REGRESS %-18s %s' "${n}" "${tstat}"
  else printf 'PASS  %-20s %s' "${n}" "${tstat}"; fi
}

# Wait for background RUNS_LONG passes and report each target's combined result.
finish_runslong(){
  [ -s "${RUNSLONG_PENDING}" ] || return 0
  local n log long tstat
  while read -r n; do
    log="${LOGDIR}/ctest-${n}${LOG_TAG}.log"; long="${log%.log}-runslong.log"
    echo "-------------------- CTEST ${n} RUNS_LONG (waiting) --------------------"
    until [ -f "${long}.rc" ]; do sleep 30; done
    if [ "$(cat "${long}.rc")" = 124 ]; then tstat="T:timeout"; else tstat="$(ctest_result "$n" "$log" "${long}")"; fi
    echo "RESULT ${n} (with RUNS_LONG): ${tstat}  (${log})"
    SUMMARY="${SUMMARY}$(ctest_summary_line "${n}" "${tstat} (with RUNS_LONG)")"$'\n'
  done <"${RUNSLONG_PENDING}"
  rm -f "${RUNSLONG_PENDING}"
}

# Accept the latest run's failures for $1 as its baseline.
record_baseline(){
  local n="$1" latest f
  latest="$(ls -1 "${HISTDIR}/${n}${LOG_TAG}-"*.failed 2>/dev/null | tail -1)"
  [ -n "${latest}" ] || { echo "no ctest history for ${n}; run --run-ctest ${n} first" >&2; return 1; }
  f="$(baseline_file "$n")"
  mkdir -p "$(dirname "$f")"
  cp "${latest}" "$f"
  echo "${f}: $(wc -l <"$f" | tr -d ' ') accepted failure(s) from $(basename "${latest}" .failed)"
}

# Artifact predicates. The FILENAME SHAPES are platform-specific (MSVC emits
# Foo.lib/Foo.dll and foo.exe, with no "lib" prefix, where Unix emits
# libFoo.a/libFoo.so|dylib and foo), so they come from platform.sh and only the
# per-target STEMS live here. Before this split every check below was
# Unix-shaped and a fully-built Windows tree scored as a build FAILURE --
# which, for ITK, aborted the whole matrix on its first target.
_find_any(){                    # <dir> <glob>... -> 0 if any file matches
  local d="$1"; shift
  [ -d "$d" ] || return 1
  local g; local -a args=()
  for g in "$@"; do [ ${#args[@]} -gt 0 ] && args+=(-o); args+=(-iname "$g"); done
  find "$d" \( "${args[@]}" \) 2>/dev/null | grep -q .
}
# Read the globs into an array rather than splitting $(...): unquoted expansion
# would let the shell glob them against the CWD before find ever sees them.
has_lib(){                      # <dir> <stem-without-lib-prefix>
  local g; local -a gl=()
  while IFS= read -r g; do gl+=("$g"); done < <(lib_globs "$2")
  _find_any "$1" "${gl[@]}"; }
has_any_lib(){                  # <dir>
  local g; local -a gl=()
  while IFS= read -r g; do gl+=("$g"); done < <(any_lib_globs)
  _find_any "$1" "${gl[@]}"; }
has_exe(){ _find_any "$1" "${2}${EXE_SUFFIX}"; }   # <dir> <name-without-suffix>

artifact_ok(){
  local n="$1" b
  b="$(bdir "$n")"
  case "$n" in
    ITK)       # A stale ITKCommon library from an earlier build satisfies this on its
               # own, so when wrapping is configured ON also require the generated
               # python package -- otherwise a ninja that stopped early still scores PASS.
               has_lib "${b}/lib" 'ITKCommon-*' || return 1  # version-agnostic (6.0, 5.4, ...)
               if grep -q '^ITK_WRAP_PYTHON:BOOL=ON' "${b}/CMakeCache.txt" 2>/dev/null; then
                 [ -f "${b}/Wrapping/Generators/Python/itk/__init__.py" ] || return 1
               fi
               return 0 ;;
    elastix)   has_exe "${b}/bin" elastix ;;
    c3d)       has_exe "${b}" 'c?d' || has_lib "${b}" 'Convert3D*' ;;
    RTK)       has_exe "${b}/bin" rtkamsterdamshroud ;;
    SimpleITK) has_lib "${b}" 'SimpleITK*' ;;
    ANTs)        has_exe "${b}" antsRegistration ;;
    BRAINSTools) has_exe "${b}" BRAINSFit ;;
    OpenIGTLink)   has_lib "${b}" 'OpenIGTLink*' ;;
    OpenIGTLinkIO) has_lib "${b}" 'igtlio*' || has_lib "${b}" 'OpenIGTLinkIO*' ;;
    vtkAddon)    has_lib "${b}" 'vtkAddon*' ;;
    IGSIO)       has_lib "${b}" 'vtkIGSIO*' ;;
    PlusLib)     has_lib "${b}" 'vtkPlus*' || has_lib "${b}" 'Plus*' ;;
    Slicer)      has_exe "$(bdir Slicer)/Slicer-build" 'SlicerApp-real' \
                 || has_lib "$(bdir Slicer)/Slicer-build" 'MRMLCore*' ;;
    SlicerExtensions) has_any_lib "${b}" ;;
    # -perm -100 (user execute), NOT -111: -111 requires the group and other
    # execute bits too, so it matches nothing under a umask of 077.
    SphinxExamples)   find "${b}/bin" -type f -perm -100 2>/dev/null | grep -q . ;;
    *)  # external ITK modules link their lib into the ITK tree, not their own
        has_any_lib "${b}" || has_lib "$(bdir ITK)/lib" "itk${n}-*" ;;
  esac
}

# A module that wraps into ITK's build-tree package can leave `import itk`
# broken for every consumer, which otherwise surfaces as mass Python failures.
# Checked structurally: itk.force_load() prints the traceback but keeps going,
# and importing the wrapped ITK can crash the interpreter in VTK's destructors.
itk_python_intact(){
  local c="$(bdir ITK)/CMakeCache.txt"
  grep -q '^ITK_WRAP_PYTHON:BOOL=ON' "$c" 2>/dev/null || return 0
  "${FOREST_PYTHON:-python3}" - "$(bdir ITK)/Wrapping/Generators/Python/itk" \
    >"${LOGDIR}/itk-python-check${LOG_TAG}.log" 2>&1 <<'EOF'
import glob, os, re, sys
pkg = sys.argv[1]
bad = []
for f in sorted(os.listdir(os.path.join(pkg, "Configuration"))):
    m = re.match(r"(\w+)Config\.py$", f)
    if not m:
        continue
    n = m.group(1)
    py = os.path.exists(os.path.join(pkg, n + "Python.py"))
    so = bool(glob.glob(os.path.join(pkg, "_%sPython*.so" % n))
              or glob.glob(os.path.join(pkg, "_%sPython*.pyd" % n)))  # Windows
    if not (py and so):
        bad.append("%s (module=%s extension=%s)" % (n, py, so))
for b in bad:
    print("orphaned wrapping config:", b)
print("ITK_PY_OK" if not bad else "ITK_PY_BROKEN")
EOF
  grep -q ITK_PY_OK "${LOGDIR}/itk-python-check${LOG_TAG}.log"
}

# Targets whose build drives an inner build; their artifact_ok() file can
# survive from an earlier successful build.
superbuild_target(){ case "$1" in BRAINSTools|Slicer) return 0 ;; esac; return 1; }

# Move the orphaned *Config.py files that $1 left in ITK's package aside, so
# that later targets are scored on their own builds rather than on $1's.
quarantine_orphaned_wrapping(){
  local n="$1" pkg q line mod
  pkg="$(bdir ITK)/Wrapping/Generators/Python/itk"
  q="${LOGDIR}/orphaned-wrapping${LOG_TAG}/${n}"
  while IFS= read -r line; do
    mod="${line#orphaned wrapping config: }"; mod="${mod%% *}"
    [ -f "${pkg}/Configuration/${mod}Config.py" ] || continue
    mkdir -p "${q}"
    mv "${pkg}/Configuration/${mod}Config.py" "${q}/"
    echo "  moved orphaned ${mod}Config.py to ${q}/"
  done < <(grep '^orphaned wrapping config: ' "${LOGDIR}/itk-python-check${LOG_TAG}.log")
  itk_python_intact || echo "  WARN: itk python package still broken after quarantine"
}

# Does this target's wrapping write into ITK's package?
_wraps_into_itk(){
  [ "$1" = ITK ] && return 0
  grep -q "^ITK_WRAP_PYTHON_ROOT_BINARY_DIR:[A-Z]*=$(bdir ITK)/" "$(bdir "$1")/CMakeCache.txt" 2>/dev/null
}

build_target(){
  local n="$1" tstat=""
  echo "==================== BUILD ${n} ===================="
  local _t0 _el _rc=0; _t0=$(date +%s)
  bash "${ENG}" build "${n}" >"${LOGDIR}/matrix-${n}${LOG_TAG}.log" 2>&1 || _rc=$?
  _el=$(( $(date +%s) - _t0 ))
  # Verify tests actually stayed off for extensions -- the args files bake
  # RUN_CTEST_TEST at their own configure time, so an env slip re-enables the
  # Slicer.app-launching test phase silently. Assert by artifact, not intent.
  if [ "${n}" = SlicerExtensions ] && [ "${RUN_CTEST}" = 0 ]; then
    local _on; _on="$(grep -l 'RUN_CTEST_TEST "TRUE"' "${FOREST}/SlicerExtensions/build/"*-test-command-args.cmake 2>/dev/null | wc -l | tr -d ' ')"
    [ "${_on:-0}" != 0 ] && echo "WARN ${n}: ${_on} extension(s) still have tests ENABLED despite RUN_CTEST=0 (Slicer.app may launch)"
  fi
  local _pybroke=""
  if _wraps_into_itk "${n}" && ! itk_python_intact; then
    # The detector reports "orphaned wrapping config: ..." lines, not the word
    # "error"; a message match must never decide whether the failure counts.
    _pybroke="$(grep -E 'orphaned wrapping config|Error|error' \
                  "${LOGDIR}/itk-python-check${LOG_TAG}.log" | tail -1)"
    [ -n "${_pybroke}" ] || _pybroke="itk python package check failed"
  fi
  if [ -n "${_pybroke}" ]; then
    SUMMARY="${SUMMARY}$(printf 'FAIL  %-20s %s' "${n}" '(broke itk python package)')"$'\n'
    echo "RESULT ${n}: build FAIL -- itk python package no longer imports after building ${n}"
    echo "  ${_pybroke}"
    echo "  (${LOGDIR}/itk-python-check${LOG_TAG}.log)"
    quarantine_orphaned_wrapping "${n}"
  elif [ "${_rc}" != 0 ] && superbuild_target "${n}"; then
    # A SuperBuild's artifact can predate a failed inner build, so its exit
    # status decides here.
    SUMMARY="${SUMMARY}$(printf 'FAIL  %-20s %s' "${n}" "(build failed, exit ${_rc})")"$'\n'
    echo "RESULT ${n}: build FAIL -- exit ${_rc}; existing artifacts may be stale  (${LOGDIR}/matrix-${n}${LOG_TAG}.log)"
    grep -iE 'error:|CMake Error|library not found|No such module|undefined sym' "${LOGDIR}/matrix-${n}${LOG_TAG}.log" | head -3
  elif artifact_ok "${n}"; then
    echo "RESULT ${n}: build PASS  (${_el}s)"
    if [ "${RUN_CTEST}" = 1 ]; then
      echo "-------------------- CTEST ${n} --------------------"
      tstat="$(run_ctest "${n}")"
      echo "RESULT ${n}: ${tstat}  (${LOGDIR}/ctest-${n}${LOG_TAG}.log)"
    fi
    SUMMARY="${SUMMARY}$(ctest_summary_line "${n}" "${tstat}")"$'\n'
    [[ "${tstat}" == *notrun:* ]] && echo "RESULT ${n}: FAIL -- tests not run; their executables were not built"
    [[ "${tstat}" == *new-fail:* ]] && echo "RESULT ${n}: REGRESS -- tests failing that are not accepted failures (see ${RESULTS_TSV})"
  else
    SUMMARY="${SUMMARY}$(printf 'FAIL  %-20s %7ss  %s' "${n}" "${_el}" '(build failed)')"$'\n'
    echo "RESULT ${n}: build FAIL  (${_el}s)  (${LOGDIR}/matrix-${n}${LOG_TAG}.log)"
    grep -iE 'error:|CMake Error|library not found|No such module|undefined sym' "${LOGDIR}/matrix-${n}${LOG_TAG}.log" | head -3
  fi
}

# DEFERRED — known pre-existing failures unrelated to the ITK ref under test,
# excluded until fixed (see docs/DEFERRED-FAILURES.md):
#   TubeTK c3d BioCell HASI Shape SkullStrip : need their own module/data deps
#   Ultrasound          : extra ITK COMPILE_DEPENDS / clFFT not resolved
#   LesionSizingToolkit : missing itkCannyEdgeDetectionRecursiveGaussianImageFilter.h,
#                         itkLandmarksReader.h (needs more ITK modules enabled)
# None are caused by the ITK ref under test. Re-include a target only after its cause is fixed.
# Slicer (and its full rendering+Qt VTK) precedes the VTK consumers
# (OpenIGTLinkIO/vtkAddon/IGSIO/PlusLib), which need that VTK via vtk_dir().
TARGETS=(ITK elastix SimpleITK RTK Cleaver
         PerformanceBenchmarking SimpleITKFilters SphinxExamples
         TractographyTRX VkFFTBackend Impact ANTs BRAINSTools
         OpenIGTLink Slicer SlicerExtensions
         OpenIGTLinkIO vtkAddon IGSIO PlusLib)

# QT_FREE_TARGETS — the subset that needs no Qt6. Slicer and SlicerExtensions
# link Qt directly; OpenIGTLinkIO/vtkAddon/IGSIO/PlusLib need vtk_dir(), whose
# only providers are the forest's Qt-enabled VTK or Slicer's VTK, and both go
# through qt6_or_die. Useful on a node with no usable Qt6 kit:
#   MATRIX_TARGETS="$(bash bin/run-matrix.sh --list-qt-free)" pixi run bash bin/run-matrix.sh
QT_FREE_TARGETS=(ITK elastix SimpleITK RTK Cleaver
                 PerformanceBenchmarking SimpleITKFilters
                 TractographyTRX VkFFTBackend ANTs BRAINSTools
                 OpenIGTLink)

# MATRIX_TARGETS (space-separated) overrides the built-in list, so a scoped
# sweep is a normal matrix run -- same artifact scoring, same logs, same
# summary -- rather than an ad-hoc loop that re-implements them.
[ -n "${MATRIX_TARGETS:-}" ] && read -r -a TARGETS <<<"${MATRIX_TARGETS}"

# Deferred targets (see docs/DEFERRED-FAILURES.md) as machine-readable rows.
DEFERRED_TARGETS=(
  $'TubeTK\tneeds its own module/data deps'
  $'c3d\tneeds its own module/data deps'
  $'BioCell\tneeds its own module/data deps'
  $'HASI\tneeds its own module/data deps'
  $'Shape\tneeds its own module/data deps'
  $'SkullStrip\tneeds its own module/data deps'
  $'Ultrasound\textra ITK COMPILE_DEPENDS / clFFT not resolved'
  $'LesionSizingToolkit\tneeds more ITK modules enabled (missing headers)'
)

# Query/action modes for tooling (forest_tui); default no-flag behavior unchanged.
case "${1:-}" in
  --list-targets)   printf '%s\n' "${TARGETS[@]}"; exit 0 ;;
  --list-deferred)  printf '%s\n' "${DEFERRED_TARGETS[@]}"; exit 0 ;;
  --list-qt-free)   printf '%s\n' "${QT_FREE_TARGETS[@]}"; exit 0 ;;
  --check-artifact) artifact_ok "${2:?usage: --check-artifact <target>}"; exit $? ;;
  --ctest-dir)      ctest_dir "${2:?usage: --ctest-dir <target>}"; exit 0 ;;
  --run-ctest)      CTEST_RUNS_LONG_BACKGROUND=0 run_ctest "${2:?usage: --run-ctest <target>}"; exit 0 ;;
  --record-baseline) record_baseline "${2:?usage: --record-baseline <target>}"; exit $? ;;
  --ctest-history)  [ -f "${RESULTS_TSV}" ] || { echo "no ctest history in ${LOGDIR}" >&2; exit 1; }
                    if [ -n "${2:-}" ]; then awk -F'\t' -v t="$2" 'NR==1 || $2==t' "${RESULTS_TSV}"; else cat "${RESULTS_TSV}"; fi
                    exit 0 ;;
esac

run_target(){
  local t="$1"
  # VkFFTBackend is GPU-gated: build with CUDA/Metal/OpenCL where available,
  # skip (not fail) on hosts with no GPU backend.
  if [ "$t" = VkFFTBackend ] && [ -z "$(bash "${ENG}" vkfft-backend 2>/dev/null)" ]; then
    SUMMARY="${SUMMARY}$(printf 'SKIP  %-20s %s' "${t}" '(no GPU backend)')"$'\n'
    echo "RESULT ${t}: SKIP (no CUDA/Metal/OpenCL backend)"; return
  fi
  if [ "$t" = ITK ] || [ -d "${TB}/${t}" ]; then build_target "$t"
  else SUMMARY="${SUMMARY}SKIP  ${t}"$'\n'; echo "RESULT ${t}: SKIP (not checked out)"; fi
}

# Busy cores, from summed process CPU. The load average overstates it: a
# thread-pooled ITK test keeps dozens of threads runnable on a few cores.
_busy(){ ps -A -o %cpu= 2>/dev/null | awk '{s += $1} END {printf "%d\n", s / 100}'; }

# Take one of MATRIX_PARALLEL build slots, first come first served: a lane
# queues a ticket and only the oldest ticket may start. While another target
# is building, also wait for the busy cores to fall below MATRIX_MAX_LOAD and
# for MATRIX_START_SPACING seconds since the last start, so a new build
# registers. mkdir is the atomic lock; an idle matrix always starts, so
# outside load cannot stall it.
slot_acquire(){
  local k last busy ticket
  mkdir -p "${SLOTDIR}/.queue"
  ticket="$(mktemp "${SLOTDIR}/.queue/$(date +%s).XXXXXX")"
  while :; do
    if mkdir "${SLOTDIR}/.lock" 2>/dev/null; then
      busy="$(find "${SLOTDIR}" -mindepth 1 -maxdepth 1 -type d ! -name .lock ! -name .queue | wc -l | tr -d ' ')"
      last="$(cat "${SLOTDIR}/.last-start" 2>/dev/null || echo 0)"
      if [ "$(ls "${SLOTDIR}/.queue" | sort | head -1)" = "$(basename "${ticket}")" ] \
         && { [ "${busy}" -eq 0 ] || { [ "${busy}" -lt "${MATRIX_PARALLEL}" ] \
           && [ $(( $(date +%s) - last )) -ge "${MATRIX_START_SPACING:-180}" ] \
           && [ "$(_busy)" -lt "${MATRIX_MAX_LOAD}" ]; }; }; then
        for ((k = 1; k <= MATRIX_PARALLEL; k++)); do
          if mkdir "${SLOTDIR}/${k}" 2>/dev/null; then
            date +%s >"${SLOTDIR}/.last-start"; rm -f "${ticket}"; rmdir "${SLOTDIR}/.lock"
            echo "${k}"; return
          fi
        done
      fi
      rmdir "${SLOTDIR}/.lock"
    fi
    sleep "${MATRIX_LOAD_POLL:-30}"
  done
}

# A lane builds its targets in order; lanes run side by side.
run_lane(){
  local t k
  for t in "$@"; do
    k="$(slot_acquire)"
    echo "## $(date '+%H:%M:%S') start ${t} (slot ${k}, busy cores $(_busy))"
    SUMMARY=""
    run_target "$t" >"${SUMDIR}/${t}.out" 2>&1
    cat "${SUMDIR}/${t}.out"
    printf '%s' "${SUMMARY}" >"${SUMDIR}/${t}.summary"
    rmdir "${SLOTDIR}/${k}"
  done
}

# Targets that write into ITK's build tree (wrapping into its Python package,
# libraries into its lib/) share one lane, and SphinxExamples, which imports
# that package, runs last in it. The Slicer chain is ordered: Slicer brings
# the VTK that OpenIGTLinkIO/vtkAddon/IGSIO/PlusLib need.
ITK_TREE_LANE=(RTK Cleaver PerformanceBenchmarking SimpleITKFilters TractographyTRX VkFFTBackend Impact)
SLICER_LANE=(OpenIGTLink Slicer SlicerExtensions OpenIGTLinkIO vtkAddon IGSIO PlusLib)
MATRIX_PARALLEL="${MATRIX_PARALLEL:-3}"
MATRIX_MAX_LOAD="${MATRIX_MAX_LOAD:-$(_ncpu)}"
# Concurrent builds share the cores: default each to its share, rounded up.
[ "${MATRIX_PARALLEL}" -gt 1 ] && export JOBS="${JOBS:-$(( ($(_ncpu) * 3 / 2 + MATRIX_PARALLEL - 1) / MATRIX_PARALLEL ))}"
[ -n "${MATRIX_TARGETS:-}" ] && read -r -a TARGETS <<<"${MATRIX_TARGETS}"

_in(){ local x="$1" y; shift; for y in "$@"; do [ "$x" = "$y" ] && return 0; done; return 1; }

rm -f "${RUNSLONG_PENDING}"
SLOTDIR="${LOGDIR}/.matrix-slots${LOG_TAG}"; SUMDIR="${LOGDIR}/.matrix-results${LOG_TAG}"
rm -rf "${SLOTDIR}" "${SUMDIR}"; mkdir -p "${SLOTDIR}" "${SUMDIR}"

if _in ITK "${TARGETS[@]}"; then
  run_target ITK
  artifact_ok ITK || { echo "ITK FAILED -- aborting"; printf '%s' "${SUMMARY}"; exit 1; }
fi
if [ "${MATRIX_PARALLEL}" -le 1 ]; then
  for t in "${TARGETS[@]}"; do [ "$t" = ITK ] || run_target "$t"; done
else
  itk_lane=() slicer_lane=() solo=() sphinx=()
  for t in "${TARGETS[@]}"; do
    [ "$t" = ITK ] && continue
    if [ "$t" = SphinxExamples ]; then sphinx=(SphinxExamples)
    elif _in "$t" "${SLICER_LANE[@]}"; then slicer_lane+=("$t")
    elif _in "$t" "${ITK_TREE_LANE[@]}" || { [ -d "${TB}/${t}" ] && _wraps_into_itk "$t"; }; then itk_lane+=("$t")
    else solo+=("$t"); fi
  done
  pids=()
  [ ${#itk_lane[@]} -gt 0 ] || [ ${#sphinx[@]} -gt 0 ] && { run_lane "${itk_lane[@]}" "${sphinx[@]}" & pids+=($!); }
  [ ${#slicer_lane[@]} -gt 0 ] && { run_lane "${slicer_lane[@]}" & pids+=($!); }
  for t in "${solo[@]}"; do run_lane "$t" & pids+=($!); done
  wait "${pids[@]}"
  for t in "${TARGETS[@]}"; do
    [ "$t" = ITK ] && continue
    [ -f "${SUMDIR}/${t}.summary" ] && SUMMARY="${SUMMARY}$(cat "${SUMDIR}/${t}.summary")"$'\n'
  done
fi

finish_runslong

echo; echo "==================== MATRIX ===================="
printf '%s' "${SUMMARY}"
