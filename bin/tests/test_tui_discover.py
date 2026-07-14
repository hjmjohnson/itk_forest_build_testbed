import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from forest_tui import discover

ROOT = Path(__file__).resolve().parents[2]

def _mk_forest(root: Path, name: str) -> Path:
    f = root / name
    itk = f / "ITK"
    itk.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "itk-downstream"], cwd=itk, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "x"], cwd=itk, check=True)
    return f

def test_list_forests_finds_and_describes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _mk_forest(root, "build_forest")
        f2 = _mk_forest(root, "build_forest-pr42")
        (f2 / "ITK" / "build" / "lib").mkdir(parents=True)
        (f2 / "ITK" / "build" / "lib" / "libITKCommon-6.0.a").touch()
        (f2 / "logs").mkdir()
        (f2 / "logs" / "matrix-ITK-pr42.log").touch()
        forests = discover.list_forests(root)
        by_suffix = {f.suffix: f for f in forests}
        assert set(by_suffix) == {"", "pr42"}
        assert by_suffix[""].itk_branch == "itk-downstream"
        assert len(by_suffix[""].itk_sha) >= 7
        assert by_suffix[""].itk_artifact is False
        assert by_suffix["pr42"].itk_artifact is True
        assert by_suffix["pr42"].last_matrix_log is not None

def test_list_forests_skips_forest_without_itk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "build_forest-empty").mkdir()
        forests = discover.list_forests(root)
        assert [f.suffix for f in forests] == ["empty"]
        assert forests[0].itk_sha == ""

def test_list_targets_and_deferred_against_real_matrix():
    targets = discover.list_targets(ROOT)
    assert targets[0] == "ITK" and "elastix" in targets
    deferred = dict(discover.list_deferred(ROOT))
    assert "Ultrasound" in deferred

def test_error_grep():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "x.log"
        log.write_text("ok line\nfoo.cxx:3: error: boom\nCMake Error at y\nnoise\n")
        assert discover.error_grep(log) == ["foo.cxx:3: error: boom", "CMake Error at y"]

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
