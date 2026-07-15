# PR/issue work-state ledger — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a durable per-PR work-state ledger (extends gh-comment-cache) that records session-authored state — which skill touched a PR, gate decisions, and addressed reviewer concerns — and wire `gh-triage-pr` to record + skip already-addressed concerns.

**Architecture:** A `pr_workstate.py` CLI under `skills/gh-comment-cache/scripts/` writing a **durable** SQLite DB under `~/.local/state/agent-skills/gh-comment-cache/` (survives `cache clear`), keyed by the same `workspace.py` fingerprint as the cache. `workqueue` joins it read-only against gh-comment-cache's `raw_pr_index`. `gh-triage-pr` records addressed concerns on reply and excludes them from its unresolved count on fetch.

**Tech Stack:** Python 3 (stdlib sqlite3 + argparse), the existing `gh-comment-cache/lib/agent_skills/{workspace,cache}.py`.

## Global Constraints

- **Durable, not cache** — DB at `${PR_WORKSTATE_DIR:-~/.local/state/agent-skills/gh-comment-cache}/workstate-<fp>.sqlite`, dir `0700`. NEVER in the cache path; NEVER modify `cache.py`.
- **Reuse workspace identity** — key by `agent_skills.workspace.identify(cwd).fingerprint` (imported from the sibling lib).
- **Graceful degradation** — `workqueue` works with or without the gh-comment-cache DB present; unknown repo/PR → empty, exit 0.
- **Consumer wiring is best-effort** — `gh-triage-pr` calls into `pr_workstate.py` must never break triage if the script/DB is absent (swallow errors).
- **Stdlib only.** Stage explicitly. Commit prefix `ENH:`. This is kit-repo (avenue a) work.

---

## File Structure

- `skills/gh-comment-cache/scripts/pr_workstate.py` — the ledger CLI (`set`/`concern`/`addressed`/`workqueue`).
- `skills/gh-comment-cache/scripts/test_pr_workstate.py` — standalone test runner.
- `skills/gh-triage-pr/scripts/ghtp_reply.py` — MODIFY: record addressed concern after a successful reply.
- `skills/gh-triage-pr/scripts/ghtp_fetch.py` — MODIFY: annotate `addressed_locally` + exclude from unresolved count.

---

## Task 1: `pr_workstate.py` + tests

**Files:**
- Create: `skills/gh-comment-cache/scripts/pr_workstate.py`
- Test: `skills/gh-comment-cache/scripts/test_pr_workstate.py`

**Interfaces:**
- Produces the CLI and importable helpers `mark_addressed` is NOT here (that's Task 2). Here: `set`/`concern`/`addressed`/`workqueue` subcommands over the durable DB.

- [ ] **Step 1: Write the failing test**

Create `skills/gh-comment-cache/scripts/test_pr_workstate.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/gh-comment-cache/scripts/test_pr_workstate.py`
Expected: FAIL — `pr_workstate.py` does not exist.

- [ ] **Step 3: Write the implementation**

Create `skills/gh-comment-cache/scripts/pr_workstate.py`:

```python
#!/usr/bin/env python3
"""pr_workstate.py — durable per-PR work-state ledger (extends gh-comment-cache).

Stores session-authored work-state (which skill touched a PR, gate decisions,
addressed reviewer concerns) in a DURABLE sqlite DB that survives `cache clear`:
  ${PR_WORKSTATE_DIR:-~/.local/state/agent-skills/gh-comment-cache}/workstate-<fp>.sqlite
keyed by the same workspace fingerprint as gh-comment-cache.

Modes:
  set <owner/repo> <num> [--status S] [--skill X] [--gate G] [--verdict V] [--at ISO]
  concern <owner/repo> <num> <comment_id> --by <skill> [--reopen] [--at ISO]
  addressed <owner/repo> <num>            # print addressed comment_ids
  workqueue [--repo <owner/repo>]         # join with gh-comment-cache raw_pr_index
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "lib"))
from agent_skills.workspace import identify  # noqa: E402

try:
    from agent_skills.cache import cache_path  # noqa: E402
except Exception:  # pragma: no cover
    cache_path = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_workstate (
    repo_owner    TEXT NOT NULL,
    repo_name     TEXT NOT NULL,
    number        INTEGER NOT NULL,
    status        TEXT,
    last_skill    TEXT,
    gate_state    TEXT,
    local_verdict TEXT,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (repo_owner, repo_name, number)
);
CREATE TABLE IF NOT EXISTS pr_concern_state (
    repo_owner   TEXT NOT NULL,
    repo_name    TEXT NOT NULL,
    number       INTEGER NOT NULL,
    comment_id   TEXT NOT NULL,
    addressed    INTEGER NOT NULL DEFAULT 1 CHECK (addressed IN (0, 1)),
    by_skill     TEXT,
    at           TEXT NOT NULL,
    PRIMARY KEY (repo_owner, repo_name, number, comment_id)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _state_dir():
    d = os.environ.get("PR_WORKSTATE_DIR") or os.path.expanduser(
        "~/.local/state/agent-skills/gh-comment-cache"
    )
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return str(p)


def _ws(cwd=None):
    return identify(cwd or os.getcwd())


def _db(ws):
    path = os.path.join(_state_dir(), f"workstate-{ws.fingerprint}.sqlite")
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def _split_repo(s):
    owner, name = s.split("/", 1)
    return owner, name


def cmd_set(a):
    owner, name = _split_repo(a.repo)
    con = _db(_ws())
    cur = con.execute(
        "SELECT status, last_skill, gate_state, local_verdict FROM pr_workstate"
        " WHERE repo_owner=? AND repo_name=? AND number=?",
        (owner, name, a.number),
    )
    row = cur.fetchone() or (None, None, None, None)
    status = a.status if a.status is not None else row[0]
    skill = a.skill if a.skill is not None else row[1]
    gate = a.gate if a.gate is not None else row[2]
    verdict = a.verdict if a.verdict is not None else row[3]
    con.execute(
        "INSERT INTO pr_workstate"
        " (repo_owner, repo_name, number, status, last_skill, gate_state, local_verdict, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)"
        " ON CONFLICT(repo_owner, repo_name, number) DO UPDATE SET"
        " status=excluded.status, last_skill=excluded.last_skill,"
        " gate_state=excluded.gate_state, local_verdict=excluded.local_verdict,"
        " updated_at=excluded.updated_at",
        (owner, name, a.number, status, skill, gate, verdict, a.at or _now()),
    )
    con.commit()
    print(f"pr_workstate: set {a.repo}#{a.number} status={status} skill={skill} gate={gate}")
    return 0


def cmd_concern(a):
    owner, name = _split_repo(a.repo)
    con = _db(_ws())
    addressed = 0 if a.reopen else 1
    con.execute(
        "INSERT INTO pr_concern_state"
        " (repo_owner, repo_name, number, comment_id, addressed, by_skill, at)"
        " VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(repo_owner, repo_name, number, comment_id) DO UPDATE SET"
        " addressed=excluded.addressed, by_skill=excluded.by_skill, at=excluded.at",
        (owner, name, a.number, str(a.comment_id), addressed, a.by, a.at or _now()),
    )
    con.commit()
    print(f"pr_workstate: concern {a.repo}#{a.number} comment={a.comment_id} addressed={addressed}")
    return 0


def cmd_addressed(a):
    owner, name = _split_repo(a.repo)
    con = _db(_ws())
    for (cid,) in con.execute(
        "SELECT comment_id FROM pr_concern_state"
        " WHERE repo_owner=? AND repo_name=? AND number=? AND addressed=1",
        (owner, name, a.number),
    ):
        print(cid)
    return 0


def cmd_workqueue(a):
    ws = _ws()
    con = _db(ws)
    q = "SELECT repo_owner, repo_name, number, status, last_skill, gate_state FROM pr_workstate"
    params = ()
    if a.repo:
        owner, name = _split_repo(a.repo)
        q += " WHERE repo_owner=? AND repo_name=?"
        params = (owner, name)
    rows = list(con.execute(q, params))
    counts = {}
    for o, n, num, c in con.execute(
        "SELECT repo_owner, repo_name, number, COUNT(*) FROM pr_concern_state"
        " WHERE addressed=1 GROUP BY repo_owner, repo_name, number"
    ):
        counts[(o, n, num)] = c
    titles = {}
    if cache_path is not None:
        try:
            cp = cache_path("gh-comment-cache", ws)
            if os.path.exists(cp):
                ccon = sqlite3.connect(f"file:{cp}?mode=ro", uri=True)
                for o, n, num, title, state in ccon.execute(
                    "SELECT repo_owner, repo_name, number, title, state FROM raw_pr_index"
                ):
                    titles[(o, n, num)] = (title, state)
                ccon.close()
        except Exception:
            pass
    print(f"{'PR':<26} {'state':<7} {'status':<12} {'last_skill':<24} {'gate':<12} addr")
    for o, n, num, status, skill, gate in rows:
        _t, st = titles.get((o, n, num), ("", ""))
        addr = counts.get((o, n, num), 0)
        print(
            f"{o + '/' + n + '#' + str(num):<26} {st:<7} {status or '':<12}"
            f" {skill or '':<24} {gate or '':<12} {addr}"
        )
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Durable per-PR work-state ledger")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("set")
    s.add_argument("repo")
    s.add_argument("number", type=int)
    s.add_argument("--status")
    s.add_argument("--skill")
    s.add_argument("--gate")
    s.add_argument("--verdict")
    s.add_argument("--at")
    s.set_defaults(func=cmd_set)

    c = sub.add_parser("concern")
    c.add_argument("repo")
    c.add_argument("number", type=int)
    c.add_argument("comment_id")
    c.add_argument("--by")
    c.add_argument("--reopen", action="store_true")
    c.add_argument("--at")
    c.set_defaults(func=cmd_concern)

    a = sub.add_parser("addressed")
    a.add_argument("repo")
    a.add_argument("number", type=int)
    a.set_defaults(func=cmd_addressed)

    w = sub.add_parser("workqueue")
    w.add_argument("--repo")
    w.set_defaults(func=cmd_workqueue)

    ns = p.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
```

Then: `chmod +x skills/gh-comment-cache/scripts/pr_workstate.py`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 skills/gh-comment-cache/scripts/test_pr_workstate.py`
Expected: every check `ok`, final `ALL PASS`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add skills/gh-comment-cache/scripts/pr_workstate.py skills/gh-comment-cache/scripts/test_pr_workstate.py
git commit -m "ENH: Add durable PR/issue work-state ledger pr_workstate.py (issue #5)"
```

---

## Task 2: Wire `gh-triage-pr` (record on reply, skip on fetch)

**Files:**
- Modify: `skills/gh-triage-pr/scripts/ghtp_reply.py`
- Modify: `skills/gh-triage-pr/scripts/ghtp_fetch.py`
- Test: `skills/gh-triage-pr/scripts/test_ghtp_workstate.py`

**Interfaces:**
- Consumes: `pr_workstate.py` (Task 1).
- Produces: `ghtp_fetch.mark_addressed(comments, addressed_set)` (pure) and a best-effort `ghtp_reply._record_addressed(...)`.

- [ ] **Step 1: Write the failing test**

Create `skills/gh-triage-pr/scripts/test_ghtp_workstate.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 skills/gh-triage-pr/scripts/test_ghtp_workstate.py`
Expected: FAIL — `mark_addressed` / `count_unresolved_inline` / `_record_addressed` do not exist.

- [ ] **Step 3: Add the fetch-side helpers to `ghtp_fetch.py`**

Add these two module-level functions to `skills/gh-triage-pr/scripts/ghtp_fetch.py` (near the other helpers, before `def main`):

```python
def mark_addressed(comments, addressed_set):
    """Tag each comment with addressed_locally (True if its id is in the
    locally-recorded addressed set). Returns the same list."""
    for c in comments:
        c["addressed_locally"] = str(c.get("id")) in addressed_set
    return comments


def count_unresolved_inline(comments):
    """Human inline comments that are neither resolved upstream nor addressed locally."""
    return sum(
        1
        for c in comments
        if c.get("kind") == "inline"
        and c.get("thread_state", {}).get("is_resolved") is False
        and not c.get("addressed_locally", False)
    )
```

- [ ] **Step 4: Use them in `ghtp_fetch.py:main`**

In `ghtp_fetch.py`, after the inline comment list is fully built and before the
existing `unresolved_human_inline = sum(...)` computation, load the locally
addressed set (best-effort) and apply the helpers. Add:

```python
    # Locally-recorded addressed concerns (best-effort; never break fetch).
    addressed_local = set()
    try:
        import subprocess as _sp

        _pw = os.path.expanduser("~/.claude/skills/gh-comment-cache/scripts/pr_workstate.py")
        if os.path.exists(_pw):
            _r = _sp.run(
                [sys.executable, _pw, "addressed", f"{owner}/{repo}", str(num)],
                capture_output=True, text=True, timeout=15,
            )
            addressed_local = {ln.strip() for ln in _r.stdout.splitlines() if ln.strip()}
    except Exception:
        addressed_local = set()
    mark_addressed(comments, addressed_local)
```

Then replace the existing unresolved computation:

```python
    unresolved_human_inline = sum(
        1
        for c in comments
        if c["kind"] == "inline" and c["thread_state"].get("is_resolved") is False
    )
```

with:

```python
    unresolved_human_inline = count_unresolved_inline(comments)
```

(If the surrounding variable that holds the combined comment list is not named
`comments`, use its actual name; `mark_addressed`/`count_unresolved_inline`
operate on whatever list feeds the unresolved count.)

- [ ] **Step 5: Add the best-effort recorder to `ghtp_reply.py`**

Add to `skills/gh-triage-pr/scripts/ghtp_reply.py` (before `def main`):

```python
def _record_addressed(owner, repo, num, comment_id, script=None):
    """Best-effort: record this concern as addressed in the work-state ledger.
    Never raises — triage must not break if the ledger is unavailable."""
    import subprocess as _sp

    pw = script or os.path.expanduser(
        "~/.claude/skills/gh-comment-cache/scripts/pr_workstate.py"
    )
    if not os.path.exists(pw):
        return
    try:
        _sp.run(
            [sys.executable, pw, "concern", f"{owner}/{repo}", str(num),
             str(comment_id), "--by", "gh-triage-pr"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        pass
```

Ensure `import os` is present in `ghtp_reply.py` (add it if missing). Then, in
`ghtp_reply.py:main`, immediately after the successful reply is posted (right
after the `print(f"Reply posted: ...")` line), call:

```python
    _record_addressed(args.owner, args.repo, args.num, args.comment_id)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 skills/gh-triage-pr/scripts/test_ghtp_workstate.py`
Expected: `ALL PASS`.

- [ ] **Step 7: Sanity — fetch still imports/parses**

Run: `python3 -c "import ast; ast.parse(open('skills/gh-triage-pr/scripts/ghtp_fetch.py').read()); ast.parse(open('skills/gh-triage-pr/scripts/ghtp_reply.py').read()); print('parse OK')"`
Expected: `parse OK`.

- [ ] **Step 8: Commit**

```bash
git add skills/gh-triage-pr/scripts/ghtp_reply.py skills/gh-triage-pr/scripts/ghtp_fetch.py skills/gh-triage-pr/scripts/test_ghtp_workstate.py
git commit -m "ENH: gh-triage-pr records + skips locally-addressed concerns via work-state ledger (issue #5)"
```

---

## Task 3: Acceptance + gate

**Files:** none.

- [ ] **Step 1: Both test suites green**

Run:
```bash
python3 skills/gh-comment-cache/scripts/test_pr_workstate.py
python3 skills/gh-triage-pr/scripts/test_ghtp_workstate.py
```
Expected: `ALL PASS` for both.

- [ ] **Step 2: Durability check — survives a simulated cache clear**

Run:
```bash
tmp=$(mktemp -d); r="$tmp/repo"; mkdir "$r"; git -C "$r" init -q
export PR_WORKSTATE_DIR="$tmp/state" XDG_CACHE_HOME="$tmp/cache"
( cd "$r" && python3 skills/gh-comment-cache/scripts/pr_workstate.py set Foo/Bar 1 --status pushed --at 2026-07-15T00:00:00Z >/dev/null )
rm -rf "$tmp/cache"   # simulate `cache clear`
( cd "$r" && python3 skills/gh-comment-cache/scripts/pr_workstate.py workqueue )
unset PR_WORKSTATE_DIR XDG_CACHE_HOME
```
Expected: the `Foo/Bar#1 … pushed` row still prints after the cache dir was deleted (durable state is in `PR_WORKSTATE_DIR`, not the cache).

- [ ] **Step 3: Report + gate**

Report: ledger `pr_workstate.py` + tests committed; `gh-triage-pr` records addressed concerns on reply and excludes them from its unresolved count on fetch; durability verified. Per `rules/pr-no-unsolicited.md`, do not push without an explicit human request; ask how to land it.

---

## Self-Review

**Spec coverage:**
- Durable DB under `~/.local/state/...`, workspace-keyed, not cache.py → Task 1 `_state_dir`/`_db`. ✔
- `set`/`concern`/`addressed`/`workqueue` → Task 1. ✔
- `workqueue` joins raw_pr_index read-only + degrades gracefully → Task 1 `cmd_workqueue` + tests. ✔
- gh-triage-pr records on reply + skips on fetch → Task 2. ✔
- Best-effort wiring (never breaks triage) → Task 2 `_record_addressed` + fetch try/except + test. ✔
- Durability survives cache clear → Task 3 step 2. ✔

**Placeholder scan:** full code for `pr_workstate.py`, both test files, and the gh-triage-pr edits given; the one conditional ("if the list isn't named `comments`") is a real safeguard, not a placeholder. ✔

**Type consistency:** `mark_addressed`/`count_unresolved_inline`/`_record_addressed` names match across Task 2 edits and its test; `_ws`/`cache_path`/`_db` used consistently in Task 1 and its test. ✔
