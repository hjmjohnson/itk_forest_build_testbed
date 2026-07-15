# pr_gate.py Structural Gate Hook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Structurally enforce three gates via a Claude Code PreToolUse hook — `pre-commit` clean on `git push`, `--draft` on `gh pr create`, and a recorded human approval before `gh pr create` — so the gates that `itk-cleanup-pr-lifecycle` and the `rules/` document can no longer be silently skipped.

**Architecture:** One Python module `~/src/agent-skills/bin/pr_gate.py` with three CLI modes (`hook`, `approve`, `record-precommit`), mirroring `ferpa-pre-hook.py`'s stdin/exit-code contract and fail-open discipline. Wired globally into `~/.claude/settings.json` alongside the FERPA hook. `itk-cleanup-pr-lifecycle` (kit repo) records the markers at its gates.

**Tech Stack:** Python 3 (stdlib only), git, pre-commit, Claude Code hooks, JSON settings.

## Global Constraints

- **Fail-open** — any exception, empty/malformed stdin, or unrelated command → allow (exit 0). A global Bash hook must never fail closed. Tests assert this explicitly.
- **Touch only** `git push` and `gh pr create`; every other command returns allow immediately.
- **Hook I/O contract** (from `ferpa-pre-hook.py`): read `{"tool_name","tool_input","cwd"}` on stdin; **exit 0 = allow**, **exit 2 + message on stderr = deny**.
- **State** at `~/.local/state/agent-skills/pr-gate/` (dir `0700`, files `0600`); overridable via `PR_GATE_STATE_DIR` (for tests). Approval TTL via `PR_GATE_APPROVAL_TTL_MIN` (default 60).
- **Cross-repo:** `pr_gate.py` + tests commit in the **agent-skills** repo (`~/src/agent-skills`); the lifecycle edit commits in the **kit** repo; `~/.claude/settings.json` is machine-local (edit via the `update-config` skill).
- **Do not modify `ferpa-pre-hook.py`** or its wiring; the new hook runs *in addition*.
- Stdlib only (no pip deps). Stage explicitly. Commit prefix `ENH:` (kit repo) / match agent-skills convention (also `ENH:`).

---

## File Structure

- `~/src/agent-skills/bin/pr_gate.py` — the module (hook + approve + record-precommit).
- `~/src/agent-skills/bin/test_pr_gate.py` — standalone test runner (plain python, no pytest).
- `~/.claude/settings.json` — MODIFY: append the hook to the existing PreToolUse `Bash` matcher.
- `skills/itk-cleanup-pr-lifecycle/SKILL.md` (kit repo) — MODIFY: steps 5 & 8 record the markers.

---

## Task 1: `pr_gate.py` + tests (agent-skills repo)

**Files:**
- Create: `~/src/agent-skills/bin/pr_gate.py`
- Test: `~/src/agent-skills/bin/test_pr_gate.py`

**Interfaces:**
- Produces: CLI `python3 pr_gate.py {hook|approve|record-precommit}`; importable `_decision(command, cwd) -> (allow: bool, reason: str|None)`, `_approval_path`, `_precommit_path`, `cmd_approve`, `cmd_record_precommit`.

- [ ] **Step 1: Write the failing test**

Create `~/src/agent-skills/bin/test_pr_gate.py`:

```python
#!/usr/bin/env python3
"""Standalone tests for pr_gate.py. Run: python3 test_pr_gate.py"""
import os, subprocess, sys, tempfile, time, importlib.util, json

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("pr_gate", os.path.join(HERE, "pr_gate.py"))
pr = importlib.util.module_from_spec(spec); spec.loader.exec_module(pr)

FAIL = 0
def check(desc, ok):
    global FAIL
    print(("ok   - " if ok else "FAIL - ") + desc)
    if not ok: FAIL = 1

def git(cwd, *a): subprocess.run(["git","-C",cwd,*a], check=True, capture_output=True, text=True)

def new_repo(tmp, with_config):
    r = os.path.join(tmp, "repo"); os.makedirs(r)
    git(r,"init","-q"); git(r,"config","user.email","t@t"); git(r,"config","user.name","t")
    open(os.path.join(r,"f.txt"),"w").write("x")
    if with_config: open(os.path.join(r,".pre-commit-config.yaml"),"w").write("repos: []\n")
    git(r,"add","-A"); git(r,"commit","-q","-m","initial")
    return r

def head(r): return subprocess.run(["git","-C",r,"rev-parse","HEAD"],capture_output=True,text=True).stdout.strip()

def main():
    tmp = tempfile.mkdtemp()
    os.environ["PR_GATE_STATE_DIR"] = os.path.join(tmp, "state")

    # unrelated / fail-open
    check("unrelated command allows", pr._decision("ls -la", tmp)[0] is True)
    check("git status allows", pr._decision("git status", tmp)[0] is True)

    # git push, no pre-commit config -> allow
    r0 = new_repo(tempfile.mkdtemp(), with_config=False)
    check("push w/o pre-commit config allows", pr._decision("git push origin main", r0)[0] is True)

    # git push, config present, no marker -> deny
    r1 = new_repo(tempfile.mkdtemp(), with_config=True)
    allow, reason = pr._decision("git push origin HEAD", r1)
    check("push w/ config, no marker denies", allow is False and "pre-commit" in reason)

    # record marker -> push allows
    open(pr._precommit_path(*_rb(r1)), "w").write("ok")
    check("push after marker allows", pr._decision("git push origin HEAD", r1)[0] is True)

    # move HEAD -> marker stale -> deny
    open(os.path.join(r1,"g.txt"),"w").write("y"); git(r1,"add","-A"); git(r1,"commit","-q","-m","more")
    check("push after new commit (stale marker) denies", pr._decision("git push", r1)[0] is False)

    # fixup HEAD -> deny
    r2 = new_repo(tempfile.mkdtemp(), with_config=True)
    git(r2,"commit","-q","--allow-empty","-m","fixup! initial")
    allow, reason = pr._decision("git push", r2)
    check("push with fixup! HEAD denies", allow is False and "fixup" in reason.lower())

    # gh pr create without --draft -> deny
    r3 = new_repo(tempfile.mkdtemp(), with_config=False)
    allow, reason = pr._decision("gh pr create --title x --body y", r3)
    check("gh pr create w/o --draft denies", allow is False and "draft" in reason.lower())

    # gh pr create --draft, no approval -> deny
    allow, reason = pr._decision("gh pr create --draft --title x", r3)
    check("gh pr create --draft w/o approval denies", allow is False and "approval" in reason.lower())

    # approve -> allow
    cwd0 = os.getcwd(); os.chdir(r3)
    try: pr.cmd_approve("human said yes")
    finally: os.chdir(cwd0)
    check("gh pr create --draft after approve allows", pr._decision("gh pr create --draft", r3)[0] is True)

    # expired approval -> deny
    os.environ["PR_GATE_APPROVAL_TTL_MIN"] = "0"
    root,branch,_ = _rb(r3); p = pr._approval_path(root,branch)
    os.utime(p, (time.time()-3600, time.time()-3600))
    check("expired approval denies", pr._decision("gh pr create --draft", r3)[0] is False)
    os.environ["PR_GATE_APPROVAL_TTL_MIN"] = "60"

    # fail-open: malformed stdin via CLI hook -> exit 0
    proc = subprocess.run([sys.executable, os.path.join(HERE,"pr_gate.py"),"hook"],
                          input="not json", capture_output=True, text=True)
    check("hook fail-open on malformed stdin (exit 0)", proc.returncode == 0)

    # end-to-end deny via CLI hook -> exit 2
    payload = json.dumps({"tool_name":"Bash","tool_input":{"command":"gh pr create"},"cwd":r3})
    proc = subprocess.run([sys.executable, os.path.join(HERE,"pr_gate.py"),"hook"],
                          input=payload, capture_output=True, text=True)
    check("hook denies (exit 2) on gh pr create w/o draft", proc.returncode == 2)

    print("----"); print("ALL PASS" if FAIL==0 else "SOME FAILED")
    sys.exit(FAIL)

def _rb(r):
    root = subprocess.run(["git","-C",r,"rev-parse","--show-toplevel"],capture_output=True,text=True).stdout.strip()
    branch = subprocess.run(["git","-C",r,"rev-parse","--abbrev-ref","HEAD"],capture_output=True,text=True).stdout.strip()
    return root, branch, head(r)

if __name__ == "__main__": main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 ~/src/agent-skills/bin/test_pr_gate.py`
Expected: FAIL — `pr_gate.py` does not exist (import error).

- [ ] **Step 3: Write the implementation**

Create `~/src/agent-skills/bin/pr_gate.py`:

```python
#!/usr/bin/env python3
"""
pr_gate.py — structural enforcement of PR / pre-commit gates for Claude Code.

Modes:
  pr_gate.py hook              PreToolUse hook (JSON on stdin; exit 2 = deny).
  pr_gate.py approve [--reason TEXT]
                               Record human PR approval for the current repo+branch.
  pr_gate.py record-precommit  Run `pre-commit run --all-files`; on success record a
                               marker for the current HEAD sha.

Gates (hook mode):
  git push      -> deny unless a pre-commit marker exists for the current HEAD
                   (no-op where there is no .pre-commit-config.yaml); deny if HEAD
                   is a fixup!/squash! commit.
  gh pr create  -> deny unless --draft/-d present AND a fresh approval marker
                   exists for the current repo+branch (TTL PR_GATE_APPROVAL_TTL_MIN,
                   default 60 min).

Fail-open: any error / unparseable input / unrelated command -> allow.
State: ${PR_GATE_STATE_DIR:-~/.local/state/agent-skills/pr-gate} (0700).
"""
import hashlib, json, os, re, subprocess, sys, time

STATE_DIR = os.environ.get("PR_GATE_STATE_DIR") or os.path.expanduser(
    "~/.local/state/agent-skills/pr-gate")

GIT_PUSH = re.compile(r"\bgit\s+push\b")
GH_PR_CREATE = re.compile(r"\bgh\s+pr\s+create\b")
DRAFT_FLAG = re.compile(r"(?:^|\s)(?:--draft|-d)(?:[=\s]|$)")
FIXUP_SUBJECT = re.compile(r"^(?:fixup|squash)!")


def _state_dir():
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    return STATE_DIR


def _git(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", cwd, *args],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _repo_branch(cwd):
    root = _git(cwd, "rev-parse", "--show-toplevel")
    if not root:
        return None, None, None
    return root, _git(cwd, "rev-parse", "--abbrev-ref", "HEAD"), _git(cwd, "rev-parse", "HEAD")


def _key(repo_root, branch):
    return hashlib.sha256((repo_root + "\0" + (branch or "")).encode()).hexdigest()[:16]


def _approval_path(repo_root, branch):
    return os.path.join(_state_dir(), f"approved-{_key(repo_root, branch)}")


def _precommit_path(repo_root, branch, head):
    return os.path.join(_state_dir(), f"precommit-{_key(repo_root, branch)}-{head}")


def _decision(command, cwd):
    """Return (allow: bool, reason: str|None). Pure — no exit."""
    if GIT_PUSH.search(command):
        root, branch, head = _repo_branch(cwd)
        if root and head and os.path.exists(os.path.join(root, ".pre-commit-config.yaml")):
            subject = _git(cwd, "log", "-1", "--format=%s") or ""
            if FIXUP_SUBJECT.match(subject):
                return False, ("pr-gate: HEAD is a fixup!/squash! commit — autosquash "
                               "before pushing (pre-commit-mandatory).")
            if not os.path.exists(_precommit_path(root, branch, head)):
                return False, ("pr-gate: pre-commit-mandatory — no recorded pre-commit pass "
                               "for this HEAD.\nRun:  python3 "
                               "~/src/agent-skills/bin/pr_gate.py record-precommit\n"
                               "against this exact tree, then push.")
    if GH_PR_CREATE.search(command):
        if not DRAFT_FLAG.search(command):
            return False, "pr-gate: pr-always-draft — add --draft to gh pr create."
        root, branch, _ = _repo_branch(cwd)
        if root:
            path = _approval_path(root, branch)
            ttl = float(os.environ.get("PR_GATE_APPROVAL_TTL_MIN", "60")) * 60
            fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) <= ttl
            if not fresh:
                return False, (f"pr-gate: pr-no-unsolicited — no fresh human approval for "
                               f"'{branch}'.\nAfter the human authorizes THIS PR, run:\n"
                               "  python3 ~/src/agent-skills/bin/pr_gate.py approve\nthen retry.")
    return True, None


def cmd_hook():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        data = json.loads(raw)
        if data.get("tool_name") != "Bash":
            sys.exit(0)
        command = (data.get("tool_input") or {}).get("command", "")
        if not command:
            sys.exit(0)
        cwd = data.get("cwd") or os.getcwd()
        allow, reason = _decision(command, cwd)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-open
    if not allow:
        print(reason, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


def cmd_approve(reason):
    root, branch, _ = _repo_branch(os.getcwd())
    if not root:
        print("pr_gate: not a git repository; nothing to approve", file=sys.stderr)
        return 1
    path = _approval_path(root, branch)
    with open(path, "w") as fh:
        fh.write((reason or "") + "\n")
    os.chmod(path, 0o600)
    print(f"pr_gate: recorded PR approval for {branch} ({os.path.basename(path)})")
    return 0


def cmd_record_precommit():
    root, branch, head = _repo_branch(os.getcwd())
    if not root:
        print("pr_gate: not a git repository", file=sys.stderr)
        return 1
    if not os.path.exists(os.path.join(root, ".pre-commit-config.yaml")):
        print("pr_gate: no .pre-commit-config.yaml; nothing to record")
        return 0
    try:
        rc = subprocess.run(["pre-commit", "run", "--all-files"], cwd=root).returncode
    except FileNotFoundError:
        print("pr_gate: pre-commit not installed", file=sys.stderr)
        return 1
    if rc != 0:
        print("pr_gate: pre-commit FAILED; marker NOT written", file=sys.stderr)
        return rc
    path = _precommit_path(root, branch, head)
    with open(path, "w") as fh:
        fh.write("ok\n")
    os.chmod(path, 0o600)
    print(f"pr_gate: recorded pre-commit pass for {head[:10]}")
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    mode = argv[0]
    if mode == "hook":
        cmd_hook()
        return 0
    if mode == "approve":
        reason = None
        if "--reason" in argv:
            i = argv.index("--reason")
            reason = argv[i + 1] if i + 1 < len(argv) else None
        return cmd_approve(reason)
    if mode == "record-precommit":
        return cmd_record_precommit()
    print(f"pr_gate: unknown mode {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Then: `chmod +x ~/src/agent-skills/bin/pr_gate.py`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 ~/src/agent-skills/bin/test_pr_gate.py`
Expected: every check `ok`, final `ALL PASS`, exit 0.

- [ ] **Step 5: Commit (in the agent-skills repo)**

```bash
git -C ~/src/agent-skills add bin/pr_gate.py bin/test_pr_gate.py
git -C ~/src/agent-skills commit -m "ENH: Add pr_gate.py structural PR/pre-commit gate hook (itk_forest_build_testbed#4)"
```

---

## Task 2: Wire the hook into `~/.claude/settings.json`

**Files:**
- Modify: `~/.claude/settings.json` (machine-local; use the `update-config` skill).

**Interfaces:** none (config).

- [ ] **Step 1: Add the hook command to the existing PreToolUse `Bash` matcher**

The existing PreToolUse entry matches `Read|Write|Bash|WebFetch|...` and runs `ferpa-pre-hook.py`. Add a SECOND `command` hook so both run. Two valid shapes: (a) append `{"type":"command","command":"python3 /home/johnsonhj/src/agent-skills/bin/pr_gate.py hook"}` to the existing entry's `hooks` array (it already matches Bash), or (b) add a new matcher entry `{"matcher":"Bash","hooks":[{...pr_gate...}]}`. Prefer (a) — reuse the matcher that already includes Bash. Use the `update-config` skill to apply the edit safely.

- [ ] **Step 2: Verify wiring — pr_gate present, FERPA intact, JSON valid**

Run:
```bash
python3 - <<'PY'
import json, os
d = json.load(open(os.path.expanduser("~/.claude/settings.json")))
cmds = [h["command"] for e in d["hooks"]["PreToolUse"] for h in e["hooks"]]
assert any("pr_gate.py hook" in c for c in cmds), "pr_gate hook not wired"
assert any("ferpa-pre-hook.py" in c for c in cmds), "FERPA hook missing (must be intact)"
print("wiring OK:", [c.split('/')[-1] for c in cmds])
PY
```
Expected: `wiring OK: [...]` listing both `ferpa-pre-hook.py` and `pr_gate.py hook ...`.

- [ ] **Step 3: Live smoke — hook denies a bad command via the real path**

Run:
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"gh pr create"},"cwd":"'"$HOME/src/itk_forest_build_testbed"'"}' \
  | python3 ~/src/agent-skills/bin/pr_gate.py hook; echo "exit=$?"
```
Expected: a `pr-gate: pr-always-draft ...` message on stderr and `exit=2`.

(No commit — `~/.claude/settings.json` is machine-local state.)

---

## Task 3: Record the markers in `itk-cleanup-pr-lifecycle` (kit repo)

**Files:**
- Modify: `skills/itk-cleanup-pr-lifecycle/SKILL.md` (kit repo).

**Interfaces:** Consumes `pr_gate.py approve` / `record-precommit`.

- [ ] **Step 1: Record pre-commit pass at step 5**

In `skills/itk-cleanup-pr-lifecycle/SKILL.md`, replace this exact block:

```
### 5. GATE — pre-commit (rules/pre-commit-mandatory.md)
Run `pre-commit run --all-files`. If any hook reports "files were modified",
stage the fixes, fold them into the relevant commit (`git commit --fixup` +
`git -c sequence.editor=: rebase -i --autosquash upstream/main`), and re-run.
**Do not proceed until exit code is 0.**
```

with:

```
### 5. GATE — pre-commit (rules/pre-commit-mandatory.md)
Run `python3 ~/src/agent-skills/bin/pr_gate.py record-precommit` — it runs
`pre-commit run --all-files` and records a pass marker for the current HEAD. If
any hook reports "files were modified", stage the fixes, fold them into the
relevant commit (`git commit --fixup` + `git -c sequence.editor=: rebase -i
--autosquash upstream/main`), and re-run `record-precommit`. **Do not proceed
until it exits 0.** (The push in step 9's era is blocked by the pr_gate hook
until this marker exists for the exact HEAD being pushed.)
```

- [ ] **Step 2: Record approval at step 8**

Replace this exact block:

```
### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
Summarize the change set (pattern, modules touched, commit count) to the user
and ask: *"Local work is complete and tested. Shall I open a single draft PR?"*
**Wait for an explicit human "yes". Never proceed on assumption.**
```

with:

```
### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
Summarize the change set (pattern, modules touched, commit count) to the user
and ask: *"Local work is complete and tested. Shall I open a single draft PR?"*
**Wait for an explicit human "yes". Never proceed on assumption.** ONLY after the
human authorizes THIS PR, run `python3 ~/src/agent-skills/bin/pr_gate.py approve`
to record the approval the pr_gate hook requires before `gh pr create`.
```

- [ ] **Step 3: Validate the lifecycle still resolves and references pr_gate**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
grep -c 'pr_gate.py' skills/itk-cleanup-pr-lifecycle/SKILL.md
```
Expected: `OK: all references resolve`, then `2` (record-precommit at step 5, approve at step 8).

- [ ] **Step 4: Commit (in the kit repo)**

```bash
git add skills/itk-cleanup-pr-lifecycle/SKILL.md
git commit -m "ENH: itk-cleanup-pr-lifecycle records pr_gate markers at its gates (issue #4)"
```

---

## Task 4: Acceptance + gate

**Files:** none.

- [ ] **Step 1: Full test suite green**

Run: `python3 ~/src/agent-skills/bin/test_pr_gate.py`
Expected: `ALL PASS`.

- [ ] **Step 2: End-to-end allow-path smoke (temp repo)**

Run:
```bash
tmp=$(mktemp -d); r="$tmp/repo"; mkdir "$r"; git -C "$r" init -q
git -C "$r" config user.email t@t; git -C "$r" config user.name t
: > "$r/.pre-commit-config.yaml"; echo x > "$r/f"; git -C "$r" add -A; git -C "$r" commit -qm init
# push denied before marker:
echo '{"tool_name":"Bash","tool_input":{"command":"git push"},"cwd":"'"$r"'"}' | python3 ~/src/agent-skills/bin/pr_gate.py hook; echo "no-marker exit=$?"
# record marker, then allowed:
( cd "$r" && python3 ~/src/agent-skills/bin/pr_gate.py record-precommit ) 2>/dev/null || true
key=$(python3 - "$r" <<'PY'
import hashlib,subprocess,sys
r=sys.argv[1]
root=subprocess.run(["git","-C",r,"rev-parse","--show-toplevel"],capture_output=True,text=True).stdout.strip()
br=subprocess.run(["git","-C",r,"rev-parse","--abbrev-ref","HEAD"],capture_output=True,text=True).stdout.strip()
h=subprocess.run(["git","-C",r,"rev-parse","HEAD"],capture_output=True,text=True).stdout.strip()
k=hashlib.sha256((root+chr(0)+br).encode()).hexdigest()[:16]
print(f"precommit-{k}-{h}")
PY
)
touch "$HOME/.local/state/agent-skills/pr-gate/$key"
echo '{"tool_name":"Bash","tool_input":{"command":"git push"},"cwd":"'"$r"'"}' | python3 ~/src/agent-skills/bin/pr_gate.py hook; echo "with-marker exit=$?"
```
Expected: `no-marker exit=2` then `with-marker exit=0` (record-precommit writes the marker itself when pre-commit is installed; the explicit `touch` covers the no-pre-commit-installed case).

- [ ] **Step 3: Report + gate**

Report: `pr_gate.py` + tests committed in agent-skills; hook wired into `~/.claude/settings.json` alongside FERPA (FERPA intact); lifecycle records markers at steps 5/8. Note the hook takes effect on the **next** Claude Code session (hooks load at startup). Per `rules/pr-no-unsolicited.md`, do not push either repo or open any PR without an explicit human request; ask how to land the two repos' commits.

---

## Self-Review

**Spec coverage:**
- pre-commit gate (HEAD-sha marker, no-op without config, fixup guard) → Task 1 `_decision`, Task 3 step 5. ✔
- `--draft` gate → Task 1 `_decision`. ✔
- approval gate (repo+branch marker, TTL) → Task 1 `_decision` + `cmd_approve`, Task 3 step 8. ✔
- Fail-open → Task 1 `cmd_hook` + tests (malformed stdin, unrelated cmd). ✔
- Mirror FERPA I/O contract (exit 2 deny) → Task 1 + Task 2 smoke. ✔
- Wire alongside FERPA, FERPA intact → Task 2. ✔
- State dir + env overrides → Task 1. ✔
- Full test matrix → Task 1 test file. ✔

**Placeholder scan:** `pr_gate.py` and `test_pr_gate.py` are given in full; no TBD/TODO. Task 2's edit uses the `update-config` skill (settings JSON shape varies, so the exact write is delegated to that skill with an explicit verification step). ✔

**Type consistency:** `_decision`, `_approval_path`, `_precommit_path`, `cmd_approve`, `cmd_record_precommit`, state-dir/env names (`PR_GATE_STATE_DIR`, `PR_GATE_APPROVAL_TTL_MIN`) are used identically across the module, the tests, and Tasks 2–4. ✔
