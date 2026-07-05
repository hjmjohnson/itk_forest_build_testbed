#!/usr/bin/env bash
# setup-itk-downstream-testbed.sh
#
# Build engine for the ITK downstream-breakage testbed. Checks out every
# open-source ITK consumer, instruments all builds with ccache, and builds them
# against one locally built ITK (USE_SYSTEM_ITK). Point the ITK worktree at any
# ITK ref under test (a PR, branch, tag, or SHA) with `repoint-itk`, then rebuild
# the forest to prove the change does not break downstream consumers.
#
# Pixi (pixi.toml at the repo root) drives the dependency graph:
#   pixi run build-elastix  -> builds ITK then elastix
#   pixi run build-Slicer   -> builds ITK then Slicer
#   pixi run build-remotes  -> builds ITK then all ITK remote modules (external)
# This script is the worker invoked by those tasks; it can also run standalone.
#
# Self-contained: needs only git, cmake, ninja, ccache, a C++ compiler (all
# provided by the pixi env). No local-machine state assumed. Linux + macOS.
#
# Commands:
#   checkout [name...]     create worktrees/clones (default: all)
#   configure <name>       cmake-configure one project
#   build <name>           configure (if needed) + build one project
#   build-all              build every consumer in dependency order
#   remotes                build all ITK remote modules (external, system-ITK)
#   repoint-itk            move the ITK worktree to ITK_REF (PR/branch/tag/SHA)
#   list                   print every known project + category
#   status                 ccache + worktree state
#
# Layout: this script lives in <repo>/bin; all source checkouts and build trees
# go under <repo>/build_forest (git-ignored). TESTBED is the repo root, FOREST is
# the artifact dir.
#
# Env overrides (defaults): SRC_ROOT=~/src  TESTBED=<repo root (parent of bin/)>
#   FOREST=$TESTBED/build_forest  ITK_REF=origin/main  CCACHE_DIR=~/.ccache
#   JOBS=(nproc)  CC/CXX=(auto/pixi)  HEAVY=0 (1 to include CUDA/Java/wasm remotes)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTBED="${TESTBED:-$(dirname "${SCRIPT_DIR}")}"   # repo root = parent of bin/
KIT_PRESETS="${SCRIPT_DIR%/bin}/cmake/presets"   # SCRIPT_DIR is .../kit/bin

# Bridge to versions.toml (the build-version source of truth): emit component
# rows, scalar pins, or (re)write a forest manifest. See bin/config.py.
cfg(){ python3 "${SCRIPT_DIR}/config.py" "$@"; }

# Node-specific config: source config.sh (git-ignored), generating it from the
# tracked config.json.in on first run. Each config.sh line is ${KEY:=default},
# so env vars set before invocation always win (env > config.sh > built-ins).
CONFIG_SH="${TESTBED}/config.sh"
if [ ! -f "${CONFIG_SH}" ] && command -v python3 >/dev/null 2>&1; then
  python3 "${SCRIPT_DIR}/config.py" generate >/dev/null 2>&1 || true
fi
# shellcheck disable=SC1090
[ -f "${CONFIG_SH}" ] && . "${CONFIG_SH}"

SRC_ROOT="${SRC_ROOT:-${HOME}/src}"
# Central FULL clones of every forest repo (never shallow). Each build_forest
# tree is a git worktree off the matching clone here. Override FOREST_GIT_REPOS.
REPOS="${FOREST_GIT_REPOS:-${TESTBED}/forest_git_repos}"
# build_forest root: config BUILD_FOREST_ROOT (default 'build_forest'); a
# relative value resolves against the repo root, an absolute value is used as-is.
BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT:-build_forest}"
# FOREST_REFERENCE_SUFFIX selects an alternate forest (build_forest-<suffix>)
# for side-by-side scenario comparisons against the default build_forest.
[ -n "${FOREST_REFERENCE_SUFFIX:-}" ] && BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT}-${FOREST_REFERENCE_SUFFIX}"
case "${BUILD_FOREST_ROOT}" in
  /*) FOREST="${FOREST:-${BUILD_FOREST_ROOT}}" ;;
  *)  FOREST="${FOREST:-${TESTBED}/${BUILD_FOREST_ROOT}}" ;;
esac
# All logs for a forest live inside that forest (never the kit root).
forest_log_dir(){ mkdir -p "${FOREST}/logs"; echo "${FOREST}/logs"; }
export CCACHE_DIR="${CCACHE_DIR:-${HOME}/.ccache}"
# ccache basedir policy (HYBRID; the shell is the single authority — presets do
# not set CCACHE_BASEDIR, because the rule is per-package-CLASS which preset
# macros cannot express reliably). basedir rewrites absolute paths UNDER it to
# relative before hashing, so cache is shared across forests wherever a forest
# lives; NOHASHDIR drops the CWD.
#   - Forest-wide (${FOREST}) — the default here, and the basedir for CONSUMERS
#     and SUPERBUILDS: it rewrites every forest-internal path, so a consumer's
#     sibling refs (#include ${FOREST}/ITK/...) and SuperBuild EP trees
#     (${FOREST}/<pkg>-build/VTK ...) — both OUTSIDE the package's own source —
#     still canonicalize and share across forests.
#   - Per-package (${FOREST}/<pkg>) — applied in build_one ONLY for the
#     self-contained ROOT builds in CCACHE_PERPKG_ROOTS (ITK): they reference
#     nothing outside their own source except the stable-path conda env, so a
#     tighter basedir also shares cache with standalone builds of that package.
# -ffile-prefix-map stays per-package (${sourceDir}) for every package (set by
# the preset); ccache canonicalizes that flag under whichever basedir applies.
CCACHE_PERPKG_ROOTS="${CCACHE_PERPKG_ROOTS:-ITK}"
export CCACHE_BASEDIR="${CCACHE_BASEDIR:-${FOREST}}"
export CCACHE_NOHASHDIR="${CCACHE_NOHASHDIR:-true}"
# CMake 4.x hard-rejects projects/ExternalProjects that declare
# cmake_minimum_required(VERSION <3.5) (e.g. the googletest bundled by
# ITKCleaver, whose CMake-4 fix PR #77 was abandoned upstream). The env var —
# unlike a top-level -D — propagates into nested EP configures that fail.
export CMAKE_POLICY_VERSION_MINIMUM="${CMAKE_POLICY_VERSION_MINIMUM:-3.5}"
HEAVY="${HEAVY:-0}"
# ITK ref under test: any branch, tag, SHA, remote ref (e.g. upstream/main), or
# GitHub PR shorthand (pr/NNNN -> pull/NNNN/head). `repoint-itk` moves the ITK
# worktree here; the rest of the forest then rebuilds against it.
ITK_REF="${ITK_REF:-$(cfg get components.ITK.ref)}"

if command -v nproc >/dev/null 2>&1; then JOBS="${JOBS:-$(nproc)}"
elif command -v sysctl >/dev/null 2>&1; then JOBS="${JOBS:-$(sysctl -n hw.ncpu)}"
else JOBS="${JOBS:-4}"; fi

# Force the conda toolchain for EVERY build (including SuperBuild ExternalProjects
# such as Slicer's VTK/ITK/Python); never the system or Homebrew compilers. Under
# `pixi run`, conda activation already sets CC/CXX to the env's conda compilers;
# prefer those and override anything pointing outside ${CONDA_PREFIX}. Exported so
# child ExternalProject configures inherit them.
if [ -n "${CONDA_PREFIX:-}" ]; then
  case "${CC:-}" in "${CONDA_PREFIX}"/*) : ;;
    *) for _c in "${CONDA_PREFIX}"/bin/*-cc "${CONDA_PREFIX}"/bin/clang "${CONDA_PREFIX}"/bin/gcc; do
         [ -x "${_c}" ] && { CC="${_c}"; break; }; done ;; esac
  case "${CXX:-}" in "${CONDA_PREFIX}"/*) : ;;
    *) for _x in "${CONDA_PREFIX}"/bin/*-c++ "${CONDA_PREFIX}"/bin/clang++ "${CONDA_PREFIX}"/bin/g++; do
         [ -x "${_x}" ] && { CXX="${_x}"; break; }; done ;; esac
  unset _c _x
fi
: "${CC:=$(command -v cc || command -v clang || command -v gcc)}"
: "${CXX:=$(command -v c++ || command -v clang++ || command -v g++)}"
export CC CXX
# Bake ${CONDA_PREFIX}/lib as a link-time rpath into every binary so the conda
# libc++/libc++abi/libstdc++ resolve at run time without DYLD_/LD_LIBRARY_PATH.
# Exported via LDFLAGS (which CMake seeds CMAKE_*_LINKER_FLAGS from on every
# configure) so it reaches SuperBuild inner ExternalProjects too, where a
# top-level -DCMAKE_BUILD_RPATH does not. Idempotent: skip if already present.
if [ -n "${CONDA_PREFIX:-}" ]; then
  case " ${LDFLAGS:-} " in *"-rpath,${CONDA_PREFIX}/lib "*|*"-rpath,${CONDA_PREFIX}/lib") : ;;
    *) export LDFLAGS="-Wl,-rpath,${CONDA_PREFIX}/lib${LDFLAGS:+ ${LDFLAGS}}" ;; esac
fi
# Never the Homebrew toolchain (its packages are built with a different
# compiler and ABI-mismatch the conda-forge stack). Conda-forge runtime libs
# (fftw, qt, ...) are fine; only the Homebrew *compilers* are rejected.
case "${CC}:${CXX}" in
  */opt/homebrew/*|*/usr/local/opt/*|*/usr/local/Cellar/*|*/homebrew/*)
    printf '\033[1;31m[err]\033[0m Homebrew compiler refused (CC=%s CXX=%s); run under "pixi run" or set CC/CXX to the conda toolchain\n' "${CC}" "${CXX}" >&2
    exit 1 ;;
esac

# Slicer needs a real Qt6 (its SuperBuild builds VTK/CTK against it). On macOS a
# Homebrew qt@6 on PATH shadows a user Qt: its host-tools (Qt6CoreTools, ...) get
# found from Homebrew while Qt6 itself comes from ~/Qt, which fails Qt6 package
# configuration. Prefer ~/Qt/<ver>/macos and drop Homebrew qt@6 from PATH so Qt6
# and its host-tools resolve consistently for both configure and build.
SLICER_QT_VERSION="${SLICER_QT_VERSION:-$(cfg get toolchain.slicer_qt_version)}"
# Official Qt installer platform subdir: macos on Darwin, gcc_64 on Linux.
case "$(uname -s)" in Darwin) _QT_PLAT="${QT_PLATFORM_SUBDIR:-macos}" ;; *) _QT_PLAT="${QT_PLATFORM_SUBDIR:-gcc_64}" ;; esac
# Prefer the node config's QT6_DIR; fall back to the version-derived path.
SLICER_QT_PREFIX="${SLICER_QT_PREFIX:-${QT6_DIR:-${HOME}/Qt/${SLICER_QT_VERSION}/${_QT_PLAT}}}"
# Fallback: if the pinned Qt isn't installed, pick the newest ~/Qt/6.*/${_QT_PLAT}
# that has a Qt6 config (override with SLICER_QT_PREFIX or SLICER_QT_VERSION).
if [ ! -d "${SLICER_QT_PREFIX}/lib/cmake/Qt6" ]; then
  for _q in $(ls -d "${HOME}"/Qt/6.*/"${_QT_PLAT}" 2>/dev/null | sort -Vr); do
    [ -d "${_q}/lib/cmake/Qt6" ] && { SLICER_QT_PREFIX="${_q}"; break; }
  done
  unset _q
fi
if [ "$(uname -s)" = Darwin ]; then
  PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -v '/opt/homebrew/opt/qt@6/bin' | paste -sd: -)"
  export PATH
  # Export (not just -D) so Slicer's ExternalProject sub-configures (VTK, ITK)
  # inherit it: prefer ~/Qt and drop any Homebrew qt@6 entry.
  if [ -d "${SLICER_QT_PREFIX}/lib/cmake/Qt6" ]; then
    _cpp="$(printf '%s' "${CMAKE_PREFIX_PATH:-}" | tr ':' '\n' | grep -v '/opt/homebrew/opt/qt@6' | paste -sd: - || true)"
    export CMAKE_PREFIX_PATH="${SLICER_QT_PREFIX}${_cpp:+:${_cpp}}"
    unset _cpp
  fi
fi

# pixi/conda activation injects CFLAGS/CPPFLAGS/LDFLAGS that add the conda env's
# include/lib to every compile. That leaks libintl.h (gettext) etc. into Slicer's
# bundled CPython, which then detects gettext but fails to link -lintl. All real
# deps are passed explicitly via -D flags, so drop these contaminating flags.
unset CFLAGS CPPFLAGS CXXFLAGS LDFLAGS CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH

# The unset above dropped the conda rpath along with the contaminating -I/-L
# flags. Re-export LDFLAGS with ONLY the rpath (no include/lib leakage), so the
# conda libc++/fftw resolve at run and build time — including SuperBuild inner
# ExternalProjects, where a top-level -DCMAKE_BUILD_RPATH does not reach the
# build-time tools (GenerateCLP, gtest_discover_tests) that ninja spawns.
[ -n "${CONDA_PREFIX:-}" ] && export LDFLAGS="-Wl,-rpath,${CONDA_PREFIX}/lib"

# Forest toolchain via the CMAKE_TOOLCHAIN_FILE *environment* variable (CMake
# 3.21+). Unlike a -D cache var or mark_as_superbuild (which SuperBuild inner EPs
# like Slicer's python-cmake-buildsystem do not consume), an env var is inherited
# by every EP sub-configure at every nesting level. The toolchain carries
# CMAKE_IGNORE_PREFIX_PATH=/opt/homebrew (keeps inner EPs off the Homebrew tree —
# else Slicer's CPython links Homebrew libintl's _libintl_* with no -lintl) and
# the conda build rpath. A project that sets its own -DCMAKE_TOOLCHAIN_FILE still
# wins for itself; EPs without one fall back to this env default.
export CMAKE_TOOLCHAIN_FILE="${TESTBED}/cmake/forest-toolchain.cmake"

# Forest-level build/install tree locations. Task-2 flips these two bodies to
# the nested layout; every caller goes through them so the change is one place.
build_dir(){   echo "${FOREST}/${1}/build"; }
install_dir(){ echo "${FOREST}/installed/${1}"; }   # install already uses installed/ target

ITK_BUILD="$(build_dir ITK)"       # ITK build tree
ITK_INSTALL="$(install_dir ITK)"   # installed ITK tree (consumers use this when ITK_USE_INSTALL=1)

# Consumers point ITK_DIR at the ITK build tree; it ships all CMake helper
# modules the install tree omits. Set ITK_USE_INSTALL=1 to use the install tree.
itk_dir(){
  if [ "${ITK_USE_INSTALL:-0}" = 1 ]; then
    local d; d="$(echo "${ITK_INSTALL}"/lib/cmake/ITK-* 2>/dev/null)"
    [ -f "${d}/ITKConfig.cmake" ] && { echo "${d}"; return; }
  fi
  echo "${ITK_BUILD}"; }

# nvcc is frequently installed outside PATH (/usr/local/cuda*/bin); find it so
# CMake's check_language(CUDA) succeeds and VkFFT can use the CUDA backend.
_find_nvcc(){
  command -v nvcc 2>/dev/null && return
  local c
  for c in /usr/local/cuda/bin/nvcc $(ls -d /usr/local/cuda-*/bin/nvcc 2>/dev/null | sort -Vr); do
    [ -x "$c" ] && { echo "$c"; return; }
  done; }

# VkFFT compute backend for this host: 1=CUDA, 5=Metal (macOS arm), 3=OpenCL;
# empty => no GPU backend (skip). Override with VKFFT_BACKEND.
vkfft_backend(){
  [ -n "${VKFFT_BACKEND:-}" ] && { echo "${VKFFT_BACKEND}"; return; }
  [ -n "$(_find_nvcc)" ] && { echo 1; return; }
  [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] && { echo 5; return; }
  { ls /usr/lib/*/libOpenCL.so* /usr/lib/libOpenCL.so* >/dev/null 2>&1 || [ -n "${OpenCL_LIBRARY:-}" ]; } \
    && { echo 3; return; }
  echo ""; }

# A rendering-capable VTK (vtk-config.cmake) for consumers that need one
# (vtkAddon/IGSIO/PlusLib/OpenIGTLinkIO require RenderingOpenGL2). Slicer's VTK
# (full + Qt) qualifies; BRAINSTools' VTK is headless and is NOT used here.
# Override with VTK_DIR (must point at a rendering-enabled VTK).
vtk_dir(){
  local d
  for d in "${VTK_DIR:-}" "${FOREST}/Slicer-build/VTK-build"; do
    [ -n "$d" ] && [ -f "${d}/vtk-config.cmake" ] && { echo "$d"; return; }
  done
  find "${FOREST}/Slicer-build" -maxdepth 3 -name vtk-config.cmake 2>/dev/null \
    | grep -v CMakeFiles | head -1 | xargs -r dirname; }

# Major version of the forest's ITK (from its source itkVersion.cmake). Empty
# if not checked out yet.
forest_itk_major(){
  grep -oE 'ITK_VERSION_MAJOR[^0-9]*[0-9]+' "${FOREST}/ITK/CMake/itkVersion.cmake" 2>/dev/null \
    | grep -oE '[0-9]+$' | head -1; }

# Hard requirement: ANTs master needs ITK v6+. ANTs dropped ITK5 in PR #1933
# ("ITK 6", merged 2026-03-15: External_ITKv5.cmake -> External_ITKv6.cmake,
# find_package(ITK 6 REQUIRED)). The last ITK5 ANTs master was ITK 5.4.3
# (2025-04-02). Fail fast on an ITK<6 forest rather than deep in the build.
require_itk6_for_ants(){
  local m; m="$(forest_itk_major)"
  [ -z "${m}" ] && return 0
  [ "${m}" -ge 6 ] && return 0
  # Escape hatch for building a pinned pre-2026-03-15 ANTs (last ITK5 mainline
  # was 9d0ecf098) against an ITK5 forest. Caller must have checked out an
  # ITK5-compatible ANTs worktree; modern ANTs master will still fail here.
  [ "${ANTS_ALLOW_ITK5:-0}" = 1 ] && { warn "ANTS_ALLOW_ITK5=1: building ANTs against ITK v${m} (caller pinned an ITK5-compatible ANTs)"; return 0; }
  die "ANTs requires ITK v6+, but this forest's ITK is v${m}.
  ANTs master dropped ITK5 in PR #1933 (merged 2026-03-15). Build ANTs only
  against an ITKv6 forest (e.g. BUILD_FOREST_ROOT=build_forest-itkv6_main), or
  pin a pre-2026-03-15 ANTs (<= ITK 5.4.3) via BRAINSTools_ANTs_GIT_TAG /
  External_ANTs GIT_TAG if an ITK5 build is required."
}

# A VTK for ITK's ITKVtkGlue bridge. Prefer a rendering VTK (vtk_dir); else
# reuse the BRAINSTools VTK (its OpenGL2 backend satisfies ITKVtkGlue). Empty
# when no forest VTK exists yet (fresh forest: ITK builds without VtkGlue, a
# later ITK pass picks it up once a consumer's VTK is built).
itk_vtk_dir(){
  local d
  # Prefer the dedicated full-rendering+Qt forest VTK (shared by ITK's
  # ITKVtkGlue and all consumers); then a Slicer/override VTK; then the
  # headless BRAINSTools VTK as a last resort.
  for d in "${ITK_VTK_DIR:-}" "$(build_dir VTK)" "$(vtk_dir)" \
           "${FOREST}/BRAINSTools-build/VTK-Release-build"; do
    [ -n "$d" ] && [ -f "${d}/vtk-config.cmake" ] && { echo "$d"; return; }
  done; return 0; }

# Built OpenIGTLink / OpenIGTLinkIO (the IGT comms stack PlusLib requires).
openigtlink_dir(){
  local d="${OpenIGTLink_DIR:-$(build_dir OpenIGTLink)}"
  [ -f "${d}/OpenIGTLinkConfig.cmake" ] && { echo "$d"; return; }
  find "$(build_dir OpenIGTLink)" -maxdepth 2 -name OpenIGTLinkConfig.cmake 2>/dev/null | head -1 | xargs -r dirname; }
openigtlinkio_dir(){
  local d="${OpenIGTLinkIO_DIR:-$(build_dir OpenIGTLinkIO)}"
  [ -f "${d}/OpenIGTLinkIOConfig.cmake" ] && { echo "$d"; return; }
  find "$(build_dir OpenIGTLinkIO)" -maxdepth 2 -name OpenIGTLinkIOConfig.cmake 2>/dev/null | head -1 | xargs -r dirname; }

# An already-built vtkAddon (config file) that IGSIO consumes; override with vtkAddon_DIR.
vtkaddon_dir(){
  local d="${vtkAddon_DIR:-$(build_dir vtkAddon)}"
  { [ -f "${d}/vtkAddonConfig.cmake" ] || [ -f "${d}/vtkAddon-config.cmake" ]; } && { echo "$d"; return; }
  find "$(build_dir vtkAddon)" -maxdepth 2 \( -name vtkAddonConfig.cmake -o -name vtkAddon-config.cmake \) 2>/dev/null | head -1 | xargs -r dirname; }

# An already-built IGSIO (IGSIOConfig.cmake) that PlusLib consumes; override with IGSIO_DIR.
igsio_dir(){
  local d="${IGSIO_DIR:-$(build_dir IGSIO)}"
  [ -f "${d}/IGSIOConfig.cmake" ] && { echo "$d"; return; }
  find "$(build_dir IGSIO)" -maxdepth 2 -name IGSIOConfig.cmake 2>/dev/null | head -1 | xargs -r dirname; }

# --- main consumers (name | git URL | worktree branch) — from versions.toml
mapfile -t CONSUMERS < <(cfg consumers)
# Curated, ITK-exercising subset of Slicer extensions built against the
# locally built Slicer (Slicer_DIR). Each name is a <name>.json descriptor in
# the ExtensionsIndex checkout. Add more here to widen coverage.
# Override the set with SLICER_EXTENSIONS_OVERRIDE (space-separated names) or
# SLICER_EXTENSIONS_FILE (one name per line) to widen coverage.
if [ -n "${SLICER_EXTENSIONS_FILE:-}" ] && [ -f "${SLICER_EXTENSIONS_FILE}" ]; then
  SLICER_EXTENSIONS=(); while read -r _e; do [ -n "$_e" ] && SLICER_EXTENSIONS+=("$_e"); done < "${SLICER_EXTENSIONS_FILE}"; unset _e
elif [ -n "${SLICER_EXTENSIONS_OVERRIDE:-}" ]; then
  read -ra SLICER_EXTENSIONS <<< "${SLICER_EXTENSIONS_OVERRIDE}"
else
  SLICER_EXTENSIONS=(BoneTextureExtension AnomalousFiltersExtension SlicerElastix
                     SlicerRT SlicerIGSIO SlicerANTs)
fi
# --- ITK remote modules, built EXTERNALLY against system ITK (name | URL | heavy?)
#     from versions.toml (kind = "remote")
mapfile -t REMOTES < <(cfg remotes)
BUILD_ORDER=(ITK ANTs BRAINSTools Slicer SlicerExtensions elastix c3d MITK SimpleITK)

log(){ printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }
require(){ for t in "$@"; do command -v "$t" >/dev/null 2>&1 || die "missing tool: $t"; done; }

row_for(){ # name -> "kind|url|branch_or_heavy"
  local n="$1" r
  for r in "${CONSUMERS[@]}"; do IFS='|' read -r nm url br <<<"$r"; [ "$nm" = "$n" ] && { echo "consumer|$url|$br"; return; }; done
  for r in "${REMOTES[@]}";   do IFS='|' read -r nm url hv <<<"$r"; [ "$nm" = "$n" ] && { echo "remote|$url|$hv";  return; }; done
  return 1
}
all_names(){ for r in "${CONSUMERS[@]}" "${REMOTES[@]}"; do echo "${r%%|*}"; done; }

common_cmake_args(){
  # CMAKE_IGNORE_PREFIX_PATH=/opt/homebrew keeps every find_package/find_library
  # off the Homebrew tree (its libs ABI-mismatch the conda-forge stack); the
  # conda-forge equivalents (fftw, ...) are found under ${CONDA_PREFIX}.
  # -ffile-prefix-map=${FOREST}=. canonicalizes embedded __FILE__/debug paths to
  # forest-relative so objects are byte-identical across forests (reproducible +
  # cross-forest ccache reuse). _INIT seeds the flags without clobbering
  # project-set CMAKE_<LANG>_FLAGS.
  # CMAKE_BUILD_RPATH=${CONDA_PREFIX}/lib: gtest_discover_tests runs each driver
  # at build time to enumerate tests; the drivers link conda FFTW, and ninja is
  # hardened-runtime-signed so it strips DYLD_* from spawned processes (the
  # DYLD_FALLBACK export alone is insufficient). Baking the conda libdir into the
  # build rpath lets @rpath/libfftw3*.dylib resolve at discovery and at test time.
  printf '%s ' -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
    -DCMAKE_C_COMPILER="${CC}" -DCMAKE_CXX_COMPILER="${CXX}" \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    "-DCMAKE_C_FLAGS_INIT=-ffile-prefix-map=${s:-${FOREST}}=." \
    "-DCMAKE_CXX_FLAGS_INIT=-ffile-prefix-map=${s:-${FOREST}}=." \
    "-DCMAKE_BUILD_RPATH=${CONDA_PREFIX}/lib" \
    -DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew
}

# do_overlay NAME PRESET SRC BIN [KEY=VAL ...]
#   Resolve the kit preset chain into a flattened, self-contained
#   CMakeUserPresets.json in SRC (no include back to the kit) and a matching
#   [config.NAME] record in the forest manifest, then configure via cmake.
do_overlay(){
  local name="$1" preset="$2" src="$3" bin="$4"; shift 4
  cfg resolve-overlay "${preset}" "${src}" "${bin}" "${FOREST}" "${name}" "$@"
  cmake -S "${src}" --preset "forest-${name}-local"
}

# Reuse the forest's already-built standalone ANTs (consumed via
# find_package(ANTS)) so BRAINSTools doesn't rebuild its own. Emits the flags
# only when that ANTs config exists; a no-op otherwise and on BRAINSTools mains
# without USE_SYSTEM_ANTs (BRAINSia/BRAINSTools#606).
ants_system_args(){
  # BT_NO_SYSTEM_ANTS=1 forces BRAINSTools to build its own ANTs.
  [ "${BT_NO_SYSTEM_ANTS:-0}" = 1 ] && { printf '%s ' -DUSE_SYSTEM_ANTs=OFF; return 0; }
  # ANTSConfig.cmake lives directly in the build dir with ANTS_SUPERBUILD=OFF,
  # or under ANTS-build with the SuperBuild layout.
  local c="" d
  for d in "$(build_dir ANTs)" "$(build_dir ANTs)/ANTS-build"; do
    [ -f "${d}/ANTSConfig.cmake" ] && { c="${d}"; break; }
  done
  [ -n "${c}" ] || return 0
  # ANTSConfig's set_and_check requires <prefix>/include/ANTs to exist, but the
  # build-tree export mis-computes <prefix> (BRAINSia/BRAINSTools#606). Create
  # the dir so find_package(ANTS) succeeds; real headers come from the
  # ANTS::antsUtilities target's interface includes, not this legacy variable.
  mkdir -p "${FOREST}/ANTs/include/ANTs" "${c}/include/ANTs"
  printf '%s ' -DUSE_SYSTEM_ANTs=ON "-DANTS_DIR=${c}"
}

# Full clone of one repo into the central forest_git_repos store (fetched if it
# already exists). NEVER shallow. A clean clone from the URL (no --reference) so
# the clone's object store is self-contained and integrity-checked.
ensure_repo(){
  local name="$1" url="$2" repo="${REPOS}/${name}"
  if [ -d "${repo}/.git" ]; then
    git -C "${repo}" fetch --all --tags --prune --quiet 2>/dev/null \
      || warn "${name}: fetch failed (using cached objects)"
    return 0
  fi
  mkdir -p "${REPOS}"
  log "${name}: full clone ${url} -> forest_git_repos/${name}"
  git clone "${url}" "${repo}"
}

# Default branch of the central clone (origin/HEAD, else origin/main|master).
_repo_base(){
  local repo="$1" b
  b="$(git -C "${repo}" symbolic-ref --short -q refs/remotes/origin/HEAD || true)"
  [ -n "${b}" ] && { echo "${b}"; return; }
  for b in origin/main origin/master; do
    git -C "${repo}" show-ref --verify --quiet "refs/remotes/${b}" && { echo "${b}"; return; }
  done
}

# A build_forest tree is a git worktree off the central full clone. Each tree
# gets its own branch (a branch lives in one worktree only), suffixed per
# scenario forest; consumers carry their patch-branch name, remotes get one
# synthesized. New branches start at the clone's default branch.
# Plastimatch is built from a maintained ITKv6-support branch on a fork (carries
# the ITKv6 + portability fixes), NOT upstream master. Override via env.
PLM_FORK_REMOTE="${PLM_FORK_REMOTE:-$(cfg get subbuild.Plastimatch.fork_remote)}"
PLM_FORK_URL="${PLM_FORK_URL:-$(cfg get subbuild.Plastimatch.fork_url)}"
PLM_FORK_REF="${PLM_FORK_REF:-$(cfg get subbuild.Plastimatch.fork_ref)}"

# ANTs (non-itkv5 forests) builds from a fork integration branch bundling the
# ITKv6 fix PRs; the skip_suffix forest keeps its own pinned ANTs. Override via env.
ANTS_FORK_REMOTE="${ANTS_FORK_REMOTE:-$(cfg get subbuild.ANTs.fork_remote)}"
ANTS_FORK_URL="${ANTS_FORK_URL:-$(cfg get subbuild.ANTs.fork_url)}"
ANTS_FORK_REF="${ANTS_FORK_REF:-$(cfg get subbuild.ANTs.fork_ref)}"
ANTS_FORK_SKIP_SUFFIX="${ANTS_FORK_SKIP_SUFFIX:-$(cfg get subbuild.ANTs.skip_suffix)}"

# Ensure the Plastimatch fork remote exists in the central clone and the
# ITKv6-support ref is fetched; returns the base ref the worktree should use.
_ensure_plastimatch_fork(){
  local repo="${REPOS}/Plastimatch"
  [ -d "${repo}/.git" ] || return 0
  git -C "${repo}" remote get-url "${PLM_FORK_REMOTE}" >/dev/null 2>&1 \
    || git -C "${repo}" remote add "${PLM_FORK_REMOTE}" "${PLM_FORK_URL}"
  git -C "${repo}" fetch "${PLM_FORK_REMOTE}" "${PLM_FORK_REF}" --quiet \
    || warn "Plastimatch: fetch ${PLM_FORK_REMOTE}/${PLM_FORK_REF} failed (using cached)"
}

# True when this forest should build ANTs from the fork integration branch
# (fork config present and this forest's suffix is not the skip_suffix).
_ants_use_fork(){
  [ -n "${ANTS_FORK_URL}" ] && [ -n "${ANTS_FORK_REF}" ] || return 1
  [ -n "${ANTS_FORK_SKIP_SUFFIX}" ] && [ "${FOREST_REFERENCE_SUFFIX:-}" = "${ANTS_FORK_SKIP_SUFFIX}" ] && return 1
  return 0
}

# Ensure the ANTs fork remote exists in the central clone and the integration
# ref is fetched, mirroring _ensure_plastimatch_fork.
_ensure_ants_fork(){
  local repo="${REPOS}/ANTs"
  [ -d "${repo}/.git" ] || return 0
  git -C "${repo}" remote get-url "${ANTS_FORK_REMOTE}" >/dev/null 2>&1 \
    || git -C "${repo}" remote add "${ANTS_FORK_REMOTE}" "${ANTS_FORK_URL}"
  git -C "${repo}" fetch "${ANTS_FORK_REMOTE}" "${ANTS_FORK_REF}" --quiet \
    || warn "ANTs: fetch ${ANTS_FORK_REMOTE}/${ANTS_FORK_REF} failed (using cached)"
}

checkout_one(){
  local name="$1" url="$2" branch="$3" dest="${FOREST}/$1"
  if [ -e "${dest}/.git" ]; then log "${name}: present (skip)"; return 0; fi
  ensure_repo "${name}" "${url}" || { warn "${name}: clone failed"; return 1; }
  local repo="${REPOS}/${name}"
  git -C "${repo}" worktree prune   # clear stale regs from removed/disposed forests
  # Per-scenario fork/demo-branch override: when this forest's suffix has a
  # versions.toml [scenarios.<suffix>.<name>] entry, build the component from the
  # fork's demo-<suffix> staging branch (assembled by the gh-demo-branch skill)
  # instead of the upstream default. Only affects the matching forest.
  if [ -n "${FOREST_REFERENCE_SUFFIX:-}" ]; then
    local _ov; _ov="$(cfg scenario "${FOREST_REFERENCE_SUFFIX}" "${name}" 2>/dev/null)"
    if [ -n "${_ov}" ]; then
      local ov_url ov_branch; IFS='|' read -r ov_url ov_branch <<<"${_ov}"
      log "${name}: scenario ${FOREST_REFERENCE_SUFFIX} -> ${ov_url} @ ${ov_branch}"
      git -C "${repo}" fetch --force "${ov_url}" "${ov_branch}:refs/demo/${name}-${ov_branch}" \
        || { warn "${name}: fetch demo branch ${ov_branch} from ${ov_url} failed"; return 1; }
      git -C "${repo}" worktree add -B "${ov_branch}" "${dest}" "refs/demo/${name}-${ov_branch}"
      return 0
    fi
  fi
  [ -z "${branch}" ] && branch="${name}-itk-downstream"
  branch="${branch}${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
  if [ "${name}" = Plastimatch ]; then
    # Plastimatch always (re)bases on the fork's ITKv6-support tip (-B forces
    # the branch to the fork ref even if a stale local branch exists).
    _ensure_plastimatch_fork
    log "Plastimatch: worktree (${branch} -> ${PLM_FORK_REMOTE}/${PLM_FORK_REF})"
    git -C "${repo}" worktree add -B "${branch}" "${dest}" "${PLM_FORK_REMOTE}/${PLM_FORK_REF}"
  elif [ "${name}" = ANTs ] && _ants_use_fork; then
    # Non-itkv5 forests (re)base ANTs on the fork integration branch tip.
    _ensure_ants_fork
    log "ANTs: worktree (${branch} -> ${ANTS_FORK_REMOTE}/${ANTS_FORK_REF})"
    git -C "${repo}" worktree add -B "${branch}" "${dest}" "${ANTS_FORK_REMOTE}/${ANTS_FORK_REF}"
  elif git -C "${repo}" show-ref --verify --quiet "refs/heads/${branch}"; then
    log "${name}: worktree (existing branch ${branch})"
    git -C "${repo}" worktree add "${dest}" "${branch}"
  else
    local base; base="$(_repo_base "${repo}")"
    [ -n "${base}" ] || { warn "${name}: no default branch in ${repo}"; return 1; }
    log "${name}: worktree (branch ${branch} off ${base})"
    git -C "${repo}" worktree add -b "${branch}" "${dest}" "${base}"
  fi
}

cmd_checkout(){ require git; mkdir -p "${FOREST}"
  local names=("$@"); [ ${#names[@]} -eq 0 ] && mapfile -t names < <(all_names)
  for n in "${names[@]}"; do
    local meta; meta="$(row_for "$n")" || { warn "unknown: $n"; continue; }
    IFS='|' read -r kind url br <<<"$meta"
    if [ "$kind" = remote ]; then
      [ "$br" = 1 ] && [ "${HEAVY}" != 1 ] && { log "$n: heavy (CUDA/Java/wasm); set HEAVY=1 to include (skip)"; continue; }
      checkout_one "$n" "$url" "" || warn "$n: checkout failed (skip)"
    else checkout_one "$n" "$url" "$br" || warn "$n: checkout failed (skip)"; fi
  done
  log "checkout dir: ${FOREST}"
  cfg manifest "${FOREST}" 2>/dev/null || warn "manifest write skipped"; }

cmd_repoint_itk(){ require git
  local itk="${FOREST}/ITK"
  [ -e "${itk}/.git" ] || die "ITK not checked out"   # .git is a FILE in a worktree
  local ref="${ITK_REF}" wt="itk-downstream${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
  log "move ITK worktree to ${ref}"
  git -C "${itk}" reset --hard --quiet   # clean tree so checkout can switch
  case "${ref}" in
    pr/*|pull/*)   # GitHub PR shorthand: pr/6250 -> pull/6250/head on ITK_PR_REMOTE
      local num="${ref##*/}"
      git -C "${itk}" fetch "${ITK_PR_REMOTE:-origin}" "pull/${num}/head" --quiet \
        || die "fetch PR ${num} from ${ITK_PR_REMOTE:-origin} failed"
      git -C "${itk}" checkout -f -B "${wt}" FETCH_HEAD ;;
    */*)           # remote ref (has a '/') -> fetch its remote first
      git -C "${itk}" fetch "${ref%%/*}" --quiet || warn "fetch ${ref%%/*} failed; using cached refs"
      git -C "${itk}" checkout -f -B "${wt}" "${ref}" ;;
    *)             # local branch / tag / SHA
      git -C "${itk}" checkout -f -B "${wt}" "${ref}" ;;
  esac
  warn "ITK now at ${ref}; run build-ITK then rebuild the downstream consumers"; }

# Some enabled remote modules (IOMeshMZ3, AnisotropicDiffusionLBR) ship a
# CMakeLists that calls itk_module_examples() but no examples/ dir, which is a
# fatal add_subdirectory error under BUILD_EXAMPLES=ON. Stub an empty
# examples/CMakeLists.txt for any such module so ITK configure completes.
_stub_remote_examples(){
  local src="${FOREST}/ITK" m cml
  for cml in "${src}"/Modules/*/*/CMakeLists.txt; do
    m="$(dirname "${cml}")"
    grep -q "itk_module_examples" "${cml}" 2>/dev/null || continue
    [ -d "${m}/examples" ] && continue
    mkdir -p "${m}/examples"
    printf '# Stub (itk_forest_build_testbed): module ships no examples/; satisfy itk_module_examples()\n' \
      > "${m}/examples/CMakeLists.txt"
    log "stubbed missing examples/ for $(basename "${m}")"
  done; }

# ITKDCMTK's ExternalProject exports INTERFACE_INCLUDE_DIRECTORIES pointing at
# ijg{8,12,16}/include paths that never exist (the real 12/16/8-bit IJG headers
# live in dcmjpeg/libijg{8,12,16}/). CMake rejects the dangling paths for every
# DCMTK consumer (elastix, ANTs, ...). Symlink each to the real header dir.
_fix_dcmtk_ijg_symlinks(){
  local ep="${ITK_BUILD}/Modules/ThirdParty/DCMTK/ITKDCMTK_ExtProject" n
  [ -d "${ep}/dcmjpeg" ] || return 0
  for n in 8 12 16; do
    [ -d "${ep}/dcmjpeg/libijg${n}" ] || continue
    mkdir -p "${ep}/ijg${n}"
    ln -snf "../dcmjpeg/libijg${n}" "${ep}/ijg${n}/include"
  done; }

# Several ANTs Utilities/Examples headers use ImageRegionIteratorWithIndex
# without including its header, relying on a transitive include Apple clang
# provides but GCC does not -> BRAINSTools fails to build on Linux/GCC. Add the
# missing include (after the first itk* include) to every offending file in
# every ANTs checkout in the forest (standalone + BRAINSTools' bundled ANTs).
# Recurring upstream-ANTs bug; pre-existing, not FFT.
# IGSIO sources use std::cout/cerr/endl relying on a transitive <iostream> that
# vtkSystemIncludes.h (VTK 9.6+) no longer provides; add the include where missing.
_patch_igsio_iostream(){
  local d="${FOREST}/IGSIO" f
  [ -d "${d}" ] || return 0
  while IFS= read -r f; do
    grep -qE '#include <iostream>' "${f}" && continue
    grep -qE 'std::(cout|cerr|endl)' "${f}" || continue
    perl -i -pe 'if (!$ins && /^#include/) { $_ = "#include <iostream>\n".$_; $ins=1 }' "${f}" \
      && log "patched IGSIO iostream: ${f#"${FOREST}/"}"
  done < <(grep -rlE 'std::(cout|cerr|endl)' "${d}" --include='*.cxx' --include='*.h' --include='*.hxx' 2>/dev/null)
}

# Plastimatch bundles dlib-19.1, whose unicode.h only defines unichar_traits for
# GCC <4.4 and otherwise uses std::basic_string<uint32>; modern libc++ has no
# char_traits<unsigned int>, so force the bundled traits path on all compilers.
_patch_plastimatch_dlib_unicode(){
  local f="${FOREST}/Plastimatch/libs/dlib-19.1/dlib/unicode/unicode.h"
  [ -f "${f}" ] || return 0
  grep -q "itk_forest_build_testbed" "${f}" && return 0
  perl -i -pe 's{^#if defined\(__GNUC__\) && __GNUC__ < 4 && __GNUC_MINOR__ < 4}{#if 1 // itk_forest_build_testbed: always use dlib unichar_traits (no char_traits<uint32> in libc++)}' "${f}" \
    && log "patched Plastimatch dlib unicode.h (unichar_traits)"
}

# Plastimatch's bundled demons_itk_insight includes vcl_legacy_aliases.h, removed
# from modern VXL. Drop a minimal shim (the bundled dir is on the include path)
# providing the vcl_* math aliases the bundled code uses.
_patch_plastimatch_vcl_aliases(){
  local d="${FOREST}/Plastimatch/libs/demons_itk_insight"
  [ -d "${d}" ] || return 0
  local f="${d}/vcl_legacy_aliases.h"
  grep -q "vnl_math_sqr" "${f}" 2>/dev/null && return 0
  cat > "${f}" <<'EOF'
// Shim (itk_forest_build_testbed): vcl_legacy_aliases.h and the free vnl_math_*
// functions were removed from modern VXL; map the legacy tokens the bundled
// demons code uses to their std:: / vnl_math:: replacements.
// Self-contained (no vnl/ include) so it is safe to force-include into every
// TU, including low-level libs without ITK/VNL on their include path.
#ifndef vcl_legacy_aliases_shim_h
#define vcl_legacy_aliases_shim_h
#include <cmath>
#include <algorithm>
#define vcl_abs std::abs
#define vcl_ceil std::ceil
#define vcl_fabs std::fabs
#define vcl_log std::log
#define vcl_pow std::pow
#define vcl_sqrt std::sqrt
#define vnl_math_abs std::abs
#define vnl_math_min std::min
#define vnl_math_sqr(x) ((x) * (x))
#endif
EOF
  log "added Plastimatch vcl_legacy_aliases.h shim"
}

# Register Plastimatch's bundled RANSAC sphere-estimator unit test (which drives
# vnl_levenberg_marquardt via GeometricLeastSquaresEstimate) with ctest; upstream
# never add_subdirectory's libs/ransac/Testing, so the test ships unbuilt.
_patch_plastimatch_ransac_test(){
  local cml="${FOREST}/Plastimatch/Testing/CMakeLists.txt"
  [ -f "${cml}" ] || return 0
  # Modern ITK's itkNewMacro expansion ends in a static_assert needing a ';';
  # the bundled header omits it (only surfaced now that the test compiles it).
  local hdr="${FOREST}/Plastimatch/libs/ransac/SphereParametersEstimator.h"
  [ -f "${hdr}" ] && perl -i -pe 's/^(\s*itkNewMacro\(\s*Self\s*\))\s*$/$1;/' "${hdr}"
  grep -qi "itk_forest_build_testbed: RANSAC" "${cml}" && return 0
  cat >> "${cml}" <<'EOF'

# itk_forest_build_testbed: RANSAC sphere-estimator unit test (vnl_levenberg_marquardt)
add_executable (ransac_sphere_estimator_test
  ${PLM_SOURCE_DIR}/libs/ransac/Testing/SphereParametersEstimatorTest.cxx)
target_include_directories (ransac_sphere_estimator_test PRIVATE
  ${PLM_SOURCE_DIR}/libs/ransac ${PLM_SOURCE_DIR}/libs/ransac/Common)
target_link_libraries (ransac_sphere_estimator_test ${ITK_LIBRARIES})
add_test (NAME ransac-sphere-estimator COMMAND ransac_sphere_estimator_test)
EOF
  log "registered Plastimatch RANSAC sphere-estimator ctest"
}

_patch_ants_missing_includes(){
  local a f
  while IFS= read -r a; do
    while IFS= read -r f; do
      grep -q '#include "itkImageRegionIteratorWithIndex.h"' "${f}" && continue
      grep -q "ImageRegionIteratorWithIndex" "${f}" || continue
      perl -0pi -e 's{(#include "itk[^"]+\.h"\n)}{$1#include "itkImageRegionIteratorWithIndex.h"\n}' "${f}" \
        && log "patched ANTs include: ${f#"${FOREST}/"}"
    done < <(find "${a}/Utilities" "${a}/Examples" \( -name '*.h' -o -name '*.hxx' \) 2>/dev/null)
  done < <(find "${FOREST}" -type d -name Utilities -path '*ANTs*' -exec dirname {} \; 2>/dev/null | sort -u)
}

# BRAINSTools' BRAINSConstellationDetector calls itksys::SystemTools::
# FindProgramPath(argv0, pathOut, errorMsg), removed from ITK's current KWSys.
# The modern equivalent is FindProgram(name) -> path ("" on failure). Rewrite the
# call in place. Pre-existing BRAINSTools-vs-ITK-KWSys skew, not FFT.
_patch_brainstools_kwsys(){
  local f
  while IFS= read -r f; do
    grep -q "FindProgramPath" "${f}" 2>/dev/null || continue
    perl -0pi -e 's{^(\s*)if \(!itksys::SystemTools::FindProgramPath\((argv\[0\]), (\w+), (\w+)\)\)$}{$1$3 = itksys::SystemTools::FindProgram($2);\n$1if ($3.empty())}mg' "${f}" \
      && log "patched BRAINSTools KWSys: ${f#"${FOREST}/"}"
  done < <(grep -rlE "itksys::SystemTools::FindProgramPath" "${FOREST}"/BRAINSTools* 2>/dev/null | grep -vE '/[A-Za-z]+-build/' )
}

# BRAINSABC links the legacy ${TBB_IMPORTED_TARGETS} variable, which modern
# oneTBB's TBBConfig does not set (it provides the TBB::tbb target). The empty
# variable means TBB's include never reaches BRAINSABC -> tbb/blocked_range.h not
# found on toolchains without TBB on the default path (GCC/conda). Link TBB::tbb.
_patch_brainstools_tbb(){
  local f
  # oneTBB's TBBConfig sets TBB::tbb's interface link to Threads::Threads at
  # config-load time, so find_package(Threads) MUST precede find_package(TBB)
  # (top level), or CMake errors "link interface ... contains Threads::Threads".
  for f in $(grep -rlE "find_package\(\s*TBB" "${FOREST}/BRAINSTools" 2>/dev/null | grep -vE '/[A-Za-z]+-build/'); do
    grep -q "find_package(Threads" "${f}" || {
      perl -0pi -e 's{^(\s*)(find_package\(\s*TBB)}{$1find_package(Threads REQUIRED)\n$1$2}m' "${f}"
      log "added find_package(Threads) before TBB in ${f#"${FOREST}/"}"; }
  done
  # BRAINSABC links the legacy ${TBB_IMPORTED_TARGETS} (unset by oneTBB); use the
  # modern TBB::tbb target so TBB's include reaches the compile.
  while IFS= read -r f; do
    grep -q "TBB::tbb" "${f}" || { perl -0pi -e 's{\$\{TBB_IMPORTED_TARGETS\}}{TBB::tbb}g' "${f}"; \
      log "linked TBB::tbb in ${f#"${FOREST}/"}"; }
  done < <(grep -rlE "TBB_IMPORTED_TARGETS" "${FOREST}/BRAINSTools" 2>/dev/null | grep -vE '/[A-Za-z]+-build/')
}

# The SuperBuild's inner BRAINSTools sub-build does not reliably pick up patches
# to its source CMakeLists/headers; force a cmake re-generate so the linkage and
# header changes above take effect on the next build.
_reconfigure_brainstools_inner(){
  local ib
  ib="$(find "${FOREST}/BRAINSTools-build" -maxdepth 1 -type d -name 'BRAINSTools-*-EP*-build' 2>/dev/null | head -1)"
  [ -n "${ib}" ] && [ -f "${ib}/CMakeCache.txt" ] && cmake "${ib}" >/dev/null 2>&1 || true
}

# BRAINSTools omits the trailing ';' after ITK exception/warning/debug macros
# (old ITK convention); current ITK macros require it -> "expected ';' before
# '}'". Add a ';' after each such invocation that lacks one, balanced-paren aware
# so multi-line calls terminate at the true close. Idempotent (negative
# lookahead skips calls that already end in ';').
_patch_brainstools_itk_macros(){
  local f
  while IFS= read -r f; do
    LC_ALL=C perl -0777 -pi -e \
      's{(itk(?:Generic)?\w*(?:Exception|Warning|Debug|Output)Macro\s*(\((?:[^()]++|(?2))*+\)))(?!\s*;)}{$1;}g' "${f}"
  done < <(grep -rlE "itk(Generic)?\w*(Exception|Warning|Debug|Output)Macro" "${FOREST}/BRAINSTools" \
             --include=*.cxx --include=*.h --include=*.hxx 2>/dev/null | grep -vE '/[A-Za-z]+-build/')
}

# SlicerExecutionModel's bundled tclap declares copy ctors with the
# injected-class-name plus explicit template args (MultiArg<T>(const ...)),
# which current GCC rejects ("remove the '< >'") and cascades into parse errors
# in BRAINSTools sources that include tclap. Drop the redundant <T> on the
# constructor name (the parameter's <T> stays).
_patch_sem_tclap(){
  local f
  while IFS= read -r f; do
    perl -0pi -e 's{^(\s*)([A-Za-z_]\w*)<T>(\(const )}{$1$2$3}mg' "${f}" \
      && log "patched tclap injected-class-name: ${f#"${FOREST}/"}"
  done < <(grep -rlE '^\s*[A-Za-z_]\w*<T>\(const ' "${FOREST}"/BRAINSTools-build/SlicerExecutionModel/tclap/ 2>/dev/null)
}

# Compat shim: some ITK-vendored third-party headers a few consumers still
# include (e.g. elastix's AffineLogTransform needs vnl/vnl_matrix_exp.h) are no
# longer shipped by recent ITK. Header-only files in bin/overlays/vnl/ are copied
# in only when absent, so the forest builds regardless of the ITK ref under test.
_overlay_vnl_headers(){
  local ov="${SCRIPT_DIR}/overlays/vnl" dst="${FOREST}/ITK/Modules/ThirdParty/VNL/src/vxl/core/vnl" f
  [ -d "${ov}" ] || return 0
  for f in "${ov}"/*; do
    [ -e "${f}" ] || continue
    [ -e "${dst}/$(basename "${f}")" ] || { cp "${f}" "${dst}/"; log "overlay vnl/$(basename "${f}")"; }
  done; }

# Build the dedicated full-rendering + Qt6 forest VTK shared by ITK's ITKVtkGlue
# and all VTK consumers (ANTs, Slicer, ...). Slicer VTK 9.6 source + Slicer-style
# module set + the same Qt6 Slicer uses (SLICER_QT_PREFIX). Run before ITK so
# itk_vtk_dir() resolves it. Idempotent: skips configure when build.ninja exists.
build_forest_vtk(){
  require cmake ninja ccache git
  local src="${FOREST}/VTK" b="$(build_dir VTK)"
  local tag="ddd10cf957df01f54eca6546e975e502ea248645" # slicer-v9.6.2-2026-05-15
  if [ ! -f "${src}/CMakeLists.txt" ]; then
    local existing="${FOREST}/BRAINSTools-build/VTK"
    if [ -f "${existing}/CMakeLists.txt" ]; then src="${existing}"
    else git clone https://github.com/slicer/VTK.git "${src}" \
         && git -C "${src}" checkout "${tag}"; fi
  fi
  [ -d "${SLICER_QT_PREFIX}/lib/cmake/Qt6" ] \
    || die "Qt6 not found at ${SLICER_QT_PREFIX} (set SLICER_QT_PREFIX/SLICER_QT_VERSION)"
  if [ ! -f "${b}/build.ninja" ]; then
    cmake -S "${src}" -B "${b}" $(common_cmake_args) \
      -DBUILD_SHARED_LIBS=ON -DVTK_BUILD_TESTING=OFF -DVTK_WRAP_PYTHON=OFF \
      -DVTK_SMP_IMPLEMENTATION_TYPE=Sequential -DVTK_USE_X=ON \
      -DVTK_GROUP_ENABLE_Qt=YES -DVTK_MODULE_ENABLE_VTK_GUISupportQt=YES \
      -DVTK_QT_VERSION=6 -DQt6_DIR="${SLICER_QT_PREFIX}/lib/cmake/Qt6" \
      -DCMAKE_PREFIX_PATH="${SLICER_QT_PREFIX}" \
      -DVTK_MODULE_ENABLE_VTK_ChartsCore=DONT_WANT \
      -DVTK_MODULE_ENABLE_VTK_ViewsContext2D=DONT_WANT \
      -DVTK_GROUP_ENABLE_Parallel=DONT_WANT \
      -DCMAKE_C_FLAGS="-Wno-error=implicit-function-declaration"
  fi
  cmake --build "${b}" -j"${JOBS}"
}

configure_one(){
  local name="$1" meta; meta="$(row_for "$name")" || die "unknown project: $name"
  local s="${FOREST}/${name}" b="$(build_dir "$name")"
  [ -d "$s" ] || die "${name} not checked out (run: pixi run checkout)"
  [ "$name" = ANTs ] && require_itk6_for_ants
  if [ "$name" = ITK ]; then
    local _itk_major
    _itk_major="$(grep -oE 'ITK_VERSION_MAJOR[^0-9]*[0-9]+' "${s}/CMake/itkVersion.cmake" 2>/dev/null | grep -oE '[0-9]+$' | head -1)"
    _overlay_vnl_headers
    if [ "${_itk_major:-6}" -lt 6 ]; then
      # v5 policy (module set, FFTW-on, testing/examples) lives in 10-itk-v5.json.
      local v5_preset="itk-forest-itk-v5"
      [ "${ITK_WITH_DCMTK:-0}" = 1 ] && v5_preset="itk-forest-itk-v5-dcmtk"
      do_overlay ITK "${v5_preset}" "$s" "${ITK_BUILD}"
      return
    fi
    # v6 policy (ALL_MODULES + excluded-from-all modules, FFTW-off/pocketFFT,
    # brainweb/testing/examples) lives in 10-itk-v6.json. VtkGlue is a variant
    # selected when a VTK exists; VTK_DIR is the only injected value.
    local itk_preset="itk-forest-itk-v6" itk_kvs=()
    local _itk_vtk; _itk_vtk="$(itk_vtk_dir)"
    if [ -n "${_itk_vtk}" ]; then
      itk_preset="itk-forest-itk-v6-vtkglue"
      itk_kvs+=("VTK_DIR=${_itk_vtk}")
    fi
    # Two-pass: first configure fetches remote modules (may fail on one whose
    # examples/ dir is absent); stub those, then reconfigure for real.
    cfg resolve-overlay "${itk_preset}" "$s" "${ITK_BUILD}" "${FOREST}" ITK "${itk_kvs[@]}"
    cmake -S "$s" --preset "forest-ITK-local" || true
    _stub_remote_examples
    cmake -S "$s" --preset "forest-ITK-local"
    return
  fi
  [ -f "${ITK_BUILD}/ITKConfig.cmake" ] || die "ITK not built; run: pixi run ITK"
  case "$name" in
    ANTs)
                 # Static ANTs settings (ANTS_SUPERBUILD=OFF direct build,
                 # RUN_LONG/SHORT_TESTS=ON, USE_SYSTEM_ITK=ON, lean USE_VTK=OFF)
                 # live in cmake/presets/20-ANTs.json; the max-modules bundle
                 # (USE_VTK/BUILD_ALL_ANTS_APPS) is selected via variant preset
                 # itk-forest-ants-max-modules. ANTS_VTK_DIR reuses an existing
                 # VTK (support build) instead of ANTs building its own.
                 local ants_preset="itk-forest-ants" ants_kvs=("ITK_DIR=$(itk_dir)")
                 if [ "${ANTS_MAX_MODULES:-0}" = 1 ]; then
                   ants_preset="itk-forest-ants-max-modules"
                   if [ -n "${ANTS_VTK_DIR:-}" ]; then
                     ants_kvs+=("USE_SYSTEM_VTK=ON" "VTK_DIR=${ANTS_VTK_DIR}")
                   else
                     # ANTs builds its own VTK; its bundled hdf5 uses vasprintf
                     # without _GNU_SOURCE, which GCC 14 rejects.
                     ants_kvs+=("USE_SYSTEM_VTK=OFF" "CMAKE_C_FLAGS=-Wno-error=implicit-function-declaration")
                   fi
                 fi
                 do_overlay ANTs "${ants_preset}" "$s" "$b" "${ants_kvs[@]}" ;;
    BRAINSTools)
                 # Lean defaults (USE_VTK/DICOM OFF, USE_SYSTEM_ITK, GLVND) live in
                 # 30-BRAINSTools.json; the max-modules bundle is selected via
                 # variant preset itk-forest-brainstools-max-modules; fork/ANTs
                 # wiring and orthogonal flags layer here.
                 local bt_preset="itk-forest-brainstools"
                 local bt_kvs=("ITK_DIR=$(itk_dir)"
                   "BRAINSTools_ANTs_GIT_REPOSITORY=${BRAINSTools_ANTs_GIT_REPOSITORY:-$(cfg get subbuild.BRAINSTools.ANTs_GIT_REPOSITORY)}"
                   "BRAINSTools_ANTs_GIT_TAG=${BRAINSTools_ANTs_GIT_TAG:-$(cfg get subbuild.BRAINSTools.ANTs_GIT_TAG)}")
                 if [ "${BRAINSTOOLS_MAX_MODULES:-0}" = 1 ]; then
                   bt_preset="itk-forest-brainstools-max-modules"
                   [ "${BRAINSTOOLS_BUILD_ARCHIVE:-0}" = 1 ] && bt_kvs+=("BUILD_ARCHIVE=ON")
                 fi
                 # BRAINSTOOLS_NO_ANTS=1 drops ANTs (modern ANTs requires ITK6).
                 [ "${BRAINSTOOLS_NO_ANTS:-0}" = 1 ] && bt_kvs+=("USE_ANTS=OFF")
                 # ants_system_args emits -DKEY=VAL; strip -D into overlay KVs.
                 local _asa; for _asa in $(ants_system_args); do bt_kvs+=("${_asa#-D}"); done
                 # BRAINSTOOLS_EXTRA: space-separated -DKEY=VAL flags.
                 local _bte; for _bte in ${BRAINSTOOLS_EXTRA:-}; do bt_kvs+=("${_bte#-D}"); done
                 do_overlay BRAINSTools "${bt_preset}" "$s" "$b" "${bt_kvs[@]}" ;;
    Slicer)      warn "Slicer SuperBuild is long (builds VTK/CTK + own ITK 6; Qt6 from ${SLICER_QT_PREFIX})"
                 # Policy: Slicer NEVER uses the system ITK; it always builds a
                 # dedicated Slicer-vendored ITK branch (hjmjohnson/ITK @ slicer-itk-*)
                 # via -DSlicer_ITK_GIT_TAG below. See docs/slicer-itk-policy.md.
                 [ -d "${SLICER_QT_PREFIX}/lib/cmake/Qt6" ] || die "Qt6 not found at ${SLICER_QT_PREFIX} (set SLICER_QT_PREFIX/SLICER_QT_VERSION)"
                 # Slicer forwards -DCMAKE_<LANG>_COMPILER to every ExternalProject
                 # (VTK/ITK/Python/...) but NOT the ccache *launcher*, so a launcher
                 # flag would skip ccache for those EPs. Point the compiler at ccache's
                 # Policy: use the conda toolchain (CC/CXX), never system/Homebrew;
                 # Slicer forwards CMAKE_<LANG>_COMPILER to its VTK/ITK/Python EPs.
                 # Static Slicer knobs (USE_SYSTEM_* OFF, WEBENGINE OFF, GLVND)
                 # live in 40-Slicer.json; compilers, Slicer-vendored ITK ref and
                 # Qt are layered here.
                 do_overlay Slicer itk-forest-slicer "$s" "$b" \
                   "CMAKE_C_COMPILER=${SLICER_CC:-${CC}}" \
                   "CMAKE_CXX_COMPILER=${SLICER_CXX:-${CXX}}" \
                   "Slicer_ITK_GIT_REPOSITORY=${SLICER_ITK_GIT_REPOSITORY:-$(cfg get subbuild.Slicer.ITK_GIT_REPOSITORY)}" \
                   "Slicer_ITK_GIT_TAG=${SLICER_ITK_GIT_TAG:-$(cfg get subbuild.Slicer.ITK_GIT_TAG)}" \
                   `# python EP = python-cmake-buildsystem; pin to the fork branch` \
                   `# carrying the libintl link fix (upstream PR #450) until merged.` \
                   "Slicer_python_GIT_REPOSITORY=${SLICER_PYTHON_GIT_REPOSITORY:-https://github.com/hjmjohnson/python-cmake-buildsystem.git}" \
                   "Slicer_python_GIT_TAG=${SLICER_PYTHON_GIT_TAG:-fix/link-libintl-localemodule-macos}" \
                   "Slicer_REQUIRED_QT_VERSION=${SLICER_QT_VERSION}" \
                   "Qt6_DIR=${SLICER_QT_PREFIX}/lib/cmake/Qt6" \
                   "CMAKE_PREFIX_PATH=${SLICER_QT_PREFIX}" ;;
    SlicerExtensions)
                 # Build a curated, ITK-exercising subset of Slicer extensions
                 # against the inner Slicer build (Slicer_DIR), per the
                 # Slicer/DashboardScripts SlicerExtensionsDashboardDriverScript pattern.
                 local slicer_inner="${FOREST}/Slicer-build/Slicer-build"
                 [ -f "${slicer_inner}/SlicerConfig.cmake" ] || die "Slicer not built; run: pixi run build-Slicer"
                 local descdir="${FOREST}/SlicerExtensions-descriptions"
                 rm -rf "${descdir}"; mkdir -p "${descdir}"
                 for e in "${SLICER_EXTENSIONS[@]}"; do
                   if [ -f "${s}/${e}.json" ]; then cp "${s}/${e}.json" "${descdir}/"
                   else warn "extension descriptor not found in index: ${e}.json"; fi
                 done
                 do_overlay SlicerExtensions itk-forest-base \
                   "${FOREST}/Slicer/Extensions/CMake" "$b" \
                   "Slicer_DIR=${slicer_inner}" \
                   "Slicer_EXTENSION_DESCRIPTION_DIR=${descdir}" \
                   "Qt6_DIR=${SLICER_QT_PREFIX}/lib/cmake/Qt6" \
                   "CMAKE_PREFIX_PATH=${SLICER_QT_PREFIX}" ;;
    MITK)        warn "MITK SuperBuild is long"
                 do_overlay MITK itk-forest-base "$s" "$b" \
                   "MITK_USE_SYSTEM_ITK=ON" "ITK_DIR=$(itk_dir)" ;;
    elastix)     do_overlay elastix itk-forest-base "$s" "$b" "ITK_DIR=$(itk_dir)" ;;
    c3d)         do_overlay c3d itk-forest-base "$s" "$b" "ITK_DIR=$(itk_dir)" ;;
    Plastimatch) # ITK is built with the ITKDCMTK module, so find_package(ITK)
                 # pulls DCMTK transitively; point at ITK's bundled DCMTK build.
                 # PLM_CONFIG_ENABLE_* statics live in 50-Plastimatch.json.
                 do_overlay Plastimatch itk-forest-plastimatch "$s" "$b" \
                   "ITK_DIR=$(itk_dir)" \
                   "CMAKE_CXX_FLAGS=-ffile-prefix-map=${s}=. -include ${s}/libs/demons_itk_insight/vcl_legacy_aliases.h -D_LIBCPP_ENABLE_CXX17_REMOVED_UNARY_BINARY_FUNCTION" \
                   "DCMTK_DIR=${ITK_BUILD}/Modules/ThirdParty/DCMTK/ITKDCMTK_ExtProject-build" \
                   "PLM_CONFIG_ENABLE_SSE2=${PLM_ENABLE_SSE2:-OFF}" ;;
    SimpleITK)   warn "SimpleITK SuperBuild (C++ only; WRAP_DEFAULT=OFF)"
                 do_overlay SimpleITK itk-forest-simpleitk "${s}/SuperBuild" "$b" \
                   "ITK_DIR=$(itk_dir)" ;;
    RTK)         do_overlay RTK itk-forest-base "$s" "$b" \
                   "ITK_DIR=$(itk_dir)" "RTK_USE_CUDA=${RTK_USE_CUDA:-OFF}" ;;
    Ultrasound)  do_overlay Ultrasound itk-forest-base "$s" "$b" \
                   "ITK_DIR=$(itk_dir)" "ITKUltrasound_USE_VTK=OFF" ;;
    OpenIGTLink) log "OpenIGTLink (protocol v3, static)"
                 do_overlay OpenIGTLink itk-forest-openigtlink "$s" "$b" ;;
    OpenIGTLinkIO) local _vtk _oi; _vtk="$(vtk_dir)"; _oi="$(openigtlink_dir)"
                 [ -n "${_vtk}" ] || die "OpenIGTLinkIO: no built VTK — build Slicer (full VTK) or set VTK_DIR"
                 [ -n "${_oi}" ] || die "OpenIGTLinkIO: OpenIGTLink not built — run: build OpenIGTLink"
                 log "OpenIGTLinkIO: VTK_DIR=${_vtk}  OpenIGTLink_DIR=${_oi}"
                 do_overlay OpenIGTLinkIO itk-forest-base "$s" "$b" \
                   "VTK_DIR=${_vtk}" "OpenIGTLink_DIR=${_oi}" "IGTLIO_USE_GUI=OFF" ;;
    vtkAddon)    local _vtk; _vtk="$(vtk_dir)"
                 [ -n "${_vtk}" ] || die "vtkAddon: no built VTK (vtk-config.cmake) found — build Slicer (full VTK) or set VTK_DIR"
                 log "vtkAddon: VTK_DIR=${_vtk}"
                 do_overlay vtkAddon itk-forest-base "$s" "$b" "VTK_DIR=${_vtk}" ;;
    IGSIO)       local _vtk _va; _vtk="$(vtk_dir)"; _va="$(vtkaddon_dir)"
                 [ -n "${_vtk}" ] || die "IGSIO: no built VTK (vtk-config.cmake) found — build Slicer (full VTK) or set VTK_DIR"
                 [ -n "${_va}" ] || die "IGSIO: vtkAddon not built — run: build vtkAddon (or set vtkAddon_DIR)"
                 log "IGSIO: ITK_DIR=$(itk_dir)  VTK_DIR=${_vtk}  vtkAddon_DIR=${_va}"
                 do_overlay IGSIO itk-forest-base "$s" "$b" \
                   "ITK_DIR=$(itk_dir)" "VTK_DIR=${_vtk}" "vtkAddon_DIR=${_va}" "IGSIO_USE_3DSlicer=OFF" ;;
    PlusLib)     local _vtk _igsio _oi _oio; _vtk="$(vtk_dir)"; _igsio="$(igsio_dir)"
                 _oi="$(openigtlink_dir)"; _oio="$(openigtlinkio_dir)"
                 [ -n "${_vtk}" ] || die "PlusLib: no built VTK (vtk-config.cmake) found — build Slicer (full VTK) or set VTK_DIR"
                 [ -n "${_igsio}" ] || die "PlusLib: IGSIO not built — run: build IGSIO (or set IGSIO_DIR)"
                 [ -n "${_oio}" ] || die "PlusLib: OpenIGTLinkIO not built (igtlioConverter target required) — run: build OpenIGTLinkIO"
                 log "PlusLib: ITK_DIR=$(itk_dir)  VTK_DIR=${_vtk}  IGSIO_DIR=${_igsio}  OpenIGTLinkIO_DIR=${_oio}"
                 do_overlay PlusLib itk-forest-base "$s" "$b" \
                   "ITK_DIR=$(itk_dir)" "VTK_DIR=${_vtk}" "IGSIO_DIR=${_igsio}" "PLUS_USE_OpenIGTLink=ON" \
                   "OpenIGTLink_DIR=${_oi}" "OpenIGTLinkIO_DIR=${_oio}" ;;
    VkFFTBackend)
                 local _vk; _vk="$(vkfft_backend)"
                 [ -n "${_vk}" ] || die "VkFFTBackend: no GPU backend (CUDA/Metal/OpenCL) on this host"
                 local _vk_kvs=("ITK_DIR=$(itk_dir)" "VKFFT_BACKEND=${_vk}")
                 [ "${_vk}" = 1 ] && _vk_kvs+=("CMAKE_CUDA_COMPILER=$(_find_nvcc)")
                 log "VkFFTBackend: VKFFT_BACKEND=${_vk} (1=CUDA 5=Metal 3=OpenCL)"
                 do_overlay VkFFTBackend itk-forest-base "$s" "$b" "${_vk_kvs[@]}" ;;
    *)  do_overlay "${name}" itk-forest-base "$s" "$b" "ITK_DIR=$(itk_dir)" ;;
  esac
}


# Conda's libjpeg-turbo ships jconfig.h/jpeglib.h/jerror.h/jmorecfg.h in the env
# include dir, which is first on the compile -I path and shadows ITK's *vendored*
# jpeg headers. ITK's vendored jpeg then includes conda's jconfig.h (no symbol
# mangling) while jpeg_nbits.c self-mangles, leaving libitkjpeg internally
# inconsistent (undefined itk_jpeg_nbits_table). Every consumer here vendors its
# own jpeg, so the conda headers are unused at compile time; hide them.
_hide_conda_jpeg_shadow_headers(){
  local inc="${PIXI_PROJECT_ROOT:-${TESTBED}}/.pixi/envs/default/include"
  [ -d "$inc" ] || inc="${TESTBED}/.pixi/envs/default/include"
  local h
  for h in jconfig.h jpeglib.h jerror.h jmorecfg.h jpegint.h jconfigint.h; do
    [ -f "${inc}/${h}" ] && mv "${inc}/${h}" "${inc}/${h}.itk-shadow-disabled"
  done; :; }

build_one(){ require cmake ninja ccache
  _hide_conda_jpeg_shadow_headers
  local name="$1" b="$(build_dir "$1")"; [ "$name" = ITK ] && b="${ITK_BUILD}"
  [ "$name" = ANTs ] && require_itk6_for_ants
  # Slicer's bundled TBB (tbbbind) and other EPs include env-provided headers
  # (hwloc.h, ...) that the conda compiler only finds via CPATH (no -I is added
  # otherwise). The conflicting jpeg headers are already hidden above.
  case "$name" in
    Slicer|SlicerExtensions)
      export CPATH="${PIXI_PROJECT_ROOT:-${TESTBED}}/.pixi/envs/default/include${CPATH:+:${CPATH}}" ;;
  esac
  # Plastimatch's force-include shim must exist before configure (CMake's
  # compiler checks use CMAKE_CXX_FLAGS, which references it).
  [ "$name" = Plastimatch ] && { _patch_plastimatch_vcl_aliases; _patch_plastimatch_ransac_test; }
  # A complete configure leaves build.ninja; a half-failed one leaves only
  # CMakeCache.txt. Require build.ninja so a broken tree is reconfigured.
  [ -f "${b}/build.ninja" ] || configure_one "$name"
  # Re-stub missing remote-module examples/ dirs before building ITK: repoint-itk's
  # `git reset --hard` removes these untracked stubs, and a ninja-triggered
  # reconfigure during `cmake --build` then fails (e.g. IOMeshMZ3 examples/).
  [ "$name" = ITK ] && _stub_remote_examples
  [ "$name" = ANTs ] && _patch_ants_missing_includes
  [ "$name" = IGSIO ] && _patch_igsio_iostream
  [ "$name" = Plastimatch ] && { _patch_plastimatch_dlib_unicode; _patch_plastimatch_vcl_aliases; }
  log "build ${name} (-j${JOBS})"
  # Per-package basedir only for self-contained roots; consumers/SuperBuilds keep
  # the forest-wide default so their cross-package refs and EP trees stay inside
  # the basedir subtree. See the CCACHE_PERPKG_ROOTS block near the top.
  case " ${CCACHE_PERPKG_ROOTS} " in
    *" ${name} "*) export CCACHE_BASEDIR="${FOREST}/${name}" ;;
    *)             export CCACHE_BASEDIR="${FOREST}" ;;
  esac
  if [ "$name" = BRAINSTools ]; then
    # BRAINSTools' SuperBuild clones ANTs during the build; first pass fetches
    # (may fail on the ANTs include bug), patch, second pass resumes. The
    # BRAINSTools KWSys/TBB fixes apply up front (their source is present); ANTs
    # and SlicerExecutionModel/tclap are cloned during the build, so re-apply
    # after the first pass.
    _patch_brainstools_kwsys
    _patch_brainstools_tbb
    _patch_brainstools_itk_macros
    cmake --build "$b" -j"${JOBS}" || true
    _patch_ants_missing_includes
    _patch_brainstools_kwsys
    _patch_brainstools_tbb
    _patch_brainstools_itk_macros
    _patch_sem_tclap
    _reconfigure_brainstools_inner
    cmake --build "$b" -j"${JOBS}"
  else
    cmake --build "$b" -j"${JOBS}"
  fi
  # After ITK builds, repair the ITKDCMTK export's dangling ijg include paths so
  # downstream DCMTK consumers (elastix, ANTs, ...) configure cleanly.
  local rc=$?   # the build's real status; ITK post-steps below must not clobber it
  [ "$name" = ITK ] && _fix_dcmtk_ijg_symlinks
  [ "$name" = ITK ] && [ "${ITK_USE_INSTALL:-0}" = 1 ] && install_itk
  return "${rc}"; }

# Install ITK so downstreams can consume the install tree (ITK_USE_INSTALL=1).
# Works around a stale install rule for the generated itk_jpeg_mangle.h by
# copying it where the rule expects.
install_itk(){
  local gen="${ITK_BUILD}/Modules/ThirdParty/JPEG/src/itkjpeg-turbo/itk_jpeg_mangle.h"
  local src="${FOREST}/ITK/Modules/ThirdParty/JPEG/src/itkjpeg-turbo/itk_jpeg_mangle.h"
  [ -f "${gen}" ] && [ ! -f "${src}" ] && cp "${gen}" "${src}"
  log "install ITK -> ${ITK_INSTALL}"
  cmake --install "${ITK_BUILD}" --prefix "${ITK_INSTALL}" >/dev/null; }

cmd_remotes(){ build_one ITK || warn "ITK (re)build issue; continuing with existing ITK build tree"
  for r in "${REMOTES[@]}"; do IFS='|' read -r nm url hv <<<"$r"
    [ "$hv" = 1 ] && [ "${HEAVY}" != 1 ] && { log "$nm: heavy (skip; HEAVY=1 to include)"; continue; }
    [ -d "${FOREST}/${nm}" ] || { warn "$nm not checked out (skip)"; continue; }
    build_one "$nm" || warn "$nm FAILED to build"
  done; }

cmd_status(){
  log "TESTBED=${TESTBED}  FOREST=${FOREST}  JOBS=${JOBS}  HEAVY=${HEAVY}"
  log "CC=${CC}  CXX=${CXX}  CCACHE_DIR=${CCACHE_DIR}"
  command -v ccache >/dev/null && ccache -s 2>/dev/null | head -6 || warn "no ccache"
  echo; log "checked out:"; ls -1 "${FOREST}" 2>/dev/null | grep -vE -- '-build$' || true; }

cmd_list(){ echo "# consumers (build order: ${BUILD_ORDER[*]})"
  for r in "${CONSUMERS[@]}"; do echo "  ${r%%|*}"; done
  echo "# ITK remote modules (external, system-ITK)"
  for r in "${REMOTES[@]}"; do IFS='|' read -r nm url hv <<<"$r"
    echo "  ${nm}$([ "$hv" = 1 ] && echo '  [heavy: HEAVY=1]')"; done; }

case "${1:-checkout}" in
  checkout)  shift; cmd_checkout "$@" ;;
  configure) shift; configure_one "${1:?configure <name>}" ;;
  build)     shift; build_one "${1:?build <name>}"; cfg manifest "${FOREST}" 2>/dev/null || true ;;
  build-all) for n in "${BUILD_ORDER[@]}"; do [ -d "${FOREST}/$n" ] && build_one "$n"; done
             cfg manifest "${FOREST}" 2>/dev/null || true ;;
  remotes)   cmd_remotes; cfg manifest "${FOREST}" 2>/dev/null || true ;;
  repoint-itk) cmd_repoint_itk; cfg manifest "${FOREST}" 2>/dev/null || true ;;
  manifest)  cfg manifest "${FOREST}" ;;
  list)      cmd_list ;;
  status)    cmd_status ;;
  vtk)       build_forest_vtk ;;
  vkfft-backend) vkfft_backend ;;
  *) die "unknown command '$1' (checkout|configure|build|build-all|remotes|repoint-itk|manifest|list|status|vtk|vkfft-backend)" ;;
esac
