# Deferred / known forest-matrix failures

Targets that fail for reasons **independent of the vnl/FFT change under test**.
Each is a pre-existing consumer-vs-ITK skew or an ITK-`main` gap, reproducible
on a vanilla `main` ITK, not introduced by the branch being validated. Recorded
here so a red cell is never mistaken for a regression.

Last validated: PocketFFT branch `pocketfft-backend` (`e817a4dc60`), macOS arm64
+ Linux x86_64 (cortex).

## Environment fixes applied (now green)

These were testbed-configuration gaps, fixed in `bin/setup-vxl-downstream-testbed.sh`:

| Was failing | Cause | Fix |
|---|---|---|
| SimpleITK (configure) | `ITK::SimpleITKFiltersModule` target absent | `-DModule_SimpleITKFilters=ON` in the ITK build |
| ITK (configure) | `IOMeshMZ3`, `AnisotropicDiffusionLBR` call `itk_module_examples()` with no `examples/` dir under `BUILD_EXAMPLES=ON` | `_stub_remote_examples` stubs an empty `examples/CMakeLists.txt` |
| DCMTK consumers (configure) | `ITK::ITKIODCMTK` export references dangling `ijg{8,12,16}/include` paths | `_fix_dcmtk_ijg_symlinks` symlinks them to `dcmjpeg/libijg{N}` |
| elastix (compile, partial) | ITK `main` vnl no longer ships `vnl/vnl_matrix_exp.h` (elastix `AffineLogTransform`) | `bin/overlays/vnl/vnl_matrix_exp.{h,hxx}` overlaid header-only via `_overlay_vnl_headers` — resolves the **compile** error (see elastix link caveat below) |

## Still deferred — genuine upstream / consumer-version skews (not FFT)

### elastix — `vnl_matrix_exp` explicit instantiations missing from libitkvnl
The header overlay above fixes the compile, but elastix's `libelxCommon.a`
(`elxTransformFactoryRegistration.cxx`) still fails to **link**:
`Undefined symbols: vnl_matrix_exp<vnl_matrix<double>>(...)` and the
`vnl_matrix_fixed<double,N,N>` (N=1..4) forms. ITK `main` removed not just the
header but the `Templates/vnl_matrix_exp+*.cxx` explicit instantiations that
elastix expects compiled into libitkvnl. Fully fixing this needs those
instantiation TUs re-added to ITK's vnl `CMakeLists.txt` and an ITK rebuild — an
ITK-side change, out of scope for testbed env. Pre-existing on vanilla `main`,
orthogonal to the FFT change.

### SimpleITK — `EnhancementEnum` API mismatch
After enabling `Module_SimpleITKFilters`, SimpleITK fails compiling
`Code/BasicFilters/src/sitkCoherenceEnhancingDiffusionImageFilter.cxx`:
`no type named 'EnhancementEnum' in itk::CoherenceEnhancingDiffusionImageFilter`.
The SimpleITK checkout predates a rename in the `AnisotropicDiffusionLBR` remote
module. A SimpleITK-vs-module version mismatch; unrelated to vnl/FFT. Fix is to
bump the SimpleITK checkout (or the module) — not a testbed-env change.

### Slicer / SlicerExtensions — `itkNamespace.h` absent from ITK
Slicer's vendored `Libs/ITKFactoryRegistration/itkFactoryRegistration.h`
`#include`s `itkNamespace.h`, which does not exist in current ITK `main`
(nor on this branch — verified). Slicer's ITKFactoryRegistration snapshot is
matched to its pinned older ITK; building Slicer against a newer `main` ITK
fails. Being addressed upstream (ITK-side). On re-point, Slicer's ITK
ExternalProject may also hit an `ITK-gitupdate` "could not apply" conflict from
a stale clone at the previous tip — clear `Slicer-build/ITK*` to force a fresh
clone. The ITK *library* builds clean for Slicer; only Slicer's own factory-reg
lib is blocked.

### VkFFTBackend — OpenCL not available (cortex/headless Linux only)
`Could NOT find OpenCL (missing: OpenCL_LIBRARY)`. The headless Linux host has
no OpenCL runtime; macOS provides it as a system framework, where VkFFTBackend
builds. Platform dependency, not FFT (zero FFT/vnl refs in the log).

### BRAINSTools — ANTs `itkSurfaceImageCurvature.h` missing include (GCC only)
On GCC (cortex), `'ImageRegionIteratorWithIndex' does not name a type` in
ANTs's `Utilities/itkSurfaceImageCurvature.{h,hxx}` — the header uses the
iterator without including `itkImageRegionIteratorWithIndex.h` and relies on a
transitive include that Apple clang provides but GCC does not. Pre-existing ANTs
code bug surfaced by the stricter compiler; a one-line `#include` upstream fix.
Not FFT (the standalone ANTs target builds; BRAINSTools bundles its own ANTs
that compiles this Examples header).

## Platform matrix (PocketFFT branch e817a4dc60)

| Target | macOS arm64 | Linux x86_64 (cortex) | Blocker (if red) |
|---|---|---|---|
| ITK, RTK, Cleaver, PerfBenchmarking, SimpleITKFilters, TractographyTRX, ANTs | PASS | PASS | — |
| VkFFTBackend | PASS | FAIL | cortex: no OpenCL |
| BRAINSTools | PASS | FAIL | cortex: ANTs GCC missing-include |
| SimpleITK | FAIL | PASS | macOS: SimpleITK `EnhancementEnum` skew |
| elastix | FAIL | FAIL | vnl_matrix_exp instantiations |
| Slicer / SlicerExtensions | FAIL | FAIL | `itkNamespace.h` (ITK-side, upstream) |

## Notes

- All targets above fail identically on a vanilla `main` ITK (or for a
  platform-dependency reason); none are caused by the PocketFFT backend change.
- Every FFT-relevant consumer builds clean against the branch where its platform
  dependencies are satisfied: ITK, ANTs, RTK, Cleaver, PerformanceBenchmarking,
  SimpleITKFilters, TractographyTRX on both; VkFFTBackend + BRAINSTools on macOS.
