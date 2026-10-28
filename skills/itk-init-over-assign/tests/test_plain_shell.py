import os
import stat
import subprocess
from pathlib import Path

import pytest

from ioa import tidy

RUN_PY = Path(__file__).resolve().parents[1] / "run.py"
BREW_PYTHON = Path("/opt/homebrew/bin/python3")


def _tools(d: Path, names=tidy.CLANG_TOOLS) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text("#!/bin/sh\n")
        (d / n).chmod((d / n).stat().st_mode | stat.S_IXUSR)
    return d


@pytest.fixture
def isolated(monkeypatch):
    tidy._CHOSEN.clear()
    monkeypatch.setattr(tidy, "WELL_KNOWN", ())
    monkeypatch.setattr(tidy, "_versioned", lambda pattern: [])
    for var in ("IOA_LLVM_BIN", "LLVM_BIN", "CONDA_PREFIX"):
        monkeypatch.setenv(var, "")
        monkeypatch.delenv(var)
    yield
    tidy._CHOSEN.clear()


def test_all_clang_tools_come_from_the_first_complete_directory(tmp_path, monkeypatch, isolated):
    partial = _tools(tmp_path / "partial", ("clang-tidy", "clang-format", "run-clang-tidy"))
    full = _tools(tmp_path / "full")
    conda = _tools(tmp_path / "conda" / "bin")
    monkeypatch.setenv("PATH", os.pathsep.join([str(partial), str(full)]))
    monkeypatch.setenv("CONDA_PREFIX", str(conda.parent))
    assert {Path(tidy.tool(t)).parent for t in tidy.CLANG_TOOLS} == {full}


def test_conda_is_the_last_resort(tmp_path, monkeypatch, isolated):
    partial = _tools(tmp_path / "partial", ("clang-tidy",))
    conda = _tools(tmp_path / "conda" / "bin")
    monkeypatch.setenv("PATH", str(partial))
    monkeypatch.setenv("CONDA_PREFIX", str(conda.parent))
    assert tidy.llvm_bin() == conda


def test_explicit_directory_wins_and_must_be_complete(tmp_path, monkeypatch, isolated):
    full = _tools(tmp_path / "full")
    chosen = _tools(tmp_path / "chosen")
    monkeypatch.setenv("PATH", str(full))
    monkeypatch.setenv("LLVM_BIN", str(chosen))
    assert tidy.llvm_bin() == chosen
    monkeypatch.setenv("IOA_LLVM_BIN", str(_tools(tmp_path / "bad", ("clang-tidy",))))
    with pytest.raises(SystemExit, match="clang-query"):
        tidy.llvm_bin()


def test_llvm_bin_option_exports_the_directory(tmp_path, monkeypatch, isolated):
    import argparse

    ap = argparse.ArgumentParser()
    tidy.add_llvm_bin_option(ap)
    tidy.use_llvm_bin(ap.parse_args(["--llvm-bin", str(_tools(tmp_path / "x"))]))
    assert os.environ["IOA_LLVM_BIN"] == str((tmp_path / "x").resolve())
    assert tidy.llvm_bin() == (tmp_path / "x").resolve()


@pytest.mark.skipif(not BREW_PYTHON.exists(), reason="no /opt/homebrew/bin/python3")
def test_run_py_reaches_preflight_from_a_plain_shell_without_pixi(tmp_path):
    env = {"HOME": os.environ["HOME"], "PATH": "/opt/homebrew/bin:/usr/bin:/bin"}
    helped = subprocess.run([str(BREW_PYTHON), str(RUN_PY), "--help"], env=env,
                            capture_output=True, text=True, timeout=120)
    assert helped.returncode == 0 and "--llvm-bin" in helped.stdout
    repo, build = tmp_path / "repo", tmp_path / "build"
    repo.mkdir()
    build.mkdir()
    done = subprocess.run([str(BREW_PYTHON), str(RUN_PY), "--repo", str(repo), "--build", str(build),
                           "--dry-run"], env=env, capture_output=True, text=True, timeout=120)
    out = done.stdout + done.stderr
    assert done.returncode == 2 and "refused (not-a-repo)" in out, out
    assert "pixi" not in out and "not found" not in out


def test_stages_inherit_the_masters_llvm_directory(tmp_path, monkeypatch, isolated):
    from ioa import pipeline

    full = _tools(tmp_path / "full")
    monkeypatch.setenv("PATH", str(full))
    seen = []
    monkeypatch.setattr(pipeline.subprocess, "run",
                        lambda argv, **kw: seen.append(kw["env"]) or subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(pipeline.stages, "snapshot", lambda repo: "t")
    stage = pipeline.Stage("x", ["true"], None)
    pipeline.run_stage("x", stage, tmp_path, tmp_path, tmp_path / "run")
    assert seen and seen[0]["IOA_LLVM_BIN"] == str(full)
