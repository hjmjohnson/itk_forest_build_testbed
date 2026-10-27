import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ioa.compile_commands import command_for, including_tus

HEADER_SUFFIXES = {".h", ".hxx", ".hpp", ".hh"}
CAP = 8
_DROP_WITH_ARG = {"-o", "-MF", "-MT", "-MQ"}
_DROP = {"-c", "-MD", "-MMD", "-M", "-MM"}
_COMMON = [
    "-fsyntax-only", "-Wunused-but-set-variable", "-Werror=unused-but-set-variable",
    "-Wunused-variable", "-Werror=unused-variable",
]


@dataclass
class GateResult:
    ok: bool
    failed: dict[Path, str] = field(default_factory=dict)


def warning_flags(argv: list[str]) -> list[str]:
    if "clang" in " ".join(argv):
        return _COMMON + ["-Wunused-local-typedef", "-Werror=unused-local-typedef"]
    return _COMMON + ["-Wunused-local-typedefs", "-Werror=unused-local-typedefs"]


def strip_output_flags(argv: list[str]) -> list[str]:
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
        elif a in _DROP_WITH_ARG:
            skip = True
        elif a not in _DROP:
            out.append(a)
    return out


def is_header(path: Path) -> bool:
    return path.suffix in HEADER_SUFFIXES


def expand(
    files: list[Path], graph: Path, repo_root: Path
) -> tuple[list[Path], list[Path]]:
    tus: list[Path] = []
    dead: list[Path] = []
    for f in files:
        if not is_header(f):
            found = [f]
        else:
            found = including_tus(f, graph, repo_root, cap=CAP)
            if not found:
                dead.append(f)
        tus.extend(t for t in found if t not in tus)
    return tus, dead


def _compile(tu: Path, graph: Path, repo_root: Path) -> str | None:
    base = command_for(tu, graph, repo_root)
    argv = strip_output_flags(base)
    argv = argv + warning_flags(base)
    env = {**os.environ, "CCACHE_DISABLE": "1"}
    p = subprocess.run(argv, cwd=graph, env=env, capture_output=True, text=True)
    if p.returncode == 0:
        return None
    lines = [
        ln for ln in (p.stdout + p.stderr).splitlines()
        if "error" in ln.lower() or "warning" in ln.lower()
    ]
    return "\n".join(lines[:8]) or f"exit {p.returncode}"


def run(graph: Path, files: list[Path], repo_root: Path) -> GateResult:
    tus, dead = expand(files, graph, repo_root)
    failed = {h: "no-including-tu" for h in dead}
    for tu in tus:
        try:
            msg = _compile(tu, graph, repo_root)
        except KeyError:
            msg = "no-compile-command"
        if msg is not None:
            failed[tu] = msg
    return GateResult(ok=not failed, failed=failed)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ioa.gate")
    ap.add_argument("--expand", action="store_true", required=True)
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args(argv)
    tus, dead = expand(a.files, a.graph, a.repo_root)
    for tu in tus:
        print(tu)
    for h in dead:
        print(f"no-including-tu\t{h}", file=sys.stderr)
    return 3 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
