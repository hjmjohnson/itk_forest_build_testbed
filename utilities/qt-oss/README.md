# Open-source Qt 6 for MSVC on Windows

`C:\Qt` is the **only** place the kit looks for the Slicer-supported Qt
(`config.json.in`, `QT6_DIR` → `C:/Qt/<ver>/msvc2022_64`). What matters is that
what lives there is the **open-source** build.

## Do not use the Qt online installer

The installer **hides the open-source option entirely once your Qt Account holds
any evaluation entitlement**. It then routes you into the commercial flow: no
open-source license page, no plain MSVC kit selection, and what lands in `C:\Qt`
is a time-limited trial that stops being licensed on a date you did not choose.
The entitlement is attached to the *account*, not the installation, so no amount
of clicking will turn a trial into the open-source build.

Diagnose an existing tree:

```bash
qt=$(cygpath -u 'C:/Qt')          # never hardcode /c — see docs/windows.md
grep -E "License schema|License expiry" "$qt/InstallationLog.txt" | sort -u
ls "$qt"/*/msvc*/bin/licheck.exe 2>/dev/null   # present => commercial build
```

`License schema [Supported Evaluation]` with an expiry date means it is a trial.
An open-source tree has no `InstallationLog.txt`, no `MaintenanceTool.exe` and
no `licheck.exe`.

## Install with aqtinstall

`aqtinstall` downloads the same official open-source archives from
`download.qt.io` — no Qt Account, no `licheck`, no expiry.

**Install it from git master, not PyPI.** Qt reorganized the download repository
at 6.11.0, splitting the per-version folder into one folder per architecture:

    .../desktop/qt6_6100/qt6_6100/Updates.xml             # <= 6.10
    .../desktop/qt6_6112/qt6_6112_msvc2022_64/Updates.xml # >= 6.11

aqtinstall handles this as of [PR #1000][pr1000] (merged 2026-03-24, closing
[issue #959][i959]), but the newest *release* — v3.3.0, 2025-06-02 — predates
that merge by nine months. PyPI's aqtinstall therefore fails every 6.11.x call
with `Failed to download checksum for the file 'Updates.xml'` (see the still-open
[issue #1007][i1007]). Master is correct; switch back to PyPI once a release
after v3.3.0 exists.

```bash
py -3 -m venv /c/tmp/aqtvenv
/c/tmp/aqtvenv/Scripts/python.exe -m pip install \
  "git+https://github.com/miurahr/aqtinstall.git@master"
/c/tmp/aqtvenv/Scripts/python.exe -m aqt \
  install-qt windows desktop 6.11.2 win64_msvc2022_64 \
  -m qt5compat qtmultimedia qtpositioning qtshadertools qtscxml \
     qtwebchannel qtwebengine qtwebsockets qtimageformats \
  --outputdir 'C:/Qt'
```

Result: `C:/Qt/6.11.2/msvc2022_64`, which `pixi run config` resolves into
`QT6_DIR`.

[pr1000]: https://github.com/miurahr/aqtinstall/pull/1000
[i959]: https://github.com/miurahr/aqtinstall/issues/959
[i1007]: https://github.com/miurahr/aqtinstall/issues/1007

## The module set

Those `-m` modules are exactly what `Slicer/CMakeLists.txt` builds into
`Slicer_REQUIRED_QT_MODULES` for a Qt6 Windows build with multimedia, WebEngine,
the extension manager, i18n and testing enabled:

| aqt module | supplies |
|---|---|
| *(base)* | Core Gui Widgets Network OpenGL OpenGLWidgets PrintSupport UiTools Xml Svg Sql Qml Quick QuickWidgets LinguistTools Test GuiPrivate |
| `qt5compat` | Core5Compat |
| `qtmultimedia` | Multimedia MultimediaWidgets |
| `qtscxml` | StateMachine |
| `qtwebengine` | WebEngineCore WebEngineWidgets |
| `qtwebchannel` | WebChannel |
| `qtpositioning` | Positioning (WebEngine dependency) |
| `qtshadertools` | ShaderTools (Quick dependency) |
| `qtwebsockets`, `qtimageformats` | WebEngine dev tools, packaging image plugins |

`GuiPrivate` is required because Slicer's `qSlicerApplication::setHasBorderInFullScreen`
reaches into `QWindowsWindow` on Windows for Qt >= 6.9. Note that `qtwebengine`
lives in a separate `extensions/` repository on `download.qt.io`, not alongside
the other addons — aqt handles that transparently for Qt >= 6.8.

## Verify by artifact

```bash
. bin/platform.sh && msvc_activate
cmake -S <probe> -B <build> -G Ninja -DQt6_DIR=C:/Qt/6.11.2/msvc2022_64/lib/cmake/Qt6
cmake --build <build>
```

A `find_package(Qt6 REQUIRED COMPONENTS ...)` over the full Slicer list must
configure *and* link a trivial `QApplication` executable. Configuring alone is
not proof, and neither is aqt's exit code.
