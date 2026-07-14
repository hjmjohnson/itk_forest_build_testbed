import asyncio, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from forest_tui.plan import Step
from forest_tui import runner

def _run(coro):
    return asyncio.run(coro)

def test_parse_ctest_token():
    assert runner.parse_ctest_token("blah\nT:150/150\n") == ("PASS", "T:150/150")
    assert runner.parse_ctest_token("T:142/150") == ("FAIL", "T:142/150")
    assert runner.parse_ctest_token("T:skip:no-harness") == ("SKIP", "T:skip:no-harness")
    assert runner.parse_ctest_token("T:timeout") == ("FAIL", "T:timeout")
    assert runner.parse_ctest_token("T:0/0:no-tests") == ("PASS", "T:0/0:no-tests")
    assert runner.parse_ctest_token("garbage") == ("FAIL", "T:unknown")

def test_run_step_streams_and_logs():
    with tempfile.TemporaryDirectory() as tmp:
        forest = Path(tmp); (forest / "logs").mkdir()
        step = Step("echo hello", ["bash", "-c", "echo hello; echo two"], {}, "checkout")
        lines = []
        res = _run(runner.run_step(step, Path.cwd(), forest, lines.append))
        assert res.status == "PASS"
        assert "hello" in lines[0]
        assert "hello" in res.log.read_text()

def test_run_step_build_fail_by_artifact_despite_exit_zero():
    with tempfile.TemporaryDirectory() as tmp:
        forest = Path(tmp); (forest / "logs").mkdir()
        step = Step("build ITK", ["bash", "-c", "echo 'x.cxx:1: error: nope'; exit 0"],
                    {}, "build", target="ITK")
        res = _run(runner.run_step(step, Path.cwd(), forest, lambda s: None))
        assert res.status == "FAIL"
        assert "error: nope" in res.detail

def test_run_step_nonbuild_fails_by_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        forest = Path(tmp); (forest / "logs").mkdir()
        step = Step("repoint-itk bad", ["bash", "-c", "exit 3"], {}, "repoint")
        res = _run(runner.run_step(step, Path.cwd(), forest, lambda s: None))
        assert res.status == "FAIL"

def test_run_step_survives_very_long_line():
    with tempfile.TemporaryDirectory() as tmp:
        forest = Path(tmp); (forest / "logs").mkdir()
        step = Step("long line", ["bash", "-c", "printf 'a%.0s' {1..100000}; echo; echo done"],
                    {}, "checkout")
        res = _run(runner.run_step(step, Path.cwd(), forest, lambda s: None))
        assert res.status == "PASS"

def test_run_step_cancellation_terminates_process_group():
    async def go():
        with tempfile.TemporaryDirectory() as tmp:
            forest = Path(tmp); (forest / "logs").mkdir()
            step = Step("long sleep", ["bash", "-c", "sleep 12345.6"], {}, "checkout")
            task = asyncio.ensure_future(runner.run_step(step, Path.cwd(), forest, lambda s: None))
            await asyncio.sleep(0.3)
            task.cancel()
            try:
                await task
                raised = False
            except asyncio.CancelledError:
                raised = True
            assert raised
    _run(go())
    time.sleep(0.5)
    found = subprocess.run(["pgrep", "-f", "sleep 12345.6"], stdout=subprocess.DEVNULL)
    assert found.returncode != 0

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
