#!/usr/bin/env bash
# Align a consumer C++ project with the ITKv6 clang-format style (clang-format 19.1.7).
# Complement to the itk5to6 migration, NOT a migration step. Built on style_common.sh.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$(cd "$HERE/../lib" && pwd)/style_common.sh"

STYLE_TOOL="clang-format"
STYLE_BIN="clang-format"
STYLE_VERSION="19.1.7"
STYLE_FILE_GLOBS=('*.c' '*.cc' '*.h' '*.cxx' '*.hxx')
STYLE_EXCLUDE_RE='(^|/)(ThirdParty|Data)/|pocketfft_hdronly\.h'
STYLE_PIXI_ASSET="$ASSETS/pixi-clang-format.toml"
STYLE_HOOK_ASSET="$ASSETS/pre-commit-clang-format.snippet.yaml"
CANONICAL="$ASSETS/itkv6.clang-format"

# A .clang-format is "ITK-flavored" if it carries ITK's generator marker.
cf_is_itk() { grep -q 'clang-format.bash\|only relevant for clang-format version' "$1" 2>/dev/null; }
cf_old_version() { grep -oE 'clang-format version [0-9]+\.[0-9]+\.[0-9]+' "$1" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1; }

# Classify the repo's .clang-format: absent | current | outdated-itk | different
cf_classify() {
  local cfg="$1/.clang-format"
  [ -f "$cfg" ] || { printf 'absent'; return; }
  if cf_is_itk "$cfg"; then
    if grep -q "$STYLE_VERSION" "$cfg"; then printf 'current'; else printf 'outdated-itk'; fi
  else
    printf 'different'
  fi
}

style_config_label() { printf '.clang-format'; }
style_has_config() { [ "$(cf_classify "$1")" = "current" ]; }

style_status_note() {
  local repo="$1" old
  case "$(cf_classify "$repo")" in
    current)       printf '.clang-format: present, ITKv6 (%s)' "$STYLE_VERSION" ;;
    outdated-itk)  old="$(cf_old_version "$repo/.clang-format")"
                   printf '.clang-format: OUTDATED ITK style (clang-format %s) — run add-config to update to %s' \
                     "${old:-unknown}" "$STYLE_VERSION" ;;
    different)     printf '.clang-format: a DIFFERENT (non-ITK) project style — adopting ITKv6 is a significant restyle; run add-config --accept-restyle to replace it' ;;
    absent)        printf '.clang-format: MISSING — run: add-config' ;;
  esac
}

style_diff_one() {  # $1 runner cmd, $2 abs file ; 0 = already formatted, 1 = would change
  local runner="$1" f="$2"; local R=($runner)
  "${R[@]}" --style=file "$f" 2>/dev/null | diff -q - "$f" >/dev/null 2>&1
}
style_apply_one() { local runner="$1" f="$2"; local R=($runner); "${R[@]}" -i --style=file "$f"; }

style_add_config() {
  local repo="" accept=0 a
  for a in "$@"; do case "$a" in --accept-restyle) accept=1 ;; *) repo="$a" ;; esac; done
  repo="$(sc_repo "${repo:-$PWD}")"
  sc_require_clean_tree "$repo" || return 3
  local kind; kind="$(cf_classify "$repo")"
  case "$kind" in
    current)
      printf '[add-config] %s/.clang-format already ITKv6 (%s); nothing to do.\n' "$repo" "$STYLE_VERSION"; return 0 ;;
    outdated-itk)
      local old; old="$(cf_old_version "$repo/.clang-format")"
      printf '[add-config] updating OUTDATED ITK .clang-format (clang-format %s) -> %s.\n' "${old:-unknown}" "$STYLE_VERSION"
      cp "$CANONICAL" "$repo/.clang-format"; git -C "$repo" add -- .clang-format
      sc_commit_msg "STYLE: Update ITK .clang-format to clang-format $STYLE_VERSION" \
        "Refresh the existing ITK clang-format config (was clang-format ${old:-an older version}) to" \
        "the ITKv6 baseline ($STYLE_VERSION). Run align-clang-format.sh run --apply to reformat."
      return 0 ;;
    different)
      if [ "$accept" -ne 1 ]; then
        printf '[add-config] REFUSING to overwrite: this project has its OWN .clang-format style.\n' >&2
        printf '[add-config] Adopting the ITKv6 style is a SIGNIFICANT restyle of the whole project.\n' >&2
        printf '[add-config] If that is truly intended, re-run: add-config --accept-restyle %s\n' "$repo" >&2
        return 2
      fi
      printf '[add-config] replacing the project .clang-format with the ITKv6 style (--accept-restyle).\n'
      cp "$CANONICAL" "$repo/.clang-format"; git -C "$repo" add -- .clang-format
      sc_commit_msg "STYLE: Adopt ITKv6 .clang-format (clang-format $STYLE_VERSION)" \
        "Replace the project's previous clang-format style with the ITKv6 baseline" \
        "($STYLE_VERSION) for consistency with ITK. This is a deliberate whole-project restyle."
      return 0 ;;
    absent)
      cp "$CANONICAL" "$repo/.clang-format"; git -C "$repo" add -- .clang-format
      printf '[add-config] wrote and staged %s/.clang-format (ITKv6 / clang-format %s).\n' "$repo" "$STYLE_VERSION"
      sc_commit_msg "STYLE: Add ITKv6 .clang-format (clang-format $STYLE_VERSION)" \
        "Adopt the ITKv6 clang-format configuration so this project formats" \
        "identically to ITK. Run align-clang-format.sh run --apply to reformat."
      return 0 ;;
  esac
}

sc_main "$@"
