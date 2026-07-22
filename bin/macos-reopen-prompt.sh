#!/usr/bin/env bash
# Suppress (or restore) the macOS "unexpectedly quit while reopening windows"
# dialog for the Slicer builds this forest produces.
#
#   bash bin/macos-reopen-prompt.sh status     # what is set right now
#   bash bin/macos-reopen-prompt.sh suppress   # stop the dialog appearing
#   bash bin/macos-reopen-prompt.sh restore    # back to macOS default
#
#   --global   also apply to NSGlobalDomain (EVERY app, not just Slicer)
#
# WHY
# ---
# Slicer extension tests launch Slicer.app. When one crashes, macOS records the
# crash and puts up a MODAL dialog on the next launch asking whether to reopen
# windows. It blocks that launch until a human dismisses it, so an unattended
# sweep of 253 extensions can wedge the machine behind a stack of dialogs.
#
# `ApplePersistenceIgnoreState = YES` tells Cocoa to ignore saved window state,
# which is what the dialog exists to offer -- so the prompt stops appearing.
# Note the polarity: YES = ignore restore state = NO dialog.
#
# SCOPE
# -----
# Default scope is Slicer's bundle id ONLY. This is deliberate: the global
# domain changes window-restore behaviour for every Cocoa app the user runs,
# which is a real change to their machine and well beyond what a build sweep
# needs. Use --global only with intent.
#
# This does NOT prevent crashes and does NOT suppress crash reports; the .ips
# files in ~/Library/Logs/DiagnosticReports still record every one. It only
# stops the modal prompt from blocking automation.
set -uo pipefail

KEY=ApplePersistenceIgnoreState
APP_DOMAIN="${SLICER_BUNDLE_ID:-org.slicer.slicer}"

action=""
use_global=0
for a in "$@"; do
  case "$a" in
    status|suppress|restore) action="$a" ;;
    --global) use_global=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done
[ -n "${action}" ] || { sed -n '2,10p' "$0"; exit 2; }

domains=("${APP_DOMAIN}")
[ "${use_global}" = 1 ] && domains+=("NSGlobalDomain")

show(){
  local d="$1" v
  if [ "${d}" = NSGlobalDomain ]; then
    v="$(defaults read -g "${KEY}" 2>/dev/null)" || v="<unset (macOS default: prompt shown)>"
  else
    v="$(defaults read "${d}" "${KEY}" 2>/dev/null)" || v="<unset (macOS default: prompt shown)>"
  fi
  printf '  %-22s %s = %s\n' "${d}" "${KEY}" "${v}"
}

case "${action}" in
  status)
    echo "Current ${KEY}:"
    show "${APP_DOMAIN}"
    show NSGlobalDomain
    echo
    echo "  YES = saved window state ignored -> reopen dialog suppressed"
    ;;
  suppress)
    for d in "${domains[@]}"; do
      if [ "${d}" = NSGlobalDomain ]; then
        defaults write -g "${KEY}" -bool YES
      else
        defaults write "${d}" "${KEY}" -bool YES
      fi
      echo "suppressed: ${d}"
    done
    echo "Reopen dialog will no longer appear for the above."
    ;;
  restore)
    # `delete` returns to the macOS default rather than writing NO, so the
    # setting disappears entirely instead of leaving a stale explicit value.
    for d in "${domains[@]}"; do
      if [ "${d}" = NSGlobalDomain ]; then
        defaults delete -g "${KEY}" 2>/dev/null && echo "restored: ${d}" || echo "already default: ${d}"
      else
        defaults delete "${d}" "${KEY}" 2>/dev/null && echo "restored: ${d}" || echo "already default: ${d}"
      fi
    done
    ;;
esac
