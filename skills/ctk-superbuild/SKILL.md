---
name: ctk-superbuild
version: 1.0.0
purpose: Run the CTK superbuild (all dependencies + CTK) using the LLVM/Clang compiler from Homebrew.
description: Run the CTK superbuild (all dependencies + CTK) using the LLVM/Clang compiler from Homebrew.
triggers:
  - ctk-superbuild
  - /ctk-superbuild
user_invocable: true
cmd: false
argument_hint: null
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
    network_required: false
    git_required: false
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools: []
  python_packages: []
  scripts: []
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
ctk-superbuild — Full CTK superbuild (all deps + CTK) (no arguments)

Usage:
  /ctk-superbuild               Build all external deps + CTK

Uses Homebrew LLVM/Clang. Configures if needed, then builds.
```

Run the full CTK superbuild, which builds all external dependencies (VTK, DCMTK, PythonQt, etc.) and then CTK itself.

## Prerequisites

The build directory must be configured first. If `cmake-build-clazy/CMakeCache.txt` does not exist, run the configure step:

```bash
cd ~/src/CTK && cmake \
  -DCMAKE_BUILD_TYPE:STRING=Debug \
  -DCMAKE_CXX_COMPILER:STRING=/opt/homebrew/opt/llvm/bin/clang++ \
  -DCMAKE_C_COMPILER:STRING=/opt/homebrew/opt/llvm/bin/clang \
  -DCMAKE_OSX_SYSROOT:PATH=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk \
  -DCMAKE_EXPORT_COMPILE_COMMANDS:BOOL=ON \
  -DBUILD_TESTING:BOOL=ON \
  -DCTK_QT_VERSION:STRING=6 \
  -DCTK_SUPERBUILD:BOOL=ON \
  -DCTK_BUILD_SHARED_LIBS:BOOL=ON \
  -DCTK_ENABLE_Widgets:BOOL=ON \
  -DCTK_APP_ctkDICOM:BOOL=ON \
  -DCTK_LIB_Core:BOOL=ON \
  -DCTK_LIB_Widgets:BOOL=ON \
  -DCTK_LIB_DICOM/Core:BOOL=ON \
  -DCTK_LIB_DICOM/Widgets:BOOL=ON \
  -DCTK_LIB_PluginFramework:BOOL=ON \
  -DCTK_LIB_Scripting/Python/Core:BOOL=ON \
  -DCTK_LIB_Scripting/Python/Widgets:BOOL=ON \
  -DCTK_LIB_Visualization/VTK/Core:BOOL=ON \
  -DCTK_LIB_Visualization/VTK/Widgets:BOOL=ON \
  -DCTK_LIB_Visualization/VTK/Widgets_USE_TRANSFER_FUNCTION_CHARTS:BOOL=ON \
  -DQt6_DIR:PATH=/opt/homebrew/opt/qt/lib/cmake/Qt6 \
  -DPYTHON_EXECUTABLE:FILEPATH=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
  -DPYTHON_INCLUDE_DIR:PATH=/Library/Frameworks/Python.framework/Versions/3.12/include/python3.12 \
  -DPYTHON_LIBRARY:FILEPATH=/Library/Frameworks/Python.framework/Versions/3.12/lib/libpython3.12.dylib \
  -B cmake-build-clazy -S .
```

**IMPORTANT:** `CMAKE_OSX_SYSROOT` must point to the CommandLineTools SDK (`/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk`), not the Xcode SDK. This ensures `compile_commands.json` records the correct sysroot for clazy-standalone, which uses Homebrew LLVM's clang internally.

## Steps

### Step 1: Build

```bash
cd ~/src/CTK && cmake --build cmake-build-clazy -j8
```

This may take a long time on a clean build (10+ minutes). Run it in the background if appropriate. For incremental builds after source changes, prefer `/ctk-build` which only rebuilds the inner CTK project.

### Step 2: Report

If the build succeeds, report success with the number of compilation units.
If the build fails, show the last 40 lines of output and identify the failing target/file.

## Arguments

If the user passes a target name (e.g., `/ctk-superbuild CTKWidgets`), append `--target <target>` to the cmake build command.
