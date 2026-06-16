# Slicer on macOS — Qt, ccache, conda-flag specifics

Slicer's SuperBuild builds VTK/CTK against a **real Qt6** and builds its **own
ITK 6** (the testbed's headless ITK has `Module_ITKVtkGlue=OFF`, so it cannot
satisfy `Slicer_USE_SYSTEM_ITK`). `bin/setup-itk-downstream-testbed.sh` handles
three macOS gotchas; all are in the `Slicer)` case + the env block near the top.

## 1. Qt resolution — drop Homebrew qt@6, pin ~/Qt

A Homebrew `qt@6` on `PATH`/`CMAKE_PREFIX_PATH` shadows a user `~/Qt` install:
the host-tools (`Qt6CoreTools`, …) resolve from Homebrew while `Qt6` itself
comes from `~/Qt`, which fails Qt6 package configuration. The script:

- strips `/opt/homebrew/opt/qt@6/bin` from `PATH`,
- removes any `qt@6` entry from `CMAKE_PREFIX_PATH` and **exports**
  `CMAKE_PREFIX_PATH=$SLICER_QT_PREFIX` (so Slicer's EP sub-configures inherit it),
- pins `SLICER_QT_PREFIX=~/Qt/$SLICER_QT_VERSION/macos` (default
  `SLICER_QT_VERSION=6.9.1`), with a fallback that picks the newest
  `~/Qt/6.*/macos` that has a `lib/cmake/Qt6`.

Override with `SLICER_QT_VERSION` or `SLICER_QT_PREFIX`.

## 2. conda CFLAGS leak — unset before configuring

pixi/conda activation exports `CFLAGS/CPPFLAGS/LDFLAGS` that add the env's
`include/lib` to every compile. That leaks `libintl.h` (gettext) into Slicer's
bundled CPython, which then detects gettext but fails to link `-lintl`. All real
deps are passed explicitly via `-D`, so the script `unset`s
`CFLAGS CPPFLAGS CXXFLAGS LDFLAGS CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH`.

## 3. Compilers — conda toolchain only, never Homebrew

The Slicer configure passes the conda `CC`/`CXX` and
`CMAKE_<LANG>_COMPILER_LAUNCHER=ccache`. Homebrew compilers are refused at
startup (they are built with a different compiler and ABI-mismatch the
conda-forge stack); conda-forge runtime libs like fftw/qt are fine. Override
the compilers for the Slicer step only with `SLICER_CC` / `SLICER_CXX`.

## ITK branch Slicer builds

`Slicer_ITK_GIT_REPOSITORY` / `Slicer_ITK_GIT_TAG` select the ITK that Slicer's
SuperBuild builds — a `slicer-v6.0.0-*` branch on `hjmjohnson/ITK`. Override via
`SLICER_ITK_GIT_REPOSITORY` / `SLICER_ITK_GIT_TAG`.

## Known quirk

`pixi run build-Slicer`'s `depends-on` only runs `build-ITK`, not the Slicer
step. Invoke the engine directly when needed:

```bash
pixi run bash ./bin/setup-itk-downstream-testbed.sh build Slicer
```

## SlicerExtensions

Built against the inner Slicer build (`Slicer_DIR =
build_forest/Slicer-build/Slicer-build`) for a curated, ITK-exercising subset
(`BoneTextureExtension`, `AnomalousFiltersExtension`, `SlicerElastix`). Widen
coverage by editing `SLICER_EXTENSIONS` in the engine.
