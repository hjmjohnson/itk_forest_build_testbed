import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


def test_valid_keys_pass():
    vers = {"scenarios": {"itk-main": {"elastix": {}}, "svdc": {"x": {}}},
            "subbuild": {"ANTs": {"skip_suffix": "itk-release-5.4"}}}
    assert config.validate_suffix_keys(vers) == []


def test_malformed_itk_scenario_key_is_error():
    vers = {"scenarios": {"itk-": {"elastix": {}}}}
    errs = config.validate_suffix_keys(vers)
    assert len(errs) == 1, errs
    assert "itk-" in errs[0]


def test_itk_key_with_invalid_slug_is_error():
    vers = {"scenarios": {"itk-bad..slug": {"elastix": {}}}}
    errs = config.validate_suffix_keys(vers)
    assert len(errs) == 1, errs


def test_malformed_skip_suffix_is_error():
    vers = {"subbuild": {"ANTs": {"skip_suffix": "itk-"}}}
    errs = config.validate_suffix_keys(vers)
    assert len(errs) == 1, errs


def test_freeform_keys_are_not_validated():
    vers = {"scenarios": {"svdc": {}, "base": {}, "linpackref": {}},
            "subbuild": {"ANTs": {"skip_suffix": "svdc"}}}
    assert config.validate_suffix_keys(vers) == []


def test_unmatched_scenario_warns_but_is_not_an_error():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        vers = {"scenarios": {"itk-main": {"elastix": {}}}}
        assert config.validate_suffix_keys(vers) == []          # not an error
        w = config.warn_unmatched_scenarios(vers, d)            # but warns
        assert len(w) == 1 and "itk-main" in w[0], w
        os.makedirs(os.path.join(d, "build_forest-itk-main"))
        assert config.warn_unmatched_scenarios(vers, d) == []   # silent once present
    finally:
        shutil.rmtree(d)


def test_live_versions_toml_is_valid():
    # The real file must be migrated (itkv6_main -> itk-main, itkv5 ->
    # itk-release-5.4) and must validate.
    vers = config.load_versions()
    assert config.validate_suffix_keys(vers) == []
    assert "itkv6_main" not in vers.get("scenarios", {}), \
        "scenarios.itkv6_main not migrated to itk-main"
    assert vers["subbuild"]["ANTs"]["skip_suffix"] == "itk-release-5.4", \
        vers["subbuild"]["ANTs"]["skip_suffix"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
