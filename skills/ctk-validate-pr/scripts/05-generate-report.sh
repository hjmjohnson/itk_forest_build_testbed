#!/usr/bin/env bash
# Generate a GitHub-ready comparative validation report with status indicators.
#
# Usage: 05-generate-report.sh <ctk_src> <slicer_bld> <proposed_hash> [<reference_hash>] [<pr_number>]
#
# Status indicators (comparing proposed vs reference):
#   :white_check_mark:  0 errors (clean)
#   :warning:           warnings increased vs reference
#   :no_entry_sign:     new errors or new test failures vs reference
#   (no icon)           unchanged or improved from reference
#
# Output: report to stdout (pipe to 06-post-report.sh or gh pr comment)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CTK_SRC="${1:-$HOME/src/CTK}"
SLICER_BLD="${2:-$HOME/src/Slicer-bld}"
PROPOSED_HASH="${3:?Usage: $0 <ctk_src> <slicer_bld> <proposed_hash> [reference_hash] [pr_num]}"
REFERENCE_HASH="${4:-}"
PR_NUM="${5:-}"

CACHE_DIR="${CTK_SRC}/.claude/validate-cache"
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PLATFORM=$(uname -srm)

PROPOSED_SHORT="${PROPOSED_HASH:0:8}"
REFERENCE_SHORT=""
[ -n "${REFERENCE_HASH}" ] && REFERENCE_SHORT="${REFERENCE_HASH:0:8}"

########################################################################
# Helpers
########################################################################
read_val() {
  local file="$1" key="$2" default="${3:-N/A}"
  if [ -f "${file}" ]; then
    local val
    val=$({ grep "^${key}=" "${file}" || true; } | head -1 | cut -d= -f2-)
    [ -n "${val}" ] && echo "${val}" || echo "${default}"
  else
    echo "${default}"
  fi
}

read_block() {
  local file="$1" tag="$2"
  if [ -f "${file}" ]; then
    sed -n "/^${tag}<<ENDBLOCK/,/^ENDBLOCK/p" "${file}" | { grep -v "^${tag}<<ENDBLOCK\|^ENDBLOCK" || true; }
  fi
}

count_pattern() {
  local file="$1" pattern="$2"
  if [ -f "${file}" ]; then
    { grep "${pattern}" "${file}" || true; } | wc -l | tr -d ' '
  else
    echo "N/A"
  fi
}

# Status icon for error counts: :white_check_mark: if 0, :no_entry_sign: if new errors vs ref
err_icon() {
  local proposed="$1" reference="${2:-N/A}"
  if [ "${proposed}" = "N/A" ]; then echo ""; return; fi
  if [ "${proposed}" -eq 0 ] 2>/dev/null; then
    echo ":white_check_mark:"
  elif [ "${reference}" != "N/A" ] && [ "${proposed}" -gt "${reference}" ] 2>/dev/null; then
    echo ":no_entry_sign:"
  else
    echo ""
  fi
}

# Status icon for warning counts: :white_check_mark: if 0, :warning: if increased vs ref
warn_icon() {
  local proposed="$1" reference="${2:-N/A}"
  if [ "${proposed}" = "N/A" ]; then echo ""; return; fi
  if [ "${proposed}" -eq 0 ] 2>/dev/null; then
    echo ":white_check_mark:"
  elif [ "${reference}" != "N/A" ] && [ "${proposed}" -gt "${reference}" ] 2>/dev/null; then
    echo ":warning:"
  else
    echo ""
  fi
}

# Status icon for test failures: :white_check_mark: if 0, :no_entry_sign: if new failures vs ref
fail_icon() {
  local proposed="$1" reference="${2:-N/A}"
  if [ "${proposed}" = "N/A" ]; then echo ""; return; fi
  if [ "${proposed}" -eq 0 ] 2>/dev/null; then
    echo ":white_check_mark:"
  elif [ "${reference}" != "N/A" ] && [ "${proposed}" -gt "${reference}" ] 2>/dev/null; then
    echo ":no_entry_sign:"
  else
    echo ""
  fi
}

# Format a build result cell: "N errors, M warnings ICON"
fmt_build() {
  local p_err="$1" p_warn="$2" r_err="${3:-N/A}" r_warn="${4:-N/A}"
  local ei wi
  ei=$(err_icon "${p_err}" "${r_err}")
  wi=$(warn_icon "${p_warn}" "${r_warn}")
  local icons=""
  [ -n "${ei}" ] && icons=" ${ei}"
  [ -n "${wi}" ] && icons="${icons} ${wi}"
  echo "${p_err} errors, ${p_warn} warnings${icons}"
}

# Format a test result cell: "P/T passed, F failed ICON"
fmt_test() {
  local p_passed="$1" p_total="$2" p_failed="$3" r_failed="${4:-N/A}"
  local fi_icon
  fi_icon=$(fail_icon "${p_failed}" "${r_failed}")
  local icon=""
  [ -n "${fi_icon}" ] && icon=" ${fi_icon}"
  if [ "${p_failed}" = "0" ]; then
    icon=" :white_check_mark:"
  fi
  echo "${p_passed}/${p_total} passed, ${p_failed} failed${icon}"
}

########################################################################
# Load results for a given hash
########################################################################
load_results() {
  local hash="$1" prefix="$2"
  local cache="${CACHE_DIR}/${hash}"

  local commit_info="unknown"
  [ -f "${cache}/commit-info.txt" ] && commit_info=$(cat "${cache}/commit-info.txt")
  printf -v "${prefix}COMMIT_INFO" '%s' "${commit_info}"
  printf -v "${prefix}HASH" '%s' "${hash}"
  printf -v "${prefix}SHORT" '%s' "${hash:0:8}"

  # CTK Qt5 build
  eval "${prefix}QT5_BUILD_ERRORS=$(count_pattern "${cache}/ctk-qt5-build.log" ' error:')"
  local qt5w
  qt5w=$({ grep ' warning:' "${cache}/ctk-qt5-build.log" 2>/dev/null || true; } | { grep -v '\[-Wclazy' || true; } | wc -l | tr -d ' ')
  eval "${prefix}QT5_BUILD_WARNINGS=${qt5w}"

  # CTK Qt6 build
  if [ -f "${cache}/ctk-qt6-build.log" ]; then
    eval "${prefix}QT6_BUILD_ERRORS=$(count_pattern "${cache}/ctk-qt6-build.log" ' error:')"
    local qt6w
    qt6w=$({ grep ' warning:' "${cache}/ctk-qt6-build.log" 2>/dev/null || true; } | { grep -v '\[-Wclazy' || true; } | wc -l | tr -d ' ')
    eval "${prefix}QT6_BUILD_WARNINGS=${qt6w}"
  else
    eval "${prefix}QT6_BUILD_ERRORS=N/A"
    eval "${prefix}QT6_BUILD_WARNINGS=N/A"
  fi

  # CTK tests
  eval "${prefix}QT5_TEST_TOTAL=$(read_val "${cache}/ctk-qt5-test-summary.txt" TOTAL 0)"
  eval "${prefix}QT5_TEST_PASSED=$(read_val "${cache}/ctk-qt5-test-summary.txt" PASSED 0)"
  eval "${prefix}QT5_TEST_FAILED=$(read_val "${cache}/ctk-qt5-test-summary.txt" FAILED 0)"
  eval "${prefix}QT5_TEST_FAILURES='$(read_block "${cache}/ctk-qt5-test-summary.txt" FAILURES)'"
  eval "${prefix}QT6_TEST_TOTAL=$(read_val "${cache}/ctk-qt6-test-summary.txt" TOTAL 0)"
  eval "${prefix}QT6_TEST_PASSED=$(read_val "${cache}/ctk-qt6-test-summary.txt" PASSED 0)"
  eval "${prefix}QT6_TEST_FAILED=$(read_val "${cache}/ctk-qt6-test-summary.txt" FAILED 0)"
  eval "${prefix}QT6_TEST_FAILURES='$(read_block "${cache}/ctk-qt6-test-summary.txt" FAILURES)'"

  # Slicer CTK build (classified)
  eval "${prefix}SLICER_CTK_SRC_ERRORS=$(read_val "${cache}/slicer-build-summary.txt" CTK_SRC_ERRORS 'N/A')"
  eval "${prefix}SLICER_CTK_SRC_WARNINGS=$(read_val "${cache}/slicer-build-summary.txt" CTK_SRC_WARNINGS 'N/A')"
  eval "${prefix}SLICER_CTK_DEP_ERRORS=$(read_val "${cache}/slicer-build-summary.txt" CTK_DEP_ERRORS 'N/A')"
  eval "${prefix}SLICER_CTK_DEP_WARNINGS=$(read_val "${cache}/slicer-build-summary.txt" CTK_DEP_WARNINGS 'N/A')"
  eval "${prefix}SLICER_CTK_BUILD_ERRORS=$(read_val "${cache}/slicer-build-summary.txt" CTK_BUILD_ERRORS 'N/A')"
  eval "${prefix}SLICER_CTK_BUILD_WARNINGS=$(read_val "${cache}/slicer-build-summary.txt" CTK_BUILD_WARNINGS 'N/A')"

  # Slicer inner build (classified)
  eval "${prefix}SLICER_BUILD_ERRORS=$(read_val "${cache}/slicer-build-summary.txt" SLICER_BUILD_ERRORS 'N/A')"
  eval "${prefix}SLICER_BUILD_WARNINGS=$(read_val "${cache}/slicer-build-summary.txt" SLICER_BUILD_WARNINGS 'N/A')"
  eval "${prefix}SLICER_CTK_ERRORS=$(read_val "${cache}/slicer-build-summary.txt" SLICER_CTK_ERRORS 'N/A')"
  eval "${prefix}SLICER_CTK_WARNINGS=$(read_val "${cache}/slicer-build-summary.txt" SLICER_CTK_WARNINGS 'N/A')"
  eval "${prefix}SLICER_OWN_ERRORS=$(read_val "${cache}/slicer-build-summary.txt" SLICER_OWN_ERRORS 'N/A')"
  eval "${prefix}SLICER_OWN_WARNINGS=$(read_val "${cache}/slicer-build-summary.txt" SLICER_OWN_WARNINGS 'N/A')"

  # Slicer tests (classified)
  eval "${prefix}SLICER_TEST_TOTAL=$(read_val "${cache}/slicer-test-summary.txt" TOTAL 'N/A')"
  eval "${prefix}SLICER_TEST_PASSED=$(read_val "${cache}/slicer-test-summary.txt" PASSED 'N/A')"
  eval "${prefix}SLICER_TEST_FAILED=$(read_val "${cache}/slicer-test-summary.txt" FAILED 'N/A')"
  eval "${prefix}SLICER_CTK_FAIL_COUNT=$(read_val "${cache}/slicer-test-summary.txt" CTK_FAILURE_COUNT 0)"
  eval "${prefix}SLICER_OWN_FAIL_COUNT=$(read_val "${cache}/slicer-test-summary.txt" SLICER_OWN_FAILURE_COUNT 0)"
  eval "${prefix}SLICER_CTK_FAIL_LIST='$(read_block "${cache}/slicer-test-summary.txt" CTK_FAILURES)'"
  eval "${prefix}SLICER_OWN_FAIL_LIST='$(read_block "${cache}/slicer-test-summary.txt" SLICER_OWN_FAILURES)'"
}

########################################################################
# Load data
########################################################################
load_results "${PROPOSED_HASH}" "P_"
HAS_REF=false
if [ -n "${REFERENCE_HASH}" ] && [ -d "${CACHE_DIR}/${REFERENCE_HASH}" ]; then
  load_results "${REFERENCE_HASH}" "R_"
  HAS_REF=true
fi

########################################################################
# Generate report
########################################################################
PR_TITLE=""
[ -n "${PR_NUM}" ] && PR_TITLE=" for PR #${PR_NUM}"

cat <<EOMD
## CTK Validation Report${PR_TITLE}

**Date:** ${TIMESTAMP}
**Platform:** ${PLATFORM}

| Role | CTK Hash | Commit |
|------|----------|--------|
| **Proposed** | [\`${P_SHORT}\`](https://github.com/commontk/CTK/commit/${PROPOSED_HASH}) | ${P_COMMIT_INFO} |
EOMD

if [ "${HAS_REF}" = true ]; then
  echo "| **Reference** | [\`${R_SHORT}\`](https://github.com/commontk/CTK/commit/${REFERENCE_HASH}) | ${R_COMMIT_INFO} |"
fi

echo ""
echo "> :white_check_mark: = 0 errors/failures (clean) | :warning: = warnings increased vs reference | :no_entry_sign: = new errors or test failures vs reference"
echo ""

########################################################################
# Action summary matrix with indicators
########################################################################
echo "### Validation Actions Performed"
echo ""
echo "| # | Action | Scope | Qt | Proposed (\`${P_SHORT}\`) | Reference (\`${R_SHORT:-N/A}\`) |"
echo "|---|--------|-------|----|--------------------------|-------------------------------|"

# Row 1: CTK Qt5 build
echo "| 1 | Build | CTK standalone | Qt5 | $(fmt_build "${P_QT5_BUILD_ERRORS}" "${P_QT5_BUILD_WARNINGS}" "${R_QT5_BUILD_ERRORS:-N/A}" "${R_QT5_BUILD_WARNINGS:-N/A}") | ${R_QT5_BUILD_ERRORS:-N/A} errors, ${R_QT5_BUILD_WARNINGS:-N/A} warnings |"

# Row 2: CTK Qt6 build
echo "| 2 | Build | CTK standalone | Qt6 | $(fmt_build "${P_QT6_BUILD_ERRORS}" "${P_QT6_BUILD_WARNINGS}" "${R_QT6_BUILD_ERRORS:-N/A}" "${R_QT6_BUILD_WARNINGS:-N/A}") | ${R_QT6_BUILD_ERRORS:-N/A} errors, ${R_QT6_BUILD_WARNINGS:-N/A} warnings |"

# Row 3: CTK Qt5 tests
echo "| 3 | Test | CTK standalone | Qt5 | $(fmt_test "${P_QT5_TEST_PASSED}" "${P_QT5_TEST_TOTAL}" "${P_QT5_TEST_FAILED}" "${R_QT5_TEST_FAILED:-N/A}") | ${R_QT5_TEST_PASSED:-N/A}/${R_QT5_TEST_TOTAL:-N/A} passed, ${R_QT5_TEST_FAILED:-N/A} failed |"

# Row 4: CTK Qt6 tests
echo "| 4 | Test | CTK standalone | Qt6 | $(fmt_test "${P_QT6_TEST_PASSED}" "${P_QT6_TEST_TOTAL}" "${P_QT6_TEST_FAILED}" "${R_QT6_TEST_FAILED:-N/A}") | ${R_QT6_TEST_PASSED:-N/A}/${R_QT6_TEST_TOTAL:-N/A} passed, ${R_QT6_TEST_FAILED:-N/A} failed |"

# Row 5: CTK-in-Slicer build
echo "| 5 | Build | CTK-in-Slicer (clean) | Qt5 | $(fmt_build "${P_SLICER_CTK_BUILD_ERRORS}" "${P_SLICER_CTK_BUILD_WARNINGS}" "${R_SLICER_CTK_BUILD_ERRORS:-N/A}" "${R_SLICER_CTK_BUILD_WARNINGS:-N/A}") | ${R_SLICER_CTK_BUILD_ERRORS:-N/A} errors, ${R_SLICER_CTK_BUILD_WARNINGS:-N/A} warnings |"

# Row 6: Slicer inner build
echo "| 6 | Build | Slicer inner build | Qt5 | $(fmt_build "${P_SLICER_BUILD_ERRORS}" "${P_SLICER_BUILD_WARNINGS}" "${R_SLICER_BUILD_ERRORS:-N/A}" "${R_SLICER_BUILD_WARNINGS:-N/A}") | ${R_SLICER_BUILD_ERRORS:-N/A} errors, ${R_SLICER_BUILD_WARNINGS:-N/A} warnings |"

# Row 7: Slicer tests
echo "| 7 | Test | Slicer inner build | Qt5 | $(fmt_test "${P_SLICER_TEST_PASSED}" "${P_SLICER_TEST_TOTAL}" "${P_SLICER_TEST_FAILED}" "${R_SLICER_TEST_FAILED:-N/A}") | ${R_SLICER_TEST_PASSED:-N/A}/${R_SLICER_TEST_TOTAL:-N/A} passed, ${R_SLICER_TEST_FAILED:-N/A} failed |"

echo ""

########################################################################
# Warning analysis (only when proposed has more warnings than reference)
########################################################################
emit_warning_analysis() {
  local label="$1" log="$2" p_warn="$3" r_warn="${4:-N/A}"

  # Skip if no increase or N/A
  if [ "${p_warn}" = "N/A" ] || [ "${r_warn}" = "N/A" ]; then return; fi
  if [ "${p_warn}" -le "${r_warn}" ] 2>/dev/null; then return; fi
  if [ ! -f "${log}" ]; then return; fi

  local delta=$((p_warn - r_warn))
  echo "<details><summary>:warning: ${label}: ${delta} new warnings (${r_warn} → ${p_warn})</summary>"
  echo ""
  echo "**By category:**"
  echo ""
  echo "| Count | Category |"
  echo "|-------|----------|"
  { grep ' warning:' "${log}" || true; } | { grep -v '\[-Wclazy' || true; } | \
    { grep -oE '\[-W[^]]+' || true; } | sort | uniq -c | sort -rn | \
    while read -r cnt cat; do echo "| ${cnt} | \`${cat}\` |"; done
  echo ""
  echo "**By source:**"
  echo ""
  echo "| Count | Source | Origin |"
  echo "|-------|--------|--------|"
  { grep ' warning:' "${log}" || true; } | { grep -v '\[-Wclazy' || true; } | \
    grep -oE '^[^:]+' | sort | uniq -c | sort -rn | \
    while read -r cnt path; do
      local origin="external"
      if echo "${path}" | grep -q '/CTK/Libs\|/CTK/Plugins\|/CTK/Applications'; then
        local short_path
        short_path=$(echo "${path}" | sed 's|.*/CTK/||')
        origin="**CTK source**"
        path="${short_path}"
      elif echo "${path}" | grep -q 'PythonQt'; then
        origin="PythonQt (external)"
      elif echo "${path}" | grep -q 'python'; then
        origin="Python headers (external)"
      fi
      echo "| ${cnt} | \`${path}\` | ${origin} |"
    done
  echo ""
  echo "</details>"
  echo ""
}

P_CACHE="${CACHE_DIR}/${PROPOSED_HASH}"
R_CACHE="${CACHE_DIR}/${REFERENCE_HASH:-nonexistent}"
emit_warning_analysis "CTK standalone Qt5" "${P_CACHE}/ctk-qt5-build.log" "${P_QT5_BUILD_WARNINGS}" "${R_QT5_BUILD_WARNINGS:-N/A}"
emit_warning_analysis "CTK standalone Qt6" "${P_CACHE}/ctk-qt6-build.log" "${P_QT6_BUILD_WARNINGS}" "${R_QT6_BUILD_WARNINGS:-N/A}"

########################################################################
# CTK-in-Slicer build detail (classified)
########################################################################
cat <<EOMD
### CTK-in-Slicer Build Detail (classified warnings)

| Source | Proposed errors | Proposed warnings | Reference errors | Reference warnings |
|--------|-----------------|-------------------|------------------|-------------------|
| **CTK source code** | ${P_SLICER_CTK_SRC_ERRORS} $(err_icon "${P_SLICER_CTK_SRC_ERRORS}" "${R_SLICER_CTK_SRC_ERRORS:-N/A}") | ${P_SLICER_CTK_SRC_WARNINGS} $(warn_icon "${P_SLICER_CTK_SRC_WARNINGS}" "${R_SLICER_CTK_SRC_WARNINGS:-N/A}") | ${R_SLICER_CTK_SRC_ERRORS:-N/A} | ${R_SLICER_CTK_SRC_WARNINGS:-N/A} |
| CTK dependencies | ${P_SLICER_CTK_DEP_ERRORS} $(err_icon "${P_SLICER_CTK_DEP_ERRORS}" "${R_SLICER_CTK_DEP_ERRORS:-N/A}") | ${P_SLICER_CTK_DEP_WARNINGS} $(warn_icon "${P_SLICER_CTK_DEP_WARNINGS}" "${R_SLICER_CTK_DEP_WARNINGS:-N/A}") | ${R_SLICER_CTK_DEP_ERRORS:-N/A} | ${R_SLICER_CTK_DEP_WARNINGS:-N/A} |
| **Slicer (CTK-related)** | ${P_SLICER_CTK_ERRORS} $(err_icon "${P_SLICER_CTK_ERRORS}" "${R_SLICER_CTK_ERRORS:-N/A}") | ${P_SLICER_CTK_WARNINGS} $(warn_icon "${P_SLICER_CTK_WARNINGS}" "${R_SLICER_CTK_WARNINGS:-N/A}") | ${R_SLICER_CTK_ERRORS:-N/A} | ${R_SLICER_CTK_WARNINGS:-N/A} |
| Slicer (own code) | ${P_SLICER_OWN_ERRORS} $(err_icon "${P_SLICER_OWN_ERRORS}" "${R_SLICER_OWN_ERRORS:-N/A}") | ${P_SLICER_OWN_WARNINGS} $(warn_icon "${P_SLICER_OWN_WARNINGS}" "${R_SLICER_OWN_WARNINGS:-N/A}") | ${R_SLICER_OWN_ERRORS:-N/A} | ${R_SLICER_OWN_WARNINGS:-N/A} |
EOMD

echo ""

########################################################################
# Slicer test detail (classified)
########################################################################
cat <<EOMD
### Slicer Test Detail (classified failures)

| Category | Proposed (\`${P_SHORT}\`) | Reference (\`${R_SHORT:-N/A}\`) |
|----------|--------------------------|-------------------------------|
| CTK-related failures | ${P_SLICER_CTK_FAIL_COUNT} $(fail_icon "${P_SLICER_CTK_FAIL_COUNT}" "${R_SLICER_CTK_FAIL_COUNT:-N/A}") | ${R_SLICER_CTK_FAIL_COUNT:-N/A} |
| Slicer-own failures | ${P_SLICER_OWN_FAIL_COUNT} $(fail_icon "${P_SLICER_OWN_FAIL_COUNT}" "${R_SLICER_OWN_FAIL_COUNT:-N/A}") | ${R_SLICER_OWN_FAIL_COUNT:-N/A} |
| **Total failed** | ${P_SLICER_TEST_FAILED} $(fail_icon "${P_SLICER_TEST_FAILED}" "${R_SLICER_TEST_FAILED:-N/A}") | ${R_SLICER_TEST_FAILED:-N/A} |
EOMD

echo ""

########################################################################
# Known failure cross-reference
########################################################################
KNOWN_FAILURES_FILE="${SCRIPT_DIR}/../known-failure-prs.txt"

# Annotate a failure list: for each failed test, look up in known-failure-prs.txt
# and emit a markdown table with test name, status, and PR/issue link.
annotate_failures() {
  local failures="$1"
  local qt_label="$2"
  if [ -z "${failures}" ]; then return; fi

  echo "**${qt_label}:**"
  echo ""
  echo "| Test | Status | Related PR/Issue |"
  echo "|------|--------|-----------------|"

  echo "${failures}" | while IFS= read -r line; do
    # Extract test name: "  NNN - testName (Result)"
    local test_name
    test_name=$(echo "${line}" | sed 's/.*- \([^ ]*\) .*/\1/' | tr -d ' ')
    [ -z "${test_name}" ] && continue

    local result
    result=$(echo "${line}" | sed 's/.*(\(.*\)).*/\1/')

    # Look up in known failures file
    local matched=false
    if [ -f "${KNOWN_FAILURES_FILE}" ]; then
      while IFS='|' read -r pattern category pr_ref description; do
        # Skip comments and empty lines
        case "${pattern}" in '#'*|'') continue;; esac
        pattern=$(echo "${pattern}" | tr -d ' ')
        if echo "${test_name}" | grep -qE "${pattern}"; then
          category=$(echo "${category}" | tr -d ' ')
          pr_ref=$(echo "${pr_ref}" | tr -d ' ')
          description=$(echo "${description}" | sed 's/^ *//')
          local icon link
          case "${category}" in
            open-pr)     icon=":arrows_counterclockwise:" ;;
            infrastructure) icon=":desktop_computer:" ;;
            known-bug)   icon=":bug:" ;;
            wontfix)     icon=":heavy_minus_sign:" ;;
            *)           icon=":grey_question:" ;;
          esac
          if [ "${pr_ref}" != "none" ]; then
            link="${pr_ref}"
          else
            link="—"
          fi
          echo "| \`${test_name}\` | ${icon} ${result} | ${link} — ${description} |"
          matched=true
          break
        fi
      done < "${KNOWN_FAILURES_FILE}"
    fi

    if [ "${matched}" = false ]; then
      echo "| \`${test_name}\` | ${result} | *unknown — not in known failures database* |"
    fi
  done
  echo ""
}

########################################################################
# CTK test failure details (expandable, annotated)
########################################################################
if [ -n "${P_QT5_TEST_FAILURES}" ] || [ -n "${P_QT6_TEST_FAILURES}" ]; then
  echo "<details><summary>CTK Test Failures (proposed <code>${P_SHORT}</code>)</summary>"
  echo ""
  annotate_failures "${P_QT5_TEST_FAILURES}" "Qt5 (${P_QT5_TEST_FAILED} failures)"
  annotate_failures "${P_QT6_TEST_FAILURES}" "Qt6 (${P_QT6_TEST_FAILED} failures)"
  echo "</details>"
  echo ""
fi

if [ "${HAS_REF}" = true ]; then
  if [ -n "${R_QT5_TEST_FAILURES}" ] || [ -n "${R_QT6_TEST_FAILURES}" ]; then
    echo "<details><summary>CTK Test Failures (reference <code>${R_SHORT}</code>)</summary>"
    echo ""
    annotate_failures "${R_QT5_TEST_FAILURES}" "Qt5 (${R_QT5_TEST_FAILED} failures)"
    annotate_failures "${R_QT6_TEST_FAILURES}" "Qt6 (${R_QT6_TEST_FAILED} failures)"
    echo "</details>"
    echo ""
  fi
fi

########################################################################
# Slicer test failure details (expandable, classified)
########################################################################
if [ -n "${P_SLICER_CTK_FAIL_LIST}" ]; then
  echo "<details><summary>Slicer CTK-related Test Failures (proposed)</summary>"
  echo ""
  echo '```'
  echo "${P_SLICER_CTK_FAIL_LIST}"
  echo '```'
  echo "</details>"
  echo ""
fi

if [ -n "${P_SLICER_OWN_FAIL_LIST}" ]; then
  echo "<details><summary>Slicer-own Test Failures (proposed)</summary>"
  echo ""
  echo '```'
  echo "${P_SLICER_OWN_FAIL_LIST}"
  echo '```'
  echo "</details>"
  echo ""
fi

echo ""
echo "> :arrows_counterclockwise: = addressed in open PR | :desktop_computer: = infrastructure/display dependent | :bug: = known bug | :heavy_minus_sign: = wontfix"
echo ""
echo "---"
echo "Generated by \`/ctk-validate-pr\` skill | cache: \`${CACHE_DIR}\`"
