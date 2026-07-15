#!/usr/bin/env python3
"""Tests for the gh-triage-pr work-state wiring. Run: python3 test_ghtp_workstate.py"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FAIL = 0


def check(desc, ok):
    global FAIL
    print(("ok   - " if ok else "FAIL - ") + desc)
    if not ok:
        FAIL = 1


def main():
    fetch = load("ghtp_fetch")
    comments = [
        {"kind": "inline", "id": 111, "thread_state": {"is_resolved": False}},
        {"kind": "inline", "id": 222, "thread_state": {"is_resolved": False}},
        {"kind": "top_level", "id": 333, "thread_state": {}},
    ]
    out = fetch.mark_addressed(comments, {"222"})
    by_id = {c["id"]: c for c in out}
    check("111 not addressed_locally", by_id[111]["addressed_locally"] is False)
    check("222 addressed_locally", by_id[222]["addressed_locally"] is True)
    # unresolved count excludes locally-addressed inline
    n = fetch.count_unresolved_inline(out)
    check("unresolved count excludes locally-addressed", n == 1)

    reply = load("ghtp_reply")
    # best-effort recorder must not raise even if pr_workstate is unreachable
    try:
        reply._record_addressed("Foo", "Bar", 1, 999, script="/nonexistent/pr_workstate.py")
        check("_record_addressed swallows errors", True)
    except Exception:
        check("_record_addressed swallows errors", False)

    print("----")
    print("ALL PASS" if FAIL == 0 else "SOME FAILED")
    sys.exit(FAIL)


if __name__ == "__main__":
    main()
