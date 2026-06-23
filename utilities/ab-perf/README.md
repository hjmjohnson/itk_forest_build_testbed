# A/B performance + correctness testing utilities

Reusable harness for asking: **"does dependency change X regress or speed up its
downstream consumers?"** — built for this testbed's forest layout, where one
consumer (ANTs, BRAINSTools, …) is built against two variants of a dependency
(e.g. ITK `main` vs an ITK PR).

## Scripts

| Script | Role |
|---|---|
| `time-ctest.sh` | Time one build tree: repeated serial `ctest`, raw samples + stats (min/median/mean/stdev/CV) + a correctness run. |
| `ab-compare.py` | Diff two summaries with a **noise-aware verdict** (flags `inconclusive` when Δ < CV). |
| `ab-run.sh` | End-to-end driver: locate the consumer's ctest tree in each forest, time both, compare. |

```bash
# Both forests must already be built. Then:
utilities/ab-perf/ab-run.sh ANTs 'ANTS_ROT|ANTS_SYN' \
    build_forest-itkv6_main build_forest-pr6487 5
```

## Methodology (and its limits)

1. **Clean isolation.** The consumer *source* must be byte-identical in both
   forests; only the dependency under test may differ. Best case: the PR's
   merge-base equals the baseline tip, so the diff is exactly the PR commits.
   Verify with `git -C <forest>/<consumer> rev-parse HEAD` on both sides.
2. **Identical dependency config.** Configure the dependency the same way in
   both forests (same enabled modules). In this testbed the PR forest reuses the
   baseline's VTK via `ITK_VTK_DIR=<baseline>/VTK-build` so ITKVtkGlue/testing
   flags match.
3. **Serial timing (`-j1`).** Each test's wall time is its own, not contended by
   parallel siblings. `min` = least-contended sample; `median`/`CV` quantify noise.
4. **Repeats.** ≥5 recommended; more for high-variance (deformable registration)
   tests. Re-running is cheap once built.

### ⚠ Indicator vs rigorous results
On a **shared host** and/or with a non-zero **niceness** (this testbed's agent
runs at `nice=5`), wall times are inflated and carry large run-to-run variance
from background contention. The A/B comparison cancels *systematic* effects
(both sides equally de-prioritized) but **not** random contention. In practice
heavy tests can show CV ≈ 15–25%, which swamps a single-digit-percent effect.

**Treat results from such a host as INDICATOR results, not rigorous
measurements.** `ab-compare.py` enforces this by flagging any per-test delta
smaller than the pooled CV as `inconclusive`, and aggregating only the
low-noise (CV<8%) subset. For a publishable measurement, re-run on a quiesced,
dedicated host: `nice=0`, no concurrent load, cores pinned (`taskset`/`numactl`),
n≥20.

### Interpreting "no change" for a dependency-internal change
A dependency change may only alter the consumer's behavior **transitively** —
i.e. the consumer calls a dependency API whose *internals* changed, without the
consumer itself being modified. If the consumer was **not** updated to adopt a
new/faster interface directly, any speedup is limited to what the dependency's
internal use unlocks; the larger gains from direct adoption are **unlocked but
unimplemented**. Note this explicitly when reporting, and check whether the
changed code is on the consumer's hot path (a transitive-usage grep, not just a
direct-symbol grep) before concluding a test subset is representative.

## Output layout
`<out-dir>/<label>_{env.txt,full.log,samples.tsv,summary.tsv}` — env captures
host/niceness/loadavg at run time; keep it with the numbers.
