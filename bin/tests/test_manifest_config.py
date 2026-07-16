import os, sys, tempfile, tomllib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

def test_config_record_written_and_preserved():
    with tempfile.TemporaryDirectory() as forest:
        config._write_config_record(forest, "ANTs", "itk-forest-ants-max-modules",
                                    {"USE_VTK": "ON", "ITK_DIR": "/x"})
        path = os.path.join(forest, "manifest.toml")
        data = tomllib.load(open(path, "rb"))
        assert data["config"]["ANTs"]["preset"] == "itk-forest-ants-max-modules"
        assert data["config"]["ANTs"]["USE_VTK"] == "ON"
        # a second consumer must not clobber the first
        config._write_config_record(forest, "BRAINSTools", "itk-forest-brainstools",
                                    {"USE_VTK": "OFF"})
        data = tomllib.load(open(path, "rb"))
        assert set(data["config"]) == {"ANTs", "BRAINSTools"}

def test_emit_and_parse_forest_section():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        comps = {"ITK": {"url": "u", "ref": "origin/release-5.4",
                         "slug": "release-5.4", "branch": "b",
                         "sha": "c8721a5c93", "kind": "consumer"}}
        meta = {"name": "build_forest-itk-release-5.4",
                "itk_version": "5.4.6"}
        config._emit_manifest(d, comps, {}, meta)
        c, cfg, fm = config._parse_manifest(os.path.join(d, "manifest.toml"))
        assert c["ITK"]["ref"] == "origin/release-5.4", c["ITK"]
        assert c["ITK"]["slug"] == "release-5.4", c["ITK"]
        assert fm["name"] == "build_forest-itk-release-5.4", fm
        assert fm["itk_version"] == "5.4.6", fm
    finally:
        shutil.rmtree(d)


def test_parse_manifest_returns_three_values():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        config._emit_manifest(d, {}, {}, None)
        r = config._parse_manifest(os.path.join(d, "manifest.toml"))
        assert len(r) == 3, f"expected (components, config, forest_meta), got {len(r)}"
    finally:
        shutil.rmtree(d)


def test_parse_missing_manifest_returns_three_empties():
    r = config._parse_manifest("/nonexistent/manifest.toml")
    assert r == ({}, {}, {}), r


def test_itk_version_parsed():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "CMakeLists.txt"), "w") as f:
            f.write('set(ITK_VERSION_MAJOR "5")\n'
                    'set(ITK_VERSION_MINOR "4")\n'
                    'set(ITK_VERSION_PATCH "6")\n')
        assert config._itk_version(d) == "5.4.6"
    finally:
        shutil.rmtree(d)


def test_itk_version_unparseable_returns_none():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "CMakeLists.txt"), "w") as f:
            f.write("project(NotITK)\n")
        assert config._itk_version(d) is None
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
