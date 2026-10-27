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


def test_clean_ctest_records_empty_failed_list(tmp_path, fake_kit):
    ctest = (fake_kit.parent / "ctest" / "Testing" / "Temporary")
    script = fake_kit / "bin" / "run-matrix.sh"
    script.write_text(script.read_text().replace("printf", "rm -f \"{}\"/LastTestsFailed.log #".format(ctest)))
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
