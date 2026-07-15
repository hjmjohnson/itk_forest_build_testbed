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
