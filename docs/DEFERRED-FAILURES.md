# Deferred / known forest-matrix failures

Matrix targets that fail for a reason unrelated to the ITK ref under test.
Each is a consumer-vs-ITK-version mismatch, a missing build option, or a
platform limit. They are recorded here so that a red cell is never mistaken
for a regression.

Last validated: 2026-11-07, Linux x86_64 (cortex, conda gcc 14, CUDA 13.3).

- `build_forest-itk-main`: ITK `upstream/main` (`4dbf73815e`, 6.0.0)
- `build_forest-itk-release-5.4`: ITK `upstream/release-5.4` (`eef984f4982`,
  5.4.8)

macOS arm64 and Windows were not re-run in this pass.

## Current matrix (Linux)

| Target | itk-main | release-5.4 |
|---|---|---|
| ITK, ANTs, BRAINSTools, elastix, RTK | PASS | PASS |
| Cleaver, PerformanceBenchmarking | PASS | PASS |
| SimpleITKFilters, TractographyTRX | PASS | PASS |
| VkFFTBackend (CUDA) | PASS | PASS |
| OpenIGTLink, OpenIGTLinkIO, vtkAddon | PASS | PASS |
| IGSIO, PlusLib | PASS | PASS |
| Slicer, SlicerExtensions | PASS * | PASS |
| SimpleITK | PASS | FAIL (expected) |
| SphinxExamples | PASS | FAIL (expected) |
| Impact | not checked out | PASS |

\* Slicer passes on ITK `main` only with ITK #7139 applied to the ITK that
Slicer builds (see "Pending upstream" below).

## Expected failures on ITK 5.4

These do not show a defect in ITK 5.4; the consumer or the preset needs
something ITK 5.4 does not provide.

**SimpleITK requires ITK 6.** SimpleITK `main` links `ITK::ITKCommonModule`
and the other module interface targets, which ITK 5.4 does not export:

    Target "SimpleITKCommon" links to: ITK::ITKCommonModule
    but the target was not found.

To cover SimpleITK in the 5.4 forest, pin it to a release that supports
ITK 5.4 rather than `main`.

**SphinxExamples requires ITK's Python wrapping.** The v5 preset
(`cmake/presets/10-itk-v5.json`) does not set `ITK_WRAP_PYTHON`, so
`setup-itk-downstream-testbed.sh` stops with "ITK ... was built without
ITK_WRAP_PYTHON". The v6 preset wraps, so it passes in the itk-main forest.

## Pending upstream

**ITK #7139: GDCM with `ITK_USE_SYSTEM_ZLIB=ON`.** Slicer configures ITK
with its own zlib. Since ITK ffb72589ad and 371fc394d6, `gdcmCommon` compiles
`gdcmDeflateStream.cxx` without zlib's include directory:

    itk_zlib.h:35:11: fatal error: zlib.h: No such file or directory

ITK #7139 links `gdcmCommon` to `ITK::ITKZLIBModule`. Until it merges, the
itk-main forest carries that change as an uncommitted edit in
`build_forest-itk-main/Slicer/build/ITK`. A clean Slicer build loses the edit
and fails again. After the merge, re-mint `[scenarios.itk-main.Slicer]
ITK_GIT_TAG` in `versions.toml`. The earlier report on #6563 described the
same failure on Windows.

## Testbed pitfalls fixed on 2026-11-07

Each of these produced a red cell unrelated to ITK. They are fixed in the
kit, and they are listed here so the symptoms are recognizable.

- **Slicer loaded conda's libpython.** The pixi env and Slicer both ship
  `libpython3.12.so`. Slicer now links with `--enable-new-dtags` and is
  configured with `Slicer_USE_SYSTEM_QT=ON` on Linux, so its launcher puts
  `python-install/lib` first. Symptom: `python-ensurepip` or
  `GenerateLazyVtkModule.py` fails with
  `No module named '_sysconfigdata__linux_x86_64-linux-gnu'` or
  "exit abnormally".
- **conda's cross linker ignores a library's RPATH.** The engine restores
  `-Wl,--allow-shlib-undefined` on Linux. Symptom: CTK's `ctkDICOM` link
  fails with `libopenjp2.so.7, needed by libdcmjp2kcs ... not found`.
- **CUDA upgraded in place.** `/usr/local/cuda/bin/nvcc` kept its path while
  `cuda-13.2` disappeared. The engine now reconfigures from scratch when the
  cached `CUDA_cudart_LIBRARY` is gone. Symptom: ninja error on a missing
  `libcudart.so`, and an orphaned `VkFFTBackendConfig.py` in ITK's package.
- **Patches leaking into ExternalProject sources.** The BRAINSTools TBB patch
  no longer edits checkouts under `BRAINSTools/build/`. Symptom:
  `tbb-gitupdate.cmake` fails to move oneTBB to a new tag.
- **A hung NFS PATH entry.** A stalled `/nas4321` mount in `PATH` blocked
  matrix lanes in uninterruptible I/O. Run the matrix with NFS entries
  removed from `PATH`.

## Resolved since the PocketFFT validation (2026-06/07)

The earlier version of this file listed these as deferred. All of them now
pass on Linux against ITK `main`:

- elastix: the `vnl_matrix_exp` link failure.
- SimpleITK: the `EnhancementEnum` mismatch.
- Slicer: `itkNamespace.h`. Slicer's ITK tags now carry the custom-namespace
  patch.
- BRAINSTools: the full SuperBuild. BRAINSTools #691 fixed the `vnl_svd` use
  that ITK 6's `ITK_LEGACY_REMOVE` exposed.

The environment fixes from that pass are still applied by the engine:
`Module_SimpleITKFilters`, `_stub_remote_examples`, `_fix_dcmtk_ijg_symlinks`,
`_overlay_vnl_headers`, `_patch_ants_missing_includes`, and
`_patch_brainstools_kwsys`.
