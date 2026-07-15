#!/usr/bin/env python3
"""Standalone tests for pr_workstate.py. Run: python3 test_pr_workstate.py"""
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "pr_workstate.py")
FAIL = 0


def check(desc, ok):
    global FAIL
    print(("ok   - " if ok else "FAIL - ") + desc)
    if not ok:
        FAIL = 1


def run(args, cwd, env):
    return subprocess.run(
        [sys.executable, SCRIPT, *args], cwd=cwd, env=env, capture_output=True, text=True
    )


def main():
    tmp = tempfile.mkdtemp()
    repo = os.path.join(tmp, "wsrepo")
    os.makedirs(repo)
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True)

    env = dict(os.environ)
    env["PR_WORKSTATE_DIR"] = os.path.join(tmp, "state")
    env["XDG_CACHE_HOME"] = os.path.join(tmp, "cache")

    # set + re-set a subset keeps prior fields
    r = run(["set", "InsightSoftwareConsortium/ITK", "6500", "--status", "gated",
             "--skill", "itk-cleanup-pr-lifecycle", "--gate", "precommit-ok",
             "--at", "2026-07-15T00:00:00Z"], repo, env)
    check("set exits 0", r.returncode == 0)
    r = run(["set", "InsightSoftwareConsortium/ITK", "6500", "--status", "pushed",
             "--at", "2026-07-15T01:00:00Z"], repo, env)
    check("re-set partial exits 0", r.returncode == 0)
    r = run(["workqueue"], repo, env)
    check("workqueue shows updated status pushed", "pushed" in r.stdout)
    check("workqueue keeps prior last_skill", "itk-cleanup-pr-lifecycle" in r.stdout)

    # concern + addressed
    run(["concern", "InsightSoftwareConsortium/ITK", "6500", "12345",
         "--by", "gh-triage-pr", "--at", "2026-07-15T02:00:00Z"], repo, env)
    r = run(["addressed", "InsightSoftwareConsortium/ITK", "6500"], repo, env)
    check("addressed lists the comment id", r.stdout.strip() == "12345")
    # reopen removes it from addressed
    run(["concern", "InsightSoftwareConsortium/ITK", "6500", "12345", "--by",
         "gh-triage-pr", "--reopen", "--at", "2026-07-15T03:00:00Z"], repo, env)
    r = run(["addressed", "InsightSoftwareConsortium/ITK", "6500"], repo, env)
    check("reopen clears addressed", r.stdout.strip() == "")

    # workqueue joins gh-comment-cache raw_pr_index title when present
    import importlib.util
    spec = importlib.util.spec_from_file_location("pw", SCRIPT)
    pw = importlib.util.module_from_spec(spec)
    os.environ["PR_WORKSTATE_DIR"] = env["PR_WORKSTATE_DIR"]
    os.environ["XDG_CACHE_HOME"] = env["XDG_CACHE_HOME"]
    os.chdir(repo)
    spec.loader.exec_module(pw)
    ws = pw._ws()
    cp = pw.cache_path("gh-comment-cache", ws)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    cc = sqlite3.connect(cp)
    cc.execute(
        "CREATE TABLE raw_pr_index (repo_owner TEXT, repo_name TEXT, number INTEGER,"
        " title TEXT, state TEXT)"
    )
    cc.execute(
        "INSERT INTO raw_pr_index VALUES (?,?,?,?,?)",
        ("InsightSoftwareConsortium", "ITK", 6500, "Fix the thing", "open"),
    )
    cc.commit()
    cc.close()
    r = run(["workqueue"], repo, env)
    check("workqueue joins title from cache DB", "open" in r.stdout)

    # unknown repo -> empty, exit 0
    r = run(["addressed", "Foo/Bar", "1"], repo, env)
    check("unknown repo addressed empty exit 0", r.returncode == 0 and r.stdout.strip() == "")

    print("----")
    print("ALL PASS" if FAIL == 0 else "SOME FAILED")
    sys.exit(FAIL)


if __name__ == "__main__":
    main()
