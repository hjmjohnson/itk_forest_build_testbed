import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from forest_tui.plan import (CtestOpts, Selections, build_steps, emit_plan_script,
                             forest_dir, prereq_closure)

ORDER = ["ITK", "elastix", "SimpleITK", "ANTs", "BRAINSTools",
         "OpenIGTLink", "Slicer", "SlicerExtensions", "OpenIGTLinkIO"]

def test_forest_dir():
    assert forest_dir(Path("/r"), "") == Path("/r/build_forest")
    assert forest_dir(Path("/r"), "pr6487") == Path("/r/build_forest-pr6487")

def test_prereq_closure_pulls_chain_in_order():
    assert prereq_closure(["BRAINSTools"], ORDER) == ["ITK", "ANTs", "BRAINSTools"]
    assert prereq_closure(["OpenIGTLinkIO"], ORDER) == ["ITK", "OpenIGTLink", "Slicer", "OpenIGTLinkIO"]
    assert prereq_closure(["elastix"], ORDER) == ["ITK", "elastix"]

def test_build_steps_repoint_and_builds_and_ctest():
    sel = Selections(forest_suffix="pr9999", create_forest=False, itk_ref="pr/9999",
                     full_matrix=False, projects=["ITK", "elastix"],
                     ctest={"elastix": CtestOpts(True, "elx", 100, 900)})
    steps = build_steps(sel)
    kinds = [s.kind for s in steps]
    assert kinds == ["repoint", "build", "build", "ctest"]
    assert steps[0].env["ITK_REF"] == "pr/9999"
    assert all(s.env.get("FOREST_REFERENCE_SUFFIX") == "pr9999" for s in steps)
    ct = steps[-1]
    assert ct.argv[-2:] == ["--run-ctest", "elastix"]
    assert ct.env["CTEST_INCLUDE"] == "elx"
    assert ct.env["CTEST_TIMEOUT"] == "100"
    assert ct.env["CTEST_TARGET_TIMEOUT"] == "900"

def test_build_steps_new_forest_starts_with_checkout():
    sel = Selections("fresh", True, "upstream/main", False, ["ITK"], {})
    assert [s.kind for s in build_steps(sel)] == ["checkout", "repoint", "build"]

def test_build_steps_full_matrix_supersedes_projects():
    sel = Selections("", False, "", True, ["ITK", "elastix"], {})
    steps = build_steps(sel)
    assert [s.kind for s in steps] == ["matrix"]
    assert "FOREST_REFERENCE_SUFFIX" not in steps[0].env

def test_emit_plan_script_is_runnable_shell():
    sel = Selections("pr9999", False, "pr/9999", False, ["ITK"], {})
    txt = emit_plan_script(sel, build_steps(sel))
    assert txt.startswith("#!/usr/bin/env bash")
    assert "Forest: build_forest-pr9999 | ITK: pr/9999" in txt
    assert "FOREST_REFERENCE_SUFFIX=pr9999 ITK_REF=pr/9999 bash bin/setup-itk-downstream-testbed.sh repoint-itk" in txt

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
