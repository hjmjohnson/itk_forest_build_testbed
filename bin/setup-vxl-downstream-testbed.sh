#!/usr/bin/env bash
# setup-vxl-downstream-testbed.sh
#
# Build engine for the VXL/VNL downstream-breakage testbed. Checks out every
# open-source ITK consumer the vxl fork must not break, instruments all builds
# with ccache, and builds them against the locally built ITK (USE_SYSTEM_ITK).
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
#   sync-vnl               rsync local vxl into ITK's vendored vnl, then rebuild ITK
#   list                   print every known project + category
#   status                 ccache + worktree state
#
# Layout: this script lives in <repo>/bin; all source checkouts and build trees
# go under <repo>/build_forest (git-ignored). TESTBED is the repo root, FOREST is
# the artifact dir.
#
# Env overrides (defaults): SRC_ROOT=~/src  TESTBED=<repo root (parent of bin/)>
#   FOREST=$TESTBED/build_forest  VXL_SRC=$SRC_ROOT/vxl  CCACHE_DIR=~/.ccache
#   JOBS=(nproc)  CC/CXX=(auto/pixi)  HEAVY=0 (1 to include CUDA/Java/wasm remotes)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTBED="${TESTBED:-$(dirname "${SCRIPT_DIR}")}"   # repo root = parent of bin/

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
VXL_SRC="${VXL_SRC:-${SRC_ROOT}/vxl}"
export CCACHE_DIR="${CCACHE_DIR:-${HOME}/.ccache}"
# Path-independent caching across build_forest-<suffix> forests: rewrite
# testbed-absolute paths to relative before hashing, and don't hash the CWD
# (safe: Release builds carry no -g CWD-sensitive debug info).
export CCACHE_BASEDIR="${CCACHE_BASEDIR:-${TESTBED}}"
export CCACHE_NOHASHDIR="${CCACHE_NOHASHDIR:-true}"
HEAVY="${HEAVY:-0}"
# ITK base ref: the branch that vendors for/itk-vxl-master with a matching VNL
# wrapper (vcl is INTERFACE/header-only). sync-vnl then overlays the working
# tree's vxl. Override to test a later re-vendor branch / proposed PR.
ITK_REF="${ITK_REF:-update-vnl-stripped-vxl-v3}"

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
    *) CC="$(ls "${CONDA_PREFIX}"/bin/*-cc "${CONDA_PREFIX}"/bin/clang "${CONDA_PREFIX}"/bin/gcc 2>/dev/null | head -1)" ;; esac
  case "${CXX:-}" in "${CONDA_PREFIX}"/*) : ;;
    *) CXX="$(ls "${CONDA_PREFIX}"/bin/*-c++ "${CONDA_PREFIX}"/bin/clang++ "${CONDA_PREFIX}"/bin/g++ 2>/dev/null | head -1)" ;; esac
fi
: "${CC:=$(command -v cc || command -v clang || command -v gcc)}"
: "${CXX:=$(command -v c++ || command -v clang++ || command -v g++)}"
export CC CXX

# Slicer needs a real Qt6 (its SuperBuild builds VTK/CTK against it). On macOS a
# Homebrew qt@6 on PATH shadows a user Qt: its host-tools (Qt6CoreTools, ...) get
# found from Homebrew while Qt6 itself comes from ~/Qt, which fails Qt6 package
# configuration. Prefer ~/Qt/<ver>/macos and drop Homebrew qt@6 from PATH so Qt6
# and its host-tools resolve consistently for both configure and build.
SLICER_QT_VERSION="${SLICER_QT_VERSION:-6.9.1}"
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

# Resolve a ccache-wrapping compiler for Slicer's ExternalProjects. Slicer
# forwards -DCMAKE_<LANG>_COMPILER to every EP but NOT the ccache *launcher*, so
# pointing the compiler at ccache's libexec wrapper (which execs the real clang
# from PATH) is what gets ccache into VTK/ITK/Python/Slicer. Falls back to a
# plain compiler (builds, no ccache) when no libexec wrapper is found.
slicer_cc(){  # $1 = clang | clang++
  local name="$1" d
  for d in "$(brew --prefix ccache 2>/dev/null)/libexec" \
           /opt/homebrew/opt/ccache/libexec /usr/local/opt/ccache/libexec \
           /usr/lib/ccache /usr/lib64/ccache; do
    [ -x "${d}/${name}" ] && { printf '%s' "${d}/${name}"; return; }
  done
  [ -x "/usr/bin/${name}" ] && { printf '%s' "/usr/bin/${name}"; return; }
  command -v "${name}" 2>/dev/null || printf '%s' "${name}"
}

ITK_BUILD="${FOREST}/ITK-build"       # ITK build tree
ITK_INSTALL="${FOREST}/ITK-install"   # installed ITK (its export defines vcl) — consumers use this

# Consumers point ITK_DIR at the ITK build tree. Its build-tree export now
# defines the vcl static target (vxl vcl/CMakeLists.txt exports it), and the
# build tree ships all CMake helper modules the install tree omits. Set
# ITK_USE_INSTALL=1 to use the install tree instead.
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

# An already-built VTK (vtk-config.cmake) for consumers that need one (PlusLib).
# Reuses the Slicer or BRAINSTools VTK build; override with VTK_DIR.
vtk_dir(){
  local d
  for d in "${VTK_DIR:-}" \
           "${FOREST}/Slicer-build/VTK-build" \
           "${FOREST}/BRAINSTools-build/VTK-Release-build"; do
    [ -n "$d" ] && [ -f "${d}/vtk-config.cmake" ] && { echo "$d"; return; }
  done
  find "${FOREST}" -maxdepth 3 -name vtk-config.cmake 2>/dev/null \
    | grep -v CMakeFiles | head -1 | xargs -r dirname; }

# Built OpenIGTLink / OpenIGTLinkIO (the IGT comms stack PlusLib requires).
openigtlink_dir(){
  local d="${OpenIGTLink_DIR:-${FOREST}/OpenIGTLink-build}"
  [ -f "${d}/OpenIGTLinkConfig.cmake" ] && { echo "$d"; return; }
  find "${FOREST}/OpenIGTLink-build" -maxdepth 2 -name OpenIGTLinkConfig.cmake 2>/dev/null | head -1 | xargs -r dirname; }
openigtlinkio_dir(){
  local d="${OpenIGTLinkIO_DIR:-${FOREST}/OpenIGTLinkIO-build}"
  [ -f "${d}/OpenIGTLinkIOConfig.cmake" ] && { echo "$d"; return; }
  find "${FOREST}/OpenIGTLinkIO-build" -maxdepth 2 -name OpenIGTLinkIOConfig.cmake 2>/dev/null | head -1 | xargs -r dirname; }

# An already-built vtkAddon (config file) that IGSIO consumes; override with vtkAddon_DIR.
vtkaddon_dir(){
  local d="${vtkAddon_DIR:-${FOREST}/vtkAddon-build}"
  { [ -f "${d}/vtkAddonConfig.cmake" ] || [ -f "${d}/vtkAddon-config.cmake" ]; } && { echo "$d"; return; }
  find "${FOREST}/vtkAddon-build" -maxdepth 2 \( -name vtkAddonConfig.cmake -o -name vtkAddon-config.cmake \) 2>/dev/null | head -1 | xargs -r dirname; }

# An already-built IGSIO (IGSIOConfig.cmake) that PlusLib consumes; override with IGSIO_DIR.
igsio_dir(){
  local d="${IGSIO_DIR:-${FOREST}/IGSIO-build}"
  [ -f "${d}/IGSIOConfig.cmake" ] && { echo "$d"; return; }
  find "${FOREST}/IGSIO-build" -maxdepth 2 -name IGSIOConfig.cmake 2>/dev/null | head -1 | xargs -r dirname; }

# --- main consumers:  name | git URL | worktree branch
CONSUMERS=(
  "ITK|https://github.com/InsightSoftwareConsortium/ITK.git|itk-vxl-master"
  "ANTs|https://github.com/ANTsX/ANTs.git|ants-vxl-master"
  "BRAINSTools|https://github.com/BRAINSia/BRAINSTools.git|braintools-vxl-master"
  "Slicer|https://github.com/Slicer/Slicer.git|slicer-vxl-master"
  "SlicerExtensions|https://github.com/Slicer/ExtensionsIndex.git|main"
  "elastix|https://github.com/SuperElastix/elastix.git|elastix-vxl-master"
  "MITK|https://github.com/MITK/MITK.git|mitk-vxl-master"
  "c3d|https://github.com/pyushkevich/c3d.git|c3d-vxl-master"
  "SimpleITK|https://github.com/SimpleITK/SimpleITK.git|simpleitk-vxl-master"
  "OpenIGTLink|https://github.com/openigtlink/OpenIGTLink.git|openigtlink-vxl-master"
  "OpenIGTLinkIO|https://github.com/IGSIO/OpenIGTLinkIO.git|openigtlinkio-vxl-master"
  "vtkAddon|https://github.com/Slicer/vtkAddon.git|vtkaddon-vxl-master"
  "IGSIO|https://github.com/IGSIO/IGSIO.git|igsio-vxl-master"
  "PlusLib|https://github.com/PlusToolkit/PlusLib.git|pluslib-vxl-master"
)
# Curated, ITK/vnl-exercising subset of Slicer extensions built against the
# locally built Slicer (Slicer_DIR). Each name is a <name>.json descriptor in
# the ExtensionsIndex checkout. Add more here to widen coverage.
SLICER_EXTENSIONS=(BoneTextureExtension AnomalousFiltersExtension SlicerElastix)
# --- ITK remote modules, built EXTERNALLY against system ITK.  name | git URL | heavy?
REMOTES=(
  "BioCell|https://github.com/InsightSoftwareConsortium/ITKBioCell.git|0"
  "Cleaver|https://github.com/SCIInstitute/ITKCleaver.git|0"
  "CudaCommon|https://github.com/RTKConsortium/ITKCudaCommon.git|1"
  "HASI|https://github.com/KitwareMedical/HASI.git|0"
  "IOOpenSlide|https://github.com/InsightSoftwareConsortium/ITKIOOpenSlide.git|1"
  "LesionSizingToolkit|https://github.com/InsightSoftwareConsortium/LesionSizingToolkit.git|0"
  "PerformanceBenchmarking|https://github.com/InsightSoftwareConsortium/ITKPerformanceBenchmarking.git|0"
  "RTK|https://github.com/RTKConsortium/RTK.git|0"
  "SCIFIO|https://github.com/scifio/scifio-imageio.git|1"
  "Shape|https://github.com/SlicerSALT/ITKShape.git|0"
  "SimpleITKFilters|https://github.com/InsightSoftwareConsortium/ITKSimpleITKFilters.git|0"
  "SkullStrip|https://github.com/InsightSoftwareConsortium/ITKSkullStrip.git|0"
  "SphinxExamples|https://github.com/InsightSoftwareConsortium/ITKSphinxExamples.git|0"
  "TractographyTRX|https://github.com/tee-ar-ex/ITKTractographyTRX.git|0"
  "TubeTK|https://github.com/InsightSoftwareConsortium/ITKTubeTK.git|0"
  "Ultrasound|https://github.com/KitwareMedical/ITKUltrasound.git|0"
  "VkFFTBackend|https://github.com/InsightSoftwareConsortium/ITKVkFFTBackend.git|0"
  "WebAssemblyInterface|https://github.com/InsightSoftwareConsortium/ITK-Wasm.git|1"
)
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
  printf '%s ' -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
    -DCMAKE_C_COMPILER="${CC}" -DCMAKE_CXX_COMPILER="${CXX}" \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
}

checkout_one(){
  local name="$1" url="$2" branch="$3" dest="${FOREST}/$1"
  # A branch can only be checked out in one worktree; suffix per-forest.
  [ -n "${branch}" ] && branch="${branch}${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}"
  if [ -e "${dest}/.git" ]; then log "${name}: present (skip)"; return 0; fi
  local canon="${SRC_ROOT}/${name}"
  if [ -d "${canon}/.git" ] && [ -n "${branch}" ]; then
    log "${name}: worktree from ${canon} (branch ${branch})"
    git -C "${canon}" show-ref --verify --quiet "refs/heads/${branch}" \
      && git -C "${canon}" worktree add "${dest}" "${branch}" \
      || git -C "${canon}" worktree add -b "${branch}" "${dest}"
  else
    log "${name}: clone ${url}"
    git clone --depth 1 "${url}" "${dest}"
  fi
}

cmd_checkout(){ require git; mkdir -p "${FOREST}"
  local names=("$@"); [ ${#names[@]} -eq 0 ] && mapfile -t names < <(all_names)
  for n in "${names[@]}"; do
    local meta; meta="$(row_for "$n")" || { warn "unknown: $n"; continue; }
    IFS='|' read -r kind url br <<<"$meta"
    if [ "$kind" = remote ]; then
      [ "$br" = 1 ] && [ "${HEAVY}" != 1 ] && { log "$n: heavy (CUDA/Java/wasm); set HEAVY=1 to include (skip)"; continue; }
      checkout_one "$n" "$url" ""
    else checkout_one "$n" "$url" "$br"; fi
  done
  log "checkout dir: ${FOREST}"; }

cmd_repoint_itk(){ require git
  local itk="${FOREST}/ITK"
  [ -e "${itk}/.git" ] || die "ITK not checked out"   # .git is a FILE in a worktree
  log "discard any vendored overlay, move ITK worktree to ${ITK_REF}"
  git -C "${itk}" reset --hard --quiet   # drop prior sync-vnl overlay so checkout can switch
  local remote="${ITK_REF%%/*}"
  if [ "${remote}" != "${ITK_REF}" ]; then  # remote ref (has a '/') -> fetch first
    git -C "${itk}" fetch "${remote}" --quiet || warn "fetch ${remote} failed; using cached refs"
  fi
  git -C "${itk}" checkout -f -B "itk-vxl-master${FOREST_REFERENCE_SUFFIX:+-${FOREST_REFERENCE_SUFFIX}}" "${ITK_REF}"
  warn "ITK now at ${ITK_REF}; run sync-vnl then build-ITK to apply the vxl change"; }

cmd_sync_vnl(){ require rsync
  local vendored="${FOREST}/ITK/Modules/ThirdParty/VNL/src/vxl"
  [ -d "${vendored}" ] || die "vendored vnl missing at ${vendored} (checkout ITK first)"
  log "rsync ${VXL_SRC}/{vcl,core,v3p} -> vendored vnl"
  for sub in vcl core v3p; do [ -d "${VXL_SRC}/${sub}" ] && \
    rsync -a --delete --exclude '.git' --exclude 'build*/' \
      "${VXL_SRC}/${sub}/" "${vendored}/${sub}/"; done
  # config/ holds the CMake probes (e.g. ConfigurePlatformMathTarget); sync
  # additively so vxl-owned modules update without removing ITK-added files.
  [ -d "${VXL_SRC}/config" ] && rsync -a --exclude '.git' \
    "${VXL_SRC}/config/" "${vendored}/config/"
  warn "rebuild: pixi run build-ITK   (then any downstream)"; }

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

# ITK main's vendored vnl no longer ships some headers that downstream consumers
# still include (e.g. elastix's AffineLogTransform needs vnl/vnl_matrix_exp.h).
# That gap is pre-existing in ITK main and orthogonal to the change under test,
# so overlay the missing header-only files to isolate the validation. Files live
# in bin/overlays/vnl/ and are copied only when absent from the vendored vnl.
_overlay_vnl_headers(){
  local ov="${SCRIPT_DIR}/overlays/vnl" dst="${FOREST}/ITK/Modules/ThirdParty/VNL/src/vxl/core/vnl" f
  [ -d "${ov}" ] || return 0
  for f in "${ov}"/*; do
    [ -e "${f}" ] || continue
    [ -e "${dst}/$(basename "${f}")" ] || { cp "${f}" "${dst}/"; log "overlay vnl/$(basename "${f}")"; }
  done; }

configure_one(){
  local name="$1" meta; meta="$(row_for "$name")" || die "unknown project: $name"
  local s="${FOREST}/${name}" b="${FOREST}/${name}-build"
  [ -d "$s" ] || die "${name} not checked out (run: pixi run checkout)"
  if [ "$name" = ITK ]; then
    # system FFTW (double+single) so ITKUltrasound and other FFT consumers build.
    # CONDA_PREFIX is set inside the pixi env, which provides the fftw package.
    local fftw=()
    if [ -n "${CONDA_PREFIX:-}" ] && [ -f "${CONDA_PREFIX}/include/fftw3.h" ]; then
      fftw=(-DITK_USE_FFTWD=ON -DITK_USE_FFTWF=ON -DITK_USE_SYSTEM_FFTW=ON
            -DFFTW_INCLUDE_PATH="${CONDA_PREFIX}/include"
            -DFFTW_LIB_SEARCHPATH="${CONDA_PREFIX}/lib")
    else warn "fftw not found in env; building ITK without FFTW (Ultrasound will fail)"; fi
    # Enable modules ingested into ITK main that downstreams need as
    # COMPILE_DEPENDS (e.g. ITKUltrasound). No fetching — these live in main.
    # Modules downstreams need compiled into ITK: Ultrasound's COMPILE_DEPENDS
    # plus ANTs' required set (ITKReview, GenericLabelInterpolator, AdaptiveDenoising,
    # MGHIO). TractographyTRX is genuinely remote (not ingested) so it is left off.
    # Superset of ITK's own pixi `configure-ci` module list, plus ANTs' required
    # set (ITKReview). Keep in sync with ITK pyproject.toml [tasks.configure-ci].
    local mods=(
      -DModule_AdaptiveDenoising=ON -DModule_AnisotropicDiffusionLBR=ON
      -DModule_BoneEnhancement=ON -DModule_BoneMorphometry=ON
      -DModule_BSplineGradient=ON -DModule_Cuberille=ON
      -DModule_FastBilateral=ON -DModule_FixedPointInverseDisplacementField=ON
      -DModule_Fpfh=ON -DModule_GenericLabelInterpolator=ON
      -DModule_GrowCut=ON -DModule_HigherOrderAccurateGradient=ON
      -DModule_IOFDF=ON -DModule_IOMeshMZ3=ON -DModule_IOMeshSTL=ON
      -DModule_IOMeshSWC=ON -DModule_IOTransformDCMTK=ON -DModule_ITKDCMTK=ON
      -DModule_IsotropicWavelets=ON -DModule_LabelErodeDilate=ON
      -DModule_MGHIO=ON -DModule_MeshNoise=ON -DModule_MeshToPolyData=ON
      -DModule_MinimalPathExtraction=ON -DModule_Montage=ON
      -DModule_MorphologicalContourInterpolation=ON
      -DModule_MultipleImageIterator=ON -DModule_ParabolicMorphology=ON
      -DModule_PhaseSymmetry=ON -DModule_PolarTransform=ON
      -DModule_PrincipalComponentsAnalysis=ON -DModule_RANSAC=ON
      -DModule_RLEImage=ON -DModule_SimpleITKFilters=ON
      -DModule_SmoothingRecursiveYvvGaussianFilter=ON
      -DModule_SplitComponents=ON -DModule_Strain=ON
      -DModule_StructuralSimilarity=ON -DModule_SubdivisionQuadEdgeMeshFilter=ON
      -DModule_TextureFeatures=ON -DModule_Thickness3D=ON
      -DModule_TotalVariation=ON -DModule_TwoProjectionRegistration=ON
      -DModule_VariationalRegistration=ON
      -DModule_ITKReview=ON)
    # ITK_BUILD_ALL_MODULES so downstreams (ANTs/c3d/...) find non-default
    # modules they depend on (e.g. AdaptiveDenoising, MorphologicalContourInterpolation).
    local _itk_cmake=(cmake -S "$s" -B "${ITK_BUILD}" $(common_cmake_args)
      -DBUILD_EXAMPLES=ON -DITK_USE_BRAINWEB_DATA=ON
      -DITK_BUILD_DEFAULT_MODULES=ON -DITK_BUILD_ALL_MODULES=ON
      "${fftw[@]}" "${mods[@]}")
    _overlay_vnl_headers
    # First pass fetches the enabled remote modules (and may fail on one that
    # calls itk_module_examples() without an examples/ dir); stub those, then
    # configure for real.
    "${_itk_cmake[@]}" || true
    _stub_remote_examples
    "${_itk_cmake[@]}"
    return
  fi
  [ -f "${ITK_BUILD}/ITKConfig.cmake" ] || die "ITK not built; run: pixi run ITK"
  case "$name" in
    ANTs)        cmake -S "$s" -B "$b" $(common_cmake_args) -DUSE_SYSTEM_ITK=ON -DITK_DIR="$(itk_dir)" \
                   -DUSE_VTK=OFF -DUSE_TractographyTRX=OFF ;;
    BRAINSTools) cmake -S "$s" -B "$b" $(common_cmake_args) -DUSE_SYSTEM_ITK=ON -DITK_DIR="$(itk_dir)" \
                   -DOpenGL_GL_PREFERENCE=GLVND -DUSE_VTK=OFF -DBRAINSTools_BUILD_DICOM_SUPPORT=OFF ;;
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
                 cmake -S "$s" -B "$b" $(common_cmake_args) \
                   -DCMAKE_C_COMPILER="${SLICER_CC:-${CC}}" \
                   -DCMAKE_CXX_COMPILER="${SLICER_CXX:-${CXX}}" \
                   -DSlicer_ITK_GIT_REPOSITORY="${SLICER_ITK_GIT_REPOSITORY:-https://github.com/hjmjohnson/ITK}" \
                   -DSlicer_ITK_GIT_TAG="${SLICER_ITK_GIT_TAG:-slicer-v6.0.0-2026-06-11-57ff6c6}" \
                   -DSlicer_REQUIRED_QT_VERSION="${SLICER_QT_VERSION}" \
                   -DQt6_DIR="${SLICER_QT_PREFIX}/lib/cmake/Qt6" \
                   -DCMAKE_PREFIX_PATH="${SLICER_QT_PREFIX}" \
                   -DSlicer_BUILD_WEBENGINE_SUPPORT=OFF \
                   -DSlicer_USE_SYSTEM_CTKAPPLAUNCHER=OFF \
                   -DSlicer_USE_SYSTEM_sqlite=OFF \
                   -DSlicer_USE_SYSTEM_zlib=OFF \
                   -DSlicer_USE_SYSTEM_tbb=OFF ;;
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
                 cmake -S "${FOREST}/Slicer/Extensions/CMake" -B "$b" $(common_cmake_args) \
                   -DSlicer_DIR="${slicer_inner}" \
                   -DSlicer_EXTENSION_DESCRIPTION_DIR="${descdir}" \
                   -DQt6_DIR="${SLICER_QT_PREFIX}/lib/cmake/Qt6" \
                   -DCMAKE_PREFIX_PATH="${SLICER_QT_PREFIX}" \
                   ;;
    MITK)        warn "MITK SuperBuild is long";   cmake -S "$s" -B "$b" $(common_cmake_args) -DMITK_USE_SYSTEM_ITK=ON -DITK_DIR="$(itk_dir)" ;;
    elastix)     cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" ;;
    c3d)         cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" ;;
    SimpleITK)   warn "SimpleITK SuperBuild (C++ only; WRAP_DEFAULT=OFF)"
                 cmake -S "${s}/SuperBuild" -B "$b" $(common_cmake_args) \
                   -DUSE_SYSTEM_ITK=ON -DITK_DIR="$(itk_dir)" \
                   -DWRAP_DEFAULT=OFF -DBUILD_EXAMPLES=OFF ;;
    RTK)         cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" \
                   -DRTK_USE_CUDA="${RTK_USE_CUDA:-OFF}" ;;
    Ultrasound)  # optional VTK off; ignore Homebrew so its broken VTK/HDF5 config isn't found
                 cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" \
                   -DITKUltrasound_USE_VTK=OFF \
                   -DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew ;;
    OpenIGTLink) log "OpenIGTLink (protocol v3, static)"
                 cmake -S "$s" -B "$b" $(common_cmake_args) -DBUILD_SHARED_LIBS=OFF \
                   -DOpenIGTLink_PROTOCOL_VERSION_3=ON -DOpenIGTLink_ENABLE_VIDEOSTREAMING=OFF ;;
    OpenIGTLinkIO) local _vtk _oi; _vtk="$(vtk_dir)"; _oi="$(openigtlink_dir)"
                 [ -n "${_vtk}" ] || die "OpenIGTLinkIO: no built VTK — build Slicer/BRAINSTools or set VTK_DIR"
                 [ -n "${_oi}" ] || die "OpenIGTLinkIO: OpenIGTLink not built — run: build OpenIGTLink"
                 log "OpenIGTLinkIO: VTK_DIR=${_vtk}  OpenIGTLink_DIR=${_oi}"
                 cmake -S "$s" -B "$b" $(common_cmake_args) -DVTK_DIR="${_vtk}" -DOpenIGTLink_DIR="${_oi}" \
                   -DIGTLIO_USE_GUI=OFF ;;
    vtkAddon)    local _vtk; _vtk="$(vtk_dir)"
                 [ -n "${_vtk}" ] || die "vtkAddon: no built VTK (vtk-config.cmake) found — build Slicer/BRAINSTools or set VTK_DIR"
                 log "vtkAddon: VTK_DIR=${_vtk}"
                 cmake -S "$s" -B "$b" $(common_cmake_args) -DVTK_DIR="${_vtk}" ;;
    IGSIO)       local _vtk _va; _vtk="$(vtk_dir)"; _va="$(vtkaddon_dir)"
                 [ -n "${_vtk}" ] || die "IGSIO: no built VTK (vtk-config.cmake) found — build Slicer/BRAINSTools or set VTK_DIR"
                 [ -n "${_va}" ] || die "IGSIO: vtkAddon not built — run: build vtkAddon (or set vtkAddon_DIR)"
                 log "IGSIO: ITK_DIR=$(itk_dir)  VTK_DIR=${_vtk}  vtkAddon_DIR=${_va}"
                 cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" \
                   -DVTK_DIR="${_vtk}" -DvtkAddon_DIR="${_va}" -DIGSIO_USE_3DSlicer=OFF ;;
    PlusLib)     local _vtk _igsio _oi _oio; _vtk="$(vtk_dir)"; _igsio="$(igsio_dir)"
                 _oi="$(openigtlink_dir)"; _oio="$(openigtlinkio_dir)"
                 [ -n "${_vtk}" ] || die "PlusLib: no built VTK (vtk-config.cmake) found — build Slicer/BRAINSTools or set VTK_DIR"
                 [ -n "${_igsio}" ] || die "PlusLib: IGSIO not built — run: build IGSIO (or set IGSIO_DIR)"
                 [ -n "${_oio}" ] || die "PlusLib: OpenIGTLinkIO not built (igtlioConverter target required) — run: build OpenIGTLinkIO"
                 log "PlusLib: ITK_DIR=$(itk_dir)  VTK_DIR=${_vtk}  IGSIO_DIR=${_igsio}  OpenIGTLinkIO_DIR=${_oio}"
                 cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" \
                   -DVTK_DIR="${_vtk}" -DIGSIO_DIR="${_igsio}" -DPLUS_USE_OpenIGTLink=ON \
                   -DOpenIGTLink_DIR="${_oi}" -DOpenIGTLinkIO_DIR="${_oio}" ;;
    VkFFTBackend)
                 local _vk; _vk="$(vkfft_backend)"
                 [ -n "${_vk}" ] || die "VkFFTBackend: no GPU backend (CUDA/Metal/OpenCL) on this host"
                 local _cuda=(); [ "${_vk}" = 1 ] && _cuda=(-DCMAKE_CUDA_COMPILER="$(_find_nvcc)")
                 log "VkFFTBackend: VKFFT_BACKEND=${_vk} (1=CUDA 5=Metal 3=OpenCL)"
                 cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" \
                   -DVKFFT_BACKEND="${_vk}" "${_cuda[@]}" ;;
    *)  cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" ;;
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
  local name="$1" b="${FOREST}/${1}-build"; [ "$name" = ITK ] && b="${ITK_BUILD}"
  # A complete configure leaves build.ninja; a half-failed one leaves only
  # CMakeCache.txt. Require build.ninja so a broken tree is reconfigured.
  [ -f "${b}/build.ninja" ] || configure_one "$name"
  [ "$name" = ANTs ] && _patch_ants_missing_includes
  [ "$name" = IGSIO ] && _patch_igsio_iostream
  log "build ${name} (-j${JOBS})"
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
  [ "$name" = ITK ] && _fix_dcmtk_ijg_symlinks
  [ "$name" = ITK ] && [ "${ITK_USE_INSTALL:-0}" = 1 ] && install_itk; }

# Install ITK so downstreams consume the install tree (whose export defines the
# vcl static-import target). Works around a stale install rule for the generated
# itk_jpeg_mangle.h by copying it where the rule expects.
install_itk(){
  local gen="${ITK_BUILD}/Modules/ThirdParty/JPEG/src/itkjpeg-turbo/itk_jpeg_mangle.h"
  local src="${FOREST}/ITK/Modules/ThirdParty/JPEG/src/itkjpeg-turbo/itk_jpeg_mangle.h"
  [ -f "${gen}" ] && [ ! -f "${src}" ] && cp "${gen}" "${src}"
  log "install ITK -> ${ITK_INSTALL}"
  cmake --install "${ITK_BUILD}" --prefix "${ITK_INSTALL}" >/dev/null; }

cmd_remotes(){ build_one ITK
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
  build)     shift; build_one "${1:?build <name>}" ;;
  build-all) for n in "${BUILD_ORDER[@]}"; do [ -d "${FOREST}/$n" ] && build_one "$n"; done ;;
  remotes)   cmd_remotes ;;
  sync-vnl)  cmd_sync_vnl ;;
  repoint-itk) cmd_repoint_itk ;;
  list)      cmd_list ;;
  status)    cmd_status ;;
  vkfft-backend) vkfft_backend ;;
  *) die "unknown command '$1' (checkout|configure|build|build-all|remotes|sync-vnl|list|status|vkfft-backend)" ;;
esac
