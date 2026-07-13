#!/bin/bash
# \author Hans J. Johnson
# Bash script to run clazy static analysis on CTK C++ source files.
#
# After analysis, the file list is pruned to contain only files that
# produced warnings, so subsequent runs skip clean files.  Each clazy
# level maintains its own file list.
#
# When --export-fixes is given, each source file gets its own YAML
# fix file in a per-level directory, then the YAMLs are split into
# per-check subdirectories for one-check-at-a-time application.
#
# Workflow:
#   1. run_clazy_ctk.sh -f level0        # scan + export + split by check
#   2. run_clazy_ctk.sh -L level0        # list available checks
#   3. run_clazy_ctk.sh -F level0 CHECK  # apply one check's fixes
#   4. git add -A && git commit ...       # commit that check
#   5. repeat 3-4 for each check

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── defaults ──────────────────────────────────────────────────────────
readonly DEFAULT_LEVEL="level0"
readonly DEFAULT_SRC_DIR="${HOME}/src/CTK"
readonly DEFAULT_HEADER_FILTER='.*ctk.*'

# ── usage / help ──────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [LEVEL]

Run clazy-standalone on CTK C++ sources and log warnings.

Positional:
  LEVEL                Clazy check level or comma-separated check names.
                       Valid: level0, level1, level2, manual, or specific
                       checks (e.g. connect-by-name,qstring-allocations).
                       Default: ${DEFAULT_LEVEL}

Options:
  -s, --src-dir DIR    CTK source directory       (default: ${DEFAULT_SRC_DIR})
  -b, --bld-dir DIR    CTK inner build directory   (default: <src-dir>/cmake-build-clazy-qt6/CTK-build)
  -j, --jobs N         Parallel clazy jobs         (default: $(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4))
  -a, --all            Force a fresh scan of all source files, ignoring
                       any previously narrowed file list.
  -f, --export-fixes   Export YAML fix files and split by check name.
                       Fixes are stored in <bld-dir>/clazy-fixes-<LEVEL>/.
  -L, --list-fixes     List available check names from previously exported
                       fixes, then exit.
  -F, --apply-fixes CHECK
                       Apply fixes for a single CHECK via clang-apply-replacements,
                       then exit. CHECK must match a DiagnosticName
                       (e.g. clazy-old-style-connect).
  -h, --help           Show this help message and exit.

Environment (overridden by flags):
  SRC_DIR              Same as --src-dir
  BLD_DIR              Same as --bld-dir

Examples:
  $(basename "$0")                                 # level0, default dirs
  $(basename "$0") level1                          # level1 checks
  $(basename "$0") -j4 -s ~/src/CTK level2
  $(basename "$0") --all level0                    # rescan all files
  $(basename "$0") -f level0                       # export + split fix YAMLs
  $(basename "$0") -L level0                       # list available checks
  $(basename "$0") -F clazy-old-style-connect level0  # apply one check
  $(basename "$0") connect-by-name,qstring-allocations

Typical fix workflow:
  1. $(basename "$0") -f level2                    # export fixes
  2. $(basename "$0") -L level2                    # see what's available
  3. $(basename "$0") -F clazy-old-style-connect level2  # apply one check
  4. git add -A && git commit -m "STYLE: ..."      # commit that check
  5. Repeat steps 3-4 for each check
EOF
  exit "${1:-0}"
}

# ── argument parsing ──────────────────────────────────────────────────
CLAZY_LEVEL=""
SRC_DIR="${SRC_DIR:-${DEFAULT_SRC_DIR}}"
BLD_DIR="${BLD_DIR:-}"
JOBS="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
FORCE_ALL=false
EXPORT_FIXES=false
APPLY_CHECK=""
LIST_FIXES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--src-dir)      SRC_DIR="$2";        shift 2 ;;
    -b|--bld-dir)      BLD_DIR="$2";        shift 2 ;;
    -j|--jobs)         JOBS="$2";           shift 2 ;;
    -a|--all)          FORCE_ALL=true;      shift   ;;
    -f|--export-fixes) EXPORT_FIXES=true;   shift   ;;
    -L|--list-fixes)   LIST_FIXES=true;     shift   ;;
    -F|--apply-fixes)  APPLY_CHECK="$2";    shift 2 ;;
    -h|--help)         usage 0                      ;;
    -*)                echo "Error: unknown option '$1'" >&2; usage 1 ;;
    *)
      if [[ -z "${CLAZY_LEVEL}" ]]; then
        CLAZY_LEVEL="$1"; shift
      else
        echo "Error: unexpected argument '$1'" >&2; usage 1
      fi
      ;;
  esac
done

CLAZY_LEVEL="${CLAZY_LEVEL:-${DEFAULT_LEVEL}}"
BLD_DIR="${BLD_DIR:-${SRC_DIR}/cmake-build-clazy-qt6/CTK-build}"

# ── derived paths ─────────────────────────────────────────────────────
readonly COMPILE_COMMANDS="${BLD_DIR}/compile_commands.json"
readonly CLAZY_LOG="${BLD_DIR}/clazy-${CLAZY_LEVEL}-$(date +%Y%m%d-%H%M%S).log"
readonly ALL_FILES_LIST="${BLD_DIR}/clazy_all_files.list"
readonly SRC_FILES_LIST="${BLD_DIR}/clazy_${CLAZY_LEVEL}_files.list"
readonly FIXES_DIR="${BLD_DIR}/clazy-fixes-${CLAZY_LEVEL}"
readonly BY_CHECK_DIR="${FIXES_DIR}/by-check"
readonly SPLIT_SCRIPT="${SCRIPT_DIR}/split_fixes_by_check.py"

# ── prerequisite checks ──────────────────────────────────────────────
if ! command -v clazy-standalone &>/dev/null; then
  echo "Error: clazy-standalone not found in PATH." >&2
  echo "Install via: brew install clazy" >&2
  exit 1
fi

if ! command -v brew &>/dev/null; then
  echo "Error: Homebrew not found — needed to locate LLVM resource dir." >&2
  exit 1
fi

if [[ ! -f "${COMPILE_COMMANDS}" ]]; then
  echo "Error: compile_commands.json not found at ${COMPILE_COMMANDS}" >&2
  echo "Run /ctk-superbuild first." >&2
  exit 1
fi

# ── LLVM resource directory ──────────────────────────────────────────
readonly LLVM_PREFIX="$(brew --prefix llvm)"
readonly LLVM_VERSION="$("${LLVM_PREFIX}/bin/clang" -dumpversion | cut -d. -f1)"
readonly LLVM_RESOURCE_DIR="${LLVM_PREFIX}/lib/clang/${LLVM_VERSION}"
readonly CLANG_APPLY_REPLACEMENTS="${LLVM_PREFIX}/bin/clang-apply-replacements"

if [[ ! -d "${LLVM_RESOURCE_DIR}/include" ]]; then
  echo "Error: LLVM resource dir missing headers: ${LLVM_RESOURCE_DIR}/include" >&2
  exit 1
fi

# ── list-fixes mode (early exit) ─────────────────────────────────────
if "${LIST_FIXES}"; then
  if [[ ! -d "${FIXES_DIR}" ]]; then
    echo "Error: no fixes directory found at ${FIXES_DIR}" >&2
    echo "Run with --export-fixes first." >&2
    exit 1
  fi
  if [[ ! -f "${SPLIT_SCRIPT}" ]]; then
    echo "Error: split script not found at ${SPLIT_SCRIPT}" >&2
    exit 1
  fi
  python3 "${SPLIT_SCRIPT}" --list "${FIXES_DIR}"
  exit 0
fi

# ── apply-fixes mode (early exit) ────────────────────────────────────
if [[ -n "${APPLY_CHECK}" ]]; then
  CHECK_DIR="${BY_CHECK_DIR}/${APPLY_CHECK}"

  if [[ ! -d "${BY_CHECK_DIR}" ]]; then
    echo "Error: no per-check fixes found at ${BY_CHECK_DIR}" >&2
    echo "Run with --export-fixes first to generate and split fix YAMLs." >&2
    exit 1
  fi

  if [[ ! -d "${CHECK_DIR}" ]]; then
    echo "Error: no fixes for check '${APPLY_CHECK}'" >&2
    echo ""
    echo "Available checks:"
    ls -1 "${BY_CHECK_DIR}"
    exit 1
  fi

  YAML_COUNT="$(find "${CHECK_DIR}" -name '*.yaml' -type f | wc -l | tr -d ' ')"
  if [[ "${YAML_COUNT}" -eq 0 ]]; then
    echo "No YAML fix files found for ${APPLY_CHECK}."
    exit 0
  fi

  if [[ ! -x "${CLANG_APPLY_REPLACEMENTS}" ]]; then
    echo "Error: clang-apply-replacements not found at ${CLANG_APPLY_REPLACEMENTS}" >&2
    echo "Install LLVM via: brew install llvm" >&2
    exit 1
  fi

  echo "──────────────────────────────────────────────"
  echo "Check        : ${APPLY_CHECK}"
  echo "Fix files    : ${YAML_COUNT}"
  echo "Fixes dir    : ${CHECK_DIR}"
  echo "──────────────────────────────────────────────"

  "${CLANG_APPLY_REPLACEMENTS}" "${CHECK_DIR}"

  # Remove applied check directory so it isn't re-applied.
  rm -rf "${CHECK_DIR}"

  echo "Fixes for '${APPLY_CHECK}' applied."
  echo "Review with : git diff"
  echo "Commit with : git add -A && git commit -m 'STYLE: Apply clazy ${APPLY_CHECK} fixes'"

  # Show remaining checks.
  REMAINING_CHECKS="$(find "${BY_CHECK_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${REMAINING_CHECKS}" -gt 0 ]]; then
    echo ""
    echo "Remaining checks (${REMAINING_CHECKS}):"
    ls -1 "${BY_CHECK_DIR}"
  else
    echo ""
    echo "All checks applied."
  fi
  exit 0
fi

# ── build the file list ──────────────────────────────────────────────
# Master list of all cpp files (regenerated when missing).
if [[ ! -f "${ALL_FILES_LIST}" ]]; then
  echo "Generating master file list …"
  (cd "${SRC_DIR}" && find Libs Applications -name '*.cpp' -print0) > "${ALL_FILES_LIST}"
fi

# Per-level file list: starts as a copy of the master list, then gets
# narrowed to only files that produced warnings after each run.
if [[ ! -f "${SRC_FILES_LIST}" ]] || "${FORCE_ALL}"; then
  cp "${ALL_FILES_LIST}" "${SRC_FILES_LIST}"
fi

readonly FILE_COUNT="$(tr -cd '\0' < "${SRC_FILES_LIST}" | wc -c | tr -d ' ')"

# ── prepare fixes directory ──────────────────────────────────────────
if "${EXPORT_FIXES}"; then
  rm -rf "${FIXES_DIR}"
  mkdir -p "${FIXES_DIR}"
fi

echo "──────────────────────────────────────────────"
echo "Clazy level  : ${CLAZY_LEVEL}"
echo "Source dir   : ${SRC_DIR}"
echo "Build dir    : ${BLD_DIR}"
echo "Resource dir : ${LLVM_RESOURCE_DIR}"
echo "Files to scan: ${FILE_COUNT}"
echo "Parallel jobs: ${JOBS}"
echo "Log file     : ${CLAZY_LOG}"
if "${EXPORT_FIXES}"; then
  echo "Fixes dir    : ${FIXES_DIR}"
fi
echo "──────────────────────────────────────────────"

# ── run clazy ─────────────────────────────────────────────────────────
# When exporting fixes, each source file needs its own YAML to avoid
# clobbering under parallel execution.  A small wrapper script
# generates a unique filename per source file.
if "${EXPORT_FIXES}"; then
  WRAPPER="$(mktemp)"
  trap 'rm -f "${WRAPPER}"' EXIT
  cat > "${WRAPPER}" <<'WRAPPER_EOF'
#!/bin/bash
set -uo pipefail
CHECKS="$1"; shift
HEADER_FILTER="$1"; shift
RESOURCE_DIR="$1"; shift
COMPILE_DB="$1"; shift
FIXES_DIR="$1"; shift
for src_file in "$@"; do
  # Derive a unique YAML filename from the source path.
  fix_name="$(echo "${src_file}" | sed 's|[/.]|_|g')"
  fix_path="${FIXES_DIR}/${fix_name}.yaml"
  clazy-standalone \
    -checks="${CHECKS}" \
    -header-filter="${HEADER_FILTER}" \
    --extra-arg=-resource-dir="${RESOURCE_DIR}" \
    --export-fixes="${fix_path}" \
    -p "${COMPILE_DB}" \
    "${src_file}" 2>&1
  # Remove empty fix files (check produced no fix-its).
  if [[ -f "${fix_path}" ]] && [[ ! -s "${fix_path}" ]]; then
    rm -f "${fix_path}"
  fi
done
WRAPPER_EOF
  chmod +x "${WRAPPER}"

  xargs -0 -P "${JOBS}" -n 5 \
    bash "${WRAPPER}" \
      "${CLAZY_LEVEL}" \
      "${DEFAULT_HEADER_FILTER}" \
      "${LLVM_RESOURCE_DIR}" \
      "${COMPILE_COMMANDS}" \
      "${FIXES_DIR}" \
    < "${SRC_FILES_LIST}" \
    2>&1 | tee "${CLAZY_LOG}"
else
  xargs -0 -P "${JOBS}" -n 20 \
    clazy-standalone \
      -checks="${CLAZY_LEVEL}" \
      -header-filter="${DEFAULT_HEADER_FILTER}" \
      --extra-arg=-resource-dir="${LLVM_RESOURCE_DIR}" \
      -p "${COMPILE_COMMANDS}" \
    < "${SRC_FILES_LIST}" \
    2>&1 | tee "${CLAZY_LOG}"
fi

# ── split fixes by check name ────────────────────────────────────────
if "${EXPORT_FIXES}"; then
  YAML_COUNT="$(find "${FIXES_DIR}" -maxdepth 1 -name '*.yaml' -type f | wc -l | tr -d ' ')"
  echo ""
  echo "Exported ${YAML_COUNT} YAML fix file(s) to ${FIXES_DIR}"

  if [[ "${YAML_COUNT}" -gt 0 ]] && [[ -f "${SPLIT_SCRIPT}" ]]; then
    echo ""
    echo "Splitting fixes by check name …"
    python3 "${SPLIT_SCRIPT}" "${FIXES_DIR}"
    echo ""
    echo "To apply fixes one check at a time:"
    echo "  $(basename "$0") -F <CHECK_NAME> ${CLAZY_LEVEL}"
  elif [[ "${YAML_COUNT}" -gt 0 ]]; then
    echo "Warning: split script not found at ${SPLIT_SCRIPT}" >&2
    echo "Fix YAMLs are unsplit — apply manually." >&2
  fi
fi

# ── narrow the file list to only files with warnings ──────────────────
# Extract unique source files that produced warnings from the log.
WARNING_FILES="$(grep -E '^/' "${CLAZY_LOG}" | grep 'warning:' | cut -d: -f1 | sort -u || true)"

if [[ -n "${WARNING_FILES}" ]]; then
  # Convert absolute paths back to relative (matching the find output)
  # and rebuild a NUL-delimited list of only those files.
  local_warning_files="$(echo "${WARNING_FILES}" | sed "s|^${SRC_DIR}/||")"

  # Rebuild the NUL-delimited file list with only warning-producing files.
  : > "${SRC_FILES_LIST}.tmp"
  while IFS= read -r -d '' filepath; do
    if echo "${local_warning_files}" | grep -qxF "${filepath}"; then
      printf '%s\0' "${filepath}" >> "${SRC_FILES_LIST}.tmp"
    fi
  done < "${SRC_FILES_LIST}"
  mv "${SRC_FILES_LIST}.tmp" "${SRC_FILES_LIST}"

  REMAINING="$(tr -cd '\0' < "${SRC_FILES_LIST}" | wc -c | tr -d ' ')"
  echo ""
  echo "──────────────────────────────────────────────"
  echo "Narrowed ${CLAZY_LEVEL} file list: ${REMAINING} files with warnings (was ${FILE_COUNT})"
  echo "File list   : ${SRC_FILES_LIST}"
else
  echo ""
  echo "──────────────────────────────────────────────"
  echo "No warnings found — removing level file list (all clean)."
  rm -f "${SRC_FILES_LIST}"
fi

echo "Log file    : ${CLAZY_LOG}"
echo "CLAZY_LOG_PATH=${CLAZY_LOG}"
