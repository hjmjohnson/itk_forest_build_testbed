#!/usr/bin/env python3
"""Compare two ITK builds: warnings/errors and CTest status.

Consumes the build log + CTest Test.xml from each of two ITK build trees
(typically release-5.4 vs latest main) and emits a Markdown comparison:
build-warning deltas (new/fixed/common), build errors, and per-test status
changes (regressions, fixes, new/removed/flaky).

Usage:
  analyze_results.py \
    --label-a release-5.4 --log-a A.buildlog --xml-a A/Test.xml \
    --label-b main         --log-b B.buildlog --xml-b B/Test.xml \
    [--ref-a SHA] [--ref-b SHA] --out report.md
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET

# /abs/path/file.cxx:123:45: warning: text [-Wflag]   (line/col optional)
_DIAG = re.compile(r"^(?P<path>[^\s:][^:]*):(?P<line>\d+):(?:(?P<col>\d+):)?\s+"
                   r"(?P<kind>warning|error):\s+(?P<msg>.*)$")


def parse_build_log(path):
    """Return {'warnings': {norm: count}, 'errors': [lines], 'raw_warn': N}."""
    warnings, errors, raw_warn = {}, [], 0
    if not path or not os.path.exists(path):
        return {"warnings": warnings, "errors": errors, "raw_warn": 0, "missing": True}
    with open(path, errors="replace") as fh:
        for line in fh:
            m = _DIAG.match(line.rstrip("\n"))
            if not m:
                continue
            base = os.path.basename(m.group("path"))
            msg = m.group("msg").strip()
            if m.group("kind") == "warning":
                raw_warn += 1
                # Normalize: basename + message (drops line/col so the same
                # warning at a shifted line still matches between refs).
                key = f"{base}: {msg}"
                warnings[key] = warnings.get(key, 0) + 1
            else:
                errors.append(f"{base}:{m.group('line')}: {msg}")
    return {"warnings": warnings, "errors": errors, "raw_warn": raw_warn, "missing": False}


def parse_ctest_xml(path):
    """Return {test_name: status} where status in passed/failed/notrun/other."""
    tests = {}
    if not path or not os.path.exists(path):
        return tests
    root = ET.parse(path).getroot()
    for t in root.iter("Test"):
        status = t.get("Status")  # passed | failed | notrun
        name_el = t.find("Name")
        if name_el is not None and status:
            tests[name_el.text] = status
    return tests


def _flag(msg):
    m = re.search(r"\[-W[^\]]+\]", msg)
    return m.group(0) if m else "(no flag)"


def warning_section(a, la, b, lb):
    aw, bw = a["warnings"], b["warnings"]
    only_a = sorted(set(aw) - set(bw))
    only_b = sorted(set(bw) - set(aw))
    common = set(aw) & set(bw)
    out = ["## Build warnings\n"]
    out.append(f"| | {la} | {lb} |")
    out.append("|---|---:|---:|")
    out.append(f"| total warning lines | {a['raw_warn']} | {b['raw_warn']} |")
    out.append(f"| unique warnings | {len(aw)} | {len(bw)} |")
    out.append(f"| common unique | {len(common)} | {len(common)} |")
    out.append(f"| only here | {len(only_a)} | {len(only_b)} |\n")
    # group the new-in-B warnings by flag (the regressions main introduced)
    if only_b:
        out.append(f"<details>\n<summary>New in {lb} ({len(only_b)})</summary>\n")
        byflag = {}
        for w in only_b:
            byflag.setdefault(_flag(w), []).append(w)
        for fl in sorted(byflag):
            out.append(f"\n**{fl}** ({len(byflag[fl])})")
            for w in byflag[fl][:50]:
                out.append(f"- {w}")
        out.append("\n</details>\n")
    if only_a:
        out.append(f"<details>\n<summary>Only in {la} — fixed/absent in {lb} ({len(only_a)})</summary>\n")
        for w in only_a[:100]:
            out.append(f"- {w}")
        out.append("\n</details>\n")
    return "\n".join(out)


def error_section(a, la, b, lb):
    out = ["## Build errors\n"]
    out.append(f"| | {la} | {lb} |")
    out.append("|---|---:|---:|")
    out.append(f"| error lines | {len(a['errors'])} | {len(b['errors'])} |\n")
    for lbl, d in ((la, a), (lb, b)):
        if d["errors"]:
            out.append(f"<details>\n<summary>{lbl} errors ({len(d['errors'])})</summary>\n")
            out += [f"- {e}" for e in d["errors"][:100]]
            out.append("\n</details>\n")
    return "\n".join(out)


def test_section(ta, la, tb, lb):
    names = sorted(set(ta) | set(tb))
    regress, fixes, newt, removed, flaky = [], [], [], [], []
    for n in names:
        sa, sb = ta.get(n), tb.get(n)
        if sa is None:
            newt.append((n, sb))
        elif sb is None:
            removed.append((n, sa))
        elif sa != sb:
            if sa == "passed" and sb == "failed":
                regress.append(n)
            elif sa == "failed" and sb == "passed":
                fixes.append(n)
            else:
                flaky.append((n, sa, sb))

    def cnt(t, s):
        return sum(1 for v in t.values() if v == s)

    out = ["## Tests (CTest)\n"]
    out.append(f"| status | {la} | {lb} |")
    out.append("|---|---:|---:|")
    for s in ("passed", "failed", "notrun"):
        out.append(f"| {s} | {cnt(ta, s)} | {cnt(tb, s)} |")
    out.append(f"| total | {len(ta)} | {len(tb)} |\n")
    out.append(f"- **Regressions ({la}→{lb}, passed→failed): {len(regress)}**")
    out.append(f"- Fixes (failed→passed): {len(fixes)}")
    out.append(f"- Only in {la} (removed): {len(removed)}")
    out.append(f"- Only in {lb} (new): {len(newt)}")
    out.append(f"- Other status changes: {len(flaky)}\n")
    if regress:
        out.append("<details>\n<summary>⚠ Regressions (pass→fail)</summary>\n")
        out += [f"- {n}" for n in regress]
        out.append("\n</details>\n")
    for title, items in ((f"Fixes (fail→pass)", [n for n in fixes]),
                         (f"Other status changes", [f"{n}: {a}→{b}" for n, a, b in flaky]),
                         (f"New in {lb}", [f"{n} [{s}]" for n, s in newt]),
                         (f"Only in {la}", [f"{n} [{s}]" for n, s in removed])):
        if items:
            out.append(f"<details>\n<summary>{title} ({len(items)})</summary>\n")
            out += [f"- {x}" for x in items[:200]]
            out.append("\n</details>\n")
    return "\n".join(out), len(regress)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--label-a", required=True)
    p.add_argument("--label-b", required=True)
    p.add_argument("--log-a"); p.add_argument("--log-b")
    p.add_argument("--xml-a"); p.add_argument("--xml-b")
    p.add_argument("--ref-a", default="?"); p.add_argument("--ref-b", default="?")
    p.add_argument("--out", required=True)
    a = p.parse_args()

    ba, bb = parse_build_log(a.log_a), parse_build_log(a.log_b)
    ta, tb = parse_ctest_xml(a.xml_a), parse_ctest_xml(a.xml_b)
    tests_md, n_regress = test_section(ta, a.label_a, tb, a.label_b)

    head = [f"# ITK comparison: {a.label_a} vs {a.label_b}\n",
            f"- **{a.label_a}**: `{a.ref_a}`",
            f"- **{a.label_b}**: `{a.ref_b}`\n",
            f"**Headline:** {len(bb['errors'])} build error(s) in {a.label_b}; "
            f"{n_regress} test regression(s) ({a.label_a}→{a.label_b}); "
            f"{max(0, bb['raw_warn'] - ba['raw_warn'])} net new warning line(s).\n"]
    report = "\n".join(head) + "\n" + \
        error_section(ba, a.label_a, bb, a.label_b) + "\n" + \
        warning_section(ba, a.label_a, bb, a.label_b) + "\n" + tests_md
    with open(a.out, "w") as fh:
        fh.write(report)
    print(a.out)
    # Non-zero exit if main introduced errors or test regressions.
    return 1 if (bb["errors"] or n_regress) else 0


if __name__ == "__main__":
    sys.exit(main())
