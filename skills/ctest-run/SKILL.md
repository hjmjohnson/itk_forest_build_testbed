---
name: ctest-run
version: 1.0.0
purpose: Run CTest on a CTK build directory, produce JUnit XML output, parse it, and print a summary of passed/failed/errored/ski...
description: Run CTest on a CTK build directory, produce JUnit XML output, parse it, and print a summary of passed/failed/errored/skipped tests.
triggers:
  - ctest-run
  - /ctest-run
user_invocable: true
cmd: false
argument_hint: "[build-dir] [-R test-name]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
    network_required: false
    git_required: false
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools: []
  python_packages: []
  scripts: []
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
ctest-run — Run CTest, parse JUnit XML, report summary

Usage:
  /ctest-run                              Run tests in default CTK build dir
  /ctest-run /path/to/build               Run tests in specified build dir
  /ctest-run -R ctkDICOM                  Run only tests matching pattern
```

Run CTest on the CTK build directory, parse the JUnit XML results, and report a summary.

## Steps

### Step 1: Run CTest

Run CTest with JUnit XML output. Use `--output-on-failure` so failed test output is captured.

```bash
ctest --timeout 10 --test-dir /Users/johnsonhj/src/CTK/cmake-build-clazy/CTK-build/ \
  --output-on-failure \
  --output-junit /Users/johnsonhj/src/CTK/cmake-build-clazy/CTK-build/ctest-results.xml
```

This may take several minutes. Run it with a generous timeout (10 minutes).

### Step 2: Parse and summarize results

After CTest finishes, run this Python script to parse the JUnit XML and produce a JSON summary:

```bash
python3 - <<'PY'
import xml.etree.ElementTree as ET
import json
import sys

xml_path = "/Users/johnsonhj/src/CTK/cmake-build-clazy/CTK-build/ctest-results.xml"
json_path = "/Users/johnsonhj/src/CTK/cmake-build-clazy/CTK-build/ctest-results.json"

root = ET.parse(xml_path).getroot()

out = {"testsuites": []}

# CTest outputs <testsuite> as root (not wrapped in <testsuites>)
# Handle both: root is testsuite, or root is testsuites containing testsuite children
if root.tag == "testsuite":
    suites = [root]
elif root.tag == "testsuites":
    suites = root.findall("testsuite")
else:
    suites = root.findall("testsuite")

for ts in suites:
    suite = {
        "name": ts.attrib.get("name"),
        "tests": int(ts.attrib.get("tests", 0)),
        "failures": int(ts.attrib.get("failures", 0)),
        "errors": int(ts.attrib.get("errors", 0)),
        "skipped": int(ts.attrib.get("skipped", 0)) if ts.attrib.get("skipped") else 0,
        "time": float(ts.attrib.get("time", 0.0)),
        "testcases": [],
    }
    for tc in ts.findall("testcase"):
        case = {
            "name": tc.attrib.get("name"),
            "classname": tc.attrib.get("classname"),
            "time": float(tc.attrib.get("time", 0.0)),
            "status": "passed",
        }
        if tc.find("failure") is not None:
            case["status"] = "failed"
            case["failure"] = tc.find("failure").attrib.get("message", "")
        elif tc.find("error") is not None:
            case["status"] = "error"
            case["error"] = tc.find("error").attrib.get("message", "")
        elif tc.find("skipped") is not None:
            case["status"] = "skipped"
        suite["testcases"].append(case)
    out["testsuites"].append(suite)

with open(json_path, "w") as f:
    json.dump(out, f, indent=2)

# Print summary
total = sum(s["tests"] for s in out["testsuites"])
failed = sum(s["failures"] for s in out["testsuites"])
errors = sum(s["errors"] for s in out["testsuites"])
skipped = sum(s["skipped"] for s in out["testsuites"])
passed = total - failed - errors - skipped

print(f"\n{'='*60}")
print(f"CTest Results Summary")
print(f"{'='*60}")
print(f"  Total:   {total}")
print(f"  Passed:  {passed}")
print(f"  Failed:  {failed}")
print(f"  Errors:  {errors}")
print(f"  Skipped: {skipped}")
print(f"{'='*60}")

# List failures and errors
for s in out["testsuites"]:
    for tc in s["testcases"]:
        if tc["status"] == "failed":
            msg = tc.get("failure", "")
            print(f"  FAIL: {tc['name']}  -- {msg}")
        elif tc["status"] == "error":
            msg = tc.get("error", "")
            print(f"  ERROR: {tc['name']}  -- {msg}")

print(f"\nWrote {json_path}")
PY
```

### Step 3: Report to user

Present the summary table to the user. If there are failures, list each failed test name and its failure message. If all tests passed, confirm a clean run.

## Arguments

If the user passes a test name filter (e.g., `/ctest-run DICOM`), append `-R <filter>` to the ctest command to run only matching tests.
