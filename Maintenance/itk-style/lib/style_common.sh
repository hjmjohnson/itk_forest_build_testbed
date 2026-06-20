#!/usr/bin/env bash
# Shared scaffold for ITKv6 style-alignment tools (clang-format, black, ...).
# A tool script sources this, sets the STYLE_* variables, defines the four
# tool hooks, then calls `sc_main "$@"`. Common behavior — repo resolution,
# version-pinned runner discovery (PATH/pixi/pipx/uvx), file discovery, diff
# counting, staging, and the doctor/check/add-config/run/hook subcommands —
# lives here so each formatter only declares what differs.
#
# A tool script MUST set:
#   STYLE_TOOL        human name (e.g. "clang-format")
#   STYLE_BIN         executable name (e.g. "clang-format", "black")
#   STYLE_VERSION     exact pinned version (e.g. "19.1.7", "24.2.0")
#   STYLE_FILE_GLOBS  bash array of git pathspecs (e.g. ('*.py'))
#   STYLE_EXCLUDE_RE  ERE of repo-relative paths to skip (e.g. '(^|/)ThirdParty/')
#   STYLE_PIXI_ASSET  path to the pixi manifest snippet for this tool
#   STYLE_HOOK_ASSET  path to the pre-commit hook snippet for this tool
# and MUST define:
#   style_has_config <repo>   -> 0 if the repo's config matches ITKv6, else 1
#   style_config_label        -> echo the config artifact name (e.g. ".clang-format")
#   style_diff_one <runner> <abs_file>  -> 0 if already formatted, 1 if it would change
#   style_apply_one <runner> <abs_file> -> reformat the file in place
#   style_add_config <args...> -> parse [repo] [flags], add/stage the tool's config,
#                                 print a suggested message (receives raw `add-config` args)
# MAY define (optional):
#   style_status_note <repo>  -> echo a nuanced one-line status for `check` when the
#                                config is not the current ITKv6 one (e.g. outdated vs different)
#
# Provided here: ASSETS (the assets/ dir). Nothing here commits/branches/PRs.

ASSETS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../assets" && pwd)"

sc_die() { printf '%s: %s\n' "${STYLE_TOOL:-style}" "$*" >&2; exit 1; }

# Resolve a repo arg (or PWD) to the git work-tree root.
sc_repo() {
  local r="${1:-$PWD}"
  r="$(cd "$r" 2>/dev/null && pwd)" || sc_die "no such directory: ${1:-$PWD}"
  git -C "$r" rev-parse --is-inside-work-tree >/dev/null 2>&1 || sc_die "not a git work tree: $r"
  git -C "$r" rev-parse --show-toplevel
}

# Report the checkout vs the primary repo's primary branch (origin/HEAD).
# Style alignment is only meaningful against the current primary branch; a stale
# checkout silently reformats year-old code. Suppress with STYLE_NO_BASE_CHECK=1.
sc_primary_branch_report() {
  [ "${STYLE_NO_BASE_CHECK:-0}" = "1" ] && return 0
  local path="${1:-$PWD}"
  git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  local primary
  primary="$(git -C "$path" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/@@')"
  if [ -z "$primary" ]; then
    git -C "$path" rev-parse --verify -q origin/main >/dev/null && primary="origin/main"
    [ -z "$primary" ] && git -C "$path" rev-parse --verify -q origin/master >/dev/null && primary="origin/master"
  fi
  [ -n "$primary" ] || { printf '[base] ⚠ no origin primary branch found; not validated against a primary branch.\n' >&2; return 0; }
  # Refresh the remote-tracking ref by default; STYLE_NO_FETCH=1 skips it.
  local freshness="as of last local fetch"
  if [ "${STYLE_NO_FETCH:-0}" = "1" ]; then
    freshness="--no-fetch; as of last local fetch"
  elif git -C "$path" fetch --quiet "${primary%%/*}" "${primary#*/}" 2>/dev/null; then
    freshness="just fetched"
  else
    freshness="fetch failed; as of last local fetch"
  fi
  local h b bd counts behind ahead
  h="$(git -C "$path" rev-parse --short HEAD)"; b="$(git -C "$path" rev-parse --short "$primary")"
  bd="$(git -C "$path" log -1 --format=%cs "$primary" 2>/dev/null)"
  counts="$(git -C "$path" rev-list --left-right --count "$primary...HEAD" 2>/dev/null)"
  behind="$(printf '%s' "$counts" | awk '{print $1}')"; ahead="$(printf '%s' "$counts" | awk '{print $2}')"
  if [ "${behind:-0}" -gt 0 ] || [ "$h" != "$b" ]; then
    printf '[base] ⚠ WARNING: checkout is %s commit(s) BEHIND %s (and %s ahead). HEAD %s, %s %s (%s, %s).\n' "${behind:-?}" "$primary" "${ahead:-?}" "$h" "$primary" "$b" "$bd" "$freshness" >&2
    printf '[base]     Style results are only valid against current %s; fetch+rebase, or set STYLE_NO_BASE_CHECK=1.\n' "$primary" >&2
  else
    printf '[base] HEAD %s == %s (%s, %s).\n' "$h" "$primary" "$bd" "$freshness" >&2
  fi
  return 0
}

# Parse a semver-ish version from a command's --version output.
sc_ver() { "$@" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1; }

# Echo "SRC<TAB>RUNNER_CMD" for STYLE_BIN at STYLE_VERSION, else return 1.
# Order: PATH -> pixi -> pipx -> uvx. (pipx/uvx are version-on-demand, so they
# are reported as available even if not yet installed locally.)
sc_find_runner() {
  local repo="${1:-$PWD}"
  if command -v "$STYLE_BIN" >/dev/null 2>&1 && [ "$(sc_ver "$STYLE_BIN")" = "$STYLE_VERSION" ]; then
    printf 'PATH\t%s' "$STYLE_BIN"; return 0
  fi
  if command -v pixi >/dev/null 2>&1 && \
     [ "$(cd "$repo" && sc_ver pixi run "$STYLE_BIN" 2>/dev/null)" = "$STYLE_VERSION" ]; then
    printf 'pixi\tpixi run %s' "$STYLE_BIN"; return 0
  fi
  if command -v pipx >/dev/null 2>&1; then
    printf 'pipx\tpipx run %s==%s' "$STYLE_BIN" "$STYLE_VERSION"; return 0
  fi
  if command -v uvx >/dev/null 2>&1; then
    printf 'uvx\tuvx %s@%s' "$STYLE_BIN" "$STYLE_VERSION"; return 0
  fi
  return 1
}

# List in-scope files (repo-relative), honoring STYLE_FILE_GLOBS + STYLE_EXCLUDE_RE.
sc_files() {
  local repo="$1"
  git -C "$repo" ls-files "${STYLE_FILE_GLOBS[@]}" 2>/dev/null \
    | { [ -n "$STYLE_EXCLUDE_RE" ] && grep -vE "$STYLE_EXCLUDE_RE" || cat; } || true
}

# Count files that would change; print their names to stderr. Echo the count.
sc_diff_files() {
  local repo="$1" runner="$2" n=0 f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if ! style_diff_one "$runner" "$repo/$f"; then printf '  %s\n' "$f" >&2; n=$((n+1)); fi
  done < <(sc_files "$repo")
  printf '%s' "$n"
}

# Print a framed suggested commit message (subject + body lines passed as args after subject).
sc_commit_msg() {
  local subject="$1"; shift
  printf '%s\n' '----- suggested commit message -----'
  printf '%s\n\n' "$subject"
  printf '%s\n' "$@"
  printf '%s\n' '----- review, then commit yourself -----'
}

sc_doctor() {
  local repo found src runner
  repo="$(sc_repo "${1:-$PWD}")" 2>/dev/null || repo="$PWD"
  if found="$(sc_find_runner "$repo")"; then
    IFS=$'\t' read -r src runner <<<"$found"
    printf '%s runner: %s  (via %s)\n' "$STYLE_TOOL" "$runner" "$src"
    if [ "$src" = "pipx" ] || [ "$src" = "uvx" ]; then
      printf 'note: first run downloads %s %s on demand.\n' "$STYLE_BIN" "$STYLE_VERSION"
    fi
    return 0
  fi
  printf 'No %s %s runner found (checked PATH, pixi, pipx, uvx).\n' "$STYLE_BIN" "$STYLE_VERSION" >&2
  printf 'Provision with pixi (recommended):\n  cp %s ./pixi.toml && pixi run %s --version\n' \
    "$STYLE_PIXI_ASSET" "$STYLE_BIN" >&2
  printf 'Or: pipx run %s==%s   (or wire up the pre-commit hook: this-tool hook)\n' \
    "$STYLE_BIN" "$STYLE_VERSION" >&2
  return 1
}

# Require a clean working tree before a reformatting/config-adding action so
# each run yields exactly ONE clean commit. Untracked files ignored. Override
# with STYLE_ALLOW_DIRTY=1. Returns 3 on a dirty tree.
sc_require_clean_tree() {
  [ "${STYLE_ALLOW_DIRTY:-0}" = "1" ] && return 0
  local repo="$1" n
  n="$(git -C "$repo" status --porcelain --untracked-files=no 2>/dev/null | grep -cE '^([MDRC].| [MD])')"
  [ "${n:-0}" -eq 0 ] && return 0
  printf '[%s] ABORT: %s existing modified file(s) in the working tree.\n' "$STYLE_TOOL" "$n" >&2
  printf '[%s]   Each run must produce ONE clean commit. Commit or stash first, then re-run.\n' "$STYLE_TOOL" >&2
  printf '[%s]   Override (not recommended): STYLE_ALLOW_DIRTY=1.\n' "$STYLE_TOOL" >&2
  return 3
}

sc_check() {
  local repo; repo="$(sc_repo "${1:-$PWD}")"
  sc_primary_branch_report "$repo"
  local rc=0
  if style_has_config "$repo"; then
    printf '[check] %s: present, ITKv6 (%s)\n' "$(style_config_label)" "$STYLE_VERSION"
  else
    if declare -F style_status_note >/dev/null 2>&1; then
      printf '[check] %s\n' "$(style_status_note "$repo")"
    else
      printf '[check] %s: MISSING or not ITKv6 — run: add-config\n' "$(style_config_label)"
    fi
    rc=2
  fi
  local found src runner
  if found="$(sc_find_runner "$repo")"; then
    IFS=$'\t' read -r src runner <<<"$found"
    printf '[check] %s runner: %s (via %s)\n' "$STYLE_TOOL" "$runner" "$src"
    local n; n="$(sc_diff_files "$repo" "$runner")"
    if [ "$n" -eq 0 ]; then
      printf '[check] formatting: consistent (0 files would change)\n'
    else
      printf '[check] formatting: %s file(s) would change — run: run --apply (file list above)\n' "$n"; rc=2
    fi
  else
    printf '[check] %s %s: NOT available — run: doctor\n' "$STYLE_BIN" "$STYLE_VERSION"; rc=2
  fi
  return $rc
}

sc_run() {
  local apply=0 repo_arg=""
  while [ "$#" -gt 0 ]; do
    case "$1" in --apply) apply=1 ;; *) repo_arg="$1" ;; esac; shift
  done
  local repo; repo="$(sc_repo "${repo_arg:-$PWD}")"
  sc_primary_branch_report "$repo"
  style_has_config "$repo" || printf '[run] WARNING: no ITKv6 %s in repo; run add-config first.\n' "$(style_config_label)" >&2
  local found src runner
  found="$(sc_find_runner "$repo")" || sc_die "no $STYLE_BIN $STYLE_VERSION runner; run: doctor"
  IFS=$'\t' read -r src runner <<<"$found"
  if [ "$apply" -eq 0 ]; then
    printf '[run] DRY RUN (via %s). Files that would change:\n' "$src"
    local n; n="$(sc_diff_files "$repo" "$runner")"
    printf '[run] %s file(s) would change. Re-run with --apply to reformat.\n' "$n"
    [ "$n" -eq 0 ] && return 0 || return 2
  fi
  sc_require_clean_tree "$repo" || return 3
  local changed=() f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if ! style_diff_one "$runner" "$repo/$f"; then style_apply_one "$runner" "$repo/$f" && changed+=("$f"); fi
  done < <(sc_files "$repo")
  if [ "${#changed[@]}" -eq 0 ]; then printf '[run] already consistent; nothing changed.\n'; return 0; fi
  git -C "$repo" add -- "${changed[@]}"
  printf '[run] reformatted and staged %s file(s) (via %s).\n' "${#changed[@]}" "$src"
  sc_commit_msg "STYLE: Apply ITKv6 $STYLE_TOOL ($STYLE_BIN $STYLE_VERSION)" \
    "Reformat to the ITKv6 $STYLE_TOOL style for consistency with ITK." \
    "No functional changes."
}

sc_hook() {
  local repo; repo="$(sc_repo "${1:-$PWD}")" 2>/dev/null || repo=""
  printf '# Add the following to %s/.pre-commit-config.yaml (merge the repos: list):\n\n' "${repo:-<repo>}"
  cat "$STYLE_HOOK_ASSET"
  printf '\nThen:  pre-commit install && pre-commit run %s --all-files\n' "$STYLE_BIN"
}

sc_main() {
  local sub="${1:-help}"; shift || true
  # Strip global base-check flags from anywhere in the args.
  local _a; local _args=()
  for _a in "$@"; do
    case "$_a" in
      --no-fetch) STYLE_NO_FETCH=1 ;;
      --no-base-check) STYLE_NO_BASE_CHECK=1 ;;
      --allow-dirty) STYLE_ALLOW_DIRTY=1 ;;
      *) _args+=("$_a") ;;
    esac
  done
  set -- "${_args[@]+"${_args[@]}"}"
  case "$sub" in
    doctor)     sc_doctor "$@" ;;
    check)      sc_check "$@" ;;
    add-config) style_add_config "$@" ;;
    run)        sc_run "$@" ;;
    hook)       sc_hook "$@" ;;
    *) cat <<EOF
$(basename "$0") — align a project with the ITKv6 $STYLE_TOOL style ($STYLE_BIN $STYLE_VERSION)
  doctor                  find a $STYLE_BIN $STYLE_VERSION runner (PATH/pixi/pipx/uvx)
  check [repo]            diagnose config + formatting drift
  add-config [repo]       add + stage the ITKv6 $STYLE_TOOL config ($(style_config_label))
  run [--apply] [repo]    dry-run diff (default) or reformat + stage
  hook [repo]             print the ITKv6 pre-commit hook snippet
check/run report the checkout vs the primary branch (origin/HEAD), fetching it
first by default. run/add-config refuse a dirty working tree so each yields one
clean commit. Flags: --no-fetch (skip the fetch), --no-base-check (skip the
report), --allow-dirty (skip the clean-tree check). Never commits, branches,
or opens PRs.
EOF
       ;;
  esac
}
