#!/usr/bin/env python3
"""Per-conversion coverage parity: old CTest alone vs its GoogleTest alone.

For each conversion, runs the original CTest by itself in the before build and
the converted GoogleTest cases (exactly the TEST()s in the new file) by
themselves in the after build, each with its own raw profile, exports library
line coverage from the driver that ran it, and checks that every line covered
by the original is also covered by the conversion.

Usage: per_test_coverage.py <inventory.json> <before-build> <before-src>
                            <after-build> <after-src> <out-dir> [jobs]
"""

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

XC = Path("/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin")
IGNORE = "(/test/|/ThirdParty/|/_deps/|-build/)"


def ctest_commands(build):
    """Map ctest name -> argv, from ctest's JSON listing."""
    r = subprocess.run(
        ["ctest", "--test-dir", build, "--show-only=json-v1"], capture_output=True, text=True, check=True
    )
    return {t["name"]: t.get("command", []) for t in json.loads(r.stdout)["tests"]}


TEST_INFRASTRUCTURE = "Modules/Core/TestKernel/"


def export_lines(raws, binaries, src, workdir):
    """Covered library lines (TestKernel excluded) from raw profiles of the given binaries."""
    covered = {}
    if not raws or not binaries:
        return covered
    prof = workdir / "merged.profdata"
    subprocess.run([XC / "llvm-profdata", "merge", "-sparse", *raws, "-o", prof], check=True)
    root = str(Path(src).resolve()) + "/"
    for b in binaries:
        out = subprocess.run(
            [XC / "llvm-cov", "export", "-format=lcov", "-instr-profile", prof, b, f"-ignore-filename-regex={IGNORE}"],
            capture_output=True,
            text=True,
        ).stdout
        current = None
        for line in out.splitlines():
            if line.startswith("SF:"):
                p = line[3:]
                current = p[len(root):] if p.startswith(root) else p
                if current.startswith(TEST_INFRASTRUCTURE):
                    current = None
            elif line.startswith("DA:") and current:
                n, c = line[3:].split(",")[:2]
                if int(c) > 0:
                    covered.setdefault(current, set()).add(int(n))
    for raw in raws:
        raw.unlink()
    return covered


def run_and_export(build, src, names, commands, workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LLVM_PROFILE_FILE=str(workdir / "%p.profraw"))
    regex = "|".join(f"^{re.escape(n)}$" for n in names)
    r = subprocess.run(
        ["ctest", "--test-dir", build, "-R", regex, "--output-on-failure"], env=env, capture_output=True, text=True
    )
    m = re.search(r"(\d+) tests failed out of (\d+)", r.stdout)
    status = {"ran": int(m.group(2)) if m else 0, "failed": int(m.group(1)) if m else None}
    binaries = sorted({commands[n][0] for n in names if commands.get(n)})
    return status, export_lines(list(workdir.glob("*.profraw")), binaries, src, workdir)


def driver_overhead(binary, src, workdir):
    """Lines a legacy driver covers before dispatching to any test.

    The generated driver main calls ProcessArgumentsAndRegisterRequiredFactories
    before looking up the test name, so an unknown name runs exactly that
    startup code, prints the test list, and exits.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LLVM_PROFILE_FILE=str(workdir / "%p.profraw"))
    subprocess.run([binary, "__no_such_test__"], env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    return export_lines(list(workdir.glob("*.profraw")), [binary], src, workdir)


def main():
    inv, bb, bs, ab, asrc, out = sys.argv[1:7]
    jobs = int(sys.argv[7]) if len(sys.argv) > 7 else 4
    out = Path(out)
    shutil.rmtree(out, ignore_errors=True)
    inventory = json.loads(Path(inv).read_text())
    before_cmds, after_cmds = ctest_commands(bb), ctest_commands(ab)
    overheads = {}
    for b in sorted({before_cmds[e["legacy_test"]][0] for e in inventory if before_cmds.get(e["legacy_test"])}):
        overheads[b] = driver_overhead(b, bs, out / "overhead" / Path(b).name)
    (out).mkdir(parents=True, exist_ok=True)
    (out / "driver_overhead_lines.json").write_text(
        json.dumps({Path(b).name: sum(len(v) for v in o.values()) for b, o in overheads.items()}, indent=1)
    )

    def one(e):
        new_text = (Path(asrc) / e["new_file"]).read_text()
        cases = re.findall(r"^\s*TEST(?:_F)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)", new_text, re.M)
        after_names = [f"{s}.{c}" for s, c in cases]
        missing_after = [n for n in after_names if n not in after_cmds]
        bstat, bcov = run_and_export(bb, bs, [e["legacy_test"]], before_cmds, out / "work" / e["legacy_test"] / "before")
        astat, acov = run_and_export(ab, asrc, after_names, after_cmds, out / "work" / e["legacy_test"] / "after")
        overhead = overheads.get(before_cmds.get(e["legacy_test"], [""])[0], {})
        lost = {f: sorted(lines - acov.get(f, set()) - overhead.get(f, set())) for f, lines in bcov.items()}
        lost = {f: v for f, v in lost.items() if v}
        res = {
            "legacy_test": e["legacy_test"],
            "stream": e["stream"],
            "gtest_cases": after_names,
            "gtest_cases_not_registered": missing_after,
            "before": bstat,
            "after": astat,
            "covered_before": sum(len(v) for v in bcov.values()),
            "covered_after": sum(len(v) for v in acov.values()),
            "lost_lines": sum(len(v) for v in lost.values()),
            "lost": lost,
        }
        verdict = "OK" if not lost and bstat["failed"] == 0 and astat["failed"] == 0 and astat["ran"] else "CHECK"
        res["verdict"] = verdict
        print(
            f"{verdict} {e['legacy_test']}: before {res['covered_before']} lines, "
            f"after {res['covered_after']}, lost {res['lost_lines']}",
            flush=True,
        )
        return res

    with ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(one, inventory))
    (out / "per_test_coverage.json").write_text(json.dumps(results, indent=1))
    bad = [r for r in results if r["verdict"] != "OK"]
    print(f"{len(results)} conversions, {len(bad)} need a look")


if __name__ == "__main__":
    main()
