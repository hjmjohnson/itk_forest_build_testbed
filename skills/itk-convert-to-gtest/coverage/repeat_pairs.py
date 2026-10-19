#!/usr/bin/env python3
"""Rerun selected old/new test pairs several times and report stable losses.

A line counts as lost only if the original test covered it in every run and
the converted test covered it in none. Lines that come and go between runs of
the same test vary on their own and are not attributable to the conversion.

Usage: repeat_pairs.py <inventory.json> <before-build> <before-src> <after-build>
                       <after-src> <out-dir> <runs> <legacy_test>...
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from per_test_coverage import ctest_commands, driver_overhead, run_and_export  # noqa: E402


def main():
    inv, bb, bs, ab, asrc, out, runs, *names = sys.argv[1:]
    runs, out = int(runs), Path(out)
    inventory = {e["legacy_test"]: e for e in json.loads(Path(inv).read_text())}
    bcmd, acmd = ctest_commands(bb), ctest_commands(ab)
    report = {}
    for name in names:
        e = inventory[name]
        text = (Path(asrc) / e["new_file"]).read_text()
        cases = [f"{s}.{c}" for s, c in re.findall(r"^\s*TEST(?:_F)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)", text, re.M)]
        overhead = driver_overhead(bcmd[name][0], bs, out / name / "overhead")
        before_runs, after_runs = [], []
        for r in range(runs):
            before_runs.append(run_and_export(bb, bs, [name], bcmd, out / name / f"before{r}")[1])
            after_runs.append(run_and_export(ab, asrc, cases, acmd, out / name / f"after{r}")[1])
        files = set().union(*before_runs)
        stable_lost, varying = {}, {}
        for f in files:
            always_before = set.intersection(*[b.get(f, set()) for b in before_runs])
            ever_before = set.union(*[b.get(f, set()) for b in before_runs])
            ever_after = set.union(*[a.get(f, set()) for a in after_runs])
            lost = always_before - ever_after - overhead.get(f, set())
            vary = (ever_before - always_before) - ever_after - overhead.get(f, set())
            if lost:
                stable_lost[f] = sorted(lost)
            if vary:
                varying[f] = sorted(vary)
        report[name] = {"stable_lost": stable_lost, "varying_only": varying}
        print(f"{name}: stable lost {sum(map(len, stable_lost.values()))} lines in {len(stable_lost)} files;"
              f" varying {sum(map(len, varying.values()))}", flush=True)
        for f, ls in stable_lost.items():
            print(f"    {f}: {ls}")
    (out / "repeat_pairs.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
