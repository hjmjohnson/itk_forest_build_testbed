# shellcheck shell=bash
# Shared plumbing for the itk-*/detect.sh candidate scanners.
#
# Source it, then use the three helpers:
#
#     . "$(dirname "${BASH_SOURCE[0]}")/../lib/detect-common.sh"
#     itk_detect_init "${1:-.}"
#     hits="$(itk_detect_grep "$MY_REGEX" "${ITK_DETECT_SOURCES[@]}")"
#     itk_detect_report "$(itk_detect_count "$hits")"
#
# Contract every detector honours:
#   * stdout ends with a `----` rule and one `match_count: <N>` line, which is
#     the number itk-incremental-refactor-loop parses to decide it is dry.
#   * exit 0 whenever the scan ran, including a zero count. Exit 2 means the
#     scan could not run (bad path, not a work tree). "Nothing to do" is a
#     result, not a failure.

# The pathspec arrays are read by the sourcing detect.sh, not here.
# shellcheck disable=SC2034

# Source files a C++ scan should cover.
ITK_DETECT_SOURCES=('*.h' '*.hxx' '*.hpp' '*.cxx' '*.cpp' '*.cc' '*.txx')

# Headers only — for scans whose pattern can only occur in a class definition.
ITK_DETECT_HEADERS=('*.h' '*.hxx' '*.hpp')

# Vendored code is never ours to rewrite. The directory patterns catch the
# ThirdParty/ convention; the named files are upstream libraries that sit in a
# module's own include/ and so escape it (verify with:
# `git ls-files '*.hpp' '*.cc' | grep -v ThirdParty`).
ITK_DETECT_EXCLUDES=(
    ':(exclude)*ThirdParty/*'
    ':(exclude)*/ThirdParty/*'
    ':(exclude)*third_party/*'
    ':(exclude)*/third_party/*'
    ':(exclude)*nanoflann.hpp'
)

# itk_detect_init <repo-path>
# cd into the repo and confirm it is a git work tree, or exit 2.
itk_detect_init() {
    local repo="${1:-.}"
    cd "$repo" 2>/dev/null || {
        echo "detect: not a directory: $repo" >&2
        exit 2
    }
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
        echo "detect: not a git work tree: $repo" >&2
        exit 2
    }
}

# itk_detect_grep <extended-regex> [pathspec...]
# git grep -nE with the shared excludes appended. Prints file:line:text.
# A zero match count is not an error, so the non-zero rc is swallowed.
itk_detect_grep() {
    local regex="$1"
    shift
    git grep -nE "$regex" -- "$@" "${ITK_DETECT_EXCLUDES[@]}" 2>/dev/null || true
}

# itk_detect_count <hits>
# Count non-empty lines. Safe when hits is the empty string.
itk_detect_count() {
    printf '%s' "${1:-}" | grep -c . || true
}

# itk_detect_report <count> [note...]
# Emit the machine-readable footer. Any extra arguments are printed after it as
# human-facing notes, so a detector can explain its false-positive profile
# without disturbing the parseable line.
itk_detect_report() {
    local count="${1:-0}"
    shift || true
    echo "----"
    echo "match_count: ${count}"
    local note
    for note in "$@"; do
        echo "$note"
    done
    return 0
}
