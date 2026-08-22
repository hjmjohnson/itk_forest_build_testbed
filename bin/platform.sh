# platform.sh — host-platform abstraction for the forest engine.
#
# Sourced (never executed) by bin/*.sh. The kit runs natively on macOS, Linux
# and Windows; every place where those three genuinely differ resolves through
# a helper here rather than through an inline `uname` test scattered across the
# engine. Nothing in this file has an effect on macOS/Linux beyond defining
# FOREST_OS and identity-function versions of the helpers, so the Unix code
# paths stay byte-identical to what they were before Windows existed.
#
# Provides:
#   FOREST_OS            macos | linux | windows
#   npath <p>            path in the form the NATIVE toolchain understands
#   PATHSEP              list separator for CMAKE_PREFIX_PATH & friends
#   FOREST_PYTHON[_PRE]  a working Python 3 interpreter
#   pixi_env_bindirs <e> / pixi_env_include <e>   conda env layout
#   msvc_activate        import the MSVC build environment (Windows only)
#   qt_platform_subdir   official-Qt-installer platform directory name

case "$(uname -s)" in
  Darwin)               FOREST_OS=macos   ;;
  Linux)                FOREST_OS=linux   ;;
  MINGW*|MSYS*|CYGWIN*) FOREST_OS=windows ;;
  *)                    FOREST_OS=linux   ;;   # best effort; behaves as Unix
esac
export FOREST_OS

# --- paths -----------------------------------------------------------------
#
# On Windows the engine runs under an MSYS2 bash whose paths ("/cygdrive/c/...",
# or "/c/..." depending on the /etc/fstab of the Git install) are meaningless to
# cmake.exe, cl.exe and ninja.exe. Every path that will reach a native tool —
# or be written into a CMakeUserPresets.json — must therefore be converted.
#
# The engine converts its ROOTS once (TESTBED, FOREST, SRC_ROOT, REPOS,
# CCACHE_DIR) and everything else is derived from those by string
# concatenation, so a single conversion at the top covers the hundreds of
# -D<pkg>_DIR= arguments downstream. MSYS2's bash accepts native "C:/..." form
# for its own builtins (test/cd/mkdir/ls), so the converted roots keep working
# for the shell too — verified, not assumed.
#
# Mixed form ("C:/x/y", -m) is used rather than backslash form (-w) because it
# needs no escaping in shell, JSON or CMake.
# npath: native form, for anything handed to cmake/cl/ninja or written into a
#        CMakeUserPresets.json.
# upath: shell form, for anything that goes into bash's own $PATH. These are
#        NOT interchangeable on Windows: $PATH is colon-separated, so a native
#        "C:/x" entry is ambiguous (the drive colon reads as a separator) and
#        must be "/c/x" or "/cygdrive/c/x" instead.
if [ "${FOREST_OS}" = windows ]; then
  npath(){ [ -n "${1:-}" ] || return 0; cygpath -m -- "$1"; }
  # cygpath -u returns the SHORTEST POSIX spelling, which is not always a
  # round-trip. Under `pixi run` the shell is the pixi env's own MSYS2, mounting
  # "/" at <env>/Library but "/bin" at <env>/Library/usr/bin -- so
  # <env>/Library/bin shortens to "/bin", which then resolves somewhere else
  # entirely (that is how pixi's cmake fell off PATH and a system cmake 3.26
  # silently configured the forest). Verify the conversion still names the same
  # directory and keep the input when it does not.
  upath(){
    [ -n "${1:-}" ] || return 0
    local u; u="$(cygpath -u -- "$1")"
    if [ -e "$1" ] && [ ! -e "${u}" ]; then printf '%s' "$1"; else printf '%s' "${u}"; fi; }
  PATHSEP=';'
else
  npath(){ printf '%s' "${1:-}"; }
  upath(){ printf '%s' "${1:-}"; }
  PATHSEP=':'
fi
export PATHSEP

# --- python ----------------------------------------------------------------
#
# The engine shells out to bin/config.py constantly (versions.toml is the
# build-version source of truth). `python3` is not a safe assumption on
# Windows: conda/pixi win-64 environments ship python.exe with NO python3.exe,
# and a bare Windows host may have only the `py` launcher. Resolve once.
_forest_resolve_python(){
  local p
  for p in python3 python; do
    command -v "$p" >/dev/null 2>&1 && { FOREST_PYTHON="$p"; FOREST_PYTHON_PRE=""; return 0; }
  done
  if command -v py >/dev/null 2>&1; then
    FOREST_PYTHON="py"; FOREST_PYTHON_PRE="-3"; return 0
  fi
  return 1
}
_forest_resolve_python || { FOREST_PYTHON="python3"; FOREST_PYTHON_PRE=""; }
export FOREST_PYTHON FOREST_PYTHON_PRE

# --- build artifacts -------------------------------------------------------
#
# "Verify by artifact, not exit code" needs the platform's real filenames.
# MSVC writes Foo.lib / Foo.dll / foo.exe where Unix writes libFoo.a /
# libFoo.so | libFoo.dylib / foo -- note there is no "lib" prefix on Windows,
# so a Unix-shaped glob ("libITKCommon-*.a") matches nothing there and a
# fully-built tree is scored as a build FAILURE. Callers ask here instead of
# testing $FOREST_OS at each of the ~20 per-target checks in run-matrix.sh.
#
#   lib_globs <stem>  filename globs for a library built from <stem>, where
#                     <stem> is the Unix base name WITHOUT the "lib" prefix
#                     and MAY itself contain globs (e.g. "ITKCommon-*").
#   any_lib_globs     the same, for "any library at all".
#   EXE_SUFFIX        "" on Unix, ".exe" on Windows.
if [ "${FOREST_OS}" = windows ]; then
  EXE_SUFFIX=".exe"
  lib_globs(){     printf '%s\n' "${1}.lib" "${1}.dll"; }
  any_lib_globs(){ printf '%s\n' '*.lib' '*.dll'; }
else
  EXE_SUFFIX=""
  lib_globs(){     printf '%s\n' "lib${1}.a" "lib${1}.so" "lib${1}.dylib"; }
  any_lib_globs(){ printf '%s\n' '*.a' '*.so' '*.dylib'; }
fi
export EXE_SUFFIX

# --- conda/pixi environment layout -----------------------------------------
#
# A conda env puts executables in bin/ and headers in include/ on Unix, but in
# the env root + Library/bin + Scripts, and Library/include, on Windows.
pixi_env_bindirs(){   # <envroot> -> preferred-first, one per line
  if [ "${FOREST_OS}" = windows ]; then
    printf '%s\n' "${1}" "${1}/Library/bin" "${1}/Scripts"
  else
    printf '%s\n' "${1}/bin"
  fi; }
pixi_env_include(){
  if [ "${FOREST_OS}" = windows ]; then printf '%s' "${1}/Library/include"
  else printf '%s' "${1}/include"; fi; }

# --- Qt --------------------------------------------------------------------
#
# Platform directory inside an official Qt installer tree (~/Qt/<ver>/<subdir>
# on Unix, C:/Qt/<ver>/<subdir> on Windows).
qt_platform_subdir(){
  if [ -n "${QT_PLATFORM_SUBDIR:-}" ]; then printf '%s' "${QT_PLATFORM_SUBDIR}"; return; fi
  case "${FOREST_OS}" in
    macos)   printf '%s' macos ;;
    windows) printf '%s' msvc2022_64 ;;
    *)       printf '%s' gcc_64 ;;
  esac; }

# --- MSVC ------------------------------------------------------------------
#
# Import the Visual Studio build environment into this shell, so cmake's Ninja
# generator finds cl.exe/link.exe and the SDK. Idempotent, and a no-op off
# Windows. Returns non-zero if no VC++ toolset can be located; the caller
# decides whether that is fatal.
#
# Ninja (not the Visual Studio generator) is what the kit uses everywhere, and
# it is also the only generator that honours CMAKE_<LANG>_COMPILER_LAUNCHER —
# i.e. the only one under which ccache works at all. That makes activating
# vcvars in-process a hard requirement rather than a convenience: the VS
# generator would locate the toolset itself, Ninja will not.
#
# MSVC_TOOLSET pins a specific toolset (e.g. 14.38.33130) via -vcvars_ver.
msvc_activate(){
  [ "${FOREST_OS}" = windows ] || return 0
  [ -n "${_FOREST_MSVC_ACTIVE:-}" ] && return 0

  local pf86 vswhere vsroot vcvars out line k v
  # "ProgramFiles(x86)" is not a valid shell identifier, so it cannot be
  # referenced as $ProgramFiles(x86); printenv reads it by name.
  pf86="$(printenv 'ProgramFiles(x86)' 2>/dev/null || true)"
  [ -n "${pf86}" ] || pf86='C:\Program Files (x86)'
  vswhere="$(cygpath -u "${pf86}")/Microsoft Visual Studio/Installer/vswhere.exe"

  vsroot="${VSINSTALLDIR:-}"
  if [ -z "${vsroot}" ] && [ -x "${vswhere}" ]; then
    vsroot="$("${vswhere}" -latest -products '*' \
                -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 \
                -property installationPath 2>/dev/null | tr -d '\r' | head -1)"
  fi
  [ -n "${vsroot}" ] || return 1

  vcvars="$(cygpath -u "${vsroot}")/VC/Auxiliary/Build/vcvars64.bat"
  [ -f "${vcvars}" ] || return 1

  # Run vcvars in cmd and read back the environment it produced. `cmd //c`
  # (doubled slash) stops MSYS2 from rewriting the /c switch into a path, and
  # MSYS2_ARG_CONV_EXCL keeps it from mangling the batch-file argument.
  out="$(MSYS2_ARG_CONV_EXCL='*' cmd //c "call \"$(cygpath -w "${vcvars}")\" \
          ${MSVC_TOOLSET:+-vcvars_ver=${MSVC_TOOLSET}} >nul 2>&1 && set" 2>/dev/null | tr -d '\r')"
  [ -n "${out}" ] || return 1

  while IFS= read -r line; do
    k="${line%%=*}"; v="${line#*=}"
    [ "${k}" = "${line}" ] && continue          # not a KEY=VALUE line
    case "${k}" in
      # cl.exe/link.exe read these natively; they must stay in Windows form,
      # and MSYS2 does not auto-convert them.
      INCLUDE|LIB|LIBPATH|VCINSTALLDIR|VCToolsInstallDir|VCToolsVersion|\
      VSINSTALLDIR|VisualStudioVersion|WindowsSdkDir|WindowsSdkVerBinPath|\
      WindowsSDKVersion|UniversalCRTSdkDir|UCRTVersion|VSCMD_ARG_HOST_ARCH|\
      VSCMD_ARG_TGT_ARCH)
        export "${k}=${v}" ;;
      # PATH is bash's own, so it must be converted to Unix list form. vcvars
      # inherits and prepends to the PATH cmd got from us, so anything pixi put
      # there (cmake, ninja, ccache, python) survives.
      Path|PATH)
        PATH="$(cygpath -up "${v}")"; export PATH ;;
    esac
  done <<< "${out}"

  command -v cl >/dev/null 2>&1 || return 1
  _FOREST_MSVC_ACTIVE=1; export _FOREST_MSVC_ACTIVE
  return 0; }
