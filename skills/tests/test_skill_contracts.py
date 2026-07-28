"""Every skill in this tree must satisfy the v2 contract.

This tree went un-validated for months: `agent-skills doctor` defaults to its
own repo, nobody pointed `--repo-root` here, and 17 skills were failing while
still deploying — the testbed symlinks skills directly, bypassing the installer
that would have refused them. This test is the gate that keeps that from
recurring.

A skill added without v2 frontmatter fails here, not silently at load time.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _doctor() -> dict:
    # The gh-comment-cache suite puts a vendored `agent_skills` subset on
    # PYTHONPATH; it would shadow the CLI's own package and break the import.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        ["agent-skills", "doctor", "--repo-root", str(REPO_ROOT), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if not result.stdout.strip():
        pytest.fail(f"doctor produced no output (rc={result.returncode}): {result.stderr[:400]}")
    return json.loads(result.stdout)


pytestmark = pytest.mark.skipif(
    shutil.which("agent-skills") is None,
    reason="agent-skills CLI not on PATH (it ships from the agent-skills repo)",
)


def test_every_skill_passes_the_v2_contract() -> None:
    report = _doctor()
    failed = [f for f in report["findings"] if f["outcome"] != "pass"]
    assert not failed, "skills failing the v2 contract:\n" + "\n".join(
        f"  {f['name']}: {'; '.join(str(i) for i in f['issues'])}" for f in failed
    )


def test_doctor_actually_scanned_the_tree() -> None:
    """Guard the gate itself: a doctor that finds nothing would pass vacuously."""
    report = _doctor()
    on_disk = len([p for p in (REPO_ROOT / "skills").glob("*/SKILL.md")])
    assert report["total"] == on_disk, (
        f"doctor scanned {report['total']} skills but {on_disk} SKILL.md exist on disk"
    )
    assert on_disk > 40, f"only {on_disk} skills found — is REPO_ROOT wrong?"
