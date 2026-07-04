#!/usr/bin/env bash
# Peak-RSS measuring launcher, usable as a CTest TEST_LAUNCHER (CMake >=3.29)
# or standalone:  RSS_CSV=peaks.csv measure-test-rss.sh <command> [args...]
#
# Polls the launched process tree via `ps` (portable: macOS BSD + Linux GNU),
# tracks peak summed RSS, appends "<name>,<peakMB>,<exit>" to $RSS_CSV, then
# exits with the child's exit code. No /usr/bin/time dependency.
set -u

RSS_CSV="${RSS_CSV:-ctest-rss.csv}"
RSS_INTERVAL="${RSS_INTERVAL:-0.2}"

if [ "$#" -lt 1 ]; then
  echo "usage: RSS_CSV=peaks.csv $0 <command> [args...]" >&2
  exit 2
fi

# Test label: CTest passes the real command; use basename of the executable.
RSS_NAME="${RSS_NAME:-$(basename "$1")}"

"$@" &
child=$!

# Sum RSS (KB) of $child and all transitive descendants.
sum_tree_rss_kb() {
  local root=$1
  ps -A -o pid=,ppid=,rss= 2>/dev/null | awk -v root="$root" '
    { pid[$1]=1; ppid[$1]=$2; rss[$1]=$3 }
    END {
      desc[root]=1
      # iterate to closure: mark any pid whose parent is already marked
      changed=1
      while (changed) {
        changed=0
        for (p in ppid) if (!(p in desc) && (ppid[p] in desc)) { desc[p]=1; changed=1 }
      }
      total=0
      for (p in desc) if (p in rss) total+=rss[p]
      print total
    }'
}

peak_kb=0
while kill -0 "$child" 2>/dev/null; do
  cur=$(sum_tree_rss_kb "$child")
  [ -n "$cur" ] && [ "$cur" -gt "$peak_kb" ] && peak_kb=$cur
  sleep "$RSS_INTERVAL"
done
wait "$child"
status=$?

peak_mb=$(( peak_kb / 1024 ))
# Single short line (<512 bytes) -> append is atomic on POSIX even under -j.
printf '%s,%s,%s\n' "$RSS_NAME" "$peak_mb" "$status" >> "$RSS_CSV"

exit "$status"
