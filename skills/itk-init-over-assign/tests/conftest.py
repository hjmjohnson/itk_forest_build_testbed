import json
from pathlib import Path

import pytest


@pytest.fixture
def repo_root(tmp_path) -> Path:
    return tmp_path / "src"


@pytest.fixture
def fake_graph(tmp_path, repo_root) -> Path:
    graph = tmp_path / "build" / "Proj-build"
    graph.mkdir(parents=True)
    src = repo_root
    tus = [f"{d}/tu{i}.cxx" for d in ("Common", "IO", "Filtering") for i in range(7)]
    tus = tus[:20]
    entries = [
        {
            "directory": str(graph),
            "command": f"c++ -I{src}/Common -c {src}/{tu} -o {tu}.o",
            "file": str(src / tu),
            "output": f"{tu}.o",
        }
        for tu in tus
    ]
    gen = str((graph / "moc_gen.cxx").resolve())
    entries.append(
        {
            "directory": str(graph),
            "command": f"c++ -c {gen} -o moc_gen.cxx.o",
            "file": gen,
            "output": "moc_gen.cxx.o",
        }
    )
    (graph / "compile_commands.json").write_text(json.dumps(entries))
    deps = {"Common/foo.h": tus + [gen], "Common/one.h": [tus[0]], "Dead/other.h": []}
    (graph / ".ioa-deps.json").write_text(json.dumps(deps))
    return graph
