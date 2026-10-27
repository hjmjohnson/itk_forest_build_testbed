import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
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
    passed: list[Path] = field(default_factory=list)


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
        elif a in _DROP:
            continue
        elif a.startswith("-o") or a.startswith(("-MF", "-MT", "-MQ")):
            continue
        else:
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
    try:
        p = subprocess.run(argv, cwd=graph, env=env, capture_output=True, text=True)
    except OSError as exc:
        return f"cannot run {argv[0]}: {exc}"
    if p.returncode == 0:
        return None
    lines = [
        ln for ln in (p.stdout + p.stderr).splitlines()
        if "error" in ln.lower() or "warning" in ln.lower()
    ]
    return "\n".join(lines[:8]) or f"exit {p.returncode}"


def workers() -> int:
    return max(2, (os.cpu_count() or 2) // 2)


def _check(tu: Path, graph: Path, repo_root: Path) -> str | None:
    try:
        return _compile(tu, graph, repo_root)
    except KeyError:
        return "no-compile-command"


def run(graph: Path, files: list[Path], repo_root: Path) -> GateResult:
    tus, dead = expand(files, graph, repo_root)
    failed = {h: "no-including-tu" for h in dead}
    passed: list[Path] = []
    with ThreadPoolExecutor(max_workers=workers()) as pool:
        results = list(pool.map(lambda tu: _check(tu, graph, repo_root), tus))
    for tu, msg in zip(tus, results):
        if msg is None:
            passed.append(tu)
        else:
            failed[tu] = msg
    return GateResult(ok=not failed, failed=failed, passed=passed)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ioa.gate")
    ap.add_argument("--expand", action="store_true")
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args(argv)
    if not a.expand:
        r = run(a.graph, a.files, a.repo_root)
        for tu in r.passed:
            print(f"PASS {tu}")
        for f, msg in r.failed.items():
            print(f"FAIL {f}: {msg.splitlines()[0]}")
        return 0 if r.ok else 1
    tus, dead = expand(a.files, a.graph, a.repo_root)
    for tu in tus:
        print(tu)
    for h in dead:
        print(f"no-including-tu\t{h}", file=sys.stderr)
    return 3 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
