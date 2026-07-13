---
name: clazy-check
version: 1.0.0
purpose: Run clazy-standalone static analysis on CTK source files.
description: Run clazy-standalone static analysis on CTK source files. Only performs checks and writes log files — does NOT fix anything. Recommends automated and manual fixes for use with /clazy-fix.
triggers:
  - clazy-check
  - /clazy-check
user_invocable: true
cmd: false
argument_hint: "[level0|level1|level2] [qt5|qt6]"
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
  tier: project
  target_projects:
    - ctk
  needs_loader_dir: true
  adapters:
    - claude-code
---

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
clazy-check — Run clazy static analysis on CTK (check only, no fixes)

Usage:
  /clazy-check                  Run level1 checks on Qt6 build (default)
  /clazy-check level0           Run level0 checks only
  /clazy-check level2           Run level2 checks (noisy)
  /clazy-check qt5              Analyze Qt5 build
  /clazy-check qt6              Analyze Qt6 build
```

Run clazy-standalone static analysis on CTK C++ source files. This skill **only** runs checks and produces log files — it does NOT modify source code. It recommends which fixes to apply via `/clazy-fix`.

## Context and Purpose

CTK is the upstream library for **3D Slicer** and other Qt-based medical image analysis tools. Clazy analysis finds:
- **Real bugs** hidden as style warnings (returning-void-expression, incorrect-emit)
- **Performance regressions** from implicit container copies (range-loop-detach, function-args-by-ref)
- **Qt6 portability issues** (qAsConst deprecation, QRegExp removal, signal const qualifiers)
- **Python binding problems** (missing Q_OBJECT breaks qobject_cast and PythonQt scripting)

**C++ standard**: CTK builds with `-std=c++17`.

## Prerequisites

- The superbuild must have completed (via `/ctk-superbuild`) with `CMAKE_OSX_SYSROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk`
- A successful build (via `/clazy-build`) so that `compile_commands.json` is up to date

**IMPORTANT:** Homebrew's `clazy-standalone` reports a phantom resource dir. The `run_clazy_ctk.sh` script resolves the correct LLVM resource dir automatically.

### First-time IDE/LSP setup (run once per machine)

`compile_commands.json` is generated in the inner build dir but clangd needs it at the repo root. Without this, the IDE shows false-positive errors like `'QObject' file not found`:

```bash
# Symlink compile_commands.json to the repo root (Qt6 build is preferred)
ln -sf ~/src/CTK/cmake-build-clazy-qt6/CTK-build/compile_commands.json ~/src/CTK/compile_commands.json

# Create .clangd config so clangd finds it
cat > ~/src/CTK/.clangd << 'EOF'
CompileFlags:
  CompilationDatabase: .
EOF
```

Both files are already listed in `.gitignore`. After creating, restart clangd (VS Code: `Cmd+Shift+P` → "clangd: Restart language server").

## Steps

### Step 1: Determine check level and flags

Use the argument as the clazy check level. If no argument is provided, default to `level0`.

Valid levels: `level0`, `level1`, `level2`, `manual`, or a comma-separated list of specific checks (e.g., `connect-by-name,qstring-allocations`).

Additional flags to consider:
- If the user asks for a fresh/full scan, add `--all`
- If the user wants YAML fix files exported for `/clazy-fix`, add `--export-fixes` (`-f`)
- If the user wants to list available auto-fixes from a previous export, use `--list-fixes` (`-L`)

### Step 2: Run the clazy script

```bash
bash /Users/johnsonhj/src/CTK/.claude/skills/clazy-check/run_clazy_ctk.sh [FLAGS] [LEVEL]
```

| Flag | Purpose |
|------|---------|
| `LEVEL` (positional) | Clazy level or comma-separated checks. Default: `level0` |
| `-s, --src-dir DIR` | CTK source directory (default: `~/src/CTK`) |
| `-b, --bld-dir DIR` | CTK inner build directory |
| `-j, --jobs N` | Parallel clazy jobs (default: CPU count) |
| `-a, --all` | Force fresh scan of all files, ignoring narrowed list |
| `-f, --export-fixes` | Export YAML fix files, split by check name |
| `-L, --list-fixes` | List available check names from exported fixes |
| `-h, --help` | Show help |

This may take several minutes. Run it in the background if the user doesn't need immediate results.

**IMPORTANT:** Do NOT use `-F` (apply-fixes) from this skill. Applying fixes is the responsibility of `/clazy-fix`.

### Step 3: Summarize results

After clazy finishes, the script automatically:
1. Narrows the per-level file list to only files with warnings
2. If `--export-fixes` was used: splits YAML fix files by check name

Parse the log file and report:

```bash
CLAZY_LOG="$(ls -t ~/src/CTK/cmake-build-clazy-qt6/CTK-build/clazy-*.log | head -1)"

# Total warnings
grep -c 'warning:' "${CLAZY_LOG}"

# Breakdown by check name
grep -oE '\[-Wclazy-[^]]+' "${CLAZY_LOG}" | sed 's/\[-Wclazy-//' | sort | uniq -c | sort -rn

# Top 10 files with most warnings
grep 'warning:' "${CLAZY_LOG}" | cut -d: -f1 | sort | uniq -c | sort -rn | head -10
```

Report:
1. Total number of warnings
2. Breakdown by check name with counts
3. Top 10 files with the most warnings
4. If `--export-fixes` was used: which checks have auto-fixes available and how many files

### Step 4: Recommend fixes for /clazy-fix

Categorize each check into one of these recommendation tiers:

**Tier 1 — High-value mechanical fixes (use `/clazy-fix <check>`):**
Checks with clear, safe fix patterns that improve code quality. Listed roughly in priority order:

| Check | Why it matters | Volume in CTK |
|-------|---------------|---------------|
| `incorrect-emit` | Correctness — missing/wrong emit | low |
| `const-signal-or-slot` | Correctness — const signals are invalid | low |
| `returning-void-expression` | **Often a real bug** — signal after return is dead code | low-medium |
| `missing-qobject-macro` | Correctness — breaks PythonQt scripting (critical for Slicer) | low |
| `global-const-char-pointer` | Correctness — pointer should be const-to-const | low |
| `non-pod-global-static` | Safety — crashes at static dtor time, Qt startup | low-medium |
| `range-loop-detach` | Performance — avoid implicit container copy in range-for | medium |
| `range-loop-reference` | Performance — avoid copy of loop variable | medium |
| `use-static-qregularexpression` | Performance — avoid recompiling regex each call | medium |
| `function-args-by-ref` | Performance — avoid copy of implicitly-shared Qt types | high |
| `function-args-by-value` | Performance — avoid ref to cheap/trivial types | medium |
| `container-anti-pattern` | Performance — avoid `.values()`, `.keys()` temp lists | medium |
| `connect-not-normalized` | Correctness — SIGNAL/SLOT mismatch causes silent connect failure | low |
| `unused-non-trivial-variable` | Code quality — dead code with non-trivial ctor/dtor | low |
| `strict-iterators` | Correctness — using non-const iterator detaches COW container | low |
| `qmap-with-pointer-key` | Correctness/Performance — pointer ordering in QMap is non-deterministic | low |
| `qproperty-without-notify` | Correctness — QML/Python bindings miss updates without NOTIFY | medium |
| `detaching-temporary` | Performance — avoid detaching implicit copy of temporary | low |

**Tier 2 — Requires care (inform user of trade-offs):**
- `connect-by-name` — requires slot renaming or connect() rewrite; affects UI files
- `child-event-qobject-cast` — use qobject_cast in childEvent
- `readlock-detaching` — careful with lock scope

**Tier 3 — Skip by default (informational only):**
Checks that require API changes or are too risky for automated fixing:
- `overloaded-signal` — requires signal renaming (ABI break). **Skip unless user explicitly asks.**
- `no-module-include` — risky without knowing exact class includes. **Skip unless user explicitly asks.**
- `overridden-signal` — design issue, requires careful analysis

**Known false-positive checks (document but do not fix):**
- `fully-qualified-moc-types` — In CTK, ALL ~490 warnings are false positives. CTK types like `ctkFoo` are in global namespace (no CTK:: prefix); clazy incorrectly flags them. Confirmed false positive — do NOT fix.

Present the recommendation as a prioritized list with estimated effort.

Tell the user the log file path so they can reference it in subsequent `/clazy-fix` invocations.

## File List Behavior

The script maintains two kinds of file lists in the build directory:

- **`clazy_all_files.list`** — master list of all `.cpp` files (NUL-delimited). Regenerated if missing.
- **`clazy_<LEVEL>_files.list`** — per-level list, narrows to only files with warnings after each run.

This means:
- First run at a level: scans all files
- Subsequent runs: scans only files that had warnings previously
- `--all` flag: resets a level's list back to the full master list

## Arguments

Optional: the clazy check level or comma-separated check names.

Examples:
- `/clazy-check` — runs level0 (default)
- `/clazy-check level1` — runs level1 checks
- `/clazy-check level2` — runs level2 checks (expect ~10,000+ warnings, several minutes)
- `/clazy-check --all level0` — force full rescan
- `/clazy-check -f level0` — export auto-fix YAMLs
- `/clazy-check -L level0` — list available auto-fixes
- `/clazy-check connect-by-name,qstring-allocations` — specific checks only

## Level Warning Counts (approximate, for CTK as of 2026-03)

| Level | Total warnings | Notes |
|-------|---------------|-------|
| level0 | ~40 | All fixed on `apply_clazy_skills` branch |
| level1 | ~350 | All Tier 1 fixed on `apply_clazy_skills` branch |
| level2 | ~10,900 | Many are `function-args-by-ref` (335), `function-args-by-value` (161), `container-anti-pattern` |

When reporting level2 results, warn the user that it produces a large log and suggest working through checks one at a time with `/clazy-fix`.
