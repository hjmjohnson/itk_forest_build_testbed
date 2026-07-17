# Cross-project analysis: an eight-year-old baseline that encoded a wrong answer

**Date:** 2026-07-17
**Found by:** ITK downstream build testbed (`hjmjohnson/itk_forest_build_testbed`)
**Projects spanned:** ITK → BRAINSTools
**Status:** root-caused; **not an ITK defect** — action is downstream baseline regeneration

## One-line summary

ITK PR #6569 (merged 2026-07-16) corrected two coupled bugs in
`JointHistogramMutualInformationImageToImageMetricv4`; BRAINSTools' MIH regression
baselines were generated in 2018 against the *buggy* metric, so they now fail —
by being compared against a snapshot of a wrong answer.

## Why it is interesting

This is the **inverse** of the `sampleIO.c` finding from the same run
(`2026-07-17-nrrdio-main-collision.md`). There, a green suite was silently wrong.
Here, a red suite is correctly reporting that an intentional upstream correction
changed the answer — and the *test is right to fire*.

The two together make the point that "tests passed" and "tests failed" are both
uninterpretable without knowing what the test measures:

| | NrrdIO finding | JHMI finding (this doc) |
|---|---|---|
| suite says | **green** | **red** |
| reality | 17 tests silently absent | upstream fix working as intended |
| correct action | fix the library | regenerate the baseline |

## Discovery path

1. BRAINSTools `767ba471` built against ITK `release-5.4` (5.4.6) and ITK `main`
   (6.0.0); same ANTs, same ctest invocation. **ITK the only variable.**
2. Exactly two tests differed: `BRAINSFitTest_MIHAffineRotationMasks` and
   `BRAINSFitTest_MIHScaleSkewVersorRotationMasks`. v5 10/10 pass, v6 0/10 —
   deterministic, so not the flake class that bit the sibling ANTs test.
3. **"Masks" is not the discriminator** — `AffineRotationMasks`,
   `MSEAffineRotationMasks`, `NCAffineRotationMasks`, `RigidRotationMasks` all pass
   on v6. Masks are fine.
4. **The metric is.** Both failures pass `--costMetric MIH`, across two different
   transform types (Affine *and* ScaleSkewVersor). `MIH` →
   `itk::JointHistogramMutualInformationImageToImageMetricv4`
   (`BRAINSCommonLib/BRAINSFitHelper.cxx:412-420`), 200 histogram bins.
5. `git log v5.4.6..upstream/main -- '*JointHistogramMutualInformation*'` puts two
   `BUG:` commits against that exact class at the top of the log.

## Root cause

**ITK PR #6569** — "BUG: Fix JointHistogramMutualInformation metric marginals and
derivative", by `physwkim` (Sang Woo Kim), merged **2026-07-16T11:40:41Z**.

| commit | author | date | effect |
|---|---|---|---|
| `da915f91578` | Sang Woo Kim | 2026-07-09 | marginal pairing + MI gradient |
| `3ddebbf1d94` | Hans J. Johnson | 2026-07-09 | derivative scaled by moving-intensity normalization |
| `6a6d15a57cf` | | | remove dead helper |
| `73a9b1d644a` | | | **enforce test checks, verify the derivative** |

None are in `release-5.4`; all are in `main`. That is the entire v5/v6 split.

### Two independent bugs, not one

1. **Wrong objective.** `ComputeJointPDFPoint()` indexes the joint PDF as
   `(fixed bin, moving bin)`, but each marginal was stored in the *other* array.
   `GetValue()` therefore divided `p(a,b)` by `p_moving(a)·p_fixed(b)` — not
   mutual information. PR #6569 proves this algebraically: `GetValue()` on old ITK
   matches the swapped pairing to 12 significant digits.
2. **Gradient inconsistent with that objective too.** The scaling factor
   `log(2)*dMmPDF*J/Pm - dJPDF*(log J - log Pm)` "is not the differential of any MI
   estimate" — wrong sign on the marginal term, joint term weighted by a log ratio
   instead of `1/J`.

So the optimizer was not minimizing MI, and was not following the gradient of the
thing it *was* minimizing either.

### Why it survived ~8 years

ITK's only numeric registration test of this metric
(`itkImageToImageMetricv4RegistrationTest2`) registers an image against **a cyclic
shift of itself**, so `p_fixed ≈ p_moving` and swapping the marginals is a no-op.
The bug was undetectable by that test's data *by construction*.

BRAINSFit registers a real brain with masks — genuinely asymmetric marginals — so
the bug was live there the whole time, frozen into the baseline.

## Proof (measured 2026-07-17, in `build_forest-itk-main`)

### 1. Causation — decisive

Reverting **only** `da915f91578` + `3ddebbf1d94` on ITK v6 (three header files;
they touch zero test files) and rebuilding:

```
BRAINSFitTest_MIHAffineRotationMasks ............ Passed
BRAINSFitTest_MIHScaleSkewVersorRotationMasks ... Passed
100% tests passed
```

Nothing else changed. PR #6569 is the cause.

### 2. Correctness — mathematical, baseline-independent

`73a9b1d644a` added a derivative-vs-finite-difference check. Run **main's test
against the reverted (old) metric math**:

```
Analytic derivative disagrees with finite difference of the value:
  analytic[0]:                -0.000731416
  central finite difference:   0.270065
```

Wrong **sign**; **~369x** too small. A correct derivative must equal the finite
difference of its own value function. The corrected metric passes this test (ITK's
5 JHMI tests: 5/5 on v6).

This — not the image comparison — is the definitive proof. It involves no baseline.

### 3. Accuracy — supporting, and honestly thin

Ground truth: `test.nii.gz` (fixed) and `rotation.test.nii.gz` (moving) are the
same 64³ brain, intensity-histogram correlation **0.9999**. A perfect registration
resamples moving onto fixed and reproduces it. MSE shares no machinery with MI and
was untouched by #6569; because the content is identical, the true alignment
optimizes both at the same place, so MSE can adjudicate MI here.

MSE vs the fixed image, in-mask (21084 of 262144 voxels):

| result | MSE |
|---|---|
| moving, unregistered | 1016.288 |
| stored 2018 baseline | 55.721 |
| OLD metric | 55.898 |
| **NEW metric** | **54.792** |

The corrected metric is closer to truth than the old metric **and than the baseline
it is failed against**. NCC agrees (0.91374 vs 0.91001).

**Caveat, stated rather than smoothed:** the margin is **2%**, and *whole-image*
MSE is 2% **worse** for the new result (110.399 vs 107.930). Whole-image is
arguably not a fair referee — `--maskProcessingMode ROI` means the registration
only ever optimized in-mask — but 2% is not proof either way. The margin is small
because the wrong objective was strongly *correlated* with the right one; both land
near the true optimum. Rely on §2, not §3.

`MSE(baseline, old_result) = 0.1100` confirms the baseline is the old metric's
answer, reproduced almost exactly. `MSE(baseline, new_result) = 0.4421`.

### 4. Mechanism — why the old code registered well but sub-optimally

The wrong objective still correlates with alignment, and the line search accepts
steps on *value*, so registration improved 1016 → 55.9 regardless. But a
wrong-signed search direction plateaus early, and the convergence checker calls it:

| | ITK 5.4.6 | ITK 6.0.0 |
|---|---|---|
| convergence | iteration **11** | iteration **17** |
| in-mask MSE | 55.898 | 54.792 |

Six more iterations of real optimization. The old run did not converge to a worse
optimum so much as **stop early on a bad direction** — sub-optimal, not broken.
That is why it looked fine for eight years.

## The test was doing its job

`BRAINSFitTest_MIH*` is a **regression** test: `--compare` against a recorded
snapshot with `--compareIntensityTolerance 7` and
`--compareNumberOfPixelsTolerance 777`. It answers *"does this still equal what I
recorded?"* — it cannot answer *"is this better?"*, and was never built to.

Its failure is the test **working**. Measured `ImageError = 1756` against a 777
tolerance = **2.26x the band** the authors considered acceptable drift; that ratio
is what justified investigating rather than dismissing it as float noise.

The instrument that *can* adjudicate is the finite-difference check `73a9b1d644a`
added. #6569 did not only fix the math — it upgraded the test from regression to
verification, which is why the bug died the moment the right instrument existed.

## Action: regenerate the BRAINSTools baselines

```
TestData/BRAINSFitTest_MIHAffineRotationMasks.result.nii.gz.sha512
  last touched: 2018-11-24 (Hans Johnson, "ENH: Update reference data to sha512 on new data source.")
```

For a regression test, the snapshot **is** the spec — and this spec is now
known-false. Regenerating is the correct action, not a workaround.

**ITK reached the identical conclusion for its own tests.** PR #6569's body:

> `itkSimpleImageRegistrationTest{Float,Double}` baselines encode the old metric's
> output and need regeneration — @hjmjohnson has offered to push regenerated `.cid`
> links to this branch.

BRAINSTools is the same situation, one repo downstream, unnoticed because its CI
runs on ITK v5 where the fix is absent.

**Nothing to fix in ITK.** Both affected baselines:

- `BRAINSFitTest_MIHAffineRotationMasks.result.nii.gz`
- `BRAINSFitTest_MIHScaleSkewVersorRotationMasks.result.nii.gz`

Not yet regenerated as of this writing — regenerating committed reference data is a
real change and is gated on human authorization.

## Verification log

| claim | evidence |
|---|---|
| MIH → JHMI metric | `BRAINSFitHelper.cxx:412-420`, `--costMetric MIH` |
| masks are not the cause | `AffineRotationMasks`, `MSE*`, `NC*`, `Rigid*Masks` all pass on v6 |
| fixes absent from 5.4 | `git merge-base --is-ancestor <sha> upstream/release-5.4` → no, for all three |
| causation | revert 2 metric commits on v6 → 2/2 pass |
| old derivative is wrong | main's test vs reverted metric: analytic −0.000731416 vs FD 0.270065 |
| new derivative is right | 5/5 ITK JHMI tests pass on v6 |
| ground truth is valid | fixed/moving histogram correlation 0.9999, identical geometry |
| new is closer to truth | in-mask MSE 54.792 (new) < 55.721 (baseline) < 55.898 (old) |
| baseline == old metric | `MSE(baseline, old) = 0.1100` in-mask |
| baseline is stale | last touched 2018-11-24; fix merged 2026-07-16 |
| failure exceeds noise band | ImageError 1756 vs `compareNumberOfPixelsTolerance 777` = 2.26x |
