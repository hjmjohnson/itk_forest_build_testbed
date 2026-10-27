#!/usr/bin/env python3
"""Move constructor-body member assignments into initializer lists, then promote
constant initializers to default member initializers, using clang-tidy fixes.

Edits the working tree and writes a manifest; never commits.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "itk-init-over-assign" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import postfix as pf  # noqa: E402
from ioa.comments import check_hunks  # noqa: E402
from ioa.compile_commands import find_graph  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.skip import Reason  # noqa: E402

KIND = "member-init"
PMI = "prefer-member-initializer"
DMI = "use-default-member-init"
CHECKS = {
    PMI: "cppcoreguidelines-prefer-member-initializer",
    DMI: "modernize-use-default-member-init",
}
EXCLUDED = ("ThirdParty", "build", "Utilities")
KV = re.compile(r"^( *)(- )?(\w+):\s*(.*)$")


def tool(name: str) -> str:
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix and (Path(prefix) / "bin" / name).exists():
        return str(Path(prefix) / "bin" / name)
    found = shutil.which(name)
    if found is None:
        raise SystemExit(f"member_init: {name} not found in $CONDA_PREFIX/bin or on PATH")
    return found


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


def _scalar(v: str) -> str:
    v = v.strip()
    if v.startswith("'"):
        return v[1:-1].replace("''", "'")
    if v.startswith('"'):
        return json.loads(v)
    return v


def parse_fixes(text: str) -> list[Diag]:
    """Read clang-tidy -export-fixes YAML (the subset clang-tidy emits)."""
    out: list[Diag] = []
    cur: dict | None = None
    section = sub = ""
    for line in text.splitlines():
        kv = KV.match(line)
        if not kv:
            continue
        col = len(kv[1]) + (2 if kv[2] else 0)
        key, val = kv[3], kv[4]
        if col == 4 and key == "DiagnosticName":
            cur = {"check": _scalar(val), "message": "", "repls": []}
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
        elif col == 10 and sub == "Replacements":
            if kv[2]:
                cur["repls"].append({})
            cur["repls"][-1][key] = _scalar(val)
    return [
        Diag(d["check"], d["message"], tuple(
            Repl(Path(r["FilePath"]), int(r["Offset"]), int(r["Length"]), r["ReplacementText"])
            for r in d["repls"]
        ))
        for d in out
    ]


def _ere(s: str) -> str:
    return re.sub(r"([.^$|()\[\]{}*+?\\])", r"\\\1", s)


def in_scope(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return False
    return not any(p in EXCLUDED for p in rel.parts[:-1])


def run_tidy(graph: Path, root: Path, cls: str) -> list[Diag]:
    excluded = "|".join(EXCLUDED)
    with tempfile.TemporaryDirectory() as fixes:
        subprocess.run(
            [
                tool("run-clang-tidy"),
                "-clang-tidy-binary", tool("clang-tidy"),
                "-clang-apply-replacements-binary", tool("clang-apply-replacements"),
                "-p", str(graph), f"-checks=-*,{CHECKS[cls]}",
                f"-header-filter=^{_ere(str(root))}/",
                f"-exclude-header-filter=/({excluded})/",
                "-export-fixes", fixes, "-quiet", "-j", str(os.cpu_count() or 1),
                f"^{re.escape(str(root))}/(?!(?:.*/)?(?:{excluded})/)",
            ],
            capture_output=True, text=True,
        )
        diags: list[Diag] = []
        for y in sorted(Path(fixes).glob("*.yaml")):
            parsed = parse_fixes(y.read_text(errors="surrogateescape"))
            if not any(d.check == "clang-diagnostic-error" for d in parsed):
                diags += parsed
    seen, out = set(), []
    for d in diags:
        if d.check != CHECKS[cls] or not d.repls or d in seen:
            continue
        if all(in_scope(r.file, root) for r in d.repls):
            seen.add(d)
            out.append(d)
    return out


class Doc:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        self.text = self.data.decode("utf-8", "surrogateescape")
        self.m, self.comments = pf.mask(self.text)

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


@dataclass
class Skip:
    file: Path
    first: int
    last: int
    reason: Reason
    note: str
    cls: str


class Planner:
    def __init__(self, root: Path):
        self.root = root
        self.docs: dict[Path, Doc] = {}
        self.edits: dict[Path, list[tuple[int, int, str]]] = defaultdict(list)
        self.skips: list[Skip] = []
        self.partners: set[frozenset[Path]] = set()
        self._index: list[str] | None = None

    def doc(self, path: Path) -> Doc:
        path = path.resolve()
        if path not in self.docs:
            self.docs[path] = Doc(path)
        return self.docs[path]

    def skip(self, doc: Doc, a: int, b: int, reason: Reason, note: str, cls: str) -> None:
        self.skips.append(Skip(doc.path, doc.line(a), doc.line(b), reason, note, cls))

    def _files(self) -> list[str]:
        if self._index is None:
            res = subprocess.run(["git", "-C", str(self.root), "ls-files"], capture_output=True, text=True)
            self._index = res.stdout.splitlines()
        return self._index

    def _include(self, doc: Doc, name: str) -> Path | None:
        local = doc.path.parent / name
        if local.is_file():
            return local
        hits = [f for f in self._files() if f == name or f.endswith("/" + name)]
        return self.root / hits[0] if hits else None

    def members(self, doc: Doc, ctor: pf.Ctor) -> list[str] | None:
        cands = [doc]
        if not ctor.in_class:
            for inc in re.findall(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"]+)[>"]', doc.text, re.M):
                path = self._include(doc, inc)
                if path is not None and in_scope(path, self.root):
                    cands.append(self.doc(path))
        for cand in cands:
            span = pf.find_class(cand.m, ctor.cls)
            if span is not None:
                return pf.data_members(cand.m, *span)
        return None

    def plan_pmi(self, diags: list[Diag]) -> None:
        groups: dict[tuple[Path, int], list] = defaultdict(list)
        for seq, d in enumerate(diags):
            ins = [r for r in d.repls if r.length == 0 and r.text.strip()]
            rem = [r for r in d.repls if r.text == ""]
            if len(ins) != 1 or len(rem) != 1 or ins[0].file != rem[0].file:
                continue
            doc = self.doc(ins[0].file)
            at = doc.c(ins[0].offset)
            body = pf.body_after(doc.m, at)
            if body is not None:
                a, b = doc.c(rem[0].offset), doc.c(rem[0].offset + rem[0].length)
                groups[(doc.path, body)].append((seq, at, a, b, ins[0].text))
        for (path, body), items in groups.items():
            self._plan_ctor(self.docs[path], body, items)

    def _plan_ctor(self, doc: Doc, body: int, items: list) -> None:
        ctor = pf.parse_ctor(doc.text, doc.m, doc.comments, body)
        if ctor is None:
            return self.skip(doc, body, body, Reason.ORDER_VIOLATION, "unparsed constructor", PMI)
        members = self.members(doc, ctor)
        if members is None:
            return self.skip(doc, ctor.sig_end, body, Reason.ORDER_VIOLATION, "class not found", PMI)
        keyed, removals, stranded = [], [], []
        for seq, at, a, b, text in items:
            s, e, carried, strands = pf.statement_removal(doc.text, doc.comments, a, b)
            if strands:
                stranded.append((a, b))
            entry_text = re.sub(r"^\s*[:,]?\s*|\s*,?\s*$", "", text)
            name = pf.IDENT.match(entry_text).group()
            keyed.append(((at, 0, seq), pf.Entry(name, entry_text, trail=carried)))
            removals.append((s, e, ""))
        if stranded:
            for a, b in stranded:
                self.skip(doc, a, b, Reason.COMMENT_STRANDED, "comment above the assignment", PMI)
            return
        keyed += [((e.start, 1, 0), e) for e in ctor.entries]
        merged = [e for _, e in sorted(keyed, key=lambda k: k[0])]
        ordered, note = pf.plan_order(merged, members)
        if ordered is None:
            return self.skip(doc, ctor.sig_end, body, Reason.ORDER_VIOLATION, note, PMI)
        self.edits[doc.path] += [(ctor.sig_end, body, pf.render(ctor, ordered)), *removals]

    def plan_dmi(self, diags: list[Diag]) -> None:
        groups: dict[tuple[Path, int], list] = defaultdict(list)
        for d in diags:
            ins = [r for r in d.repls if r.length == 0 and r.text.startswith("{")]
            rem = [r for r in d.repls if r.text == "" and r.length > 0]
            if len(ins) != 1 or len(rem) != 1:
                continue
            hdoc, cdoc = self.doc(ins[0].file), self.doc(rem[0].file)
            at = hdoc.c(ins[0].offset)
            if pf.POINTERISH.search(pf.decl_head(hdoc.m, at)):
                continue
            ra = cdoc.c(rem[0].offset)
            body = pf.body_after(cdoc.m, ra)
            if body is not None:
                groups[(cdoc.path, body)].append((hdoc, at, ins[0].text, ra))
        for (path, body), items in groups.items():
            cdoc = self.docs[path]
            ctor = pf.parse_ctor(cdoc.text, cdoc.m, cdoc.comments, body)
            if ctor is None:
                self.skip(cdoc, body, body, Reason.ORDER_VIOLATION, "unparsed constructor", DMI)
                continue
            removed = []
            for hdoc, at, text, ra in items:
                entry = next((e for e in ctor.entries if e.start <= ra <= e.end), None)
                if entry is None:
                    continue
                ls, le = pf.line_bounds(hdoc.text, at, at)
                if entry.lead or (entry.trail and any(ls <= c0 < le for c0, _ in hdoc.comments)):
                    self.skip(cdoc, entry.start, entry.end, Reason.COMMENT_STRANDED,
                              "comment cannot follow the default member initializer", DMI)
                    continue
                self.edits[hdoc.path].append((at, at, text))
                if entry.trail:
                    self.edits[hdoc.path].append((le, le, " " + entry.trail))
                removed.append(entry)
                self.partners.add(frozenset((hdoc.path, cdoc.path)))
            if removed:
                keep = [e for e in ctor.entries if e not in removed]
                self.edits[path].append((ctor.sig_end, body, pf.render(ctor, keep)))


def apply_edits(edits: dict[Path, list[tuple[int, int, str]]], docs: dict[Path, Doc]) -> None:
    lines = ["---", "MainSourceFile: \"\"", "Diagnostics:"]
    for path, items in edits.items():
        doc = docs[path]
        lines += [
            "  - DiagnosticName: \"ioa-member-init\"",
            "    DiagnosticMessage:",
            "      Message: \"member-init\"",
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
        subprocess.run([tool("clang-apply-replacements"), d], check=True, capture_output=True, text=True)


def changed_ranges(old: str, new: str) -> list[tuple[int, int]]:
    """Half-open 0-based line ranges of new that differ from old."""
    ops = difflib.SequenceMatcher(None, old.splitlines(True), new.splitlines(True), autojunk=False)
    return [(j1, j2) for tag, _, _, j1, j2 in ops.get_opcodes() if tag != "equal"]


def format_changed(path: Path, old: str) -> None:
    new = path.read_text(errors="surrogateescape")
    n = max(1, new.count("\n"))
    spans = [f"--lines={max(1, j1)}:{min(n, max(j2, j1 + 1))}" for j1, j2 in changed_ranges(old, new)]
    if spans:
        subprocess.run(
            [tool("clang-format"), "-i", "--style=file", "--fallback-style=none", *spans, str(path)],
            check=True, capture_output=True, text=True,
        )


def _opcodes(a: str, b: str) -> list[tuple]:
    return difflib.SequenceMatcher(None, a.splitlines(True), b.splitlines(True), autojunk=False).get_opcodes()


def map_line(ops: list[tuple], x: int, end: bool) -> int:
    for tag, i1, i2, j1, j2 in ops:
        if (i1 < x <= i2) if end else (i1 <= x < i2):
            if tag == "equal":
                return j1 + (x - i1)
            return j2 if end else j1
    return ops[-1][4] if ops else x


def site(root: Path, path: Path, first: int, last: int, cls: str, text: str, **kw) -> Site:
    n = max(1, text.count("\n"))
    start = min(max(1, first + 1), n)
    return Site(path.relative_to(root), start, min(max(start, last), n), KIND, cls, **kw)


def run(graph: Path, root: Path, manifest: Path | None, apply: bool) -> int:
    pmi = run_tidy(graph, root, PMI)
    if not apply:
        counts: dict[tuple[str, Path], int] = defaultdict(int)
        for cls, diags in ((PMI, pmi), (DMI, run_tidy(graph, root, DMI))):
            for d in diags:
                counts[(cls, d.repls[0].file.resolve().relative_to(root))] += 1
        for (cls, rel), n in sorted(counts.items()):
            print(f"{cls} {rel} {n}")
        return 0

    p1 = Planner(root)
    p1.plan_pmi(pmi)
    orig = {p: d.text for p, d in p1.docs.items()}
    raw = {p: d.data for p, d in p1.docs.items()}
    if p1.edits:
        apply_edits(p1.edits, p1.docs)
        for path in p1.edits:
            format_changed(path, orig[path])
    post1 = {p: p.read_text(errors="surrogateescape") for p in orig}

    p2 = Planner(root)
    p2.plan_dmi(run_tidy(graph, root, DMI))
    for p, d in p2.docs.items():
        orig.setdefault(p, d.text)
        raw.setdefault(p, d.data)
        post1.setdefault(p, d.text)
    if p2.edits:
        apply_edits(p2.edits, p2.docs)
        for path in p2.edits:
            format_changed(path, post1[path])
    final = {p: p.read_text(errors="surrogateescape") for p in orig}

    sites: list[Site] = []
    for path in sorted(set(p1.edits) | set(p2.edits)):
        o, m, f = orig[path], post1[path], final[path]
        later = _opcodes(m, f)
        for j1, j2 in changed_ranges(o, m) if path in p1.edits else []:
            a, b = map_line(later, j1, False), map_line(later, j2, True)
            sites.append(site(root, path, a, b, PMI, f))
        for j1, j2 in changed_ranges(m, f) if path in p2.edits else []:
            sites.append(site(root, path, j1, j2, DMI, f))
    for s in p1.skips + p2.skips:
        f = final[s.file]
        ops = _opcodes(post1[s.file], f)
        a, b = s.first, s.last + 1
        if s.cls == PMI:
            first = _opcodes(orig[s.file], post1[s.file])
            a, b = map_line(first, a, False), map_line(first, b, True)
        sites.append(site(root, s.file, map_line(ops, a, False), map_line(ops, b, True), s.cls, f,
                          skipped=s.reason, note=s.note))

    touched = sorted(set(p1.edits) | set(p2.edits))
    if touched:
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "-U0", "--", *map(str, touched)],
            capture_output=True, text=True, check=True,
        ).stdout
        stranded = check_hunks(diff)
        bad = {(root / s.file).resolve() for s in stranded}
        for pair in p2.partners:
            if pair & bad:
                bad |= pair
        for path in bad:
            path.write_bytes(raw[path])
        sites = [s for s in sites if (root / s.file).resolve() not in bad]
        sites += [
            Site(s.file, s.line, s.line, KIND, PMI if (root / s.file).resolve() in p1.edits else DMI,
                 skipped=Reason.COMMENT_STRANDED, note=s.text)
            for s in stranded
        ]

    if manifest is not None:
        Manifest(KIND, sites).write(manifest)
    applied = sum(1 for s in sites if s.skipped is None)
    print(f"member-init: {applied} applied, {len(sites) - applied} skipped")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True, type=Path,
                    help="build dir holding compile_commands.json, or a parent of it")
    ap.add_argument("--repo", required=True, type=Path, help="repository root")
    ap.add_argument("--manifest", type=Path, help="manifest path (written only with --apply)")
    ap.add_argument("--apply", action="store_true", help="edit the working tree")
    args = ap.parse_args(argv)
    root = args.repo.resolve()
    if not root.is_dir():
        ap.error(f"--repo {args.repo} is not a directory")
    graph = args.graph.resolve()
    if not (graph / "compile_commands.json").exists():
        graph = find_graph(graph, root.name)
    return run(graph, root, args.manifest, args.apply)


if __name__ == "__main__":
    sys.exit(main())
