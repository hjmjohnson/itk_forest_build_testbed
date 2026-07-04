import os, sys, tempfile, io, contextlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

def _forest(tmp, name, sha, cfg):
    d = os.path.join(tmp, name); os.makedirs(d)
    config._emit_manifest(d, {"ITK": {"sha": sha, "kind": "consumer"}}, {"ITK": cfg})
    return d

def test_compare_reports_sha_and_config_deltas():
    with tempfile.TemporaryDirectory() as tmp:
        a = _forest(tmp, "A", "aaaaaaaaaaaa", {"preset": "itk-forest-itk-v5", "ITK_USE_FFTWD": "ON"})
        b = _forest(tmp, "B", "bbbbbbbbbbbb", {"preset": "itk-forest-itk-v6", "ITK_USE_FFTWD": "OFF"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert config.cmd_compare(a, b) == 0
        out = buf.getvalue()
        assert "ITK" in out and "aaaaaaaaaaaa" in out          # sha delta
        assert "ITK_USE_FFTWD" in out and "ON" in out and "OFF" in out  # config delta

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
