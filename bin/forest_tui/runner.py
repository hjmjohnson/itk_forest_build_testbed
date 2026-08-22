from __future__ import annotations

import asyncio
import os
import re
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .discover import check_artifact, error_grep
from .plan import Step

TOKEN_RE = re.compile(r"T:(\S+)")


@dataclass
class StepResult:
    status: str
    detail: str
    log: Path


def parse_ctest_token(text: str) -> tuple[str, str]:
    m = None
    for m in TOKEN_RE.finditer(text):
        pass
    if not m:
        return ("FAIL", "T:unknown")
    token = "T:" + m.group(1)
    body = m.group(1)
    if body.startswith("skip"):
        return ("SKIP", token)
    if body in ("timeout", "unknown"):
        return ("FAIL", token)
    nums = re.match(r"(\d+)/(\d+)", body)
    if nums:
        return ("PASS" if nums.group(1) == nums.group(2) else "FAIL", token)
    return ("FAIL", token)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


# Spawn a step in its own process group/job so cancelling kills the whole build
# tree (bash -> cmake -> ninja -> cl/gcc), not just the shell we launched.
# POSIX does that with start_new_session; Windows has no sessions, so it uses
# CREATE_NEW_PROCESS_GROUP and kills the tree by PID with taskkill /T.
if os.name == "nt":
    import subprocess

    _SPAWN_KWARGS = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}

    def terminate(proc: asyncio.subprocess.Process) -> None:
        # proc.terminate() would end only the top process, orphaning the
        # compilers underneath it; taskkill /T walks the child tree.
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except OSError:
            try:
                proc.terminate()
            except (ProcessLookupError, PermissionError):
                pass
else:
    _SPAWN_KWARGS = {"start_new_session": True}

    def terminate(proc: asyncio.subprocess.Process) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


async def run_step(step: Step, root: Path, forest: Path,
                   on_line: Callable[[str], None]) -> StepResult:
    logdir = forest / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"tui-{_slug(step.name)}.log"
    env = {**os.environ}
    env.pop("FOREST", None)
    env.update(step.env)
    proc = await asyncio.create_subprocess_exec(
        *step.argv, cwd=root, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        limit=2**20, **_SPAWN_KWARGS)
    tail: list[str] = []
    try:
        with log.open("w", errors="replace") as fh:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").rstrip("\n")
                fh.write(line + "\n")
                fh.flush()
                tail.append(line)
                on_line(line)
        rc = await proc.wait()
    finally:
        if proc.returncode is None:
            terminate(proc)
            await proc.wait()
    if step.kind == "build":
        if check_artifact(root, forest, step.target):
            return StepResult("PASS", "", log)
        return StepResult("FAIL", "; ".join(error_grep(log)), log)
    if step.kind == "ctest":
        status, token = parse_ctest_token("\n".join(tail[-20:]))
        return StepResult(status, token, log)
    return StepResult("PASS" if rc == 0 else "FAIL", f"exit {rc}" if rc else "", log)
