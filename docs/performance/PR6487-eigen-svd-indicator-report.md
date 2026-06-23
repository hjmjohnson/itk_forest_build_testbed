# ITK PR #6487 (Eigen-backed `itk::Math::SVD`) — downstream indicator report

> **STATUS: INDICATOR RESULTS, NOT A RIGOROUS EXPERIMENT.**
> All measurements were taken on a **shared, multi-tenant host** with the test
> processes running at **`nice=5`** (de-prioritized). Wall-times are inflated and
> carry large run-to-run variance (CV ≈ 12–25% on heavy tests). The A/B framing
> cancels *systematic* bias (both sides equally throttled) but **not** random
> contention. Use these numbers as directional indicators and a methodology
> template — not as publishable measurements. See "Making this rigorous" below.

White-paper source resource. Raw data: `./PR6487-eigen-svd-data/`. Reusable
harness: `../../utilities/ab-perf/`.

---

## 1. TL;DR

- **Correctness: no regressions** in any consumer. BRAINSFit **37/37 pass** on
  both ITK `main` and ITK #6487; BCD+GTRACT identical pass/fail; ANTs registration
  shows only pre-existing/flaky failures that occur on stock `main` too.
- **Performance: no change detectable above the measurement noise.** Every
  SVD-relevant per-test delta is smaller than that test's run-to-run CV. The
  BRAINSFit BSpline (deformable) tests *trend* faster on #6487 (median −6% to −14%)
  but do not clear the noise floor; the ANTs SyN tests are flat-to-noisy.
- **Caveat that bounds the whole study: zero downstream code was changed.**
  Neither ANTs nor BRAINSTools was modified to call the new `itk::Math::SVD`
  interface. They are affected only **transitively**, through ITK-internal call
  sites that the PR rerouted. The larger gains available from *direct* adoption of
  the new Eigen-backed interfaces are **unlocked but currently unimplemented.**

## 2. The change under test

PR #6487 adds `itk::Math::SVD` (Eigen-backed) and migrates ITK's own `vnl_svd`
consumers to it. Migrated call sites (level-0):

| ITK method rerouted to `itk::Math::SVD` | Frequency in a run |
|---|---|
| `KernelTransform::ComputeWMatrix` (TPS/elastic spline fit) | once per transform fit |
| `DisplacementFieldTransform::GetInverseJacobian…` | **per-point, per-iteration** (hot) |
| `BSplineScatteredDataPointSetToImageFilter` / `…ControlPointImageFilter` (lattice LSQ) | filter setup |
| `Rigid2DTransform` matrix orthogonalization | once (2D only) |
| `NiftiImageIO::SetImageIOOrientation…` | once per image read |
| `FEMLinearSystemWrapperDenseVNL::Solve` | per FEM solve |

**Clean isolation:** the PR's merge-base **is** the baseline tip
(`fb2e7fc907`), so the only difference between forests is the 7 PR commits.

| Forest | ITK | ANTs | BRAINSTools |
|---|---|---|---|
| baseline `build_forest-itkv6_main` | `fb2e7fc907` (main) | `d2fbf8bd` | `ff4c121a` |
| PR `build_forest-pr6487` | `56121749a8` (pr/6487) | `d2fbf8bd` (identical) | `ff4c121a` (identical) |

Consumer source byte-identical across forests; both ITKs configured identically
(`ITKVtkGlue` ON, `Module_ITKIODCMTK` ON, PR forest reuses the baseline VTK).

## 3. Transitive impact — which downstream modules touch the migrated code

A direct-symbol grep undercounts; what matters is whether a consumer calls an ITK
API whose *internals* changed.

**ANTs** (heavy transitive user):
- `itkantsRegistrationHelper` (core of `antsRegistration`), `antsMotionCorr`,
  `antsSliceRegularizedRegistration` → `DisplacementFieldTransform` (SyN). **HOT.**
- `N4`/`N3BiasFieldCorrection`, `FitBSplineToPoints`, `antsAtroposSegmentation`,
  point-set registration → `BSplineScatteredData` (setup-time, cooler).

**BRAINSTools:**
- **`BRAINSFit`** (`BRAINSFitHelperTemplate` drives SyN 12×, `DisplacementFieldTransform`
  8×, `BSplineTransform`) → the SVD-hot module, analogous to `antsRegistration`.
- `BRAINSConstellationDetector` (`BRAINSLmkTransform` → TPS `KernelTransform`),
  `BRAINSLandmarkInitializer` → `ComputeWMatrix`.
- GTRACT `gtractResampleDWIInPlace` → `DisplacementFieldTransform` (cool: I/O-dominated).
- **Not** an N4/`BSplineScatteredData` user — BRAINSTools uses its own `LLSBiasCorrector`.

**Test-selection consequence:** the SVD-hot downstream paths are the **deformable
registration** tests (`antsRegistration` SyN, `BRAINSFit` BSpline). Linear
affine/rigid 3D tests and BCD/GTRACT exercise the migrated code little or not at
all, so flat results there are expected and uninformative.

## 4. Methodology

Serial `ctest -j1` over the test subset, N repeats (5 for ANTs SyN / BCD+GTRACT,
3 for the longer expanded ANTs and BRAINSFit sets), machine otherwise idle,
strictly sequential runs. Per test we report median and **CV** (run-to-run
coefficient of variation). A delta is called *real* only if it exceeds the test's
CV; otherwise **inconclusive**. Harness: `utilities/ab-perf/`.

## 5. Correctness results (robust)

| Consumer / subset | baseline | PR #6487 | regressions |
|---|---|---|---|
| BRAINSFit (37 tests) | 37/37 pass | 37/37 pass | **none** |
| BRAINSTools BCD+GTRACT (20) | 18/20 | 18/20 | **none** (same 2 DICOM-fixture fails) |
| ANTs registration (35) | 30/35 | 31/35 | **none** (PR had one *fewer* flaky fail) |

**Excluded from timing (failed/not-run identically on both ITK main and #6487 —
hence not regressions), in one enumerated sentence:** (1) `ANTS_SYN_WITH_TIME[_WARP]`
— pre-existing failure on stock ITK main, unrelated to the PR; (2)
`GTRACTTest_gtractConcatDwi_Concat_Dicom[_multi]` — missing DICOM test fixtures;
(3) `antsRegistrationTest_{MSEAffine,Similarity}RotationMasks` — flaky near-threshold
mask-registration checks that flip run-to-run on both sides; (4)
`antsRegistrationTest_initializePerStage_ComparisonTesting` — *Not Run* (depends on a
skipped producer test).

## 6. Performance results (indicator only — noise-dominated)

Median seconds; Δ% = PR vs baseline (negative = faster); maxCV = larger of the two
sides' run-to-run CV. **Δ smaller than maxCV ⇒ inconclusive.**

### ANTs — deformable (SVD-hot), pooled n≈8
| test | base | PR | Δ% | maxCV | verdict |
|---|---|---|---|---|---|
| ANTS_ROT_GSYN (greedy SyN) | 13.17 | 13.52 | +2.7% | 16.5% | inconclusive |
| ANTS_ROT_EXP (elastic) | 7.15 | 7.71 | +7.9% | 19.4% | inconclusive |
| antsRegistrationTest_SyNScaleNoMasks | 1.70 | 1.70 | 0.0% | 1.3% | inconclusive |

*(The previously-reported "−5–6% ANTs speedup" was an artifact of comparing
min-of-5 across these noisy distributions; the pooled samples are near-identical,
both means ≈13.7 s for GSYN.)*

### BRAINSFit — BSpline deformable (SVD-hot), n=3
| test | base | PR | Δ% | maxCV | verdict |
|---|---|---|---|---|---|
| BRAINSFitTest_BSplineOnlyRescaleHeadMasks | 76.18 | 71.75 | −5.8% | 12.2% | inconclusive |
| BRAINSFitTest_BSplineAnteScaleRotationRescaleHeadMasks | 5.26 | 4.50 | −14.4% | 15.6% | inconclusive |
| BRAINSFitTest_BSplineScaleRotationRescaleHeadMasks | 3.67 | 3.64 | −0.8% | 14.9% | inconclusive |

*(BSpline tests trend faster on #6487 — directionally consistent with Eigen SVD
helping the hot `DisplacementFieldTransform` path — but every delta is inside the
noise band. Suggestive, not established.)*

### Cool paths (expected flat) — ANTs linear & BRAINSTools BCD/GTRACT
All deltas ≤ ~2% and inconclusive (e.g. `BRAINSAlignMSP` −0.1%, `gtractResampleDWIInPlace`
−0.8%, ANTs affine/rigid within ±2%). Consistent with these tests not exercising
the migrated SVD on a hot path.

## 7. Interpretation

1. **No correctness regression** from the `vnl_svd → Eigen` migration in any
   exercised downstream path. This is the solid, reproducible result.
2. **No performance change resolvable at this fidelity.** On a `nice=5` shared
   host the heavy-test CV (12–25%) dwarfs any plausible single-digit-percent SVD
   effect. The BRAINSFit BSpline faster-trend is the most suggestive signal but is
   not above noise.
3. **Gains are unlocked, not implemented.** Because no downstream code adopts
   `itk::Math::SVD` directly, only ITK-internal transitive call sites benefit. A
   follow-up that ports ANTs/BRAINSTools hot loops to the new interface is where a
   measurable downstream win, if any, would appear.

## 8. Making this rigorous (for the white paper's headline numbers)

Re-run on a **dedicated, quiesced host**: `nice=0`, no concurrent load, cores
pinned (`taskset`/`numactl`), CPU governor = performance, **n ≥ 20** repeats, and
report a paired test (e.g. Wilcoxon) per test plus bootstrap CIs. Focus the
deformable SVD-hot subset: `ANTS_ROT_GSYN|ANTS_ROT_EXP`, `BRAINSFitTest_BSpline*`.
Drive it with:

```bash
utilities/ab-perf/ab-run.sh ANTs 'ANTS_ROT_GSYN|ANTS_ROT_EXP' \
    build_forest-itkv6_main build_forest-pr6487 20
utilities/ab-perf/ab-run.sh BRAINSTools 'BRAINSFitTest_BSpline' \
    build_forest-itkv6_main build_forest-pr6487 20
```

## 9. Data artifacts

`./PR6487-eigen-svd-data/` — for each run label `{ants2,bfit,bt,…}_{itkmain,pr6487}`:
`*_samples.tsv` (raw per-repeat times), `*_summary.tsv` (stats), `*_full.log`
(ctest pass/fail), `*_env.txt` (host/niceness/loadavg at run time). Re-derive any
table with `utilities/ab-perf/ab-compare.py`.
