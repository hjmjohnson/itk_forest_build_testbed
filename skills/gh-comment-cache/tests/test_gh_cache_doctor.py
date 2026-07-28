"""Verify gh-comment-cache passes agent-skills doctor."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_NAME = "gh-comment-cache"


@pytest.mark.skipif(
    shutil.which("agent-skills") is None,
    reason="agent-skills CLI not on PATH (it ships from the agent-skills repo)",
)
def test_doctor_passes_for_gh_comment_cache() -> None:
    # The suite puts this skill's vendored `agent_skills` subset on PYTHONPATH;
    # it would shadow the CLI's own package and break the import.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        ["agent-skills", "doctor", "--repo-root", str(REPO_ROOT), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    report = json.loads(result.stdout)
    findings = {entry["name"]: entry for entry in report["findings"]}

    assert SKILL_NAME in findings, f"{SKILL_NAME} not found in doctor report"
    entry = findings[SKILL_NAME]
    assert entry["outcome"] == "pass", f"{SKILL_NAME} failed validation: {entry['issues']}"
