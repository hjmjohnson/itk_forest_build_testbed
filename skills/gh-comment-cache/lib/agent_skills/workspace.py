"""Workspace fingerprinting and identity (§7, Phase 1 skeleton).

A workspace is a directory tree that a skill operates over. We need a stable
identifier so that cache files for the same workspace end up in the same bucket
regardless of which relative path the user invoked the skill from. The
fingerprint is:

    sha256(normalized_root + "\\0" + (upstream_url || origin_url || ""))

truncated to the first 12 hex characters. Adding the upstream/origin URL
disambiguates two local clones of the same repo living at different paths.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """Identity of a workspace — the thing a cache key is built on."""

    normalized_root: Path
    upstream_url: str | None
    origin_url: str | None
    is_git: bool

    @property
    def fingerprint(self) -> str:
        """Return the 12-hex-char stable identifier for this workspace."""
        url = self.upstream_url or self.origin_url or ""
        payload = f"{self.normalized_root}\0{url}".encode()
        return hashlib.sha256(payload).hexdigest()[:12]


def _git_config_url(repo: Path, remote: str) -> str | None:
    """Return the remote URL for `remote`, or None if the remote is missing."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "config", "--get", f"remote.{remote}.url"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def _git_toplevel(start: Path) -> Path | None:
    """Return the git worktree root containing `start`, or None."""
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    top = result.stdout.strip()
    return Path(top) if top else None


def identify(start: Path | str) -> Workspace:
    """Compute the Workspace that `start` belongs to.

    If `start` is inside a git worktree, the normalized root is the worktree
    toplevel and the upstream/origin URLs come from git config. Otherwise the
    normalized root is `start` itself (resolved) and no URLs are recorded.
    """
    start_path = Path(start).resolve()
    top = _git_toplevel(start_path)
    if top is not None:
        return Workspace(
            normalized_root=top.resolve(),
            upstream_url=_git_config_url(top, "upstream"),
            origin_url=_git_config_url(top, "origin"),
            is_git=True,
        )
    return Workspace(
        normalized_root=start_path,
        upstream_url=None,
        origin_url=None,
        is_git=False,
    )
