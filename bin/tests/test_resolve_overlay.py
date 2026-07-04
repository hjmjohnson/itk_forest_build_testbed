import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

def test_overlay_is_flat_and_self_contained():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "ANTs"); os.makedirs(src)
        forest = d
        rc = config.cmd_resolve_overlay(
            "itk-forest-ants", src, os.path.join(src, "build"),
            forest, "ANTs", ["ITK_DIR=/x/ITK/build"])
        assert rc == 0
        doc = json.load(open(os.path.join(src, "CMakeUserPresets.json")))
        assert "include" not in doc
        p = doc["configurePresets"][0]
        assert p["name"] == "forest-ANTs-local"
        assert p["binaryDir"] == os.path.join(src, "build")
        cv = p["cacheVariables"]
        assert cv["ANTS_SUPERBUILD"] == "OFF"          # from fragment
        assert cv["ITK_DIR"] == "/x/ITK/build"          # injected kv wins
        assert cv["CMAKE_BUILD_TYPE"] == "Release"      # from base
        assert p["generator"] == "Ninja"                     # carried from 00-base
        assert p["environment"]["CCACHE_BASEDIR"] == "${sourceDir}"
        assert "installDir" in p

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
