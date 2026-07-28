#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
fetch_cdash_build.py — Fetch build details from CDash GraphQL API.

Retrieves build summary, notes, test failures, and error details for
a specific CDash build ID. Designed for diagnosing CI failures.

Exit codes:
  0  Success
  1  Argument error
  2  Network or API error
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

CDASH_GRAPHQL = "https://open.cdash.org/graphql"


def graphql(query: str) -> dict:
    """Execute a GraphQL query against CDash."""
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        CDASH_GRAPHQL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"Error: network request failed: {e}", file=sys.stderr)
        sys.exit(2)


def fetch_summary(build_id: str) -> dict:
    """Fetch build summary: name, site, timestamps, counts."""
    query = (
        """
    {
      build(id: "%s") {
        name
        stamp
        startTime
        buildWarningsCount
        buildErrorsCount
        passedTestsCount
        failedTestsCount
        notRunTestsCount
        compilerName
        compilerVersion
        operatingSystemName
        operatingSystemVersion
        site { name }
      }
    }
    """
        % build_id
    )
    data = graphql(query)
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(2)
    return data.get("data", {}).get("build", {})


def fetch_notes(build_id: str) -> list:
    """Fetch build notes (CMake config, compiler info)."""
    query = (
        """
    {
      build(id: "%s") {
        notes {
          edges {
            node { name text }
          }
        }
      }
    }
    """
        % build_id
    )
    data = graphql(query)
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(2)
    build = data.get("data", {}).get("build", {})
    notes = build.get("notes", {}).get("edges", [])
    return [edge["node"] for edge in notes]


def fetch_failed_tests(build_id: str, limit: int = 50) -> list:
    """Fetch failed test details with output."""
    query = """
    {
      build(id: "%s") {
        tests(filters: { eq: { status: FAILED } }, first: %d) {
          edges {
            node {
              name
              status
              runningTime
              details
              output
            }
          }
        }
      }
    }
    """ % (
        build_id,
        limit,
    )
    data = graphql(query)
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(2)
    build = data.get("data", {}).get("build", {})
    tests = build.get("tests", {}).get("edges", [])
    return [edge["node"] for edge in tests]


def fetch_errors(build_id: str, limit: int = 50) -> list:
    """Fetch build errors."""
    query = """
    {
      build(id: "%s") {
        buildErrors(filters: { eq: { type: ERROR } }, first: %d) {
          edges {
            node { sourceFile sourceLine stdError stdOutput }
          }
        }
      }
    }
    """ % (
        build_id,
        limit,
    )
    data = graphql(query)
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(2)
    build = data.get("data", {}).get("build", {})
    errors = build.get("buildErrors", {}).get("edges", [])
    return [edge["node"] for edge in errors]


def fetch_warnings(build_id: str, limit: int = 200) -> list:
    """Fetch build warnings."""
    query = """
    {
      build(id: "%s") {
        buildErrors(filters: { eq: { type: WARNING } }, first: %d) {
          edges {
            node { sourceFile sourceLine stdError stdOutput }
          }
        }
      }
    }
    """ % (
        build_id,
        limit,
    )
    data = graphql(query)
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
        sys.exit(2)
    build = data.get("data", {}).get("build", {})
    warnings = build.get("buildErrors", {}).get("edges", [])
    return [edge["node"] for edge in warnings]


def print_summary(build: dict) -> None:
    """Print a human-readable build summary."""
    print(f"Build: {build.get('name', 'unknown')}")
    print(f"Site:  {build.get('site', {}).get('name', 'unknown')}")
    print(f"Stamp: {build.get('stamp', 'unknown')}")
    print(f"Start: {build.get('startTime', 'unknown')}")
    print()
    compiler = build.get("compilerName", "")
    compiler_ver = build.get("compilerVersion", "")
    if compiler:
        print(f"Compiler: {compiler} {compiler_ver}")
    os_name = build.get("operatingSystemName", "")
    os_ver = build.get("operatingSystemVersion", "")
    if os_name:
        print(f"OS:       {os_name} {os_ver}")
    print()
    print(f"Errors:       {build.get('buildErrorsCount', 0)}")
    print(f"Warnings:     {build.get('buildWarningsCount', 0)}")
    print(f"Tests passed: {build.get('passedTestsCount', 0)}")
    print(f"Tests failed: {build.get('failedTestsCount', 0)}")
    print(f"Tests not run:{build.get('notRunTestsCount', 0)}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch CDash build details for CI failure diagnosis"
    )
    parser.add_argument("build_id", help="CDash build ID")
    parser.add_argument("--notes", action="store_true", help="Fetch build notes (CMake config)")
    parser.add_argument("--failed-tests", action="store_true", help="Fetch failed test details")
    parser.add_argument("--errors", action="store_true", help="Fetch build errors")
    parser.add_argument("--warnings", action="store_true", help="Fetch build warnings")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--limit", type=int, default=50, help="Max entries to fetch (default: 50)")
    args = parser.parse_args()

    # Default: show summary
    if not any([args.notes, args.failed_tests, args.errors, args.warnings]):
        build = fetch_summary(args.build_id)
        if args.json:
            print(json.dumps(build, indent=2))
        else:
            print_summary(build)
        return

    if args.notes:
        notes = fetch_notes(args.build_id)
        if args.json:
            print(json.dumps(notes, indent=2))
        else:
            for note in notes:
                print(f"=== {note.get('name', 'Note')} ===")
                print(note.get("text", ""))
                print()

    if args.failed_tests:
        tests = fetch_failed_tests(args.build_id, args.limit)
        if args.json:
            print(json.dumps(tests, indent=2))
        else:
            if not tests:
                print("No failed tests.")
            for t in tests:
                print(f"FAILED: {t['name']} ({t.get('runningTime', '?')}s)")
                if t.get("details"):
                    print(f"  Details: {t['details']}")
                if t.get("output"):
                    # Print first 50 lines of output
                    lines = t["output"].strip().split("\n")
                    for line in lines[:50]:
                        print(f"  {line}")
                    if len(lines) > 50:
                        print(f"  ... ({len(lines) - 50} more lines)")
                print()

    if args.errors:
        errors = fetch_errors(args.build_id, args.limit)
        if args.json:
            print(json.dumps(errors, indent=2))
        else:
            if not errors:
                print("No build errors.")
            for e in errors:
                src = e.get("sourceFile", "unknown")
                line = e.get("sourceLine", "?")
                msg = e.get("stdError", "") or e.get("stdOutput", "")
                print(f"{src}:{line}")
                print(f"  {msg[:200]}")
                print()

    if args.warnings:
        warnings = fetch_warnings(args.build_id, args.limit)
        if args.json:
            print(json.dumps(warnings, indent=2))
        else:
            if not warnings:
                print("No build warnings.")
            for w in warnings:
                src = w.get("sourceFile", "unknown")
                line = w.get("sourceLine", "?")
                msg = w.get("stdError", "") or w.get("stdOutput", "")
                print(f"{src}:{line}")
                print(f"  {msg[:200]}")
                print()


if __name__ == "__main__":
    main()
