#!/usr/bin/env python3
"""ab-compare.py — compare two time-ctest.sh summaries (A=baseline, B=variant).

Emits a per-test table with the A/B delta AND a noise-aware verdict: when the
pooled run-to-run variation (CV) is comparable to or larger than the measured
delta, the result is flagged INCONCLUSIVE rather than reported as a speedup or
regression. This guards against reading signal out of shared-host timing noise.

Usage:
  ab-compare.py <A_summary.tsv> <B_summary.tsv> [--a-label NAME] [--b-label NAME]

Input columns (from time-ctest.sh): test n min median mean stdev cv_pct
"""
import sys, argparse

def load(path):
    d = {}
    with open(path) as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("\t")
            if len(f) != 7 or f[0] == "test":
                continue
            d[f[0]] = dict(n=int(f[1]), min=float(f[2]), median=float(f[3]),
                           mean=float(f[4]), stdev=float(f[5]), cv=float(f[6]))
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--a-label", default="A"); ap.add_argument("--b-label", default="B")
    g = ap.parse_args()
    A, B = load(g.a), load(g.b)
    tests = sorted(set(A) & set(B))
    only = sorted(set(A) ^ set(B))

    print(f"# A={g.a_label}  B={g.b_label}   (B vs A; negative Δ% = B faster)")
    print(f"{'test':<46}{'A.med':>8}{'B.med':>8}{'Δ%med':>8}{'maxCV%':>8}  verdict")
    print("-" * 100)
    for t in tests:
        a, b = A[t], B[t]
        dmed = 100 * (b["median"] - a["median"]) / a["median"] if a["median"] else 0.0
        maxcv = max(a["cv"], b["cv"])
        # Noise-aware verdict: effect must clear the noise floor to count.
        if abs(dmed) < maxcv:
            verdict = "inconclusive (Δ<noise)"
        elif dmed < 0:
            verdict = "faster"
        else:
            verdict = "SLOWER"
        print(f"{t:<46}{a['median']:>8.2f}{b['median']:>8.2f}{dmed:>+7.1f}%{maxcv:>7.1f}%  {verdict}")
    print("-" * 100)
    # Aggregate over tests whose noise floor is small enough to trust (CV<8%).
    stable = [t for t in tests if max(A[t]["cv"], B[t]["cv"]) < 8.0]
    if stable:
        ta = sum(A[t]["median"] for t in stable); tb = sum(B[t]["median"] for t in stable)
        print(f"low-noise subset (maxCV<8%): {len(stable)} tests, "
              f"A={ta:.2f}s B={tb:.2f}s  Δ={100*(tb-ta)/ta:+.1f}%")
    if only:
        print(f"# present on only one side (excluded): {', '.join(only)}")

if __name__ == "__main__":
    main()
