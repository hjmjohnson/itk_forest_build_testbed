import json
import shlex
import subprocess
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


class NinjaNotFoundError(RuntimeError):
    pass


def _entries(graph: Path) -> list[dict]:
    return json.loads((graph / "compile_commands.json").read_text())


def _entry_file(e: dict) -> Path:
    p = Path(e["file"])
    return (p if p.is_absolute() else Path(e["directory"]) / p).resolve()


def _key(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(resolved)


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
    try:
        return subprocess.run(
            ["ninja", "-C", str(graph), "-t", "deps"],
            check=True, capture_output=True, text=True,
        ).stdout
    except FileNotFoundError as exc:
        raise NinjaNotFoundError("ninja is not on PATH") from exc


def _build_deps(graph: Path, repo_root: Path) -> dict[str, list[str]]:
    tu_of = {}
    for e in _entries(graph):
        if "output" in e:
            obj = Path(e["output"])
            obj = obj if obj.is_absolute() else Path(e["directory"]) / obj
            tu_of[obj.resolve()] = _key(_entry_file(e), repo_root)
    deps: dict[str, list[str]] = {}
    for obj, headers in parse_ninja_deps(run_ninja_deps(graph)).items():
        tu = tu_of.get((graph / obj).resolve())
        if tu is None:
            continue
        for h in headers:
            tus = deps.setdefault(_key(graph / h, repo_root), [])
            if tu not in tus:
                tus.append(tu)
    return deps


def _load_deps(graph: Path, repo_root: Path) -> dict[str, list[str]]:
    cache = graph / DEPS_CACHE
    ninja = graph / "build.ninja"
    if cache.exists() and (
        not ninja.exists() or cache.stat().st_mtime >= ninja.stat().st_mtime
    ):
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            pass
    deps = _build_deps(graph, repo_root)
    tmp = cache.with_name(cache.name + ".tmp")
    tmp.write_text(json.dumps(deps, indent=1) + "\n")
    tmp.replace(cache)
    return deps


def including_tus(
    header: Path, graph: Path, repo_root: Path, cap: int = 8
) -> list[Path]:
    deps = _load_deps(graph, repo_root)
    key = _key(header, repo_root) if header.is_absolute() else str(header)
    tus = sorted(Path(t) for t in deps.get(key, []))
    inside = [t for t in tus if not t.is_absolute()]
    outside = [t for t in tus if t.is_absolute()]
    seen: set[str] = set()
    first, rest = [], []
    for t in inside:
        (rest if t.parts[0] in seen else first).append(t)
        seen.add(t.parts[0])
    return (first + rest + outside)[:cap]


def command_for(tu: Path, graph: Path, repo_root: Path) -> list[str]:
    want = (tu if tu.is_absolute() else repo_root / tu).resolve()
    for e in _entries(graph):
        if _entry_file(e) == want:
            return e["arguments"] if "arguments" in e else shlex.split(e["command"])
    raise KeyError(str(tu))
