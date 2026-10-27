import subprocess
from pathlib import Path

_TRACKED: dict[Path, set[Path] | None] = {}


def tracked_files(repo: Path) -> set[Path] | None:
    """Resolved paths git tracks under repo, cached per repo; None outside a git checkout."""
    root = repo.resolve()
    if root not in _TRACKED:
        done = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                              capture_output=True, text=True, check=False)
        _TRACKED[root] = (
            {(root / f).resolve() for f in done.stdout.split("\0") if f}
            if done.returncode == 0 else None
        )
    return _TRACKED[root]


def is_tracked(path: Path, repo: Path) -> bool:
    tracked = tracked_files(repo)
    return tracked is None or path.resolve() in tracked
