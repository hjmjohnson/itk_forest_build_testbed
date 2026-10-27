"""clang-query plumbing shared by the init-over-assign stages: run matcher scripts over
the translation units of a compile_commands.json graph and parse `set output dump`
bindings into source locations, names, and types."""

import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ioa.tidy import database_spellings, in_scope, tool

BINDING = re.compile(r'^Binding for "([^"]+)":$')
HEAD = re.compile(r"^(\w+) 0x[0-9a-f]+ <(.*?)>(?= )(.*)$")
FULL_LOC = re.compile(r"^(?P<file>/[^<>]*?|[A-Za-z]:[\\/][^<>]*?):(?P<line>\d+):(?P<col>\d+)")
NAMED = re.compile(
    r"^\s*(?:col:\d+|line:\d+:\d+|\S+:\d+:\d+)\s+(?:(?:used|referenced|implicit|invalid|constexpr)\s+)*"
    r"(?P<name>[A-Za-z_]\w*)\s+'(?P<type>[^']*)'(?::'(?P<canon>[^']*)')?"
)


@dataclass(frozen=True)
class Node:
    """One bound AST node: its kind and begin location, plus name and types for named decls."""

    kind: str
    file: Path
    line: int
    col: int
    name: str = ""
    type: str = ""
    canonical: str = ""


@dataclass(frozen=True)
class Match:
    tu: Path
    binding: str
    node: Node


def parse_dump(text: str, tu: Path) -> list[Match]:
    """Matches from clang-query `set output dump` text; macro-expanded nodes are dropped."""
    out: list[Match] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        b = BINDING.match(line)
        if not b or i + 1 >= len(lines):
            continue
        head = HEAD.match(lines[i + 1])
        if not head or "Spelling=" in head[2] or "<scratch space>" in head[2]:
            continue
        loc = FULL_LOC.match(head[2])
        if not loc:
            continue
        named = NAMED.match(head[3])
        out.append(Match(tu, b[1], Node(
            head[1], Path(loc["file"]), int(loc["line"]), int(loc["col"]),
            named["name"] if named else "", named["type"] if named else "",
            (named["canon"] or named["type"]) if named else "",
        )))
    return out


def tus_in(graph: Path, root: Path) -> list[str]:
    """In-scope translation units, spelled as the compile database spells them."""
    return sorted(s for real, s in database_spellings(graph).items() if in_scope(real, root))


def run_query(graph: Path, scripts: list[Path], tus: list[str] | None = None,
              root: Path | None = None) -> tuple[list[Match], list[str]]:
    """Matches of the concatenated scripts over tus (default: every in-scope TU under root),
    and the TUs clang-query could not parse."""
    if tus is None:
        if root is None:
            raise ValueError("run_query needs tus or root")
        tus = tus_in(graph, root)
    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "query.cq"
        script.write_text("\n".join(p.read_text() for p in scripts))
        binary = tool("clang-query")

        def one(tu: str) -> tuple[str, subprocess.CompletedProcess]:
            return tu, subprocess.run(
                [binary, "-p", str(graph), "-f", str(script), "--extra-arg=-w", tu],
                capture_output=True, text=True, errors="surrogateescape",
            )

        with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
            results = list(pool.map(one, tus))
    matches: list[Match] = []
    dropped: list[str] = []
    for tu, res in results:
        if re.search(r"^\d+:\d+: ", res.stdout + res.stderr, re.M):
            raise RuntimeError(f"clang-query rejected the matcher script:\n{(res.stdout + res.stderr)[-2000:]}")
        if res.returncode != 0 or re.search(r": (?:fatal )?error: ", res.stderr):
            dropped.append(tu)
            continue
        matches += parse_dump(res.stdout, Path(tu))
    return matches, dropped
