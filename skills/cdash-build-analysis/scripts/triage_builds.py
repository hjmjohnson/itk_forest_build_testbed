#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
triage_builds.py — Single-command CDash nightly warning triage.

Chains list_builds and get_build_warnings to produce a deduplicated,
actionable summary of warnings grouped by flag and source file.
Auto-detects the CDash project from CTestConfig.cmake.

Exit codes:
  0  Success (results printed, possibly empty)
  2  Network or API error
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import urllib.error
import urllib.request

from cdash_config import detect_cdash_config
from get_build_warnings import extract_flag, fetch_entries

QUERY_TEMPLATE = """
{{
  project(id: "{project_id}") {{
    name
    builds(first: {limit}, filters: {{ all: [
      {{ contains: {{ stamp: "{build_type}" }} }}
      {{ gt: {{ startTime: "{since}" }} }}
    ]}}) {{
      edges {{
        node {{
          id name stamp buildType buildWarningsCount buildErrorsCount startTime
          site {{ name }}
        }}
      }}
    }}
  }}
}}
"""


def graphql(url: str, query: str) -> dict:
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"Error: network request failed: {e}", file=sys.stderr)
        sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="triage_builds.py",
        description="Triage CDash warnings into an actionable summary (auto-detects project).",
        epilog=(
            "Examples:\n"
            "  python3 scripts/triage_builds.py                    # auto-detect project\n"
            "  python3 scripts/triage_builds.py --since 48\n"
            "  python3 scripts/triage_builds.py --json\n"
            "  python3 scripts/triage_builds.py --host open.cdash.org --project Insight --project-id 2\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--type", default="Nightly", metavar="TYPE", help="Build type (default: Nightly)"
    )
    parser.add_argument(
        "--since",
        type=float,
        default=None,
        metavar="HOURS",
        help="Builds from the last N hours (default: since nightly start)",
    )
    parser.add_argument(
        "--limit-builds",
        type=int,
        default=25,
        metavar="N",
        help="Max builds to inspect (default: 25)",
    )
    parser.add_argument(
        "--limit-warnings",
        type=int,
        default=200,
        metavar="N",
        help="Max warnings per build (default: 200)",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    parser.add_argument("--host", default=None, help="CDash host (override auto-detect)")
    parser.add_argument("--project", default=None, help="CDash project name (override)")
    parser.add_argument("--project-id", default=None, help="CDash project ID (override)")
    parser.add_argument("--source-dir", default=None, help="Source dir for auto-detect")
    args = parser.parse_args()

    # Resolve CDash config
    config = detect_cdash_config(args.source_dir)
    host = args.host or config["host"]
    project = args.project or config["project"]
    project_id = args.project_id or config["project_id"]
    graphql_url = f"https://{host}/graphql" if host else None

    if not all([graphql_url, project_id]):
        print(
            "Error: Could not detect CDash project. Use --host/--project/--project-id.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"CDash: https://{host}/index.php?project={project}  (id={project_id})", file=sys.stderr)

    # Time window
    if args.since is None:
        NIGHTLY_START = "01:00:00+00:00"
        today = datetime.now(UTC).date()
        dt = datetime.fromisoformat(f"{today.isoformat()}T{NIGHTLY_START}")
        now_utc = datetime.now(UTC)
        since_dt = dt if now_utc >= dt else dt - timedelta(days=1)
    else:
        since_dt = datetime.now(UTC) - timedelta(hours=args.since)

    since_str = since_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Step 1: List builds with warnings
    query = QUERY_TEMPLATE.format(
        project_id=project_id, limit=500, build_type=args.type, since=since_str
    )
    data = graphql(graphql_url, query)

    if "errors" in data:
        print(f"Error: GraphQL returned errors: {data['errors']}", file=sys.stderr)
        sys.exit(2)

    edges = data["data"]["project"]["builds"]["edges"]
    builds = [
        e["node"]
        for e in edges
        if (e["node"].get("buildWarningsCount") or 0) > 0
        or (e["node"].get("buildErrorsCount") or 0) > 0
    ]

    builds.sort(
        key=lambda n: (n.get("buildErrorsCount") or 0, n.get("buildWarningsCount") or 0),
        reverse=True,
    )
    builds = builds[: args.limit_builds]

    if not builds:
        if args.json_output:
            print(json.dumps({"builds_inspected": 0, "warnings": []}, indent=2))
        else:
            print("No builds with warnings found.", file=sys.stderr)
        return

    # Step 2: Fetch warnings and deduplicate by (sourceFile, flag)
    seen = {}
    builds_inspected = []

    for b in builds:
        build_id = b["id"]
        build_name = b["name"]
        site = b["site"]["name"]
        builds_inspected.append({"id": build_id, "name": build_name, "site": site})

        try:
            _meta, entries = fetch_entries(
                graphql_url, str(build_id), "WARNING", args.limit_warnings
            )
        except SystemExit:
            continue

        for e in entries:
            src = e.get("sourceFile") or "<unknown>"
            if "ThirdParty" in src:
                continue
            text = e.get("stdError") or e.get("stdOutput") or ""
            flag = extract_flag(text)
            key = (src, flag)
            if key not in seen:
                seen[key] = {
                    "sourceFile": src,
                    "flag": flag,
                    "count": 0,
                    "builds": [],
                    "sample": text[:200],
                }
            seen[key]["count"] += 1
            if build_name not in seen[key]["builds"]:
                seen[key]["builds"].append(build_name)

    # Step 3: Group by flag
    by_flag = {}
    for info in seen.values():
        flag = info["flag"]
        if flag not in by_flag:
            by_flag[flag] = {"flag": flag, "total_count": 0, "files": []}
        by_flag[flag]["total_count"] += info["count"]
        by_flag[flag]["files"].append(info)

    result = sorted(by_flag.values(), key=lambda g: -g["total_count"])

    if args.json_output:
        print(
            json.dumps(
                {
                    "builds_inspected": len(builds_inspected),
                    "builds": builds_inspected,
                    "warnings_by_flag": result,
                },
                indent=2,
            )
        )
    else:
        print(
            f"Inspected {len(builds_inspected)} builds  |  "
            f"{len(seen)} unique (file, flag) pairs  |  "
            f"{len(by_flag)} distinct flags",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        print(f"{'TOTAL':>6}  {'FILES':>6}  FLAG")
        print("-" * 60)
        for group in result:
            print(f"{group['total_count']:>6}  {len(group['files']):>6}  {group['flag']}")


if __name__ == "__main__":
    main()
