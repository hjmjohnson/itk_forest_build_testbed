# Native Windows — MSVC, Ninja, ccache, and the path rules

The kit runs natively on Windows alongside macOS and Linux. One engine, one set
of presets; the places the three platforms genuinely differ resolve through
`bin/platform.sh`. This page is the Windows-specific half.

## Prerequisites

| | |
|---|---|
| **Visual Studio 2022** | Community, Professional or Enterprise, **or** Build Tools 2022 — with the *Desktop development with C++* workload. MSVC is not optional: it is the only ABI Slicer, Qt's official binaries and the wider Windows C++ ecosystem share. |
| **Qt 6 `msvc2022_64`** | An **open-source** official Qt at `C:\Qt` (so `C:/Qt/6.11.2/msvc2022_64`) — the single supported location. **Slicer only** — ITK and the plain consumers do not need it. Install it with aqtinstall, *not* the online installer; see *Qt 6* below. |
| **Git for Windows** | Supplies the MSYS2 bash the engine runs under. Already present if you cloned this repo. |
| **pixi** | Supplies cmake, ninja, ccache, python, git. |

Everything else — the toolchain, ccache, the forest — comes from `pixi run`.

Long paths help but are not sufficient on their own; see *MAX_PATH* below.

## Fast path

```bash
pixi run config                                   # writes config.sh for this node
FOREST_REFERENCE_SUFFIX=itk-main ITK_REF=origin/main pixi run checkout
FOREST_REFERENCE_SUFFIX=itk-main pixi run build-ITK
```

The forest lands in **`C:\S-itk-main`**, not under the repo — see *MAX_PATH*.

## Qt 6 — get the open-source build, not an evaluation

Qt's online installer **hides the open-source option entirely once your Qt
Account holds any evaluation entitlement**. It then routes you into the
commercial flow: no open-source license page, no plain MSVC kit selection, and
what lands in `C:\Qt` is a time-limited trial that stops being licensed on a
date you did not choose. Confirm which one you have:

```bash
qt=$(cygpath -u 'C:/Qt')          # never hardcode /c — see *Paths*, rule 3
grep -E "License schema|License expiry" "$qt/InstallationLog.txt" | sort -u
ls "$qt"/*/msvc*/bin/licheck.exe 2>/dev/null   # present => commercial build
```

`Supported Evaluation` plus an expiry date means the tree is a trial, and no
amount of clicking in the installer will turn it into the open-source build —
the entitlement is attached to the account, not the installation.

Use **`utilities/qt-oss/`** instead: `aqtinstall` fetches the same official
open-source archives straight from `download.qt.io` with no account, no
`licheck`, and no expiry. Install it from **git master**, not PyPI — Qt split
the download layout at 6.11.0 (`qt6_6112/qt6_6112_msvc2022_64/`), aqtinstall
handles it as of PR #1000 (merged 2026-03-24), but the newest release predates
that merge, so PyPI's aqtinstall fails every 6.11.x call:

```bash
py -3 -m venv /c/tmp/aqtvenv
AQT=/c/tmp/aqtvenv/Scripts/python.exe
$AQT -m pip install "git+https://github.com/miurahr/aqtinstall.git@master"
$AQT -m aqt install-qt windows desktop 6.11.2 win64_msvc2022_64 -m qt5compat qtmultimedia qtpositioning qtshadertools qtscxml qtwebchannel qtwebengine qtwebsockets qtimageformats --outputdir 'C:/Qt'
pixi run config
```

`utilities/qt-oss/README.md` explains that module set — it is exactly Slicer's
`Slicer_REQUIRED_QT_MODULES` — and how to verify the result by artifact.
`bin/setup-itk-downstream-testbed.sh` prints the same command if a Slicer build
starts without a usable Qt.

## Why Ninja and not the Visual Studio generator

ccache is the reason. The kit's whole premise is that a one-header ITK change
recompiles only the translation units that include it, and that two forests
share compiled objects. ccache attaches through
`CMAKE_<LANG>_COMPILER_LAUNCHER`, which **only the Ninja generator honours** —
under MSBuild the launcher is ignored and every rebuild is a full rebuild.

Ninja does not find a toolset by itself the way the VS generator does, so
`msvc_activate()` in `bin/platform.sh` imports `vcvars64.bat` into the engine's
shell before cmake runs. Pin a specific toolset with `MSVC_TOOLSET=14.38.33130`.

## Why `/Z7` and not `/Zi`

`cmake/presets/00-base.windows.json` sets:

```json
"CMAKE_MSVC_DEBUG_INFORMATION_FORMAT": "Embedded",
"CMAKE_POLICY_DEFAULT_CMP0141": "NEW"
```

MSVC defaults to `/Zi`, which writes debug info to a **shared .pdb** that ccache
cannot cache — every compile would miss, silently, and the testbed would degrade
into a plain build system on Windows. `Embedded` selects `/Z7`, putting debug
info in the object where ccache can store it. `CMP0141` must be `NEW` or the
abstraction is ignored.

Expect a **lower cross-forest hit rate than on Unix** regardless: MSVC has no
`-ffile-prefix-map`, so path canonicalization falls entirely to `CCACHE_BASEDIR`.

## Paths — the three rules

This is where a Windows port actually lives or dies.

**1. Native form for tools, shell form for `PATH`.** `npath` (→ `C:/x/y`, via
`cygpath -m`) for anything reaching cmake, cl, ninja or a generated
`CMakeUserPresets.json`; `upath` (→ `/c/x/y`) for anything appended to bash's
`$PATH`, because `$PATH` is colon-separated and a native `C:` reads as a
separator.

**2. Convert the roots, not the call sites.** The engine runs `TESTBED`,
`FOREST`, `SRC_ROOT`, `REPOS` and `CCACHE_DIR` through `npath` once, at the top.
Every `build_dir`, `install_dir` and `-D<pkg>_DIR=` is derived from those by
string concatenation, so one conversion covers hundreds of arguments. MSYS2's
bash accepts `C:/...` for its own `test`/`cd`/`mkdir`, so the converted roots
keep working for the shell too.

**3. Never assume `/c/`.** Git for Windows installs vary: some mount drives at
`/c`, others (no `/etc/fstab`) at `/cygdrive/c`. A hardcoded `/c/Program Files`
silently resolves *under the Git install root* and finds nothing — which is
exactly how a Visual Studio that was installed all along gets reported as
missing. Always `cygpath`.

### `CONDA_PREFIX` is backslashed

pixi exports `CONDA_PREFIX=C:\repo\...\.pixi\envs\default`. Presets interpolate
`$env{CONDA_PREFIX}/include`, and projects write such values *verbatim* into
generated CMake — ITK emits
`set(ITK_FFTW_INCLUDE_PATH "C:\repo\...")` into `ITKConfig.cmake`, where `\r`
and `\i` are invalid escapes and **every** downstream `find_package(ITK)` dies
with `Invalid character escape`. The engine therefore normalizes `CONDA_PREFIX`
and `PIXI_PROJECT_ROOT` to forward slashes at startup, which fixes every preset,
toolchain-file and SuperBuild-EP consumer of them at once.

## MAX_PATH

`BUILD_FOREST_ROOT` defaults to **`C:/S`** on Windows (`config.json.in`), so a
forest is `C:\S-itk-main` rather than
`C:\repo\itk_forest_build_testbed\build_forest-itk-main`. That buys ~40
characters before Slicer's own nesting
(`Slicer-build/ITK-build/Modules/...`) begins. `LongPathsEnabled=1` helps, but
several bundled third-party tools never opt in via their manifest, so the short
root is the real mitigation.

## Python

Conda **win-64 environments ship `python.exe` with no `python3.exe`**, and a
bare Windows host may offer only the `py` launcher. Nothing may call `python3`
unconditionally: shell code uses `$FOREST_PYTHON`/`$FOREST_PYTHON_PRE` from
`platform.sh`, and pixi tasks use `python`.

## Encoding

`bin/config.py` writes `manifest.toml`, `config.sh` and the generated presets
with an **explicit `encoding="utf-8"`**. Without it Python uses the locale
encoding (cp1252) on Windows, and the kit's em-dashes then make every
`manifest.toml` unreadable by `tomllib`, which reads strict UTF-8.

## Line endings

`.gitattributes` pins the repo to `eol=lf`. A CRLF committed from a Windows
clone breaks the other two platforms immediately: `#!/usr/bin/env bash\r` fails
with `bad interpreter: ...^M`, and a shell `case` arm gains an invisible `\r`
that never matches. If an existing clone already has CRLF in its working tree
(`git ls-files --eol` shows `w/crlf` against `i/lf`), normalize with:

```bash
git add --renormalize .     # review, then commit
```

## What is not available on Windows

- **`gengetopt`** has no conda-forge win-64 build, so RTK's *applications*
  cannot generate their `*_ggo.{h,c}`. Scoped to `[target.unix.dependencies]`;
  nothing on the ITK or Slicer path needs it.
- **`bin/run-fft-bench.sh`** still resolves `python3` directly and expects a
  macOS Python framework layout; set `BENCH_PY` to use it.

## Related

- [config.md](config.md) — `config.sh` keys and per-platform overrides
- [slicer-itk-policy.md](slicer-itk-policy.md) — which ITK Slicer vendors (**read before debugging any Slicer error**)
- [slicer-macos.md](slicer-macos.md) — the macOS equivalent of this page
