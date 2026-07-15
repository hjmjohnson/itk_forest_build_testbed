# itk-cleanup-pr-lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single parameterized "lifecycle" skill that orders, gates, and loops over existing `itk-*`/`gh-*` cleanup skills to drive an ITK cleanup change from empty branch to opened draft PR, so the chain is no longer re-derived in prose each session.

**Architecture:** A new skill directory `skills/itk-cleanup-pr-lifecycle/` containing an ordinary `SKILL.md` (the agent-followed contract — no new artifact type, no new runtime) plus two bash helpers: `list-cleanup-patterns.sh` (enumerate eligible payload skills) and `validate-lifecycle-refs.sh` (assert every referenced skill/rule exists). The skill is deployed by symlinking it under `~/.claude/skills/`, exactly like the other `itk-*` skills.

**Tech Stack:** Bash (matching the repo's `detect.sh`/`transform.sh` idiom), Markdown + YAML frontmatter (the skill), git, `gh`.

## Global Constraints

- **Avenue (a) only** — this is ITK PR/issue management; forest/downstream validation is out of scope.
- **Cross-platform** (macOS BSD + Linux GNU): `grep -E` not `-P`; no `sed -i` traps; `#!/usr/bin/env bash`; `set -uo pipefail`.
- **No new framework schema** — reuse the existing v2 frontmatter; composition expressed via `dependencies.skills`. (Decision 2(a).)
- **Ends at draft PR** — step 9 (`gh pr create --draft`); post-PR triage stays a separate `gh-triage-pr` invocation. (Decision 1(a).)
- **`agent-skills` / `doctor` is NOT on PATH** on this machine — validation is the two bash helpers, not `doctor`.
- **Staging hygiene** — stage files explicitly by path; never `git add -A`/`git add .`.
- **Commit prefixes** — kit-repo convention: `ENH:` for the new skill, `DOC:` for docs.
- **Payload family** (skills exposing `detect.sh`, as of this plan): `itk-auto-for-new`, `itk-constexpr-if-constant`, `itk-container-size-to-empty`, `itk-cstyle-to-static-cast`, `itk-ctad-iterator`, `itk-emplace-back-construct`, `itk-equals-default-special-members`, `itk-fillbuffer-over-iterate`, `itk-in-class-member-init`, `itk-iterator-drop-withindex`, `itk-prefer-prefix-increment`, `itk-read-write-image-convenience`, `itk-redundant-void-arg`, `itk-string-find-presence-test`.

---

## File Structure

- `skills/itk-cleanup-pr-lifecycle/SKILL.md` — the lifecycle contract (frontmatter + 9-step body).
- `skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh` — enumerate eligible payload skills; also backs the skill's "no-arg → list patterns" behavior.
- `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh` — assert every skill/rule referenced by the SKILL.md exists; the acceptance test for the contract.
- `skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh` — bash tests for the two helpers.

---

## Task 1: `list-cleanup-patterns.sh` — enumerate eligible payload skills

**Files:**
- Create: `skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh`
- Test: `skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`

**Interfaces:**
- Produces: an executable that prints one eligible payload skill name per line to stdout, sorted; exit 0 if ≥1 found, exit 1 if none. Consumed by Task 2's validator and by the SKILL.md at runtime.

- [ ] **Step 1: Write the failing test**

Create `skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`:

```bash
#!/usr/bin/env bash
# Tests for itk-cleanup-pr-lifecycle helper scripts.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(dirname "$here")"
fail=0
check() { # check <description> <condition-exit-code>
  if [ "$2" -eq 0 ]; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi
}

# --- list-cleanup-patterns.sh ---
out="$(bash "$skill_dir/list-cleanup-patterns.sh")"; rc=$?
check "list-cleanup-patterns.sh exits 0"                 "$([ $rc -eq 0 ] && echo 0 || echo 1)"
grep -qx "itk-container-size-to-empty" <<<"$out"; check "lists itk-container-size-to-empty" $?
grep -qx "itk-emplace-back-construct"  <<<"$out"; check "lists itk-emplace-back-construct"  $?
if grep -qx "itk-start-worktree" <<<"$out"; then check "excludes itk-start-worktree (no detect.sh)" 1; else check "excludes itk-start-worktree (no detect.sh)" 0; fi
if grep -qx "itk-cleanup-pr-lifecycle" <<<"$out"; then check "excludes self" 1; else check "excludes self" 0; fi

echo "----"
[ "$fail" -eq 0 ] && echo "ALL PASS" || { echo "SOME FAILED"; exit 1; }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`
Expected: FAIL — `list-cleanup-patterns.sh` does not exist yet (bash reports "No such file or directory"; the `exits 0` check fails).

- [ ] **Step 3: Write minimal implementation**

Create `skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh`:

```bash
#!/usr/bin/env bash
# List cleanup pattern skills eligible as itk-cleanup-pr-lifecycle payloads:
# every skills/itk-*/ that exposes a detect.sh. One skill name per line, sorted.
# Exit 0 if at least one is found, 1 otherwise.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skills_root="$(dirname "$here")"
found=0
for d in "$skills_root"/itk-*/; do
  name="$(basename "$d")"
  [ "$name" = "itk-cleanup-pr-lifecycle" ] && continue
  [ -f "${d}detect.sh" ] || continue
  echo "$name"
  found=1
done | sort
[ "$found" -eq 1 ]
```

Then: `chmod +x skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh`

- [ ] **Step 4: Run test to verify it passes**

Run: `bash skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`
Expected: PASS — every `list-cleanup-patterns.sh` check prints `ok`.

Note on the `found` subshell: the `for … | sort` pipeline runs the loop in a subshell, so the outer `found` stays 0 and the final `[ "$found" -eq 1 ]` would misreport. Verify the exit code explicitly; if it is wrong, replace the pipeline with an array:

```bash
names=()
for d in "$skills_root"/itk-*/; do
  name="$(basename "$d")"
  [ "$name" = "itk-cleanup-pr-lifecycle" ] && continue
  [ -f "${d}detect.sh" ] || continue
  names+=("$name")
done
printf '%s\n' "${names[@]}" | sort
[ "${#names[@]}" -gt 0 ]
```

Re-run the test; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh \
        skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh
git commit -m "ENH: itk-cleanup-pr-lifecycle enumerates eligible payload skills"
```

---

## Task 2: `validate-lifecycle-refs.sh` — assert referenced skills/rules exist

**Files:**
- Create: `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh`
- Modify: `skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh` (append cases)

**Interfaces:**
- Consumes: `list-cleanup-patterns.sh` (Task 1) — requires ≥1 payload.
- Produces: `validate-lifecycle-refs.sh <SKILL.md>` — exit 0 if every cited `rules/<name>.md` exists, the `itk-start-worktree` skill dir exists, and ≥1 payload is listed; exit 1 with a `MISSING:` line per failure. This is the acceptance test consumed by Task 3.

- [ ] **Step 1: Write the failing test**

Append to `skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`, before the final `echo "----"` block:

```bash
# --- validate-lifecycle-refs.sh ---
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
# A fixture that cites a real rule and a bogus one:
cat >"$tmp/GOOD.md" <<'EOF'
Uses skills/itk-start-worktree and obeys rules/pre-commit-mandatory.md.
EOF
cat >"$tmp/BAD.md" <<'EOF'
Obeys rules/this-rule-does-not-exist.md.
EOF
bash "$skill_dir/validate-lifecycle-refs.sh" "$tmp/GOOD.md"; check "validator PASSES a good fixture" $?
if bash "$skill_dir/validate-lifecycle-refs.sh" "$tmp/BAD.md" >/dev/null 2>&1; then
  check "validator FAILS a bogus-rule fixture" 1
else
  check "validator FAILS a bogus-rule fixture" 0
fi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`
Expected: FAIL — `validate-lifecycle-refs.sh` does not exist; both new checks fail.

- [ ] **Step 3: Write minimal implementation**

Create `skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh`:

```bash
#!/usr/bin/env bash
# Assert every skill/rule referenced by a lifecycle SKILL.md exists on disk.
#   validate-lifecycle-refs.sh <path-to-SKILL.md>
# Checks: (1) each cited rules/<name>.md exists under the deployed rules dir
#             (CLAUDE_RULES_DIR or ~/.claude/rules) — the kit repo's rules/ is
#             gitignored and NOT part of this repo;
#         (2) the itk-start-worktree skill dir exists;
#         (3) at least one eligible payload skill is listed.
# Prints a MISSING: line per failure; exit 1 if any, else 0.
set -uo pipefail
skill_md="${1:?usage: validate-lifecycle-refs.sh <SKILL.md>}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skills_root="$(dirname "$here")"
rc=0

# (1) cited rules resolve at the deployed rules dir (not this repo — rules/ is gitignored here)
rules_dir="${CLAUDE_RULES_DIR:-$HOME/.claude/rules}"
while IFS= read -r rulepath; do
  name="${rulepath#rules/}"
  [ -f "$rules_dir/$name" ] || { echo "MISSING: $rulepath (looked in $rules_dir)"; rc=1; }
done < <(grep -oE 'rules/[a-z0-9-]+\.md' "$skill_md" | sort -u)

# (2) fixed sub-skill
if grep -q 'itk-start-worktree' "$skill_md"; then
  [ -d "$skills_root/itk-start-worktree" ] || { echo "MISSING: skills/itk-start-worktree"; rc=1; }
fi

# (3) at least one payload
if ! bash "$here/list-cleanup-patterns.sh" >/dev/null 2>&1; then
  echo "MISSING: no eligible payload skills (no itk-*/detect.sh found)"; rc=1
fi

[ "$rc" -eq 0 ] && echo "OK: all references resolve"
exit "$rc"
```

Then: `chmod +x skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh`

- [ ] **Step 4: Run test to verify it passes**

Run: `bash skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`
Expected: PASS — including "validator PASSES a good fixture" and "validator FAILS a bogus-rule fixture".

- [ ] **Step 5: Commit**

```bash
git add skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh \
        skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh
git commit -m "ENH: itk-cleanup-pr-lifecycle validates its skill/rule references"
```

---

## Task 3: Author `SKILL.md` — the lifecycle contract

**Files:**
- Create: `skills/itk-cleanup-pr-lifecycle/SKILL.md`

**Interfaces:**
- Consumes: `list-cleanup-patterns.sh`, `validate-lifecycle-refs.sh` (Tasks 1–2), and the referenced skills/rules.
- Produces: the trigger-discoverable lifecycle contract. Validated by `validate-lifecycle-refs.sh` and a YAML frontmatter parse.

- [ ] **Step 1: Write the file**

Create `skills/itk-cleanup-pr-lifecycle/SKILL.md` with exactly this content:

````markdown
---
name: itk-cleanup-pr-lifecycle
version: 1.0.0
purpose: Drive an ITK mechanical-cleanup change from an empty branch to an opened draft PR by ordering, gating, and looping over an existing detect/transform cleanup skill and the pr-* rule gates.
description: >-
  Run a full ITK cleanup-PR lifecycle for one mechanical pattern: create an
  isolated worktree, detect and transform every site of a chosen cleanup skill
  one class at a time until dry, verify, pass the pre-commit and local-test
  gates, then stop at an explicit human gate before opening a single draft PR.
  Parameterized by the cleanup pattern skill (the payload); one lifecycle wraps
  every current and future detect/transform skill. Use when applying a
  mechanical cleanup (container-size-to-empty, declare-then-init, emplace-back,
  etc.) to ITK and shipping it as a draft PR. Trigger on:
  "itk-cleanup-pr-lifecycle", "/itk-cleanup-pr-lifecycle", "cleanup PR
  lifecycle", "run a cleanup to PR".
triggers:
  - itk-cleanup-pr-lifecycle
  - /itk-cleanup-pr-lifecycle
  - cleanup PR lifecycle
user_invocable: true
cmd: false
argument_hint: "<pattern-skill> [scope]"
contract:
  inputs:
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/**"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: true
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
  skills:
    - itk-start-worktree
    # payload cleanup skill is chosen at runtime from the detect/transform
    # family; run list-cleanup-patterns.sh for the eligible set.
  external_tools:
    - git
    - gh
    - pixi
    - pre-commit
  python_packages: []
  scripts:
    - list-cleanup-patterns.sh
    - validate-lifecycle-refs.sh
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Cleanup PR Lifecycle

Order, gate, and loop over existing skills to take ONE mechanical cleanup from an
empty branch to an opened draft PR. This skill is a thin wrapper: at each step it
defers to the referenced skill's own `SKILL.md` (the single source of truth) — it
never re-implements their procedure.

## Argument

`/itk-cleanup-pr-lifecycle <pattern-skill> [scope]`

- `<pattern-skill>` — the cleanup skill to apply (the payload), e.g.
  `itk-container-size-to-empty`. Must be one of the eligible detect/transform
  skills. **No argument → run `list-cleanup-patterns.sh`, print the eligible set,
  and stop.**
- `[scope]` — optional narrowing passed through to the payload: a module path
  (e.g. `Modules/Core/Common`) or a payload-specific filter (e.g.
  `--varname size`). Treat the payload's interface as opaque; read its
  `SKILL.md` for the flags it accepts.

Validate the argument:

```bash
bash "$(dirname "$0")/list-cleanup-patterns.sh" | grep -qx "<pattern-skill>" \
  || { echo "not an eligible cleanup pattern; choose one of:"; \
       bash "$(dirname "$0")/list-cleanup-patterns.sh"; exit 2; }
```

## Steps

Follow in order. Do not skip a **GATE**. State the repo/branch you are acting on
before each consequential command.

### 1. Isolated sandbox
Create a fresh worktree on a new branch off `upstream/main`:
`/itk-start-worktree new:cleanup-<pattern-skill>`
Work only inside the printed `WORKTREE_DIR` for the rest of the lifecycle.

### 2. Detect
Run the payload's detector to get the candidate sites within `[scope]`:
`bash skills/<pattern-skill>/detect.sh <WORKTREE_DIR>`

### 3. Transform — one class at a time, loop until dry
Apply the payload's transform, then re-detect; while candidate sites remain in
scope, transform the **next single pattern class**, confirm it compiles, and
**commit before moving to the next class** (N-Dekker incremental per-commit).
Use the payload's `transform.sh --apply` (or its documented clang-tidy command).
Re-run step 2's detector after each class; the loop ends when it reports zero
sites in scope. (When issue #3's reusable loop construct lands, delegate to it.)

### 4. Verify
`bash skills/<pattern-skill>/detect.sh <WORKTREE_DIR>` shows 0 sites in scope,
the target builds (`pixi run build-ITK`), and `git diff` shows every changed
site is a true instance of the pattern (per the payload's "Common mistakes").

### 5. GATE — pre-commit (rules/pre-commit-mandatory.md)
Run `pre-commit run --all-files`. If any hook reports "files were modified",
stage the fixes, fold them into the relevant commit (`git commit --fixup` +
`git -c sequence.editor=: rebase -i --autosquash upstream/main`), and re-run.
**Do not proceed until exit code is 0.**

### 6. Local test (rules/pr-local-test-first.md)
Build the touched code (minimum: it compiles). If the change touched or added
tests, run them: `ctest --test-dir <build> -V -R '<regex>'`. Fix before
proceeding.

### 7. Finalize commits
Ensure each commit has the correct ITK prefix (`STYLE:`/`COMP:`/`ENH:` per the
payload's guidance), minimal comments (rules/code-comment-minimization.md), and
attribution per rules/commit-attribution.md (no `Co-Authored-By` for AI).

### 8. HUMAN GATE — PR authorization (rules/pr-no-unsolicited.md)
Summarize the change set (pattern, modules touched, commit count) to the user
and ask: *"Local work is complete and tested. Shall I open a single draft PR?"*
**Wait for an explicit human "yes". Never proceed on assumption.**

### 9. Open the draft PR
Only after the human yes: author the body in a file and open a draft
(rules/pr-always-draft.md, rules/pr-message-format.md,
rules/gh-body-file-for-long-text.md):

```bash
gh pr create --draft --repo InsightSoftwareConsortium/ITK --base main \
  --head <fork>:cleanup-<pattern-skill> --title "<PREFIX>: <summary>" \
  --body-file <body.md>
```

## Ends here
Post-PR review handling (reviewer comments, CI, greptile, marking ready) is a
separate `/gh-triage-pr` invocation on a later time horizon — not part of this
lifecycle.

## Self-check
`bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md`
must print `OK: all references resolve`.
````

- [ ] **Step 2: Validate references resolve**

Run: `bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md`
Expected: `OK: all references resolve` (exit 0).

If any `MISSING: rules/<x>.md` appears, the body cited a rule filename that does
not exist under the deployed rules dir (`${CLAUDE_RULES_DIR:-$HOME/.claude/rules}`;
the kit repo's `rules/` is gitignored and not part of this repo) — fix the
citation to the correct filename (the real
rule files are `pre-commit-mandatory.md`, `pr-local-test-first.md`,
`code-comment-minimization.md`, `commit-attribution.md`, `pr-no-unsolicited.md`,
`pr-always-draft.md`, `pr-message-format.md`, `gh-body-file-for-long-text.md`).

- [ ] **Step 3: Validate frontmatter parses as YAML**

Run:
```bash
python3 - <<'PY'
import sys
txt = open("skills/itk-cleanup-pr-lifecycle/SKILL.md").read()
assert txt.startswith("---\n"), "no frontmatter fence"
fm = txt.split("---\n",2)[1]
try:
    import yaml; d = yaml.safe_load(fm)
except ModuleNotFoundError:
    # Minimal fallback: just confirm required keys are present as lines.
    for k in ("name:","triggers:","contract:","dependencies:","deployment:"):
        assert k in fm, f"missing {k}"
    print("frontmatter OK (line-check fallback)"); sys.exit(0)
for k in ("name","triggers","contract","dependencies","deployment"):
    assert k in d, f"missing {k}"
assert d["name"] == "itk-cleanup-pr-lifecycle"
assert d["contract"]["side_effects"]["user_confirmation_required"] is True
print("frontmatter OK")
PY
```
Expected: `frontmatter OK` (or the fallback line).

- [ ] **Step 4: Run the full helper test suite (regression)**

Run: `bash skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh`
Expected: `ALL PASS`.

- [ ] **Step 5: Commit**

```bash
git add skills/itk-cleanup-pr-lifecycle/SKILL.md
git commit -m "ENH: Add itk-cleanup-pr-lifecycle skill (issue #2)"
```

---

## Task 4: Deploy + acceptance trace

**Files:**
- No repo files changed (symlink is machine-local state).

**Interfaces:**
- Consumes: all prior tasks.

- [ ] **Step 1: Deploy the skill (symlink, matching other itk-* skills)**

Run:
```bash
ln -sfn "$(pwd)/skills/itk-cleanup-pr-lifecycle" "$HOME/.claude/skills/itk-cleanup-pr-lifecycle"
ls -l "$HOME/.claude/skills/itk-cleanup-pr-lifecycle"
```
Expected: a symlink pointing at `.../skills/itk-cleanup-pr-lifecycle`.

- [ ] **Step 2: Confirm the no-arg listing behavior end to end**

Run: `bash skills/itk-cleanup-pr-lifecycle/list-cleanup-patterns.sh`
Expected: the 14 payload skills, one per line, sorted, including
`itk-container-size-to-empty`; no `itk-start-worktree`, no self.

- [ ] **Step 3: Acceptance — reference + frontmatter green**

Run:
```bash
bash skills/itk-cleanup-pr-lifecycle/validate-lifecycle-refs.sh skills/itk-cleanup-pr-lifecycle/SKILL.md
bash skills/itk-cleanup-pr-lifecycle/tests/test-helpers.sh
```
Expected: `OK: all references resolve` and `ALL PASS`.

- [ ] **Step 4: Dry-run trace (no mutation)**

Manually confirm the contract is followable without executing it: read
`SKILL.md` top to bottom and verify each step names a real skill/script/rule
(already machine-checked in Step 3) and that steps 5 and 8 are clearly marked
GATEs. No commit — this is a read-only acceptance check.

- [ ] **Step 5: Mark issue #2 ready for closure (do NOT close yet)**

Report to the user: helper scripts + SKILL.md committed, deployed, validators
green. Ask whether to (a) push + open a PR for the kit repo, or (b) leave local.
Per `rules/pr-no-unsolicited.md`, do not push or open any PR without an explicit
human request.

---

## Self-Review

**Spec coverage:**
- Parameterized single lifecycle → Task 3 argument section + Task 1 enumerator. ✔
- 9-step chain with gates 5 & 8 → Task 3 body. ✔
- Loop-until-dry (prose until #3) → Task 3 step 3. ✔
- Reuse `dependencies.skills`, no new schema → Task 3 frontmatter. ✔
- Ends at draft PR; triage out of scope → Task 3 "Ends here". ✔
- Validation without `doctor` → Tasks 1–2 helpers + Task 3 steps 2–3. ✔
- Deployment via symlink → Task 4. ✔

**Placeholder scan:** No TBD/TODO; every script and the SKILL.md body are given in full. ✔

**Type consistency:** `list-cleanup-patterns.sh` and `validate-lifecycle-refs.sh` names are used identically in Tasks 1, 2, 3, 4 and inside the SKILL.md. The `<pattern-skill>` placeholder in the SKILL.md is intentional (runtime argument), not a plan placeholder. ✔
