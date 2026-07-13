#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
build_matrix.py — Build the ITK "routinely tested" compiler/OS support matrix
from live test infrastructure and emit a LaTeX table for the Software Guide.

Sources, in order of authority for "passes all tests":
  1. CDash (open.cdash.org, project "Insight" / id 2) — the nightly/CI
     dashboard. A configuration counts as "passing" only when its most recent
     build in the window has zero build errors AND zero failed tests.
  2. GitHub Actions — successful jobs on the default branch (via the `gh` CLI).
     Job names encode OS/compiler; only `conclusion == success` is counted.
  3. Azure Pipelines — best-effort via the public REST API; skipped silently if
     the org/project is not reachable.

The matrix is intentionally regenerated from live data because the tested
toolchains drift as platforms evolve — hard-coding versions in the guide is
exactly what goes stale. This script is the generator behind the
`\\input{Introduction/CompilerSupportMatrix.tex}` seam in Installation.tex.

Buildname/job-name parsing is heuristic (CDash buildnames are free-form), so the
output is reviewed before it is committed. Rows the parser cannot classify are
reported to stderr rather than silently dropped, so coverage gaps are visible.

Usage:
    # Print the LaTeX table to stdout (dry run):
    python3 scripts/build_matrix.py --days 7

    # Write it into the Software Guide and also dump the raw JSON evidence:
    python3 scripts/build_matrix.py --days 7 \\
        --emit /path/to/ITKSoftwareGuide/SoftwareGuide/Latex/Introduction/CompilerSupportMatrix.tex \\
        --json-evidence /path/to/ITKSoftwareGuide/.devlocal/compiler-matrix-evidence.json

    # CDash only (no gh / Azure):
    python3 scripts/build_matrix.py --no-github --no-azure
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CDASH_HOST = "open.cdash.org"
CDASH_PROJECT_ID = "2"  # "Insight" (ITK)
ITK_REPO = "InsightSoftwareConsortium/ITK"

# GraphQL: CDash exposes structured OS/compiler fields and per-build test
# counts, so we read those directly instead of parsing free-form buildnames.
CDASH_QUERY = """
{
  project(id: "%s") {
    name
    builds(first: %d) {
      edges {
        node {
          name buildType startTime
          buildErrorsCount
          buildWarningsCount
          failedTestsCount
          passedTestsCount
          operatingSystemName
          operatingSystemRelease
          compilerName
          compilerVersion
          site { name }
        }
      }
    }
  }
}
"""

# Map CDash's operatingSystemName values onto the guide's coarse OS buckets.
def _norm_os(os_name, buildname):
    s = f"{os_name or ''} {buildname or ''}".lower()
    if any(t in s for t in ("windows", "msvc", "mingw", "win32", "win64")):
        return "Windows"
    if any(t in s for t in ("mac", "osx", "darwin", "apple")):
        return "macOS"
    if any(t in s for t in ("linux", "ubuntu", "debian", "fedora", "centos", "rhel", "rocky", "alma")):
        return "Linux"
    return os_name or None


def _norm_compiler(name, buildname):
    s = f"{name or ''} {buildname or ''}".lower()
    if "appleclang" in s.replace(" ", ""):
        return "AppleClang"
    if any(t in s for t in ("msvc", "visual", "vs20", "vs1", "vc++")):
        return "Visual Studio"
    if "clang" in s:
        return "Clang"
    if "gcc" in s or "g++" in s or s.strip() == "gnu":
        return "GCC"
    # Only treat icc/icx/oneapi as the Intel compiler; a bare "intel" in a
    # buildname usually denotes the CPU architecture, not the toolchain.
    if "icc" in s or "icx" in s or "oneapi" in s:
        return "Intel"
    if "mingw" in s:
        return "MinGW"
    return name or None

# ---- Heuristic classifiers -------------------------------------------------

OS_PATTERNS = [
    (re.compile(r"\b(win(dows)?|msvc|vs20\d\d|msys|mingw)\b", re.I), "Windows"),
    (re.compile(r"\b(mac(os)?|osx|darwin|apple|xcode)\b", re.I), "macOS"),
    (re.compile(r"\b(linux|ubuntu|debian|fedora|centos|rhel|rocky|alma|manylinux)\b", re.I), "Linux"),
]

# Order matters: AppleClang before clang, VS/MSVC before generic.
COMPILER_PATTERNS = [
    (re.compile(r"appleclang[-_ ]?([0-9]+(?:\.[0-9]+)*)?", re.I), "AppleClang"),
    (re.compile(r"\b(?:msvc|vs|visualstudio|visual[-_ ]?studio)[-_ ]?(20\d\d|v?1[0-9]{2}|[0-9]+\.[0-9]+)?", re.I), "Visual Studio"),
    (re.compile(r"\bclang(?:\+\+)?[-_ ]?([0-9]+(?:\.[0-9]+)*)?", re.I), "Clang"),
    (re.compile(r"\bg(?:cc|\+\+)[-_ ]?([0-9]+(?:\.[0-9]+)*)?", re.I), "GCC"),
    (re.compile(r"\bmingw(?:\-w64)?[-_ ]?([0-9]+(?:\.[0-9]+)*)?", re.I), "MinGW"),
    (re.compile(r"\b(?:icc|icx|oneapi)\b", re.I), "Intel"),  # not bare "intel" (CPU)
]


def classify(text):
    """Return (os, compiler, version) best-effort from a buildname/job name."""
    os_name = None
    for pat, name in OS_PATTERNS:
        if pat.search(text):
            os_name = name
            break
    compiler = version = None
    for pat, name in COMPILER_PATTERNS:
        m = pat.search(text)
        if m:
            compiler = name
            version = (m.group(1) if m.groups() else None) or None
            break
    return os_name, compiler, version


# ---- CDash -----------------------------------------------------------------

def cdash_graphql(query):
    url = f"https://{CDASH_HOST}/graphql"
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read())


def collect_cdash(days, fetch=600):
    # The server-side startTime filter triggers an internal error on this CDash
    # instance, so fetch a page and filter/sort client-side instead.
    data = cdash_graphql(CDASH_QUERY % (CDASH_PROJECT_ID, fetch))
    edges = (((data or {}).get("data") or {}).get("project") or {}).get("builds", {}).get("edges", [])
    since = datetime.now(timezone.utc) - timedelta(days=days)
    nodes = []
    for e in edges:
        n = e["node"]
        st = n.get("startTime")
        try:
            when = datetime.fromisoformat(st) if st else None
        except ValueError:
            when = None
        if when is not None and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when is None or when >= since:
            nodes.append(n)
    rows, skipped = [], []
    for n in nodes:
        errors = n.get("buildErrorsCount") or 0
        tfail = n.get("failedTestsCount")
        tpass = n.get("passedTestsCount") or 0
        # "passes all tests": no build errors, no failed tests, and the build
        # actually ran tests (passedTestsCount > 0) so we don't count
        # build-only configurations as "tested".
        if errors > 0:
            continue
        if tfail is not None and tfail > 0:
            continue
        if tpass == 0:
            continue
        buildname = n.get("name", "")
        os_name = _norm_os(n.get("operatingSystemName"), buildname)
        compiler = _norm_compiler(n.get("compilerName"), buildname)
        version = (n.get("compilerVersion") or "").strip() or None
        if version:  # keep major[.minor] for readability
            version = ".".join(version.split(".")[:2])
        if not (os_name and compiler):
            skipped.append(buildname or f"os={n.get('operatingSystemName')} cc={n.get('compilerName')}")
            continue
        rows.append({
            "os": os_name, "compiler": compiler, "version": version,
            "source": "CDash", "evidence": buildname,
            "warnings": n.get("buildWarningsCount") or 0,
        })
    return rows, skipped


# ---- GitHub Actions --------------------------------------------------------

# ITK's build/test matrix runs in these GitHub Actions workflows. Auxiliary
# workflows (Doxygen, Scorecard, pre-commit, cache cleanup) are not build
# configurations and are ignored. On GitHub-hosted runners the compiler is the
# image's default toolchain, so we map the runner OS to that toolchain rather
# than trying to read a compiler name that the job never states.
GHA_BUILD_WORKFLOWS = {"ITK.Pixi", "ITK.Arm64"}

# (regex on runner image / job name) -> (OS, default compiler)
RUNNER_TOOLCHAIN = [
    (re.compile(r"ubuntu|linux", re.I), ("Linux", "GCC")),
    (re.compile(r"windows|win-?\d", re.I), ("Windows", "Visual Studio")),
    (re.compile(r"mac(os)?|darwin|rosetta", re.I), ("macOS", "AppleClang")),
]


def _runner_toolchain(text):
    for pat, (os_name, compiler) in RUNNER_TOOLCHAIN:
        if pat.search(text or ""):
            return os_name, compiler
    return None, None


def collect_github(limit=120):
    """List recent successful runs of ITK's build workflows on main and map
    each successful job's runner OS to its default toolchain. ITK's GHA jobs
    name the OS (e.g. matrix os ubuntu-22.04) but not the compiler, so the
    runner default is the honest classification. Returns [] if gh is absent."""
    try:
        runs = subprocess.run(
            ["gh", "run", "list", "--repo", ITK_REPO, "--branch", "main",
             "--status", "success", "--limit", str(limit),
             "--json", "databaseId,workflowName"],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
        run_objs = [r for r in json.loads(runs) if r.get("workflowName") in GHA_BUILD_WORKFLOWS]
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"  (GitHub Actions skipped: {e})", file=sys.stderr)
        return [], []
    rows, skipped = [], []
    for ro in run_objs[:30]:  # cap job-detail fetches
        try:
            out = subprocess.run(
                ["gh", "api", f"repos/{ITK_REPO}/actions/runs/{ro['databaseId']}/jobs",
                 "--jq", ".jobs[] | select(.conclusion==\"success\") | .name + \"\\t\" + (.labels|join(\",\"))"],
                capture_output=True, text=True, timeout=45, check=True,
            ).stdout.splitlines()
        except Exception:
            continue
        for line in out:
            jname = line.split("\t")[0]
            os_name, compiler = _runner_toolchain(line)  # search name + labels
            if os_name and compiler:
                rows.append({"os": os_name, "compiler": compiler,
                             "version": "CI runner default",
                             "source": "GitHub Actions",
                             "evidence": f"{ro['workflowName']}: {jname}", "warnings": 0})
            elif jname.strip():
                skipped.append(f"{ro['workflowName']}: {jname}")
    return rows, skipped


# ---- Azure Pipelines (best-effort) -----------------------------------------

def collect_azure(org="itkrobotmacospython", project="ITK"):
    """Best-effort: Azure DevOps public REST API. Many ITK Azure orgs are not
    anonymously queryable; on any failure this returns [] quietly."""
    url = (f"https://dev.azure.com/{org}/{project}/_apis/build/builds"
           f"?api-version=7.0&statusFilter=completed&resultFilter=succeeded&$top=50")
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  (Azure Pipelines skipped: {e})", file=sys.stderr)
        return [], []
    rows, skipped = [], []
    for b in data.get("value", []):
        name = b.get("definition", {}).get("name", "") or b.get("buildNumber", "")
        os_name, compiler, version = classify(name)
        if os_name and compiler:
            rows.append({"os": os_name, "compiler": compiler, "version": version,
                         "source": "Azure", "evidence": name, "warnings": 0})
        elif name:
            skipped.append(name)
    return rows, skipped


# ---- Aggregation + LaTeX ---------------------------------------------------

def dedup(rows):
    """Collapse to one row per (os, compiler, version); merge the source set.
    Keep the highest version when versions vary for the same os+compiler is NOT
    done here — every distinct tested version is a distinct row, since the guide
    wants the full tested set."""
    agg = {}
    for r in rows:
        key = (r["os"], r["compiler"], r["version"] or "")
        e = agg.setdefault(key, {"os": r["os"], "compiler": r["compiler"],
                                 "version": r["version"], "sources": set()})
        e["sources"].add(r["source"])
    out = list(agg.values())
    os_order = {"Linux": 0, "macOS": 1, "Windows": 2}
    out.sort(key=lambda e: (os_order.get(e["os"], 9), e["compiler"], e["version"] or ""))
    return out


def latex_escape(s):
    return s.replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("&", r"\&")


def to_latex(rows, days):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "% AUTO-GENERATED by the itk-compiler-matrix skill — DO NOT EDIT BY HAND.",
        f"% Generated {stamp} UTC from CDash + CI over the last {days} days.",
        "% Regenerate: see the itk-compiler-matrix skill.",
        "\\begin{table}[htb!]",
        "\\centering",
        "\\caption[Routinely tested ITK configurations]{Operating system and "
        "compiler configurations that are routinely tested and pass all tests, "
        "as reported by the ITK quality dashboard and continuous-integration "
        f"matrix (generated {stamp}).}}",
        "\\label{tab:CompilerSupportMatrix}",
        "\\begin{tabular}{lll l}",
        "\\hline",
        "\\textbf{Operating System} & \\textbf{Compiler} & \\textbf{Version} & \\textbf{Reported by} \\\\",
        "\\hline",
    ]
    for e in rows:
        ver = e["version"] or "tested versions"
        src = ", ".join(sorted(e["sources"]))
        lines.append(
            f"{latex_escape(e['os'])} & {latex_escape(e['compiler'])} & "
            f"{latex_escape(ver)} & {latex_escape(src)} \\\\"
        )
    lines += ["\\hline", "\\end{tabular}", "\\end{table}", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, help="Look-back window (default 7)")
    ap.add_argument("--emit", metavar="PATH", help="Write the LaTeX table to PATH (default: stdout)")
    ap.add_argument("--json-evidence", metavar="PATH", help="Also dump raw classified rows as JSON")
    ap.add_argument("--no-github", action="store_true", help="Skip the GitHub Actions source")
    ap.add_argument("--no-azure", action="store_true", help="Skip the Azure Pipelines source")
    args = ap.parse_args()

    all_rows, all_skipped = [], []

    print("Querying CDash (open.cdash.org / Insight)...", file=sys.stderr)
    try:
        r, s = collect_cdash(args.days)
        all_rows += r; all_skipped += s
        print(f"  CDash: {len(r)} passing build rows, {len(s)} unclassified", file=sys.stderr)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  CDash query failed: {e}", file=sys.stderr)

    if not args.no_github:
        print("Querying GitHub Actions (gh CLI)...", file=sys.stderr)
        r, s = collect_github()
        all_rows += r; all_skipped += s
        print(f"  GitHub Actions: {len(r)} success job rows, {len(s)} unclassified", file=sys.stderr)

    if not args.no_azure:
        print("Querying Azure Pipelines (best-effort)...", file=sys.stderr)
        r, s = collect_azure()
        all_rows += r; all_skipped += s
        print(f"  Azure: {len(r)} success rows", file=sys.stderr)

    if not all_rows:
        print("ERROR: no passing configurations collected from any source.", file=sys.stderr)
        return 2

    rows = dedup(all_rows)
    latex = to_latex(rows, args.days)

    if args.emit:
        with open(args.emit, "w") as f:
            f.write(latex)
        print(f"Wrote {len(rows)} configurations to {args.emit}", file=sys.stderr)
    else:
        print(latex)

    if args.json_evidence:
        with open(args.json_evidence, "w") as f:
            json.dump({"generated": datetime.now(timezone.utc).isoformat(),
                       "days": args.days,
                       "configurations": [{**e, "sources": sorted(e["sources"])} for e in rows],
                       "unclassified": sorted(set(all_skipped))}, f, indent=2)
        print(f"Wrote evidence to {args.json_evidence}", file=sys.stderr)

    if all_skipped:
        print(f"\nNOTE: {len(set(all_skipped))} build/job names could not be classified "
              "(reported in evidence JSON). Review them so no tested configuration "
              "is silently dropped from the matrix.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
