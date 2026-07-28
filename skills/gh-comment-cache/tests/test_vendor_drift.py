"""The vendored agent_skills modules must not drift from their canonical source.

The testbed is a relocatable kit, so these modules are vendored rather than
imported. That makes the agent-skills copy authoritative and this one a
generated artifact — a silent divergence here is what let gh_cache.py rot for
months before its broken migrations path was noticed.
"""

from __future__ import annotations

import os
import pathlib

import pytest

VENDORED = ("cache.py", "workspace.py")

LIB = pathlib.Path(__file__).resolve().parents[1] / "lib" / "agent_skills"
CANONICAL = pathlib.Path(
    os.environ.get("AGENT_SKILLS_REPO", pathlib.Path.home() / "src" / "agent-skills")
) / "lib" / "agent_skills"


@pytest.mark.skipif(
    not CANONICAL.is_dir(),
    reason="no agent-skills checkout to compare against (set AGENT_SKILLS_REPO)",
)
@pytest.mark.parametrize("name", VENDORED)
def test_vendored_module_matches_canonical(name: str) -> None:
    vendored = (LIB / name).read_text()
    canonical = (CANONICAL / name).read_text()
    assert vendored == canonical, (
        f"{name} has drifted from {CANONICAL / name}.\n"
        f"Re-sync with: bash {LIB.parent / 'vendor-sync.sh'}"
    )


def test_gh_cache_is_deliberately_not_vendored_verbatim() -> None:
    """gh_cache.py carries a required divergence; guard the reason, not the text."""
    migration_dir = LIB.parent.parent / "migrations"
    assert migration_dir.is_dir(), "the skill must own its migrations/ directory"
    assert (migration_dir / "001_init.sql").is_file()
    assert "gh_cache.py" not in VENDORED
