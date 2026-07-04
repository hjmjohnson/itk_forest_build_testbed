import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

FX = os.path.join(os.path.dirname(__file__), "fixtures", "presets")

def test_base_only():
    assert config.resolve_preset("base", FX) == {"CMAKE_BUILD_TYPE": "Release", "A": "1"}

def test_child_overrides_parent():
    r = config.resolve_preset("thing", FX)
    assert r == {"CMAKE_BUILD_TYPE": "Release", "A": "2", "B": "on"}

def test_two_hop_inherit():
    r = config.resolve_preset("thing-max", FX)
    assert r == {"CMAKE_BUILD_TYPE": "Release", "A": "2", "B": "on", "C": "yes"}

def test_multi_parent_earlier_wins():
    r = config.resolve_preset("multi", FX)
    assert r["X"] == "first"    # p1 (earlier) wins over p2
    assert r["Y"] == "y2"       # from p2
    assert r["Z"] == "z"        # own

def test_missing_raises():
    try:
        config.resolve_preset("nope", FX); assert False, "expected KeyError"
    except KeyError:
        pass

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
