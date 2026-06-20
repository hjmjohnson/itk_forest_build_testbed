#!/usr/bin/env bash
# Align a consumer Python project with the ITKv6 black style (black 24.2.0).
# Complement to the itk5to6 migration, NOT a migration step. Built on style_common.sh.
# black config lives in pyproject.toml [tool.black] (ITK: line-length = 88, target py310).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$(cd "$HERE/../lib" && pwd)/style_common.sh"

STYLE_TOOL="black"
STYLE_BIN="black"
STYLE_VERSION="24.2.0"
STYLE_FILE_GLOBS=('*.py')
STYLE_EXCLUDE_RE='(^|/)(ThirdParty|Data)/|build'
STYLE_PIXI_ASSET="$ASSETS/pixi-black.toml"
STYLE_HOOK_ASSET="$ASSETS/pre-commit-black.snippet.yaml"
SNIPPET="$ASSETS/black.pyproject.snippet.toml"
ITK_LINE_LENGTH=88

bk_has_section() { [ -f "$1/pyproject.toml" ] && grep -qE '^\[tool\.black\]' "$1/pyproject.toml"; }
bk_line_length() {  # echo the line-length set inside [tool.black], or empty
  awk '/^\[tool\.black\]/{f=1;next} f&&/^\[/{f=0} f&&/line-length/{gsub(/[^0-9]/,"");print;exit}' \
    "$1/pyproject.toml" 2>/dev/null
}
# absent | current | different
bk_classify() {
  local repo="$1"
  bk_has_section "$repo" || { printf 'absent'; return; }
  if [ "$(bk_line_length "$repo")" = "$ITK_LINE_LENGTH" ]; then printf 'current'; else printf 'different'; fi
}

# Drop any existing [tool.black] section, then append the canonical block.
bk_upsert_section() {
  local pp="$1" tmp; tmp="$(mktemp)"
  if [ -f "$pp" ]; then
    awk '
      /^\[tool\.black\]/{inblk=1; next}
      inblk && /^\[/{inblk=0}
      !inblk{print}
    ' "$pp" > "$tmp"
    # collapse trailing blank lines, then append the canonical block
    printf '%s\n' "$(cat "$tmp")" > "$pp"
    printf '\n' >> "$pp"
  else
    : > "$pp"
  fi
  cat "$SNIPPET" >> "$pp"
  rm -f "$tmp"
}

style_config_label() { printf '[tool.black] (pyproject.toml)'; }
style_has_config() { [ "$(bk_classify "$1")" = "current" ]; }

style_status_note() {
  local repo="$1" ll
  case "$(bk_classify "$repo")" in
    current)   printf '[tool.black]: present, ITKv6 (line-length %s)' "$ITK_LINE_LENGTH" ;;
    different) ll="$(bk_line_length "$repo")"
               printf '[tool.black]: a DIFFERENT project style (line-length %s vs ITK %s) — run add-config --accept-restyle to adopt ITKv6' \
                 "${ll:-unset}" "$ITK_LINE_LENGTH" ;;
    absent)    printf '[tool.black]: MISSING in pyproject.toml — run: add-config' ;;
  esac
}

style_diff_one() {  # 0 = already formatted, 1 = would change ; black --check exits 1 when it would reformat
  local runner="$1" f="$2"; local R=($runner)
  "${R[@]}" --quiet --check "$f" >/dev/null 2>&1
}
style_apply_one() { local runner="$1" f="$2"; local R=($runner); "${R[@]}" --quiet "$f"; }

style_add_config() {
  local repo="" accept=0 a
  for a in "$@"; do case "$a" in --accept-restyle) accept=1 ;; *) repo="$a" ;; esac; done
  repo="$(sc_repo "${repo:-$PWD}")"
  sc_require_clean_tree "$repo" || return 3
  local pp="$repo/pyproject.toml"
  case "$(bk_classify "$repo")" in
    current)
      printf '[add-config] %s already has ITKv6 [tool.black] (line-length %s); nothing to do.\n' "$pp" "$ITK_LINE_LENGTH"; return 0 ;;
    different)
      local ll; ll="$(bk_line_length "$repo")"
      if [ "$accept" -ne 1 ]; then
        printf '[add-config] REFUSING to overwrite: this project has its OWN [tool.black] (line-length %s).\n' "${ll:-unset}" >&2
        printf '[add-config] Adopting the ITKv6 black style (line-length %s) is a SIGNIFICANT restyle.\n' "$ITK_LINE_LENGTH" >&2
        printf '[add-config] If that is truly intended, re-run: add-config --accept-restyle %s\n' "$repo" >&2
        return 2
      fi
      printf '[add-config] replacing the project [tool.black] with the ITKv6 style (--accept-restyle).\n'
      bk_upsert_section "$pp"; git -C "$repo" add -- pyproject.toml
      sc_commit_msg "STYLE: Adopt ITKv6 black config (black $STYLE_VERSION)" \
        "Replace the project's previous [tool.black] (was line-length ${ll:-unset}) with the ITKv6" \
        "baseline (line-length $ITK_LINE_LENGTH, target py310). Deliberate whole-project restyle."
      return 0 ;;
    absent)
      bk_upsert_section "$pp"; git -C "$repo" add -- pyproject.toml
      printf '[add-config] added [tool.black] to %s (ITKv6 / black %s).\n' "$pp" "$STYLE_VERSION"
      sc_commit_msg "STYLE: Add ITKv6 black config (black $STYLE_VERSION)" \
        "Adopt the ITKv6 black configuration (line-length $ITK_LINE_LENGTH, target py310) so this" \
        "project formats identically to ITK. Run align-black.sh run --apply to reformat."
      return 0 ;;
  esac
}

sc_main "$@"
