---
name: clazy-configure
version: 1.0.0
purpose: Configure a new CTK superbuild environment for clazy static analysis, with all Slicer-relevant CTK features enabled.
description: Configure a new CTK superbuild environment for clazy static analysis, with all Slicer-relevant CTK features enabled. Generates compile_commands.json required by clazy-standalone. Supports macOS, Linux, and Windows. Run once before using /clazy-build, /clazy-check, /clazy-fix.
triggers:
  - clazy-configure
  - /clazy-configure
user_invocable: true
cmd: false
argument_hint: "[qt5|qt6]"
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
    network_required: true
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
  tier: project
  target_projects:
    - ctk
  needs_loader_dir: true
  adapters:
    - claude-code
---

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
clazy-configure — Configure CTK superbuild for clazy analysis

Usage:
  /clazy-configure              Configure for Qt6 (default)
  /clazy-configure qt5          Configure for Qt5
  /clazy-configure qt6          Configure for Qt6
```

Configure a CTK superbuild for clazy static analysis with all Slicer-relevant features enabled. This skill creates the CMake build directory, selects the correct compiler toolchain, and generates `compile_commands.json` (required by `clazy-standalone`).

Run this skill **once** when setting up a new environment. After configuration, use `/clazy-build` → `/clazy-check` → `/clazy-fix`.

## Architecture Overview

The CTK clazy workflow uses a two-compiler strategy:

```
clang (LLVM)  ──►  cmake --build  ──►  compile_commands.json
                                              │
clazy-standalone ◄────────────────────────────┘
     │
     ▼
clazy warnings (log files for /clazy-fix)
```

- **Build compiler**: Homebrew LLVM `clang`/`clang++` — used to actually compile CTK and produce `compile_commands.json`
- **Analysis tool**: `clazy-standalone` — reads `compile_commands.json` and runs checks without recompiling
- **Key flag**: `CMAKE_EXPORT_COMPILE_COMMANDS=ON` — tells CMake to write `compile_commands.json`

This is better than using `clazy` as the compiler directly, because:
1. Builds stay fast (no analysis overhead during normal builds)
2. Analysis can be re-run at any level without rebuilding
3. `clazy-standalone` supports parallel file-level analysis

## Prerequisites

### macOS (Homebrew) — Detailed Setup

**Install required tools:**
```bash
# LLVM (provides clang/clang++ compatible with clazy)
brew install llvm

# Clazy static analysis tool
brew install clazy

# Ninja build system (faster than make for CTK)
brew install ninja

# Qt — choose one version:
brew install qt@5   # Qt 5.15.x (Slicer's current Qt5 target)
brew install qt     # Qt 6.x (Slicer's Qt6 target, installs as qt@6)

# CMake (3.20+ required for CTK)
brew install cmake
```

**Verify installations:**
```bash
which clazy-standalone         # → /opt/homebrew/bin/clazy-standalone
clazy-standalone --version     # → clazy 1.x (clang 15+)

/opt/homebrew/opt/llvm/bin/clang++ --version  # → clang version 15+
ninja --version                # → 1.x
cmake --version                # → cmake 3.20+
```

**macOS SDK — IMPORTANT:**
CTK's configure must use the CommandLineTools SDK, not the Xcode SDK. This prevents phantom header errors with Homebrew LLVM:
```bash
# Verify CommandLineTools SDK is installed
ls /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk
# If missing, install it:
xcode-select --install
```

**Qt path for cmake (macOS):**
```bash
# Qt5
Qt5_DIR=$(brew --prefix qt@5)/lib/cmake/Qt5

# Qt6
Qt6_DIR=$(brew --prefix qt)/lib/cmake/Qt6
```

### Linux (Ubuntu/Debian)

```bash
# LLVM + clazy
sudo apt-get install clazy clang ninja-build cmake

# Qt5
sudo apt-get install qtbase5-dev qttools5-dev qtmultimedia5-dev \
    libqt5xmlpatterns5-dev libqt5svg5-dev libqt5sql5-sqlite

# Qt6
sudo apt-get install qt6-base-dev qt6-tools-dev qt6-multimedia-dev \
    libqt6svg6-dev
```

### Windows (MSVC + clazy)

Windows support requires:
- Visual Studio 2019 or 2022 with LLVM/clang-cl component
- clazy plugin for MSVC: download from https://github.com/KDE/clazy/releases
- Qt installer (Qt 5.15 or 6.x) from qt.io
- CMake 3.20+, Ninja

Note: On Windows, `clazy-standalone` analysis uses the same approach (compile_commands.json), but the compiler is `clang-cl` instead of `clang`.

## Steps

### Step 1: Detect platform and gather paths

Detect which platform we're on:

```bash
case "$(uname -s)" in
  Darwin) PLATFORM="macos" ;;
  Linux)  PLATFORM="linux" ;;
  MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
  *) echo "Unknown platform"; exit 1 ;;
esac
echo "Platform: ${PLATFORM}"
```

Determine Qt version from the argument (default: auto-detect):
- If `qt5` in argument → `QT_VERSION=5`
- If `qt6` in argument → `QT_VERSION=6`
- If neither → auto-detect from environment (check `Qt6_DIR` first, then `Qt5_DIR`)

### Step 2: Locate compiler toolchain

**macOS:**
```bash
LLVM_PREFIX="$(brew --prefix llvm)"
C_COMPILER="${LLVM_PREFIX}/bin/clang"
CXX_COMPILER="${LLVM_PREFIX}/bin/clang++"
OSX_SYSROOT="/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"

# Validate
[ -x "${CXX_COMPILER}" ] || { echo "ERROR: Homebrew LLVM not found. Run: brew install llvm"; exit 1; }
[ -d "${OSX_SYSROOT}" ] || { echo "ERROR: CommandLineTools SDK missing. Run: xcode-select --install"; exit 1; }
```

**Linux:**
```bash
C_COMPILER="$(which clang || which clang-15 || which clang-14)"
CXX_COMPILER="$(which clang++ || which clang++-15 || which clang++-14)"
[ -x "${CXX_COMPILER}" ] || { echo "ERROR: clang++ not found. Install: sudo apt-get install clang"; exit 1; }
```

**Windows:**
Use `clang-cl.exe` from the LLVM Visual Studio component. Set `CMAKE_GENERATOR_TOOLSET=ClangCL`.

### Step 3: Set source and build directories

```bash
SRC_DIR="${SRC_DIR:-${HOME}/src/CTK}"
BLD_DIR="${BLD_DIR:-${HOME}/src/CTK/cmake-build-clazy}"

[ -f "${SRC_DIR}/CMakeLists.txt" ] || { echo "ERROR: CTK source not found at ${SRC_DIR}"; exit 1; }
mkdir -p "${BLD_DIR}"
```

User can override with `/clazy-configure /path/to/src /path/to/bld`.

### Step 4: Build the cmake configure command

Construct the full configure command. The options below enable all libraries used by **3D Slicer**:

```bash
cmake \
  -G Ninja \
  -S "${SRC_DIR}" \
  -B "${BLD_DIR}" \
  -DCMAKE_BUILD_TYPE:STRING=Debug \
  -DCMAKE_EXPORT_COMPILE_COMMANDS:BOOL=ON \
  \
  # Compiler (macOS/Linux — adjust for Windows)
  -DCMAKE_C_COMPILER:FILEPATH="${C_COMPILER}" \
  -DCMAKE_CXX_COMPILER:FILEPATH="${CXX_COMPILER}" \
  \
  # macOS SDK (macOS only — omit on Linux/Windows)
  -DCMAKE_OSX_SYSROOT:PATH="${OSX_SYSROOT}" \
  \
  # Qt version
  -DCTK_QT_VERSION:STRING="${QT_VERSION}" \
  \
  # Superbuild ON (downloads and builds DCMTK, ITK, PythonQt, VTK automatically)
  -DCTK_SUPERBUILD:BOOL=ON \
  \
  # === Slicer-relevant CTK libraries ===
  -DCTK_LIB_Core:BOOL=ON \
  -DCTK_LIB_Widgets:BOOL=ON \
  -DCTK_LIB_DICOM/Core:BOOL=ON \
  -DCTK_LIB_DICOM/Widgets:BOOL=ON \
  -DCTK_LIB_PluginFramework:BOOL=ON \
  -DCTK_LIB_Scripting/Python/Core:BOOL=ON \
  -DCTK_LIB_Scripting/Python/Widgets:BOOL=ON \
  -DCTK_LIB_Visualization/VTK/Core:BOOL=ON \
  -DCTK_LIB_Visualization/VTK/Widgets:BOOL=ON \
  -DCTK_LIB_ImageProcessing/ITK/Core:BOOL=ON \
  \
  # === Slicer-relevant apps ===
  -DCTK_APP_ctkDICOM:BOOL=ON \
  \
  # === Python wrapping (required for Slicer's Python scripting) ===
  -DCTK_WRAP_PYTHONQT_LIGHT:BOOL=ON \
  \
  # === Qt Designer plugins (for UI development) ===
  -DCTK_BUILD_QTDESIGNER_PLUGINS:BOOL=ON \
  \
  # === Testing ===
  -DBUILD_TESTING:BOOL=ON \
  \
  # === Shared libraries ===
  -DCTK_BUILD_SHARED_LIBS:BOOL=ON
```

**Why Debug build?** Clazy analysis benefits from debug symbols and unoptimized code that preserves the original source structure. The clazy-standalone tool analyzes source regardless of build type, but Debug avoids confusing optimized code patterns.

**Why not VTK modules with additional flags?**
When `CTK_LIB_Visualization/VTK/Widgets=ON`, the VTK superbuild will configure VTK automatically with the required modules (`VTK_MODULE_ENABLE_VTK_ChartsCore`, `VTK_MODULE_ENABLE_VTK_GUISupportQt`, `VTK_MODULE_ENABLE_VTK_ViewsQt`). No extra flags needed at the CTK superbuild level.

### Step 5: Run CMake configure

```bash
echo "Configuring CTK superbuild at: ${BLD_DIR}"
echo "Qt version: ${QT_VERSION}"
echo "Compiler: ${CXX_COMPILER}"
echo ""

cmake [... full command from Step 4 ...]
```

This runs the **superbuild configure only** — it does NOT build yet. The superbuild will detect and configure all external dependencies (DCMTK, ITK, PythonQt, VTK). First configure takes ~30 seconds; subsequent reconfigures are fast.

### Step 6: Verify configuration

After CMake exits successfully:

```bash
# Confirm Ninja build files were created
[ -f "${BLD_DIR}/build.ninja" ] && echo "✓ Ninja build files created" || echo "✗ Configure failed"

# Note: compile_commands.json is NOT present yet — it appears after the first build
# (it lives in the inner build: ${BLD_DIR}/CTK-build/compile_commands.json)
echo "Note: compile_commands.json will be generated during first build"
echo "Run: /clazy-build"
```

### Step 7: Set up IDE/LSP support (first-time only)

After the first successful build, set up clangd so the IDE shows correct diagnostics instead of false-positive `'QObject' file not found` errors:

```bash
# Symlink compile_commands.json to the repo root (where clangd looks)
# Use the Qt6 inner build; re-run this if you switch Qt versions
ln -sf "${BLD_DIR}/CTK-build/compile_commands.json" "${SRC_DIR}/compile_commands.json"

# Create .clangd config at repo root so clangd finds it
cat > "${SRC_DIR}/.clangd" << 'EOF'
CompileFlags:
  CompilationDatabase: .
EOF

echo "✓ IDE/LSP setup complete — restart clangd to pick up changes"
echo "  VS Code: Cmd+Shift+P → 'clangd: Restart language server'"
```

Both `compile_commands.json` and `.clangd` are already in CTK's `.gitignore` — do not commit them.

**Why this is needed**: `compile_commands.json` is generated inside the inner build directory (`CTK-build/`). Clangd searches upward from any source file looking for `compile_commands.json` at a directory boundary. Without the symlink at the repo root, clangd falls back to system headers only, producing cascading false errors.

### Step 8: Report and next steps

Report:
1. Build directory path
2. Qt version detected and used
3. Compiler path
4. List of enabled CTK libraries
5. Remind user that configuration does NOT build — they need to run `/ctk-superbuild` for the first full build

**Next steps after successful configure:**
```
1. /ctk-superbuild        ← First full build (downloads all deps, builds CTK) ~30-60 min
2. /clazy-build           ← Incremental builds after source changes
3. /clazy-check level1    ← Run static analysis
4. /clazy-fix <check>     ← Fix specific check categories
```
After step 1 or 2 completes, also run the IDE setup from Step 7 above.

## Arguments

Optional arguments (positional or keyword):
- `qt5` — force Qt5 configuration (default: auto-detect)
- `qt6` — force Qt6 configuration
- `/path/to/src` — override CTK source directory (default: `~/src/CTK`)
- `/path/to/bld` — override build directory (default: `~/src/CTK/cmake-build-clazy`)
- `no-vtk` — disable VTK libraries (faster build, skips ctkVisualization*)

Examples:
- `/clazy-configure` — auto-detect Qt, use defaults
- `/clazy-configure qt6` — force Qt6
- `/clazy-configure qt5 /opt/ctk /opt/ctk-build` — custom paths with Qt5
- `/clazy-configure no-vtk` — skip VTK (faster, less comprehensive analysis)

## Platform-Specific Notes

### macOS ARM64 (Apple Silicon)

The Homebrew LLVM + clazy combination works well on ARM64. Key points:
- `brew install llvm` installs to `/opt/homebrew/opt/llvm/` (not `/usr/local/opt/llvm/`)
- The CommandLineTools SDK at `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk` avoids the Xcode.app SDK which has different header paths
- Qt6 from Homebrew (`brew install qt`) is ARM64-native
- Qt5 from Homebrew (`brew install qt@5`) is also ARM64-native as of Qt 5.15.8+

### macOS Intel (x86_64)

Same as ARM64 but Homebrew paths are `/usr/local/opt/` instead of `/opt/homebrew/opt/`.

### Linux (Ubuntu 22.04+)

```bash
# Install clazy (may need LLVM apt repository for newer versions)
wget https://apt.llvm.org/llvm.sh && chmod +x llvm.sh && sudo ./llvm.sh 17
sudo apt-get install clazy

# No CMAKE_OSX_SYSROOT needed
# No macOS-specific flags
```

### Windows

On Windows, the configure command changes:
```bat
cmake -G "Ninja" ^
  -DCMAKE_C_COMPILER=clang-cl ^
  -DCMAKE_CXX_COMPILER=clang-cl ^
  -DCMAKE_BUILD_TYPE=Debug ^
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON ^
  [... CTK options ...]
```
Note: `compile_commands.json` on Windows uses backslash paths — `clazy-standalone` handles this correctly.

## Slicer Compatibility Notes

The enabled libraries match what 3D Slicer builds against CTK:

| CTK Library | Slicer Usage |
|-------------|-------------|
| `Core` | ctkCallback, ctkErrorLogModel, ctkJobScheduler, settings |
| `Widgets` | ~100 custom Qt widgets used throughout Slicer UI |
| `DICOM/Core` | DICOM database, indexer, scheduler |
| `DICOM/Widgets` | Slicer's DICOM browser and visual browser |
| `PluginFramework` | OSGi service registry (used by Slicer's module system) |
| `Scripting/Python/Core` | PythonQt scripting infrastructure |
| `Scripting/Python/Widgets` | Python console widget |
| `Visualization/VTK/Core` | VTK/CTK bridge utilities |
| `Visualization/VTK/Widgets` | VTK rendering widgets (slice views, volume rendering) |
| `ImageProcessing/ITK/Core` | ITK error log integration |

Libraries intentionally **NOT** enabled (not used by Slicer):
- `XNAT/Core`, `XNAT/Widgets` — XNAT server integration (niche use)
- `CommandLineModules` — CLI wrapping (not part of Slicer's CTK usage)

## Reconfiguring

To change Qt version or add/remove libraries without a full rebuild:

```bash
# Reconfigure in-place (fast — only changed options are updated)
cmake -B ~/src/CTK/cmake-build-clazy \
  -DCTK_QT_VERSION:STRING=6 \
  -DCTK_LIB_XNAT/Core:BOOL=ON
```

CMake's superbuild will detect the changed options and reconfigure only the affected external projects.

To fully reset (delete all build artifacts):
```bash
rm -rf ~/src/CTK/cmake-build-clazy
/clazy-configure   # re-run this skill
/ctk-superbuild    # full rebuild (~30-60 min)
```
