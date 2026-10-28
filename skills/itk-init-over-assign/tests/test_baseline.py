import json
import os
import stat

import pytest

from ioa import baseline
from ioa.preflight import Coordinates


@pytest.fixture
def fake_kit(tmp_path):
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    ctest = tmp_path / "ctest"
    (ctest / "Testing" / "Temporary").mkdir(parents=True)
    script = kit / "bin" / "run-matrix.sh"
    script.write_text(
        f"""#!/usr/bin/env bash
case "$1" in
  --ctest-dir) echo "{ctest}" ;;
  --run-ctest)
    echo x >> "{kit}/calls"
    echo "T:1/3"
    printf '3:zeta\\n1:alpha\\n' > "{ctest}/Testing/Temporary/LastTestsFailed.log" ;;
esac
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return kit


def coords(tmp_path):
    return Coordinates("BRAINSTools", "abc123", "build_forest-x", tmp_path, "6.0.0")


def test_baseline_runs_once_per_sha(tmp_path, fake_kit):
    first = baseline.ensure(coords(tmp_path), fake_kit)
    second = baseline.ensure(coords(tmp_path), fake_kit)
    assert first == second
    assert (fake_kit / "calls").read_text().count("x") == 1
    data = json.loads(first.read_text())
    assert data["failed"] == ["alpha", "zeta"]
    assert data["repo"] == "BRAINSTools" and data["sha"] == "abc123"
    assert first.name == "BRAINSTools-abc123.json"


def swap_run(kit, body):
    script = kit / "bin" / "run-matrix.sh"
    text = script.read_text()
    head = text.split("  --run-ctest)")[0]
    script.write_text(head + "  --run-ctest)\n" + body + "\n ;;\nesac\n")


@pytest.mark.parametrize("token", ["T:skip:no-harness", "T:timeout", "T:0/0:no-tests", "T:unknown"])
def test_run_that_did_not_execute_is_an_error_and_records_nothing(tmp_path, fake_kit, token):
    swap_run(fake_kit, f'echo "{token}"')
    with pytest.raises(RuntimeError, match=token):
        baseline.ensure(coords(tmp_path), fake_kit)
    assert not (fake_kit / ".devlocal").exists()


def test_stale_failure_log_is_cleared_before_the_run(tmp_path, fake_kit):
    ctest = fake_kit.parent / "ctest" / "Testing" / "Temporary"
    (ctest / "LastTestsFailed.log").write_text("9:stale\n")
    swap_run(fake_kit, 'echo "T:5/5"')
    path = baseline.ensure(coords(tmp_path), fake_kit)
    assert json.loads(path.read_text())["failed"] == []


def test_reported_failures_without_a_log_is_an_error(tmp_path, fake_kit):
    swap_run(fake_kit, 'echo "T:2/5"')
    with pytest.raises(RuntimeError, match="T:2/5"):
        baseline.ensure(coords(tmp_path), fake_kit)


def test_clean_ctest_records_empty_failed_list(tmp_path, fake_kit):
    swap_run(fake_kit, 'echo "T:5/5"')
    path = baseline.ensure(coords(tmp_path), fake_kit)
    assert json.loads(path.read_text())["failed"] == []


def write(tmp_path, name, failed):
    p = tmp_path / name
    p.write_text(json.dumps({"failed": sorted(failed)}))
    return p


def test_new_failures_excludes_baseline_failures(tmp_path):
    b = write(tmp_path, "b.json", {"x"})
    a = write(tmp_path, "a.json", {"x", "y"})
    assert baseline.new_failures(b, a) == ["y"]


def test_standalone_env_drops_the_pixi_toolchain(monkeypatch, tmp_path):
    prefix = tmp_path / "pixi" / "envs" / "default"
    stripped = {
        "CC": f"{prefix}/bin/clang", "CXX": f"{prefix}/bin/clang++", "LD": "ld", "AR": "ar",
        "RANLIB": "ranlib", "CFLAGS": "-O2", "CXXFLAGS": "-O2", "CPPFLAGS": f"-I{prefix}/include",
        "LDFLAGS": f"-L{prefix}/lib", "LIBRARY_PATH": f"{prefix}/lib", "CPATH": f"{prefix}/include",
        "CMAKE_PREFIX_PATH": str(prefix), "CONDA_BUILD_SYSROOT": "/sdk", "CONDA_DEFAULT_ENV": "default",
        "CONDA_SHLVL": "1", "PIXI_PROJECT_ROOT": "/kit", "PIXI_ENVIRONMENT_NAME": "default",
        "SDKROOT": f"{prefix}/sdk",
    }
    for k, v in stripped.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CONDA_PREFIX", str(prefix))
    monkeypatch.setenv("HOME", "/home/me")
    monkeypatch.setenv("PATH", os.pathsep.join([f"{prefix}/bin", f"{prefix}/sbin", "/usr/bin", "/bin"]))
    env = baseline.forest_env(None)
    assert not set(stripped) & set(env)
    assert env["CONDA_PREFIX"] == str(prefix) and env["HOME"] == "/home/me"
    assert env["PATH"] == os.pathsep.join(["/usr/bin", "/bin"])
    forest = baseline.forest_env("itk-main")
    assert forest["CC"] == stripped["CC"] and forest["PATH"].startswith(f"{prefix}/bin")


def test_host_sdkroot_is_kept(monkeypatch, tmp_path):
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / "conda"))
    monkeypatch.setenv("SDKROOT", "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk")
    assert baseline.forest_env(None)["SDKROOT"].startswith("/Library/")
