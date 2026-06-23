# Forest catalog

Every "tree" the testbed builds, its upstream GitHub repository, and the
**floating upstream branch** the testbed tracks (the moving target an ITK
change must not break). The testbed checks each out into a local
`<name>-itk-downstream` worktree branched from the floating branch below; switch
a tree to a fixed tag by editing its row in `bin/setup-itk-downstream-testbed.sh`.

## Consumers (built against the local ITK via `USE_SYSTEM_ITK`)

| Tree | Repository | Floating branch |
|---|---|---|
| ITK | https://github.com/InsightSoftwareConsortium/ITK | `main` |
| ANTs | https://github.com/ANTsX/ANTs | `master` (**ITKv6-only** — see note) |
| BRAINSTools | https://github.com/BRAINSia/BRAINSTools | `main` |
| Slicer | https://github.com/Slicer/Slicer | `main` |
| SlicerExtensions (index) | https://github.com/Slicer/ExtensionsIndex | `main` |
| elastix | https://github.com/SuperElastix/elastix | `main` |
| MITK | https://github.com/MITK/MITK | `master` |
| c3d | https://github.com/pyushkevich/c3d | `master` |
| Plastimatch | https://gitlab.com/plastimatch/plastimatch | `hjmjohnson/itkv6-support` (fork; ITKv6 fixes) |
| SimpleITK | https://github.com/SimpleITK/SimpleITK | `master` |

Curated Slicer extensions (built against the inner Slicer): **BoneTextureExtension**,
**AnomalousFiltersExtension**, **SlicerElastix** — descriptors resolved from the
ExtensionsIndex above.

### ANTs requires ITKv6 (no ITK5 variant)

ANTs `master` builds **only against ITK v6+**. It dropped ITK5 in
[PR #1933 "ITK 6"](https://github.com/ANTsX/ANTs/pull/1933) (merged **2026-03-15**:
`SuperBuild/External_ITKv5.cmake` → `External_ITKv6.cmake`,
`find_package(ITK 6 REQUIRED)`). The last ITK5-based ANTs `master` was ITK 5.4.3
(2025-04-02). So ANTs cannot be built in the ITK 5.4 forest
(`build_forest-ITK-release-5-4`); use an ITKv6 forest
(`build_forest-itkv6_main`). `bin/setup-itk-downstream-testbed.sh` enforces this:
`build ANTs` / `configure ANTs` against an ITK<6 forest fails fast via
`require_itk6_for_ants()` rather than wasting a build. To build ANTs against ITK5
anyway, pin a pre-2026-03-15 ANTs tag via the SuperBuild `GIT_TAG`.

## ITK remote modules (built externally against the local ITK)

`heavy` modules (CUDA / Java / Emscripten) build only with `HEAVY=1`.

| Tree | Repository | Floating branch | Heavy |
|---|---|---|---|
| BioCell | https://github.com/InsightSoftwareConsortium/ITKBioCell | `master` | |
| Cleaver | https://github.com/SCIInstitute/ITKCleaver | `master` | |
| CudaCommon | https://github.com/RTKConsortium/ITKCudaCommon | `master` | ✔ |
| HASI | https://github.com/KitwareMedical/HASI | `main` | |
| IOOpenSlide | https://github.com/InsightSoftwareConsortium/ITKIOOpenSlide | `master` | ✔ |
| LesionSizingToolkit | https://github.com/InsightSoftwareConsortium/LesionSizingToolkit | `master` | |
| PerformanceBenchmarking | https://github.com/InsightSoftwareConsortium/ITKPerformanceBenchmarking | `master` | |
| RTK | https://github.com/RTKConsortium/RTK | `master` | |
| SCIFIO | https://github.com/scifio/scifio-imageio | `master` | ✔ |
| Shape | https://github.com/SlicerSALT/ITKShape | `master` | |
| SimpleITKFilters | https://github.com/InsightSoftwareConsortium/ITKSimpleITKFilters | `master` | |
| SkullStrip | https://github.com/InsightSoftwareConsortium/ITKSkullStrip | `master` | |
| SphinxExamples | https://github.com/InsightSoftwareConsortium/ITKSphinxExamples | `master` | |
| TractographyTRX | https://github.com/tee-ar-ex/ITKTractographyTRX | `main` | |
| TubeTK | https://github.com/InsightSoftwareConsortium/ITKTubeTK | `main` | |
| Ultrasound | https://github.com/KitwareMedical/ITKUltrasound | `master` | |
| VkFFTBackend | https://github.com/InsightSoftwareConsortium/ITKVkFFTBackend | `master` | |
| WebAssemblyInterface (ITK-Wasm) | https://github.com/InsightSoftwareConsortium/ITK-Wasm | `main` | ✔ |

The authoritative source is the `CONSUMERS` / `REMOTES` / `SLICER_EXTENSIONS`
arrays in [`bin/setup-itk-downstream-testbed.sh`](bin/setup-itk-downstream-testbed.sh);
this table mirrors them. If they diverge, the script wins — update this file.
