"""clang-tidy plumbing shared by the init-over-assign stages: run a check over a
compile_commands.json graph, read its exported fixes, and apply byte-exact edits."""

import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ioa.repo import is_tracked

EXCLUDED = ("ThirdParty", "build", "Utilities")
KV = re.compile(r"^( *)(- )?(\w+):\s*(.*)$")


CLANG_TOOLS = ("clang-tidy", "run-clang-tidy", "clang-format", "clang-query", "clang-apply-replacements")
WELL_KNOWN = (Path("/opt/homebrew/opt/llvm/bin"), Path("/usr/local/opt/llvm/bin"))
_CHOSEN: dict[tuple, Path] = {}


def _complete(d: Path) -> bool:
    return all((d / t).is_file() and os.access(d / t, os.X_OK) for t in CLANG_TOOLS)


def _versioned(pattern: str) -> list[Path]:
    found = Path("/usr/lib").glob(pattern)
    return sorted(found, key=lambda d: int(re.sub(r"\D", "", d.parent.name) or 0), reverse=True)


def llvm_bin() -> Path:
    """The one directory every clang tool comes from.

    Order: IOA_LLVM_BIN (set by --llvm-bin), LLVM_BIN, PATH, the Homebrew prefixes,
    /usr/lib/llvm-*/bin (highest version first), then $CONDA_PREFIX/bin.
    """
    env = os.environ
    key = tuple(env.get(k, "") for k in ("IOA_LLVM_BIN", "LLVM_BIN", "PATH", "CONDA_PREFIX"))
    if key in _CHOSEN:
        return _CHOSEN[key]
    explicit = env.get("IOA_LLVM_BIN") or env.get("LLVM_BIN")
    if explicit:
        d = Path(explicit)
        missing = [t for t in CLANG_TOOLS if not (d / t).is_file()]
        if missing:
            raise SystemExit(f"ioa: {', '.join(missing)} not found in {d} (from --llvm-bin, "
                             "IOA_LLVM_BIN, or LLVM_BIN)")
        _CHOSEN[key] = d
        return d
    dirs = [Path(x) for x in env.get("PATH", "").split(os.pathsep) if x]
    dirs += [*WELL_KNOWN, *_versioned("llvm-*/bin")]
    if env.get("CONDA_PREFIX"):
        dirs.append(Path(env["CONDA_PREFIX"]) / "bin")
    for d in dirs:
        if _complete(d):
            _CHOSEN[key] = d
            return d
    raise SystemExit(f"ioa: no directory holds all of {', '.join(CLANG_TOOLS)}; "
                     "pass --llvm-bin <dir> or set LLVM_BIN")


def tool(name: str) -> str:
    if name in CLANG_TOOLS:
        return str(llvm_bin() / name)
    found = shutil.which(name)
    if found is None:
        raise SystemExit(f"ioa: {name} not found on PATH")
    return found


def add_llvm_bin_option(parser) -> None:
    parser.add_argument("--llvm-bin", type=Path, metavar="DIR",
                        help="directory holding clang-tidy, run-clang-tidy, clang-format, "
                             "clang-query, and clang-apply-replacements")


def use_llvm_bin(args) -> None:
    """Export --llvm-bin as IOA_LLVM_BIN, so this process and its children use it."""
    if getattr(args, "llvm_bin", None):
        os.environ["IOA_LLVM_BIN"] = str(args.llvm_bin.resolve())


@dataclass(frozen=True)
class Repl:
    file: Path
    offset: int
    length: int
    text: str


@dataclass(frozen=True)
class Diag:
    check: str
    message: str
    repls: tuple[Repl, ...]
    file: Path | None = None
    offset: int | None = None


def _scalar(v: str) -> str:
    v = v.strip()
    if v.startswith("'"):
        return v[1:-1].replace("''", "'")
    if v.startswith('"'):
        return json.loads(v)
    return v


def parse_fixes(text: str) -> list[Diag]:
    """Read clang-tidy -export-fixes YAML (the subset clang-tidy emits)."""
    out: list[dict] = []
    cur: dict | None = None
    section = sub = ""
    for line in text.splitlines():
        kv = KV.match(line)
        if not kv:
            continue
        col = len(kv[1]) + (2 if kv[2] else 0)
        key, val = kv[3], kv[4]
        if col == 4 and key == "DiagnosticName":
            cur = {"check": _scalar(val), "message": "", "repls": [], "file": None, "offset": None}
            out.append(cur)
            section = "diag"
        elif cur is None:
            continue
        elif col == 4:
            section = "notes" if key == "Notes" else "diag"
        elif section != "diag":
            continue
        elif col == 6:
            sub = key
            if key == "Message":
                cur["message"] = _scalar(val)
            elif key == "FilePath" and _scalar(val):
                cur["file"] = Path(_scalar(val))
            elif key == "FileOffset":
                cur["offset"] = int(val)
        elif col == 10 and sub == "Replacements":
            if kv[2]:
                cur["repls"].append({})
            cur["repls"][-1][key] = _scalar(val)
    return [
        Diag(d["check"], d["message"], tuple(
            Repl(Path(r["FilePath"]), int(r["Offset"]), int(r["Length"]), r["ReplacementText"])
            for r in d["repls"]
        ), d["file"], d["offset"])
        for d in out
    ]


def _ere(s: str) -> str:
    return re.sub(r"([.^$|()\[\]{}*+?\\])", r"\\\1", s)


def in_scope(path: Path, root: Path) -> bool:
    """Under root, outside excluded directories, and tracked by git (never a build tree)."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return not any(p in EXCLUDED for p in rel.parts[:-1]) and is_tracked(path, root)


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def database_spellings(graph: Path) -> dict[Path, str]:
    """Resolved path -> the absolute spelling run-clang-tidy matches file arguments against."""
    try:
        entries = json.loads((graph / "compile_commands.json").read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for e in entries:
        spelling = os.path.abspath(os.path.join(e["directory"], e["file"]))
        out[Path(spelling).resolve()] = spelling
    return out


def root_spellings(spelled: dict[Path, str], root: Path) -> list[str]:
    """The resolved root plus every spelling of it the compile database uses."""
    found = [str(root)]
    for real, spelling in spelled.items():
        if real.is_relative_to(root):
            rel = str(real.relative_to(root))
            prefix = spelling[: -len(rel) - 1] if spelling.endswith("/" + rel) else None
            if prefix and prefix not in found:
                found.append(prefix)
    return found


def crashed_tus(output: str) -> list[str]:
    """TUs that run-clang-tidy reports as failed or killed."""
    found = re.findall(r"^Error while processing (.+?)\.?$", output, re.M)
    found += re.findall(r"^(.+?): terminated by signal \d+$", output, re.M)
    return list(dict.fromkeys(found))


def run_tidy(
    graph: Path,
    root: Path,
    check: str,
    options: dict[str, object] | None = None,
    files: list[Path] | None = None,
) -> tuple[list[Diag], list[str]]:
    """Fixes for one check, and the TUs dropped because they failed to compile.

    ``files`` limits the run to those translation units; an empty list runs nothing.
    """
    if files is not None and not files:
        return [], []
    excluded = "|".join(EXCLUDED)
    spelled = database_spellings(graph)
    roots = root_spellings(spelled, root)
    under = "|".join(_ere(r) for r in roots)
    if files is None:
        if not spelled:
            raise RuntimeError(f"run-clang-tidy failed: {graph / 'compile_commands.json'} "
                               "is unreadable or empty")
        files = [real for real in spelled if in_scope(real, root)]
        if not files:
            return [], []
    targets = [f"^{re.escape(spelled.get(Path(f).resolve(), str(Path(f).resolve())))}$" for f in files]
    config = []
    if options:
        opts = ", ".join(f"{check}.{k}: {json.dumps(v)}" for k, v in options.items())
        config = [f"-config={{CheckOptions: {{{opts}}}}}"]
    with tempfile.TemporaryDirectory() as fixes:
        res = subprocess.run(
            [
                tool("run-clang-tidy"),
                "-clang-tidy-binary", tool("clang-tidy"),
                "-clang-apply-replacements-binary", tool("clang-apply-replacements"),
                "-p", str(graph), f"-checks=-*,{check}", *config,
                f"-header-filter=^({under})/",
                f"-exclude-header-filter=/({excluded})/",
                "-export-fixes", fixes, "-quiet", "-j", str(os.cpu_count() or 1),
                *targets,
            ],
            capture_output=True, text=True,
        )
        diags: list[Diag] = []
        dropped: list[str] = []
        for y in sorted(Path(fixes).glob("*.yaml")):
            text = y.read_text(errors="surrogateescape")
            parsed = parse_fixes(text)
            if any(d.check == "clang-diagnostic-error" for d in parsed):
                main = re.search(r"^MainSourceFile:\s*(.*)$", text, re.M)
                tu = Path(_scalar(main[1])) if main else Path(y.name)
                dropped.append(_rel(tu, root))
            else:
                diags += parsed
    counted = re.search(r"^Running clang-tidy for (\d+) files", res.stdout, re.M)
    if files is not None and counted and counted[1] == "0":
        raise RuntimeError(f"run-clang-tidy matched none of {len(files)} requested file(s) in {graph}")
    for tu in crashed_tus(res.stdout + res.stderr):
        rel = _rel(Path(tu).resolve(), root)
        if rel not in dropped:
            dropped.append(f"{rel} (tidy-crash)")
    if res.returncode != 0 and not dropped:
        raise RuntimeError(f"run-clang-tidy failed (exit {res.returncode}):\n{res.stderr[-4000:]}")
    seen, out = set(), []
    for d in diags:
        if d.check != check or not d.repls or d in seen:
            continue
        if all(in_scope(r.file, root) for r in d.repls):
            seen.add(d)
            out.append(d)
    return out, dropped


class Doc:
    """A source file with byte <-> character offset mapping."""

    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        self.text = self.data.decode("utf-8", "surrogateescape")

    def c(self, byte: int) -> int:
        if self.data.isascii():
            return byte
        return len(self.data[:byte].decode("utf-8", "surrogateescape"))

    def b(self, char: int) -> int:
        if self.data.isascii():
            return char
        return len(self.text[:char].encode("utf-8", "surrogateescape"))

    def line(self, char: int) -> int:
        return self.text.count("\n", 0, char)


def apply_edits(
    edits: dict[Path, list[tuple[int, int, str]]], docs: dict[Path, Doc], name: str = "member-init"
) -> None:
    """Apply (start, end, text) character-offset edits with clang-apply-replacements."""
    lines = ["---", "MainSourceFile: \"\"", "Diagnostics:"]
    for path, items in edits.items():
        doc = docs[path]
        lines += [
            f"  - DiagnosticName: \"ioa-{name}\"",
            "    DiagnosticMessage:",
            f"      Message: \"{name}\"",
            f"      FilePath: {json.dumps(str(path))}",
            "      FileOffset: 0",
            "      Replacements:",
        ]
        for a, b, text in sorted(items):
            lines += [
                f"        - FilePath: {json.dumps(str(path))}",
                f"          Offset: {doc.b(a)}",
                f"          Length: {doc.b(b) - doc.b(a)}",
                f"          ReplacementText: {json.dumps(text)}",
            ]
        lines += ["    Level: Warning", "    BuildDirectory: \"\""]
    lines.append("...")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "fixes.yaml").write_text("\n".join(lines) + "\n")
        res = subprocess.run([tool("clang-apply-replacements"), d], capture_output=True, text=True)
        if res.returncode != 0 or res.stderr.strip():
            raise RuntimeError(f"clang-apply-replacements failed (exit {res.returncode}):\n{res.stderr[-4000:]}")


def changed_ranges(old: str, new: str) -> list[tuple[int, int]]:
    """Half-open 0-based line ranges of new that differ from old."""
    ops = difflib.SequenceMatcher(None, old.splitlines(True), new.splitlines(True), autojunk=False)
    return [(j1, j2) for tag, _, _, j1, j2 in ops.get_opcodes() if tag != "equal"]


BLOCK_END = re.compile(r"^\s*(?:(?:return|if|for|while|switch|case)\b|[{}#]|//|/\*|\*)")


def widen_to_block(lines: list[str], lo: int, hi: int) -> tuple[int, int]:
    """Extend 1-based inclusive [lo, hi] over adjacent declaration or assignment lines.

    clang-format aligns consecutive declarations, so formatting one line of a run alone
    leaves its neighbors misaligned. Blank lines, braces, control statements,
    preprocessor lines, and comments end the run.
    """
    def inside(i: int) -> bool:
        return 1 <= i <= len(lines) and lines[i - 1].strip() != "" and not BLOCK_END.match(lines[i - 1])

    while inside(lo - 1):
        lo -= 1
    while inside(hi + 1):
        hi += 1
    return lo, hi


def format_changed(path: Path, old: str) -> None:
    """clang-format the lines of path that differ from old, widened to their blocks."""
    new = path.read_text(errors="surrogateescape")
    n = max(1, new.count("\n"))
    lines = new.splitlines()
    spans = []
    for j1, j2 in changed_ranges(old, new):
        lo, hi = widen_to_block(lines, j1 + 1, max(j2, j1 + 1))
        spans.append(f"--lines={max(1, min(lo, j1))}:{min(n, hi)}")
    if spans:
        subprocess.run(
            [tool("clang-format"), "-i", "--style=file", "--fallback-style=none", *spans, str(path)],
            check=True, capture_output=True, text=True,
        )


def opcodes(a: str, b: str) -> list[tuple]:
    return difflib.SequenceMatcher(None, a.splitlines(True), b.splitlines(True), autojunk=False).get_opcodes()


def map_line(ops: list[tuple], x: int, end: bool) -> int:
    """Map 0-based line x of the old text through ops to the new text."""
    for tag, i1, i2, j1, j2 in ops:
        if (i1 < x <= i2) if end else (i1 <= x < i2):
            if tag == "equal":
                return j1 + (x - i1)
            return j2 if end else j1
    return ops[-1][4] if ops else x
