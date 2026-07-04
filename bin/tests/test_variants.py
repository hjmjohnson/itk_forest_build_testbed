import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

P = config.PRESETS_DIR

def test_ants_max_modules():
    r = config.resolve_preset("itk-forest-ants-max-modules", P)
    assert r["ANTS_SUPERBUILD"] == "OFF"   # inherited
    assert r["USE_VTK"] == "ON"            # variant override
    assert r["BUILD_ALL_ANTS_APPS"] == "ON"

def test_itk_v6_vtkglue():
    r = config.resolve_preset("itk-forest-itk-v6-vtkglue", P)
    assert r["Module_ITKVtkGlue"] == "ON"
    assert r["BUILD_TESTING"] == "OFF"
    assert r["ITK_USE_FFTWD"] == "OFF"     # inherited v6 policy

def test_brainstools_variants():
    m = config.resolve_preset("itk-forest-brainstools-max-modules", P)
    assert m["USE_VTK"] == "ON" and m["USE_DWIConvert"] == "ON"

def test_itk_v5_dcmtk():
    r = config.resolve_preset("itk-forest-itk-v5-dcmtk", P)
    assert r["Module_ITKDCMTK"] == "ON" and r["Module_ITKIODCMTK"] == "ON"

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
