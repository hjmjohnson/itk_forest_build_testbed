import os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATRIX = os.path.join(ROOT, "bin", "run-matrix.sh")

def _run(args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(["bash", MATRIX] + args, capture_output=True, text=True, env=e)

def test_list_targets_dependency_order():
    r = _run(["--list-targets"])
    assert r.returncode == 0
    targets = r.stdout.split()
    assert targets[0] == "ITK"
    assert "elastix" in targets and "Slicer" in targets
    assert targets.index("ANTs") < targets.index("BRAINSTools")
    assert targets.index("Slicer") < targets.index("SlicerExtensions")

def test_list_deferred_has_reasons():
    r = _run(["--list-deferred"])
    assert r.returncode == 0
    rows = [l.split("\t") for l in r.stdout.strip().splitlines()]
    names = [row[0] for row in rows]
    assert "Ultrasound" in names and "LesionSizingToolkit" in names
    assert all(len(row) == 2 and row[1] for row in rows)

def test_check_artifact_fails_on_empty_forest():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(["--check-artifact", "ITK"], env={"FOREST": tmp})
        assert r.returncode != 0

def test_ctest_dir_empty_on_empty_forest():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(["--ctest-dir", "elastix"], env={"FOREST": tmp})
        assert r.returncode == 0
        assert r.stdout.strip() == ""

def test_run_ctest_no_harness_token():
    with tempfile.TemporaryDirectory() as tmp:
        r = _run(["--run-ctest", "elastix"], env={"FOREST": tmp})
        assert r.returncode == 0
        assert r.stdout.strip().endswith("T:skip:no-harness")

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
