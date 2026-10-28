#!/usr/bin/env python3
"""Move constructor-body member assignments into initializer lists, then promote
constant initializers to default member initializers, using clang-tidy fixes.

Edits the working tree and writes a manifest; never commits.
"""

import argparse
import re
import secrets
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    import ioa  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "itk-init-over-assign" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import postfix as pf  # noqa: E402
from ioa.comments import check_hunks, unified_diff  # noqa: E402
from ioa.compile_commands import find_graph  # noqa: E402
from ioa.manifest import Manifest, Site  # noqa: E402
from ioa.skip import Reason  # noqa: E402
from ioa import tidy  # noqa: E402
from ioa.tidy import (  # noqa: E402
    Diag, apply_edits, changed_ranges, crashed_tus, format_changed, in_scope, map_line, run_tidy,
)
from ioa.tidy import opcodes as _opcodes  # noqa: E402

KIND = "member-init"
PMI = "prefer-member-initializer"
DMI = "use-default-member-init"
CHECKS = {
    PMI: "cppcoreguidelines-prefer-member-initializer",
    DMI: "modernize-use-default-member-init",
}


class Doc(tidy.Doc):
    def __init__(self, path: Path):
        super().__init__(path)
        self.m, self.comments = pf.mask(self.text)


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
        self.moves: list[list[tuple[Path, int]]] = []
        self.ctor_moves: list[list[tuple[Path, int, int]]] = []
        self.errors = 0
        self._index: list[str] | None = None

    def doc(self, path: Path) -> Doc:
        path = path.resolve()
        if path not in self.docs:
            self.docs[path] = Doc(path)
        return self.docs[path]

    def skip(self, doc: Doc, a: int, b: int, reason: Reason, note: str, cls: str) -> None:
        self.skips.append(Skip(doc.path, doc.line(a), doc.line(b), reason, note, cls))

    def failed(self, where: tuple[Path, int], cls: str, exc: Exception) -> None:
        """Skip one site (file, 0-based line) after an unexpected error so the stage goes on."""
        path, line = where
        self.errors += 1
        self.skips.append(Skip(path, line, line, Reason.GATE_FAILED,
                               f"internal-error:{type(exc).__name__}", cls))
        print(f"member-init: internal error at {path}:{line + 1}: {type(exc).__name__}: {exc}",
              file=sys.stderr)

    def where(self, file: Path | None, offset: int | None) -> tuple[Path, int]:
        """File and 0-based line of a byte offset, without raising."""
        path = Path(file or "<unknown>")
        try:
            doc = self.doc(path)
            return doc.path, doc.line(doc.c(offset or 0))
        except Exception:
            try:
                return path.resolve(), path.read_bytes()[:offset or 0].count(b"\n")
            except Exception:
                return path, 0

    def at(self, doc: Doc, char: int) -> tuple[Path, int]:
        return doc.path, doc.line(char)

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
        for sibling in (doc.path.with_suffix(".h"), doc.path.with_suffix(".hxx")):
            if sibling != doc.path and sibling.is_file():
                cands.append(self.doc(sibling))
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
            try:
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
            except Exception as exc:
                self.failed(self.where(d.file, d.offset), PMI, exc)
        for (path, body), items in groups.items():
            try:
                self._plan_ctor(self.docs[path], body, items)
            except Exception as exc:
                self.failed(self.where(path, None) if path not in self.docs
                            else self.at(self.docs[path], body), PMI, exc)

    def _plan_ctor(self, doc: Doc, body: int, items: list) -> None:
        ctor = pf.parse_ctor(doc.text, doc.m, doc.comments, body)
        if ctor is None:
            return self.skip(doc, body, body, Reason.GATE_FAILED, "ctor-unparsed", PMI)
        if pf.has_directive(doc.text, ctor.sig_end, body):
            return self.skip(doc, ctor.sig_end, body, Reason.PREPROCESSOR, "directive in initializer list", PMI)
        members = self.members(doc, ctor)
        if members is None:
            return self.skip(doc, ctor.sig_end, body, Reason.GATE_FAILED, "class-not-found", PMI)
        keyed, removals, stranded = [], [], []
        body_close = pf.match_fwd(doc.m, body)
        for seq, at, a, b, text in items:
            if pf.has_directive(doc.text, *pf.neighbor_lines(doc.text, a, b, body, body_close)):
                self.skip(doc, a, b, Reason.PREPROCESSOR, "directive around the assignment", PMI)
                continue
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
        if not keyed:
            return
        keyed += [((e.start, 1, 0), e) for e in ctor.entries]
        merged = [e for _, e in sorted(keyed, key=lambda k: k[0])]
        ordered, note = pf.plan_order(merged, members)
        if ordered is None:
            reason = Reason.GATE_FAILED if note == pf.UNKNOWN_INITIALIZER else Reason.ORDER_VIOLATION
            return self.skip(doc, ctor.sig_end, body, reason, note, PMI)
        self.edits[doc.path] += [(ctor.sig_end, body, pf.render(ctor, ordered)), *removals]
        self.ctor_moves.append([(doc.path, doc.line(ctor.sig_end), doc.line(body)),
                                *((doc.path, doc.line(a), doc.line(max(a, b - 1))) for a, b, _ in removals)])

    def _parse(self, doc: Doc, body: int) -> pf.Ctor | None:
        key = (doc.path, body)
        if key not in self._ctors:
            self._ctors[key] = pf.parse_ctor(doc.text, doc.m, doc.comments, body)
        return self._ctors[key]

    def _dmi_ctor(self, doc: Doc, body: int) -> pf.Ctor | None:
        """Parsed editable constructor, or None after recording why not (once)."""
        ctor = self._parse(doc, body)
        if (doc.path, body) in self._refused:
            return None
        if ctor is None:
            self.skip(doc, body, body, Reason.GATE_FAILED, "ctor-unparsed", DMI)
        elif pf.has_directive(doc.text, ctor.sig_end, body):
            self.skip(doc, ctor.sig_end, body, Reason.PREPROCESSOR, "directive in initializer list", DMI)
            ctor = None
        if ctor is None:
            self._refused.add((doc.path, body))
        return ctor

    def plan_dmi(self, diags: list[Diag]) -> None:
        self._ctors: dict[tuple[Path, int], pf.Ctor | None] = {}
        self._refused: set[tuple[Path, int]] = set()
        plans: dict[tuple[Path, int], tuple] = {}
        for d in diags:
            try:
                self._plan_dmi_diag(d, plans)
            except Exception as exc:
                self.failed(self.where(d.file, d.offset), DMI, exc)
        self._finish_dmi(plans)

    def _plan_dmi_diag(self, d: Diag, plans: dict) -> None:
        ins = [r for r in d.repls if r.length == 0 and r.text.startswith("{")]
        rem = [r for r in d.repls if r.text == "" and r.length > 0]
        if len(ins) != 1 or len(rem) != 1:
            return
        hdoc, cdoc = self.doc(ins[0].file), self.doc(rem[0].file)
        at = hdoc.c(ins[0].offset)
        if (hdoc.path, at) in plans or pf.POINTERISH.search(pf.decl_head(hdoc.m, at)):
            return
        ra = cdoc.c(rem[0].offset)
        body = pf.body_after(cdoc.m, ra)
        ctor = self._dmi_ctor(cdoc, body) if body is not None else None
        entry = ctor and next((e for e in ctor.entries if e.start <= ra <= e.end), None)
        if entry is None:
            return
        holders = [(cdoc, body, entry, False)]
        for other in pf.ctor_bodies(cdoc.m, ctor.cls):
            if other == body:
                continue
            c2 = self._parse(cdoc, other)
            if c2 is None:
                holders.append((cdoc, other, None, False))
                continue
            if c2.cls != ctor.cls:
                continue
            same = next((e for e in c2.entries if e.name == entry.name and e.text == entry.text), None)
            if same is not None:
                holders.append((cdoc, other, same, pf.has_directive(cdoc.text, c2.sig_end, other)))
        plans[(hdoc.path, at)] = (hdoc, at, ins[0].text, holders)

    def _finish_dmi(self, plans: dict) -> None:
        """Commit each default-member-init group whole: renders first, edits after."""
        groups: list[tuple] = []
        for hdoc, at, text, holders in plans.values():
            try:
                group = self._dmi_group(hdoc, at, text, holders)
            except Exception as exc:
                self.failed(self.at(hdoc, at), DMI, exc)
                continue
            if group is not None:
                groups.append(group)
        while True:
            removed: dict[tuple[Path, int], list[pf.Entry]] = defaultdict(list)
            for g in groups:
                for cdoc, body, e, _ in g[3]:
                    removed[(cdoc.path, body)].append(e)
            renders: dict[tuple[Path, int], tuple[int, int, str]] = {}
            broken = None
            for key, gone in removed.items():
                try:
                    ctor = self._ctors[key]
                    keep = [e for e in ctor.entries if e not in gone]
                    renders[key] = (ctor.sig_end, key[1], pf.render(ctor, keep))
                except Exception as exc:
                    broken = (key, exc)
                    break
            if broken is None:
                break
            key, exc = broken
            hit = [g for g in groups if any((c.path, b) == key for c, b, _, _ in g[3])]
            for g in hit:
                self.failed(self.at(g[0], g[1]), DMI, exc)
            groups = [g for g in groups if all(g is not h for h in hit)]
        for hdoc, at, text, holders, trail, le in groups:
            self.edits[hdoc.path].append((at, at, text))
            if trail:
                self.edits[hdoc.path].append((le, le, " " + trail))
            for cdoc, _, _, _ in holders:
                self.partners.add(frozenset((hdoc.path, cdoc.path)))
            self.moves.append([(hdoc.path, hdoc.line(at)),
                               *((cdoc.path, cdoc.line(e.start)) for cdoc, _, e, _ in holders)])
        for (path, _), edit in renders.items():
            self.edits[path].append(edit)

    def _dmi_group(self, hdoc: Doc, at: int, text: str, holders: list) -> tuple | None:
        """A movable group as (hdoc, at, text, holders, trail, line end), or None once skipped."""
        if any(e is None for _, _, e, _ in holders):
            for cdoc, body, e, _ in holders:
                a, b = (e.start, e.end) if e is not None else (body, body)
                self.skip(cdoc, a, b, Reason.GATE_FAILED, "ctor-unparsed", DMI)
            return None
        ls, le = pf.line_bounds(hdoc.text, at, at)
        trails = {e.trail for _, _, e, _ in holders if e.trail}
        header_comment = any(ls <= c0 < le for c0, _ in hdoc.comments)
        directive = any(d for *_, d in holders)
        if directive or any(e.lead for _, _, e, _ in holders) or len(trails) > 1 or (trails and header_comment):
            reason = Reason.PREPROCESSOR if directive else Reason.COMMENT_STRANDED
            note = "a constructor sharing this initializer cannot drop it"
            for cdoc, _, e, _ in holders:
                self.skip(cdoc, e.start, e.end, reason, note, DMI)
            return None
        return hdoc, at, text, holders, trails.pop() if trails else "", le


def site(root: Path, path: Path, first: int, last: int, cls: str, text: str, **kw) -> Site:
    n = max(1, text.count("\n"))
    start = min(max(1, first + 1), n)
    return Site(path.relative_to(root), start, min(max(start, last), n), KIND, cls, **kw)


def _label(sites: list[Site], hits: dict[int, list[int]], count: int, tag: str) -> None:
    """Union moves that share a site and give every site of a union one group id."""
    parent = list(range(count))

    def find(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for ks in hits.values():
        for k in ks[1:]:
            parent[find(k)] = find(ks[0])
    token = secrets.token_hex(4)
    for i, ks in hits.items():
        sites[i].group = f"{KIND}:{token}:{tag}-{find(ks[0])}"


def _group_ctor_moves(sites: list[Site], pmi: list[tuple[int, Path, int, int]],
                      moves: list[list[tuple[Path, int, int]]]) -> None:
    """One group id for a constructor's inserted list and every assignment it removed.

    Spans and sites are in pre-edit lines; an insertion (i1 == i2) sits before line i1.
    """
    hits: dict[int, list[int]] = {}
    for k, spans in enumerate(moves):
        for path, lo, hi in spans:
            for i, p, i1, i2 in pmi:
                inside = lo < i1 <= hi if i1 == i2 else i1 <= hi and lo <= i2 - 1
                if p == path and inside:
                    hits.setdefault(i, []).append(k)
    _label(sites, {i: list(dict.fromkeys(ks)) for i, ks in hits.items()}, len(moves), "pmi")


def _group_moves(sites: list[Site], dmi: list[tuple[int, Path, int, int]],
                 moves: list[list[tuple[Path, int]]], ops: dict[Path, list[tuple]]) -> None:
    """Give the header and source sites of each default-member-init move one group id."""
    hits: dict[int, list[int]] = {}
    for k, points in enumerate(moves):
        for path, line in points:
            at = map_line(ops.get(path, []), line, False) + 1
            for i, p, a, b in dmi:
                if p == path and a <= at <= b:
                    hits.setdefault(i, []).append(k)
    _label(sites, hits, len(moves), "dmi")


def _apply(planner: Planner, cls: str, before: dict[Path, str]) -> None:
    """Apply a pass's edits; a file that fails is restored byte for byte and skipped with
    its partners."""
    if not planner.edits:
        return
    raw = {path: planner.docs[path].data for path in planner.edits}
    try:
        apply_edits(planner.edits, planner.docs)
        for path in planner.edits:
            format_changed(path, before[path])
        return
    except Exception:
        for path, data in raw.items():
            path.write_bytes(data)
    bad: set[Path] = set()
    for path, items in planner.edits.items():
        try:
            apply_edits({path: items}, planner.docs)
            format_changed(path, before[path])
        except Exception as exc:
            bad.add(path)
            planner.failed(planner.at(planner.docs[path], min(a for a, _, _ in items)), cls, exc)
    grew = True
    while grew:
        grew = False
        for pair in planner.partners:
            if pair & bad and not pair <= bad:
                bad |= pair
                grew = True
    for path in bad:
        if path in raw:
            path.write_bytes(raw[path])
        planner.edits.pop(path, None)
    planner.moves = [mv for mv in planner.moves if not any(f in bad for f, _ in mv)]


def run(graph: Path, root: Path, manifest: Path | None, apply: bool) -> int:
    pmi, dropped = run_tidy(graph, root, CHECKS[PMI])
    if dropped:
        print(f"member-init: dropped {len(dropped)} TU(s) that failed to compile: {', '.join(dropped)}")
    if not apply:
        counts: dict[tuple[str, Path], int] = defaultdict(int)
        for cls, diags in ((PMI, pmi), (DMI, run_tidy(graph, root, CHECKS[DMI])[0])):
            for d in diags:
                counts[(cls, d.repls[0].file.resolve().relative_to(root))] += 1
        for (cls, rel), n in sorted(counts.items()):
            print(f"{cls} {rel} {n}")
        return 0

    p1 = Planner(root)
    p1.plan_pmi(pmi)
    orig = {p: d.text for p, d in p1.docs.items()}
    raw = {p: d.data for p, d in p1.docs.items()}
    _apply(p1, PMI, orig)
    post1 = {p: p.read_text(errors="surrogateescape") for p in orig}

    p2 = Planner(root)
    p2.plan_dmi(run_tidy(graph, root, CHECKS[DMI])[0])
    for p, d in p2.docs.items():
        orig.setdefault(p, d.text)
        raw.setdefault(p, d.data)
        post1.setdefault(p, d.text)
    _apply(p2, DMI, post1)
    final = {p: p.read_text(errors="surrogateescape") for p in orig}

    sites: list[Site] = []
    dmi: list[tuple[int, Path, int, int]] = []
    pmi: list[tuple[int, Path, int, int]] = []
    for path in sorted(set(p1.edits) | set(p2.edits)):
        o, m, f = orig[path], post1[path], final[path]
        later = _opcodes(m, f)
        for tag, i1, i2, j1, j2 in _opcodes(o, m) if path in p1.edits else []:
            if tag == "equal":
                continue
            a, b = map_line(later, j1, False), map_line(later, j2, True)
            pmi.append((len(sites), path, i1, i2))
            sites.append(site(root, path, a, b, PMI, f))
        for j1, j2 in changed_ranges(m, f) if path in p2.edits else []:
            dmi.append((len(sites), path, j1 + 1, max(j2, j1 + 1)))
            sites.append(site(root, path, j1, j2, DMI, f))
    _group_ctor_moves(sites, pmi, p1.ctor_moves)
    _group_moves(sites, dmi, p2.moves, {p: _opcodes(post1[p], final[p]) for p in p2.edits})
    for s in p1.skips + p2.skips:
        if s.file not in final:
            rel = s.file.relative_to(root) if s.file.is_relative_to(root) else s.file
            sites.append(Site(rel, s.first + 1, s.last + 1, KIND, s.cls, s.reason, s.note))
            continue
        f = final[s.file]
        ops = _opcodes(post1[s.file], f)
        a, b = s.first, s.last + 1
        if s.cls == PMI:
            first = _opcodes(orig[s.file], post1[s.file])
            a, b = map_line(first, a, False), map_line(first, b, True)
        sites.append(site(root, s.file, map_line(ops, a, False), map_line(ops, b, True), s.cls, f,
                          skipped=s.reason, note=s.note))

    touched = sorted(set(p1.edits) | set(p2.edits))
    bad: set[Path] = set()
    if touched:
        stranded = check_hunks("".join(
            unified_diff(path.relative_to(root).as_posix(), orig[path], final[path])
            for path in touched
        ))
        bad = {(root / s.file).resolve() for s in stranded}
        grew = True
        while grew:
            grew = False
            for pair in p2.partners:
                if pair & bad and not pair <= bad:
                    bad |= pair
                    grew = True
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
    errors = p1.errors + p2.errors
    print(f"member-init: {applied} applied, {len(sites) - applied} skipped, {len(dropped)} TU(s) dropped, "
          f"{errors} internal error(s)")
    return 1 if errors and errors >= len(sites) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True, type=Path,
                    help="build dir holding compile_commands.json, or a parent of it")
    ap.add_argument("--repo", required=True, type=Path, help="repository root")
    ap.add_argument("--manifest", type=Path, help="manifest path (written only with --apply)")
    ap.add_argument("--apply", action="store_true", help="edit the working tree")
    from ioa.tidy import add_llvm_bin_option, use_llvm_bin

    add_llvm_bin_option(ap)
    args = ap.parse_args(argv)
    use_llvm_bin(args)
    root = args.repo.resolve()
    if not root.is_dir():
        ap.error(f"--repo {args.repo} is not a directory")
    graph = args.graph.resolve()
    if not (graph / "compile_commands.json").exists():
        graph = find_graph(graph, root.name)
    return run(graph, root, args.manifest, args.apply)


if __name__ == "__main__":
    sys.exit(main())
