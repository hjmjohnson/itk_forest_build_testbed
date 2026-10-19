#!/usr/bin/env bash
# Rerun the tests of unconverted modules several times in one build and report,
# for each given file:line, in how many runs it was covered. Lines covered in
# some runs and not others vary between runs and cannot be attributed to the
# conversion.
# Usage: rerun_variability.sh <build> <src> <out> <runs> <label-regex> <driver>... -- <file:line>...
set -euo pipefail
bld=$1; src=$2; out=$3; runs=$4; labels=$5; shift 5
drivers=(); while [ "$1" != "--" ]; do drivers+=("$1"); shift; done; shift
targets=("$@")
xc=/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin
rm -rf "${out}"; mkdir -p "${out}"
for r in $(seq 1 "${runs}"); do
  d="${out}/run${r}"; mkdir -p "${d}"
  LLVM_PROFILE_FILE="${d}/%p.profraw" ctest --test-dir "${bld}" -j6 -L "${labels}" -E KWStyle > "${d}/ctest.log" 2>&1 || true
  for drv in "${drivers[@]}"; do
    raws=()
    for f in "${d}"/*.profraw; do raws+=("$f"); done
    "${xc}/llvm-profdata" merge -sparse "${raws[@]}" -o "${d}/merged.profdata" 2>/dev/null
    "${xc}/llvm-cov" export -format=lcov -instr-profile "${d}/merged.profdata" "${bld}/bin/${drv}" \
      -ignore-filename-regex='(/ThirdParty/|/_deps/|-build/)' > "${d}/${drv}.lcov" 2>/dev/null || true
  done
  rm -f "${d}"/*.profraw
  grep -E "tests passed" "${d}/ctest.log" | sed "s/^/run ${r}: /"
done
python3 - "${out}" "${runs}" "${src}" "${targets[@]}" <<'EOF'
import sys
from pathlib import Path
out, runs, src, targets = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3].rstrip("/") + "/", sys.argv[4:]
want = {}
for t in targets:
    f, l = t.rsplit(":", 1)
    want.setdefault(f, set()).add(int(l))
for f in sorted(want):
    for l in sorted(want[f]):
        hits = 0
        for r in range(1, runs + 1):
            covered = False
            for lc in (out / f"run{r}").glob("*.lcov"):
                cur = None
                for line in lc.open():
                    if line.startswith("SF:"):
                        cur = line[3:].strip()
                    elif cur == src + f and line.startswith(f"DA:{l},"):
                        covered |= int(line.split(",")[1]) > 0
            hits += covered
        print(f"{f}:{l} covered in {hits}/{runs} runs")
EOF
