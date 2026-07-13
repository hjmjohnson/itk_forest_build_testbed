#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
list_builds.py — List CDash builds that have warnings or errors.

Auto-detects the CDash project from CTestConfig.cmake in the current repo.
Works with any CDash 4.x instance (open.cdash.org, my.cdash.org, slicer.cdash.org).

Exit codes:
  0  Success (results printed, possibly empty)
  1  Argument error or project detection failure
  2  Network or API error
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cdash_config import detect_cdash_config

QUERY_TEMPLATE = """
{
  project(id: "%s") {
    name
    builds(first: %d, filters: { all: [
      { contains: { stamp: "%s" } }
      { gt: { startTime: "%s" } }
    ]}) {
      edges {
        node {
          id name stamp buildType buildWarningsCount buildErrorsCount startTime
          site { name }
        }
      }
    }
  }
}
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
        prog="list_builds.py",
        description="List CDash builds with warnings or errors (auto-detects project).",
        epilog=(
            "Examples:\n"
            "  python3 scripts/list_builds.py                    # auto-detect from CTestConfig.cmake\n"
            "  python3 scripts/list_builds.py --type Continuous\n"
            "  python3 scripts/list_builds.py --since 48 --json\n"
            "  python3 scripts/list_builds.py --host open.cdash.org --project Insight  # explicit\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--type",
        default="Nightly",
        metavar="TYPE",
        help="Build type: Nightly (default), Continuous, Experimental",
    )
    parser.add_argument(
        "--since",
        type=float,
        default=None,
        metavar="HOURS",
        help="Builds from the last N hours (default: since nightly start)",
    )
    parser.add_argument(
        "--limit", type=int, default=100, metavar="N", help="Max builds to fetch (default: 100)"
    )
    parser.add_argument(
        "--all", action="store_true", help="Show all builds, not just those with warnings/errors"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON array"
    )
    parser.add_argument("--host", default=None, help="CDash host (override auto-detect)")
    parser.add_argument("--project", default=None, help="CDash project name (override)")
    parser.add_argument("--project-id", default=None, help="CDash project ID (override)")
    parser.add_argument("--source-dir", default=None, help="Source dir for CTestConfig.cmake")
    args = parser.parse_args()

    # Resolve CDash config
    config = detect_cdash_config(args.source_dir)
    host = args.host or config["host"]
    project = args.project or config["project"]
    project_id = args.project_id or config["project_id"]
    graphql_url = f"https://{host}/graphql" if host else None

    if not all([graphql_url, project_id]):
        print(
            "Error: Could not detect CDash project. Use --host/--project/--project-id or ensure CTestConfig.cmake exists.",
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

    fetch_count = max(args.limit, 500)
    query = QUERY_TEMPLATE % (project_id, fetch_count, args.type, since_str)
    data = graphql(graphql_url, query)

    if "errors" in data:
        print(f"Error: GraphQL returned errors: {data['errors']}", file=sys.stderr)
        sys.exit(2)

    edges = data["data"]["project"]["builds"]["edges"]
    project_name = data["data"]["project"]["name"]
    nodes = [e["node"] for e in edges]

    if not args.all:
        nodes = [
            n
            for n in nodes
            if (n.get("buildWarningsCount") or 0) > 0 or (n.get("buildErrorsCount") or 0) > 0
        ]

    nodes.sort(
        key=lambda n: (
            n.get("buildErrorsCount") or 0,
            n.get("buildWarningsCount") or 0,
            n.get("startTime", ""),
        ),
        reverse=True,
    )
    nodes = nodes[: args.limit]

    if args.json_output:
        output = [
            {
                "id": n["id"],
                "name": n["name"],
                "stamp": n["stamp"],
                "buildType": n["buildType"],
                "warnings": n["buildWarningsCount"] or 0,
                "errors": n["buildErrorsCount"] or 0,
                "startTime": n["startTime"],
                "site": n["site"]["name"],
            }
            for n in nodes
        ]
        print(json.dumps(output, indent=2))
        return

    print(
        f"Project: {project_name}  |  type={args.type!r}  |  since={since_str}  |  "
        f"Fetched: {len(edges)}  |  With issues: {len(nodes)}",
        file=sys.stderr,
    )
    print(file=sys.stderr)
    print(f"{'BUILD_ID':>10}  {'W':>4}  {'E':>4}  {'STAMP':<25}  {'SITE':<25}  BUILD_NAME")
    print("-" * 110)
    for n in nodes:
        warn = n["buildWarningsCount"] or 0
        err = n["buildErrorsCount"] or 0
        print(
            f"{n['id']:>10}  {warn:>4}  {err:>4}  "
            f"{n['stamp'][:24]:<25}  {n['site']['name'][:24]:<25}  {n['name']}"
        )


if __name__ == "__main__":
    main()
