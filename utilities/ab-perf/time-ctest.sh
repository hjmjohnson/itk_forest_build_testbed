#!/usr/bin/env bash
# time-ctest.sh — repeated serial ctest timing for one build tree.
#
# Captures per-test wall times across N serial repeats, plus a one-shot
# correctness (pass/fail) run, and writes raw samples + a stats summary
# (n, min, median, mean, stdev, CV%). Designed for A/B comparison of one
# consumer built against two different dependency versions (see ab-run.sh).
#
# Usage: time-ctest.sh <build-dir> <label> <out-dir> <repeats> <ctest-name-regex>
#
# Methodology notes (read utilities/ab-perf/README.md):
#   * Serial (-j1) so each test's wall time is its own, not contended by siblings.
#   * min  = least-contended sample; median/CV characterize run-to-run noise.
#   * On a shared / nice!=0 host these are INDICATOR results — CV often exceeds
#     the effect being measured. Treat large-CV tests as inconclusive.
set -uo pipefail
[ $# -eq 5 ] || { echo "usage: $0 <build-dir> <label> <out-dir> <repeats> <regex>" >&2; exit 64; }
AB="$1"; LABEL="$2"; OUT="$3"; REP="$4"; RE="$5"
mkdir -p "$OUT"; cd "$AB" || { echo "no build dir: $AB" >&2; exit 2; }

# Record the runtime environment that affects timing (host, load, niceness).
{ echo "label=$LABEL"; echo "build=$AB"; echo "regex=$RE"; echo "repeats=$REP"
  echo "host=$(uname -n)"; echo "nproc=$(nproc 2>/dev/null)"
  echo "niceness=$(ps -o ni= -p $$ | tr -d ' ')"
  echo "loadavg=$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null)"
} > "$OUT/${LABEL}_env.txt"

# 1) One-shot correctness run (pass/fail capture).
ctest -j1 --timeout 1800 -R "$RE" > "$OUT/${LABEL}_full.log" 2>&1
echo "[correctness run done: $LABEL]"

# 2) Repeated serial timing.
: > "$OUT/${LABEL}_samples.tsv"
for i in $(seq 1 "$REP"); do
  ctest -j1 --timeout 1800 -R "$RE" 2>&1 \
    | grep -E 'Test +#[0-9]+:' \
    | sed -E "s/.*Test +#[0-9]+: +([A-Za-z0-9_.-]+) +\.+ +(Passed|\*\*\*[A-Za-z ]+) +([0-9.]+) sec.*/${i}\t\1\t\3/" \
    >> "$OUT/${LABEL}_samples.tsv"
  echo "[repeat $i/$REP done: $LABEL]"
done

# 3) Stats per test (only tests that produced a numeric time).
python3 - "$OUT/${LABEL}_samples.tsv" > "$OUT/${LABEL}_summary.tsv" <<'PY'
import sys, statistics as st
from collections import defaultdict
d=defaultdict(list)
for ln in open(sys.argv[1]):
    p=ln.rstrip("\n").split("\t")
    if len(p)!=3: continue
    try: d[p[1]].append(float(p[2]))
    except ValueError: continue
print("test\tn\tmin\tmedian\tmean\tstdev\tcv_pct")
for t in sorted(d):
    v=d[t]; mn=min(v); md=st.median(v); me=sum(v)/len(v)
    sd=st.pstdev(v) if len(v)>1 else 0.0
    cv=100*sd/me if me else 0.0
    print(f"{t}\t{len(v)}\t{mn:.2f}\t{md:.2f}\t{me:.2f}\t{sd:.2f}\t{cv:.1f}")
PY
echo "[summary: $OUT/${LABEL}_summary.tsv]"
