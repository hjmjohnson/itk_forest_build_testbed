import json
import shlex
import subprocess
from os.path import commonpath
from pathlib import Path

DEPS_CACHE = ".ioa-deps.json"


def find_graph(repo_build: Path, repo_name: str) -> Path:
    found = [
        p.parent
        for depth in ("*", "*/*")
        for p in sorted(repo_build.glob(f"{depth}/compile_commands.json"))
    ]
    if not found:
        raise FileNotFoundError(f"no compile_commands.json under {repo_build}")
    named = [g for g in found if g.name.startswith(repo_name)]
    return named[0] if named else min(found, key=lambda g: len(g.parts))


def _entries(graph: Path) -> list[dict]:
    return json.loads((graph / "compile_commands.json").read_text())


def _entry_file(e: dict) -> Path:
    p = Path(e["file"])
    return p if p.is_absolute() else Path(e["directory"]) / p


def _source_root(entries: list[dict]) -> Path:
    files = [str(_entry_file(e).parent) for e in entries]
    return Path(commonpath(files)) if files else Path("/")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def parse_ninja_deps(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur: list[str] | None = None
    for line in text.splitlines():
        if line.startswith((" ", "\t")):
            if cur is not None and line.strip():
                cur.append(line.strip())
        elif ": #deps" in line:
            cur = out.setdefault(line.split(": #deps", 1)[0], [])
        else:
            cur = None
    return out


def run_ninja_deps(graph: Path) -> str:
    return subprocess.run(
        ["ninja", "-C", str(graph), "-t", "deps"],
        check=True, capture_output=True, text=True,
    ).stdout


def _build_deps(graph: Path) -> dict[str, list[str]]:
    entries = _entries(graph)
    root = _source_root(entries)
    tu_of = {}
    for e in entries:
        if "output" in e:
            obj = Path(e["output"])
            obj = obj if obj.is_absolute() else Path(e["directory"]) / obj
            tu_of[obj.resolve()] = _rel(_entry_file(e), root)
    deps: dict[str, list[str]] = {}
    for obj, headers in parse_ninja_deps(run_ninja_deps(graph)).items():
        tu = tu_of.get((graph / obj).resolve())
        if tu is None:
            continue
        for h in headers:
            key = _rel((graph / h).resolve(), root)
            if tu not in deps.setdefault(key, []):
                deps[key].append(tu)
    return deps


def _load_deps(graph: Path) -> dict[str, list[str]]:
    cache = graph / DEPS_CACHE
    ninja = graph / "build.ninja"
    fresh = cache.exists() and (
        not ninja.exists() or cache.stat().st_mtime >= ninja.stat().st_mtime
    )
    if fresh:
        return json.loads(cache.read_text())
    deps = _build_deps(graph)
    cache.write_text(json.dumps(deps, indent=1) + "\n")
    return deps


def including_tus(header: Path, graph: Path, cap: int = 8) -> list[Path]:
    deps = _load_deps(graph)
    key = str(header)
    if header.is_absolute():
        key = _rel(header, _source_root(_entries(graph)))
    tus = sorted(Path(t) for t in deps.get(key, []))
    seen: set[str] = set()
    first, rest = [], []
    for t in tus:
        top = t.parts[0]
        (rest if top in seen else first).append(t)
        seen.add(top)
    return (first + rest)[:cap]


def command_for(tu: Path, graph: Path) -> list[str]:
    entries = _entries(graph)
    root = _source_root(entries)
    for e in entries:
        f = _entry_file(e)
        if f == tu or _rel(f, root) == str(tu):
            return e["arguments"] if "arguments" in e else shlex.split(e["command"])
    raise KeyError(str(tu))
