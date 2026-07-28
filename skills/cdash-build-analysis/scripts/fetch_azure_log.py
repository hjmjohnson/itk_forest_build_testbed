#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
fetch_azure_log.py — Fetch build timeline and logs from Azure DevOps.

Retrieves build status, timeline (steps with pass/fail), and optionally
downloads log content for failed steps. ITK Azure pipelines are public,
so no authentication is needed.

Exit codes:
  0  Success
  1  Argument error
  2  Network or API error
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

# ITK Azure DevOps organizations and their project GUIDs
ITK_AZURE_ORGS = {
    "itkrobotlinux": "07610e7d-0753-4a9f-9f63-b3f6b749d57a",
    "itkrobotlinuxpython": "59377e31-8b02-46ea-9d49-32b6bb4b2da6",
    "itkrobotmacos": "c947f891-8c0e-4d7f-9768-5685d97c2b9c",
    "itkrobotmacospython": "94b66987-4e3d-468c-9391-c75d05faf083",
    "itkrobotwindow": "52d3b1d0-6937-44c1-bc65-96b3dc4331e3",
    "itkrobotwindowpython": None,
}


def api_get(url: str) -> dict:
    """GET a JSON response from a URL."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


def api_get_text(url: str) -> str:
    """GET raw text from a URL."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


def parse_azure_url(url: str) -> tuple:
    """Extract org, project, and build ID from an Azure DevOps URL."""
    m = re.match(
        r"https://dev\.azure\.com/([^/]+)/([^/]+)/_build/results\?buildId=(\d+)",
        url,
    )
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None, None, None


def fetch_build(org: str, project: str, build_id: str) -> dict:
    """Fetch build summary."""
    url = f"https://dev.azure.com/{org}/{project}/_apis/build/builds/{build_id}?api-version=7.0"
    return api_get(url)


def fetch_timeline(org: str, project: str, build_id: str) -> dict:
    """Fetch build timeline (all steps with status)."""
    url = f"https://dev.azure.com/{org}/{project}/_apis/build/builds/{build_id}/timeline?api-version=7.0"
    return api_get(url)


def fetch_log(org: str, project: str, build_id: str, log_id: int) -> str:
    """Fetch a specific log by ID."""
    url = f"https://dev.azure.com/{org}/{project}/_apis/build/builds/{build_id}/logs/{log_id}?api-version=7.0"
    return api_get_text(url)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Azure DevOps build details for CI diagnosis"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Full Azure DevOps build URL")
    group.add_argument("--build-id", help="Build ID (requires --org and --project)")

    parser.add_argument("--org", help="Azure DevOps organization")
    parser.add_argument("--project", help="Azure DevOps project GUID")
    parser.add_argument(
        "--failed-logs",
        action="store_true",
        help="Download logs for failed steps",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.url:
        org, project, build_id = parse_azure_url(args.url)
        if not org:
            print(f"Error: could not parse Azure URL: {args.url}", file=sys.stderr)
            sys.exit(1)
    else:
        org = args.org
        project = args.project
        build_id = args.build_id
        if not org or not project:
            # Try to infer from known ITK orgs
            print("Error: --org and --project required with --build-id", file=sys.stderr)
            sys.exit(1)

    # Fetch build summary
    build = fetch_build(org, project, build_id)

    if args.json and not args.failed_logs:
        print(json.dumps(build, indent=2))
        return

    print(f"Build:  {build.get('buildNumber', '?')}")
    print(f"Status: {build.get('status', '?')}")
    print(f"Result: {build.get('result', '?')}")
    print(f"Source: {build.get('sourceBranch', '?')}")
    print(f"Start:  {build.get('startTime', '?')}")
    print(f"Finish: {build.get('finishTime', '?')}")
    print()

    # Fetch timeline
    timeline = fetch_timeline(org, project, build_id)
    records = timeline.get("records", [])

    # Show task steps
    tasks = [r for r in records if r.get("type") == "Task"]
    tasks.sort(key=lambda r: r.get("order", 0))

    failed_tasks = []
    for task in tasks:
        name = task.get("name", "?")
        result = task.get("result", "?")
        marker = "FAIL" if result == "failed" else "OK  " if result == "succeeded" else "SKIP"
        print(f"  [{marker}] {name}")
        if result == "failed":
            failed_tasks.append(task)

    if args.failed_logs and failed_tasks:
        print("\n--- Failed step logs ---\n")
        for task in failed_tasks:
            log_ref = task.get("log", {})
            log_id = log_ref.get("id")
            if log_id:
                print(f"=== {task['name']} (log {log_id}) ===")
                log_text = fetch_log(org, project, build_id, log_id)
                # Print last 100 lines (most relevant for failures)
                lines = log_text.strip().split("\n")
                if len(lines) > 100:
                    print(f"  ... ({len(lines) - 100} lines omitted) ...")
                for line in lines[-100:]:
                    print(f"  {line}")
                print()


if __name__ == "__main__":
    main()
