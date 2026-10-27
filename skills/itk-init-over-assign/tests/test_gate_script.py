import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "itk-compile-gate.sh"


def sh(*args, cwd=None):
    return subprocess.run(
        ["/bin/bash", "-c", 'set -u; exec /bin/bash "$0" "$@"', str(SCRIPT), *map(str, args)],
        capture_output=True, text=True, cwd=cwd,
    )


def test_all_dead_headers_report_and_exit_nonzero(fake_graph, repo_root):
    (repo_root / ".git").mkdir(parents=True)
    r = sh(fake_graph, repo_root / "Dead" / "other.h")
    assert r.returncode != 0
    assert "unbound" not in r.stderr
    assert "FAIL" in r.stdout and "no-including-tu" in r.stdout


def test_changed_with_no_cxx_changes_exits_zero(fake_graph, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    r = sh(fake_graph, "--changed", repo)
    assert r.returncode == 0
    assert "no changed C++ TUs vs HEAD" in r.stdout
    assert "unbound" not in r.stderr


def test_compile_failure_prints_fail_line_and_exits_nonzero(fake_graph, repo_root):
    (repo_root / ".git").mkdir(parents=True)
    r = sh(fake_graph, repo_root / "IO" / "tu0.cxx")
    assert r.returncode == 1
    assert r.stdout.startswith("FAIL ") or "\nFAIL " in r.stdout
