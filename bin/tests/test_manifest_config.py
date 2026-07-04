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

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
