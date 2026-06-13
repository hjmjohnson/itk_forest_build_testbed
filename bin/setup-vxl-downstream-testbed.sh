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

if [ -z "${CXX:-}" ]; then
  if [ -x /opt/homebrew/opt/llvm/bin/clang++ ]; then
    CC=/opt/homebrew/opt/llvm/bin/clang; CXX=/opt/homebrew/opt/llvm/bin/clang++
  else CC="$(command -v cc || command -v clang || command -v gcc)"
       CXX="$(command -v c++ || command -v clang++ || command -v g++)"; fi
fi
: "${CC:=$(command -v cc || command -v clang || command -v gcc)}"

# Slicer needs a real Qt6 (its SuperBuild builds VTK/CTK against it). On macOS a
# Homebrew qt@6 on PATH shadows a user Qt: its host-tools (Qt6CoreTools, ...) get
# found from Homebrew while Qt6 itself comes from ~/Qt, which fails Qt6 package
# configuration. Prefer ~/Qt/<ver>/macos and drop Homebrew qt@6 from PATH so Qt6
# and its host-tools resolve consistently for both configure and build.
SLICER_QT_VERSION="${SLICER_QT_VERSION:-6.9.1}"
# Prefer the node config's QT6_DIR; fall back to the version-derived path.
SLICER_QT_PREFIX="${SLICER_QT_PREFIX:-${QT6_DIR:-${HOME}/Qt/${SLICER_QT_VERSION}/macos}}"
# Fallback: if the pinned Qt isn't installed, pick the newest ~/Qt/6.*/macos
# that has a Qt6 config (override with SLICER_QT_PREFIX or SLICER_QT_VERSION).
if [ ! -d "${SLICER_QT_PREFIX}/lib/cmake/Qt6" ]; then
  for _q in $(ls -d "${HOME}"/Qt/6.*/macos 2>/dev/null | sort -Vr); do
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
      -DModule_RLEImage=ON -DModule_SmoothingRecursiveYvvGaussianFilter=ON
      -DModule_SplitComponents=ON -DModule_Strain=ON
      -DModule_StructuralSimilarity=ON -DModule_SubdivisionQuadEdgeMeshFilter=ON
      -DModule_TextureFeatures=ON -DModule_Thickness3D=ON
      -DModule_TotalVariation=ON -DModule_TwoProjectionRegistration=ON
      -DModule_VariationalRegistration=ON
      -DModule_ITKReview=ON)
    # ITK_BUILD_ALL_MODULES so downstreams (ANTs/c3d/...) find non-default
    # modules they depend on (e.g. AdaptiveDenoising, MorphologicalContourInterpolation).
    cmake -S "$s" -B "${ITK_BUILD}" $(common_cmake_args) \
      -DBUILD_EXAMPLES=ON -DITK_USE_BRAINWEB_DATA=ON \
      -DITK_BUILD_DEFAULT_MODULES=ON -DITK_BUILD_ALL_MODULES=ON \
      "${fftw[@]}" "${mods[@]}"
    return
  fi
  [ -f "${ITK_BUILD}/ITKConfig.cmake" ] || die "ITK not built; run: pixi run ITK"
  case "$name" in
    ANTs)        cmake -S "$s" -B "$b" $(common_cmake_args) -DUSE_SYSTEM_ITK=ON -DITK_DIR="$(itk_dir)" \
                   -DUSE_VTK=OFF -DUSE_TractographyTRX=OFF ;;
    BRAINSTools) cmake -S "$s" -B "$b" $(common_cmake_args) -DUSE_SYSTEM_ITK=ON -DITK_DIR="$(itk_dir)" \
                   -DUSE_VTK=OFF -DBRAINSTools_BUILD_DICOM_SUPPORT=OFF ;;
    Slicer)      warn "Slicer SuperBuild is long (builds VTK/CTK + own ITK 6; Qt6 from ${SLICER_QT_PREFIX})"
                 # The testbed ITK is headless (Module_ITKVtkGlue=OFF), so it cannot
                 # satisfy Slicer_USE_SYSTEM_ITK. Let Slicer's SuperBuild build its
                 # own ITK 6 (with ITKVtkGlue + Qt) from the slicer-v6 ITK branch.
                 [ -d "${SLICER_QT_PREFIX}/lib/cmake/Qt6" ] || die "Qt6 not found at ${SLICER_QT_PREFIX} (set SLICER_QT_PREFIX/SLICER_QT_VERSION)"
                 # Slicer forwards -DCMAKE_<LANG>_COMPILER to every ExternalProject
                 # (VTK/ITK/Python/...) but NOT the ccache *launcher*, so a launcher
                 # flag would skip ccache for those EPs. Point the compiler at ccache's
                 # libexec wrapper instead: it propagates ccache to every EP and runs
                 # real Apple clang underneath (the pixi/conda clang's darwin20 target
                 # fails the CPython _ssl link).
                 cmake -S "$s" -B "$b" $(common_cmake_args) \
                   -DCMAKE_C_COMPILER="${SLICER_CC:-$(slicer_cc clang)}" \
                   -DCMAKE_CXX_COMPILER="${SLICER_CXX:-$(slicer_cc clang++)}" \
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
    *)  cmake -S "$s" -B "$b" $(common_cmake_args) -DITK_DIR="$(itk_dir)" ;;
  esac
}

build_one(){ require cmake ninja ccache
  local name="$1" b="${FOREST}/${1}-build"; [ "$name" = ITK ] && b="${ITK_BUILD}"
  # A complete configure leaves build.ninja; a half-failed one leaves only
  # CMakeCache.txt. Require build.ninja so a broken tree is reconfigured.
  [ -f "${b}/build.ninja" ] || configure_one "$name"
  log "build ${name} (-j${JOBS})"; cmake --build "$b" -j"${JOBS}"
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
  *) die "unknown command '$1' (checkout|configure|build|build-all|remotes|sync-vnl|list|status)" ;;
esac
