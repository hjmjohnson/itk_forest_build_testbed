#!/usr/bin/env bash
# Sweep the fake downstream-consumer family against one ITK, both from its
# build tree and its install tree, and score each by ARTIFACT (the consumer
# executable on disk), never by pipe exit code.
#
# Usage:
#   run-downstream-matrix.sh --build <itk-build-dir> --install <itk-install-prefix> \
#                            --label <tag> [--out <results.tsv>]
#
# Retarget at a non-zlib ThirdParty module by exporting before calling:
#   PROBE_SRC=/abs/probe_hdf5.cxx ITK_MODULE_TARGET=ITK::ITKHDF5Module \
#   THIRDPARTY_TARGET=HDF5::HDF5  FIND_COMPONENTS=ITKIOHDF5  run-downstream-matrix.sh ...
#
# Env:
#   CMAKE, NINJA   toolchain overrides (default: cmake, ninja on PATH)
#   CONSUMERS_DIR  default: <skill>/consumers
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SELF_DIR")"
CONSUMERS_DIR="${CONSUMERS_DIR:-$SKILL_DIR/consumers}"
CMAKE="${CMAKE:-cmake}"

BUILD_DIR="" ; INSTALL_PREFIX="" ; LABEL="run" ; OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --build)   BUILD_DIR="$2"; shift 2 ;;
    --install) INSTALL_PREFIX="$2"; shift 2 ;;
    --label)   LABEL="$2"; shift 2 ;;
    --out)     OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Per-consumer override knobs (forwarded to each consumer configure).
PROBE_SRC="${PROBE_SRC:-$CONSUMERS_DIR/probe_zlib.cxx}"
ITK_MODULE_TARGET="${ITK_MODULE_TARGET:-ITK::ITKZLIBModule}"
THIRDPARTY_TARGET="${THIRDPARTY_TARGET:-ZLIB::ZLIB}"
FIND_COMPONENTS="${FIND_COMPONENTS:-ITKIOPNG}"

# Absolutize a path (cmake's ITK_DIR must be absolute: the consumer configures
# in a temp dir, so a relative ITK_DIR would resolve there and silently fail).
abspath(){ [ -n "$1" ] && ( cd "$1" 2>/dev/null && pwd ) || readlink -f "$1" 2>/dev/null; }

# Resolve the install-tree ITK config dir (<prefix>/lib/cmake/ITK-*), absolute.
install_itk_dir(){
  local p d
  p="$(abspath "$1")"
  d="$(find "$p/lib/cmake" -maxdepth 1 -type d -name 'ITK-*' 2>/dev/null | head -1)"
  [ -n "$d" ] && echo "$d"
}

[ -n "$BUILD_DIR" ] && BUILD_DIR="$(abspath "$BUILD_DIR")"

CONSUMERS="modern_libraries legacy_usefile config_nomodule components direct_target naive_thirdparty"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
[ -n "$OUT" ] || OUT="$WORK/results.tsv"
printf 'label\ttree\tconsumer\tresult\n' > "$OUT"
# Persist per-cell logs next to --out so failures are diagnosable after the run.
LOGDIR="${OUT%.tsv}.logs"; rm -rf "$LOGDIR"; mkdir -p "$LOGDIR"

run_one(){ # tree itk_dir consumer
  local tree="$1" itk_dir="$2" name="$3"
  local src="$CONSUMERS_DIR/$name" bld="$WORK/$LABEL-$tree-$name"
  local cfg_log="$LOGDIR/$LABEL-$tree-$name.cfg.log"
  local bld_log="$LOGDIR/$LABEL-$tree-$name.build.log"
  rm -rf "$bld"
  "$CMAKE" -S "$src" -B "$bld" -GNinja \
      -DITK_DIR="$itk_dir" \
      -DPROBE_SRC="$PROBE_SRC" \
      -DITK_MODULE_TARGET="$ITK_MODULE_TARGET" \
      -DTHIRDPARTY_TARGET="$THIRDPARTY_TARGET" \
      -DFIND_COMPONENTS="$FIND_COMPONENTS" \
      > "$cfg_log" 2>&1
  if [ $? -ne 0 ]; then
    # Configure-time failure (e.g. dangling ZLIB::ZLIB imported target).
    printf '%s\t%s\t%s\tFAIL-configure\n' "$LABEL" "$tree" "$name" >> "$OUT"
    return
  fi
  "$CMAKE" --build "$bld" > "$bld_log" 2>&1
  # Score by ARTIFACT, never by exit code. UseITK may redirect the runtime
  # output dir, so search the whole build tree for the executable.
  if find "$bld" -type f -name app 2>/dev/null | grep -q .; then
    printf '%s\t%s\t%s\tPASS\n' "$LABEL" "$tree" "$name" >> "$OUT"
  else
    printf '%s\t%s\t%s\tFAIL-build\n' "$LABEL" "$tree" "$name" >> "$OUT"
  fi
}

if [ -n "$BUILD_DIR" ] && [ -f "$BUILD_DIR/ITKConfig.cmake" ]; then
  for c in $CONSUMERS; do run_one buildtree "$BUILD_DIR" "$c"; done
else
  echo "WARN: no usable --build tree ($BUILD_DIR), skipping build-tree leg" >&2
fi

if [ -n "$INSTALL_PREFIX" ]; then
  idir="$(install_itk_dir "$INSTALL_PREFIX")"
  if [ -n "$idir" ]; then
    for c in $CONSUMERS; do run_one installtree "$idir" "$c"; done
  else
    echo "WARN: no ITK config under $INSTALL_PREFIX/lib/cmake, skipping install leg" >&2
  fi
fi

echo "=== results ($LABEL) ==="
column -t -s "$(printf '\t')" "$OUT"
echo "(logs + results under: $WORK -> copied below if --out given)"
[ -n "${OUT_KEEP:-}" ] && cp -r "$WORK" "$OUT_KEEP" 2>/dev/null
