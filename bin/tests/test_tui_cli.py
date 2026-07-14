import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _cli(args):
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "bin")}
    return subprocess.run([sys.executable, "-m", "forest_tui"] + args,
                          capture_output=True, text=True, cwd=ROOT, env=env)

def test_dry_run_emits_plan_script():
    r = _cli(["--dry-run", "--forest", "prX", "--ref", "pr/1234",
              "--projects", "elastix", "--ctest", "elastix"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert out.startswith("#!/usr/bin/env bash")
    assert "Forest: build_forest-prX | ITK: pr/1234" in out
    assert "build ITK" in out or "setup-itk-downstream-testbed.sh build ITK" in out
    assert "--run-ctest elastix" in out

def test_dry_run_prereq_closure_applied():
    r = _cli(["--dry-run", "--forest", "", "--projects", "BRAINSTools"])
    assert r.returncode == 0, r.stderr
    body = r.stdout
    assert body.index("build ITK") < body.index("build ANTs") < body.index("build BRAINSTools")

def test_dry_run_full_matrix():
    r = _cli(["--dry-run", "--forest", "", "--full-matrix"])
    assert r.returncode == 0, r.stderr
    assert "run-matrix.sh" in r.stdout

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
