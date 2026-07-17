import io, os, sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


def _run(monkeypatched_vers, suffix, pkg="Slicer", key="ITK_GIT_TAG"):
    """Call cmd_subbuild_get against an in-memory versions dict.
    Returns (exit_or_None, stdout). SystemExit -> code captured."""
    orig = config.load_versions
    config.load_versions = lambda: monkeypatched_vers
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = config.cmd_subbuild_get(suffix, pkg, key)
        return rc, buf.getvalue().strip()
    except SystemExit as e:
        return e.code, buf.getvalue().strip()
    finally:
        config.load_versions = orig


def test_per_forest_variant_wins():
    vers = {
        "scenarios": {"itk-main": {"Slicer": {"ITK_GIT_TAG": "slicer-v6-main"}}},
        "subbuild": {"Slicer": {"ITK_GIT_REPOSITORY": "https://x"}},
    }
    rc, out = _run(vers, "itk-main")
    assert rc == 0, rc
    assert out == "slicer-v6-main", out


def test_dotted_suffix_resolves_when_quoted():
    # "itk-release-5.4" must be one key, not nested by the dot in 5.4.
    vers = {"scenarios": {"itk-release-5.4": {"Slicer": {"ITK_GIT_TAG": "slicer-v5.4.6-x"}}}}
    rc, out = _run(vers, "itk-release-5.4")
    assert rc == 0 and out == "slicer-v5.4.6-x", (rc, out)


def test_undeclared_forest_fails_loudly():
    # No per-forest variant AND no global default -> must exit non-zero.
    vers = {"scenarios": {}, "subbuild": {"Slicer": {"ITK_GIT_REPOSITORY": "https://x"}}}
    rc, out = _run(vers, "itk-pr9999")
    assert rc not in (0, None), f"expected non-zero exit, got {rc}"
    assert "itk-pr9999" in str(rc) or "itk-pr9999" in out or "no [scenarios" in str(rc)


def test_empty_suffix_bare_forest_fails():
    # Bare build_forest (suffix "") has no variant -> fail, never silent.
    vers = {"scenarios": {}, "subbuild": {"Slicer": {}}}
    rc, _ = _run(vers, "")
    assert rc not in (0, None), f"expected non-zero exit for bare forest, got {rc}"


def test_real_versions_toml_declares_both_forests():
    # Guard the actual repo config: both live forests must resolve.
    vers = config.load_versions()
    for suffix, want in (("itk-release-5.4", "5.4"), ("itk-main", "6.0")):
        got, out = _run(vers, suffix)
        assert got == 0, f"{suffix} did not resolve: {out}"
        assert out.startswith("slicer-v"), out
        assert want in out, f"{suffix} -> {out}, expected version {want}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
