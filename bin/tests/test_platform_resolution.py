"""Tri-platform resolution: Windows gets MSVC, macOS/Linux are left untouched.

The kit builds natively on macOS, Linux and Windows from one set of presets and
one config template. The risk that buys is silent drift on the two platforms a
Windows developer cannot run, so the properties asserted here are mostly
*negative*: that adding Windows changed nothing for anybody else.

config.host_os() reads FOREST_OS, so every platform's resolution is drivable
from any host and these run identically on all three.
"""
import os, sys, json, glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

PRESETS = config.PRESETS_DIR


def _as(os_name, fn, *a, **kw):
    """Run fn with host_os() forced to os_name."""
    prev = os.environ.get("FOREST_OS")
    os.environ["FOREST_OS"] = os_name
    try:
        return fn(*a, **kw)
    finally:
        if prev is None:
            os.environ.pop("FOREST_OS", None)
        else:
            os.environ["FOREST_OS"] = prev


# --- preset overlay --------------------------------------------------------

def test_unix_base_is_unchanged_by_the_windows_overlay():
    """The GNU/Clang base must be exactly what it was before *.windows.json
    existed: same compilers, same -ffile-prefix-map, same rpath, and none of
    the MSVC keys leaking across."""
    for os_name in ("linux", "macos"):
        base = _as(os_name, config.resolve_preset, "itk-forest-base", PRESETS)
        assert base["CMAKE_C_COMPILER"] == "$env{CC}"
        assert base["CMAKE_CXX_COMPILER"] == "$env{CXX}"
        assert base["CMAKE_C_FLAGS_INIT"] == "-ffile-prefix-map=${sourceDir}=."
        assert base["CMAKE_BUILD_RPATH"] == "$env{CONDA_PREFIX}/lib"
        assert base["CMAKE_IGNORE_PREFIX_PATH"] == "/opt/homebrew"
        assert "CMAKE_MSVC_DEBUG_INFORMATION_FORMAT" not in base
        assert "CMAKE_POLICY_DEFAULT_CMP0141" not in base


def test_windows_base_is_msvc_and_drops_the_gnu_only_flags():
    base = _as("windows", config.resolve_preset, "itk-forest-base", PRESETS)
    assert base["CMAKE_C_COMPILER"] == "cl"
    assert base["CMAKE_CXX_COMPILER"] == "cl"
    # cl.exe rejects -ffile-prefix-map; rpath and the Homebrew tree are
    # meaningless on Windows.
    assert "CMAKE_C_FLAGS_INIT" not in base
    assert "CMAKE_CXX_FLAGS_INIT" not in base
    assert "CMAKE_BUILD_RPATH" not in base
    assert "CMAKE_IGNORE_PREFIX_PATH" not in base


def test_windows_keeps_ccache_viable():
    """/Zi writes debug info to a shared .pdb that ccache cannot cache, so
    without Embedded (=/Z7) every Windows compile would miss and the testbed's
    whole premise would collapse there."""
    base = _as("windows", config.resolve_preset, "itk-forest-base", PRESETS)
    assert base["CMAKE_MSVC_DEBUG_INFORMATION_FORMAT"] == "Embedded"
    assert base["CMAKE_POLICY_DEFAULT_CMP0141"] == "NEW"   # or it is ignored
    assert base["CMAKE_C_COMPILER_LAUNCHER"] == "ccache"
    assert base["CMAKE_CXX_COMPILER_LAUNCHER"] == "ccache"


def test_downstream_presets_inherit_the_platform_base_without_being_edited():
    """The overlay redefines itk-forest-base by NAME, so every preset that
    inherits it follows automatically. If this breaks, each consumer preset
    would need a Windows twin."""
    for name in ("itk-forest-slicer", "itk-forest-itk-v6"):
        win = _as("windows", config.resolve_preset, name, PRESETS)
        nix = _as("linux", config.resolve_preset, name, PRESETS)
        assert win["CMAKE_CXX_COMPILER"] == "cl"
        assert nix["CMAKE_CXX_COMPILER"] == "$env{CXX}"
        # the preset's own (platform-independent) settings survive either way
        own = set(nix) - set(win) | {"CMAKE_CXX_COMPILER"}
        assert own, f"{name} contributed no settings of its own"


def test_platform_overlays_never_load_on_a_foreign_host():
    """A *.windows.json file must be invisible to macOS/Linux, and the plain
    files must load everywhere."""
    overlays = glob.glob(os.path.join(PRESETS, "*.windows.json"))
    assert overlays, "expected at least one Windows preset overlay"
    for os_name in ("linux", "macos"):
        idx = _as(os_name, config._load_all_presets, PRESETS)
        for path in overlays:
            with open(path, encoding="utf-8") as f:
                for p in json.load(f).get("configurePresets", []):
                    # present only if a plain file also defines that name
                    if p["name"] in idx:
                        assert idx[p["name"]] != p, \
                            f"{os_name} loaded the Windows definition of {p['name']}"


# --- config.json.in per-platform overrides ---------------------------------

def test_forest_root_is_short_and_absolute_on_windows_only():
    tmpl = dict(config.load_template())
    win, ok = _as("windows", config.resolve, "BUILD_FOREST_ROOT", tmpl["BUILD_FOREST_ROOT"])
    assert ok and win == "C:/S", win        # MAX_PATH headroom for Slicer
    for os_name in ("linux", "macos"):
        val, ok = _as(os_name, config.resolve, "BUILD_FOREST_ROOT", tmpl["BUILD_FOREST_ROOT"])
        assert ok and val == "build_forest", (os_name, val)


def test_override_block_replaces_the_competing_strategy():
    spec = {"value": "unix-default", "windows": {"candidates": ["/nonexistent/*"]}}
    # windows picks candidates, and must not keep the inherited "value" where it
    # would win ahead of them
    merged = _as("windows", config._for_host, spec)
    assert "value" not in merged and "candidates" in merged
    # unix is untouched
    assert _as("linux", config._for_host, spec) == spec


def test_no_override_block_leaves_the_spec_identical():
    spec = {"value": "x", "required": False}
    for os_name in ("linux", "macos", "windows"):
        assert _as(os_name, config._for_host, spec) == spec


# --- path normalization ----------------------------------------------------

def test_npath_is_identity_off_windows():
    """A backslash is a legal filename character on Unix; rewriting it there
    would corrupt real paths."""
    for os_name in ("linux", "macos"):
        for p in ("/a//b", "/tmp/x", r"/weird\name"):
            assert _as(os_name, config._npath, p) == p


def test_npath_forward_slashes_and_collapses_on_windows():
    n = lambda p: _as("windows", config._npath, p)
    assert n(r"C:\a\b") == "C:/a/b"
    assert n("H://src") == "H:/src"          # $HOME on a drive root + "/src"
    assert n("//server/share//x") == "//server/share/x"   # UNC prefix preserved
