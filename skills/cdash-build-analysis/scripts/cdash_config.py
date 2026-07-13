#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
cdash_config.py — Auto-detect CDash configuration from the current project.

Parses CTestConfig.cmake to determine the CDash host, project name, and
GraphQL endpoint. Also resolves the CDash project ID via the GraphQL API
(needed for the builds query).

Supports:
  - open.cdash.org (ITK/Insight, VTK)
  - my.cdash.org (BRAINSTools)
  - slicer.cdash.org (Slicer, SlicerPreview)
  - Any CDash 4.x instance with a /graphql endpoint

Usage as a library:
    from cdash_config import detect_cdash_config
    config = detect_cdash_config()
    # config = {"host": "open.cdash.org", "project": "Insight", "graphql_url": "https://...", "project_id": "2"}

Usage as a CLI:
    python3 scripts/cdash_config.py [--source-dir /path/to/repo]
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Known CDash project IDs (saves a network round-trip for common projects)
KNOWN_PROJECT_IDS = {
    ("open.cdash.org", "Insight"): "2",  # ITK
    ("open.cdash.org", "VTK"): "7",  # VTK
    ("open.cdash.org", "CTK"): "56",  # CTK
}


def _find_ctest_config(source_dir: str = None) -> str:
    """Find CTestConfig.cmake, searching upward from source_dir or git root."""
    if source_dir is None:
        try:
            source_dir = (
                subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            source_dir = str(Path.cwd())

    path = Path(source_dir) / "CTestConfig.cmake"
    if path.is_file():
        return str(path)

    # Also check parent dirs (some projects nest the config)
    current = Path(source_dir)
    for _ in range(5):
        parent = current.parent
        if parent == current:
            break
        path = parent / "CTestConfig.cmake"
        if path.is_file():
            return str(path)
        current = parent

    return None


def _parse_ctest_config(config_path: str) -> dict:
    """Extract CDash host and project name from CTestConfig.cmake."""
    content = open(config_path).read()

    result = {"host": None, "project": None}

    # Try CTEST_SUBMIT_URL first (modern CMake >= 3.14)
    m = re.search(r'CTEST_SUBMIT_URL\s+"https?://([^/]+)/submit\.php\?project=([^"]+)"', content)
    if m:
        result["host"] = m.group(1)
        result["project"] = m.group(2)
        return result

    # Fall back to CTEST_DROP_SITE + CTEST_DROP_LOCATION
    m_site = re.search(r'CTEST_DROP_SITE\s+"([^"]+)"', content)
    m_loc = re.search(r'CTEST_DROP_LOCATION\s+"/submit\.php\?project=([^"]+)"', content)
    if m_site:
        result["host"] = m_site.group(1)
    if m_loc:
        result["project"] = m_loc.group(1)

    # Handle variable references in project name (e.g., ${CDASH_PROJECT_NAME})
    if result["project"] and "${" in result["project"]:
        var_name = re.search(r"\$\{(\w+)\}", result["project"]).group(1)
        m_var = re.search(rf'set\({var_name}\s+"([^"]+)"\)', content)
        if m_var:
            result["project"] = m_var.group(1)

    return result


def _resolve_project_id(host: str, project: str) -> str:
    """Resolve the numeric CDash project ID via the GraphQL API."""
    # Check known IDs first
    key = (host, project)
    if key in KNOWN_PROJECT_IDS:
        return KNOWN_PROJECT_IDS[key]

    # Query the API
    graphql_url = f"https://{host}/graphql"
    query = "{ projects { edges { node { id name } } } }"
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        graphql_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError):
        return None

    if "errors" in data:
        return None

    for edge in data.get("data", {}).get("projects", {}).get("edges", []):
        node = edge["node"]
        if node["name"] == project:
            return str(node["id"])

    return None


def detect_cdash_config(source_dir: str = None) -> dict:
    """Auto-detect CDash configuration from the current project.

    Returns a dict with keys: host, project, graphql_url, project_id, dashboard_url.
    Any key may be None if detection fails.
    """
    config_path = _find_ctest_config(source_dir)
    if config_path is None:
        return {
            "host": None,
            "project": None,
            "graphql_url": None,
            "project_id": None,
            "dashboard_url": None,
            "config_path": None,
        }

    parsed = _parse_ctest_config(config_path)
    host = parsed["host"]
    project = parsed["project"]
    graphql_url = f"https://{host}/graphql" if host else None
    project_id = _resolve_project_id(host, project) if host and project else None
    dashboard_url = f"https://{host}/index.php?project={project}" if host and project else None

    return {
        "host": host,
        "project": project,
        "graphql_url": graphql_url,
        "project_id": project_id,
        "dashboard_url": dashboard_url,
        "config_path": config_path,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Auto-detect CDash configuration from CTestConfig.cmake",
    )
    parser.add_argument(
        "--source-dir", default=None, help="Project source directory (default: git root)"
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    args = parser.parse_args()

    config = detect_cdash_config(args.source_dir)

    if args.json_output:
        print(json.dumps(config, indent=2))
    else:
        for k, v in config.items():
            print(f"  {k}: {v}")

    if config["project_id"] is None:
        print("WARNING: Could not resolve project ID", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
