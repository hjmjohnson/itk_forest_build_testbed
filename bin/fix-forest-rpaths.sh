#!/usr/bin/env bash
# Add ${CONDA_PREFIX}/lib as an rpath to already-built forest binaries that
# reference @rpath/-relative conda runtime libs (libc++, libc++abi, libunwind,
# libstdc++, ...) but whose baked rpaths do not resolve them. This repairs
# trees built before the LDFLAGS rpath export in setup-itk-downstream-testbed.sh;
# fresh builds no longer need it.
#
# Usage:
#   bin/fix-forest-rpaths.sh [--apply] [FOREST_ROOT ...]
#
# Default: dry-run over every build_forest* under the kit root. Pass --apply to
# modify binaries, or explicit forest roots to scope the pass. Idempotent.
set -euo pipefail

KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPLY=0
declare -a ROOTS=()
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) ROOTS+=("$a") ;;
  esac
done
[ "${#ROOTS[@]}" -eq 0 ] && for d in "${KIT_ROOT}"/build_forest*; do [ -d "$d" ] && ROOTS+=("$d"); done

CONDA_LIB="${CONDA_PREFIX:-${KIT_ROOT}/.pixi/envs/default}/lib"
[ -d "${CONDA_LIB}" ] || { echo "[err] conda lib dir not found: ${CONDA_LIB}" >&2; exit 1; }

OS="$(uname -s)"
# Runtime libs that, when referenced as @rpath/@loader_path-relative names,
# must resolve from the conda env.
NEEDLE='lib(c\+\+|c\+\+abi|unwind|stdc\+\+|gcc_s|omp)\.'

repaired=0 scanned=0 skipped=0

process_macho(){
  local f="$1"
  # Only touch binaries that record a conda runtime lib by @rpath name.
  otool -L "$f" 2>/dev/null | grep -Eq "@rpath/.*${NEEDLE}" || return 0
  scanned=$((scanned+1))
  # Already has a usable rpath pointing at the conda lib dir?
  if otool -l "$f" 2>/dev/null | awk '/LC_RPATH/{g=1} g&&/ path /{print $2; g=0}' \
       | grep -Fxq "${CONDA_LIB}"; then
    skipped=$((skipped+1)); return 0
  fi
  echo "  fix: ${f#${KIT_ROOT}/}"
  if [ "${APPLY}" -eq 1 ]; then
    install_name_tool -add_rpath "${CONDA_LIB}" "$f" 2>/dev/null \
      && repaired=$((repaired+1)) \
      || echo "    [warn] install_name_tool failed (codesign/permissions?)" >&2
  fi
}

process_elf(){
  local f="$1"
  command -v patchelf >/dev/null 2>&1 || { echo "[err] patchelf required on Linux" >&2; exit 1; }
  readelf -d "$f" 2>/dev/null | grep -Eq "\(RPATH\)|\(RUNPATH\)" && :
  # Add without duplicating: patchelf merges, but skip if already present.
  local cur; cur="$(patchelf --print-rpath "$f" 2>/dev/null || true)"
  case ":${cur}:" in *":${CONDA_LIB}:"*) skipped=$((skipped+1)); return 0 ;; esac
  scanned=$((scanned+1))
  echo "  fix: ${f#${KIT_ROOT}/}"
  if [ "${APPLY}" -eq 1 ]; then
    patchelf --add-rpath "${CONDA_LIB}" "$f" \
      && repaired=$((repaired+1)) \
      || echo "    [warn] patchelf failed" >&2
  fi
}

echo "conda lib : ${CONDA_LIB}"
echo "mode      : $([ "${APPLY}" -eq 1 ] && echo APPLY || echo dry-run)"
for root in "${ROOTS[@]}"; do
  echo "=== forest: ${root#${KIT_ROOT}/} ==="
  # Executables and shared libs only; skip static archives and object files.
  # Prune CMake probe/temp dirs — throwaway compiler-check artifacts, not products.
  while IFS= read -r -d '' f; do
    case "${OS}" in
      Darwin) file "$f" 2>/dev/null | grep -q 'Mach-O' && process_macho "$f" ;;
      Linux)  file "$f" 2>/dev/null | grep -q 'ELF'    && process_elf   "$f" ;;
    esac
  done < <(find "$root" \( -name CMakeFiles -o -name CMakeTmp \) -prune -o \
             -type f \( -perm -100 -o -name '*.dylib' -o -name '*.so' -o -name '*.so.*' \) -print0 2>/dev/null)
done

echo "----"
echo "referencing conda @rpath libs: ${scanned}   already-ok: ${skipped}   $([ "${APPLY}" -eq 1 ] && echo repaired || echo would-fix): $([ "${APPLY}" -eq 1 ] && echo "${repaired}" || echo "${scanned}")"
[ "${APPLY}" -eq 0 ] && echo "(dry-run; re-run with --apply to modify)"
