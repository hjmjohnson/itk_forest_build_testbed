# SuperBuild Variables to Disable / Change

## Key setting: Turn off SuperBuild

The most important change is setting `BRAINSTools_SUPERBUILD=OFF` and
`BRAINSTools_PKGBUILD=ON` in the `base_language` preset. This switches
BRAINSTools from SuperBuild mode (where it downloads and builds ITK, VTK,
etc. as ExternalProjects) to "package build" mode where it expects
pre-built dependencies to be found via `*_DIR` variables.

## Variables set by csv_update_consumer.py

The script automatically sets these in the `base_language` preset:

| Variable | Value | Effect |
|----------|-------|--------|
| `BRAINSTools_SUPERBUILD` | `OFF` | Disables the SuperBuild outer project entirely |
| `BRAINSTools_PKGBUILD` | `ON` | Enables direct-build mode expecting system packages |
| `USE_SYSTEM_ITK` | `ON` | Tells CMake to find ITK externally, not build it |
| `ITK_DIR` | `.../installed_v5.4.2/lib/cmake/ITK-5.4` | Points CMake to the pre-built ITK config |
| `USE_SYSTEM_VTK` | `ON` | Tells CMake to find VTK externally, not build it |
| `VTK_DIR` | `.../installed_v9.4.0/lib/cmake/vtk-9.4` | Points CMake to the pre-built VTK config |

## SuperBuild ExternalProjects that are now skipped

With `USE_SYSTEM_ITK=ON` and `USE_SYSTEM_VTK=ON`, the SuperBuild's
ExternalProject steps for ITK and VTK are bypassed. Specifically:

- **ITKv5** ExternalProject: download, configure, build, install steps all skipped
- **VTK** ExternalProject: download, configure, build, install steps all skipped

This saves significant build time (ITK alone can take 20-30 minutes).

## Other USE_SYSTEM variables to consider

The existing `CMakePresets.json` shows these are also used in the
`brainstools_support` preset with `OFF`:

| Variable | Current | Notes |
|----------|---------|-------|
| `USE_SYSTEM_SlicerExecutionModel` | `OFF` | Could also be pre-built if needed; lightweight so less benefit |
| `USE_SYSTEM_zlib` | `OFF` | Tiny library; system zlib works fine on most platforms |

If you later add SlicerExecutionModel or zlib to `common_support_versions`,
run `csv_update_consumer.py` again with `--pkg` for each one.

## Dependencies that remain in SuperBuild

Even with `BRAINSTools_SUPERBUILD=OFF`, you still need these to be
findable (either pre-built or from the support build):

- **ANTs**: Still built from source via the support preset, or pointed to
  via `ANTs_DIR`, `ANTs_SOURCE_DIR`, `ANTs_LIBRARY_DIR`
- **SlicerExecutionModel**: Either `USE_SYSTEM_SlicerExecutionModel=ON`
  with `SlicerExecutionModel_DIR` or built by SuperBuild

## Relationship to existing presets in CMakePresets.json

The new `base_language` preset in `CMakeUserPresets.json` inherits from
`brainstools_base` (defined in the tracked `CMakePresets.json`), so it
picks up all the `USE_*` module flags, compiler flags, and environment
settings. It overrides only:

1. The build mode (`SUPERBUILD=OFF`, `PKGBUILD=ON`)
2. The dependency paths (`ITK_DIR`, `VTK_DIR`)
3. The system-use flags (`USE_SYSTEM_ITK`, `USE_SYSTEM_VTK`)

This keeps the `CMakeUserPresets.json` minimal and avoids duplicating
the long list of `USE_BRAINS*` module toggles.

## Build workflow after wiring

```bash
# Configure (no -D flags needed — everything is in the preset)
cd ~/src/BRAINSTools
cmake --preset base_language

# Build
cmake --build cmake-csv-build -j$(sysctl -n hw.logicalcpu)

# Test
ctest --test-dir cmake-csv-build --output-on-failure
```
