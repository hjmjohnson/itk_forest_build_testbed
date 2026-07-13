---
name: clazy-fix
version: 1.0.0
purpose: Fix one clazy check at a time from /clazy-check results.
description: Fix one clazy check at a time from /clazy-check results. Reads clazy documentation for best practices, fixes all instances, performs a clean rebuild to verify no warnings/errors are introduced, runs the test suite to verify no regressions, and commits one fix class per commit.
triggers:
  - clazy-fix
  - /clazy-fix
user_invocable: true
cmd: false
argument_hint: "<check-name> [qt5|qt6]"
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
    git_required: true
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
clazy-fix — Fix one clazy check at a time, verify with build + tests

Usage:
  /clazy-fix <check-name>               Fix all instances of one check
  /clazy-fix returning-void-expression   Example: fix returning-void-expression
  /clazy-fix function-args-by-ref qt5    Fix in Qt5 build
```

Fix one clazy warning category at a time from a previous `/clazy-check` run. Each fix class gets its own commit, verified by a clean rebuild and test suite run. Verify that the solution will work with Qt5.15 and Qt6.5+, use compiler ifdefs if necessary.

## Context and Purpose

CTK is the upstream library for **3D Slicer** (medical imaging platform) and other Qt-based medical image analysis tools. Clazy fixes improve:
- **Correctness**: `returning-void-expression` and `missing-qobject-macro` hide real bugs
- **Performance**: `function-args-by-ref/value`, `range-loop-detach` avoid needless copies on Qt's implicitly-shared types
- **Qt6 readiness**: `qAsConst()` → `std::as_const()`, `QRegExp` removal, slot signature normalization
- **Downstream confidence**: Slicer, Slicer-based apps, and research tools build against CTK headers — clean clazy output means fewer surprises for consumers

**C++ standard**: CTK builds with `-std=c++17`. All C++17 features (including `std::as_const()`) are available.

## Prerequisites

- A clazy log file must exist from a previous `/clazy-check` run at `<bld-dir>/clazy-<LEVEL>-*.log`
- The CTK build must be working (via `/clazy-build`)
- Clazy check documentation is at `/opt/homebrew/Cellar/clazy/1.17_1/share/doc/clazy/`

## Steps

### Step 1: Identify the target check

If the user specifies a check name (e.g., `container-anti-pattern`), use that.

If no check is specified, find the most recent clazy log and pick the highest-frequency fixable check:

```bash
CLAZY_LOG="$(ls -t ~/src/CTK/cmake-build-clazy-qt6/CTK-build/clazy-*.log | head -1)"
grep -oE '\[-Wclazy-[^]]+' "${CLAZY_LOG}" | sed 's/\[-Wclazy-//' | sort | uniq -c | sort -rn
```

Skip already-committed checks (check `git log --oneline` for prior fix commits).
Skip `overloaded-signal` unless the user explicitly asks (requires API/ABI break).
Skip `no-module-include` unless the user explicitly asks (risky).

If the user passes `-a` or `--auto`, check for exported YAML auto-fixes and apply them via `run_clazy_ctk.sh -F <CHECK> <LEVEL>` from the `/clazy-check` skill directory instead of manual editing.

### Step 2: Read the clazy documentation

**MANDATORY** — read the documentation before attempting any fix:

```
/opt/homebrew/Cellar/clazy/1.17_1/share/doc/clazy/<level>/README-<check-name>.md
```

Where `<level>` is one of: `level0`, `level1`, `level2`, `manuallevel`.

Understand:
- What the check detects
- What the correct fix pattern is
- Any edge cases or caveats

Save the full content of the documentation — you will need it for the report in Step 10.

### Step 3: Record baseline state

Before making any changes, record the baseline so regressions can be detected:

1. **Baseline build**: Run a clean build via the superbuild target (required so PythonQt wrappers regenerate correctly):
   ```bash
   BLD_DIR=~/src/CTK/cmake-build-clazy-qt6/CTK-build
   BASELINE_BUILD_LOG="${BLD_DIR}/baseline-build-$(date +%Y%m%d-%H%M%S).log"
   cmake --build "${BLD_DIR}" --target clean 2>&1 > /dev/null
   cmake --build ~/src/CTK/cmake-build-clazy --target CTK -j8 2>&1 | tee "${BASELINE_BUILD_LOG}"
   ```

   **IMPORTANT:** Always use `cmake --build ~/src/CTK/cmake-build-clazy --target CTK` (the superbuild target),
   NOT `cmake --build ${BLD_DIR}` (inner build only). The superbuild target regenerates PythonQt wrappers
   from current headers; the inner build alone does not.

2. **Baseline tests**: Run the test suite and record results:
   ```bash
   BASELINE_TEST_LOG="${BLD_DIR}/baseline-test-$(date +%Y%m%d-%H%M%S).log"
   ctest --test-dir "${BLD_DIR}" --timeout 30 --output-on-failure 2>&1 | tee "${BASELINE_TEST_LOG}"
   ```

3. **Extract baseline counts**:
   ```bash
   BASELINE_ERRORS=$(grep -c ' error:' "${BASELINE_BUILD_LOG}" || echo 0)
   BASELINE_WARNINGS=$(grep ' warning:' "${BASELINE_BUILD_LOG}" | grep -v '\[-Wclazy' | wc -l | tr -d ' ')
   BASELINE_TEST_FAILURES=$(grep -c 'Failed\|SEGFAULT\|SIGTRAP' "${BASELINE_TEST_LOG}" || echo 0)
   ```

### Step 4: Extract all warnings for the target check

```bash
grep "\-Wclazy-<check-name>" "${CLAZY_LOG}" | sort -u
```

Group warnings by file. Count unique source locations (some warnings repeat across translation units for header files). Process one file at a time.

**For large checks (100+ unique warnings across 20+ files):** Use parallel agents dispatched in a single message, each handling a non-overlapping set of files. This is faster than serial editing and avoids context window exhaustion. See "Parallel Agent Strategy" section below.

### Step 5: Fix all instances

For each file with warnings:
1. Read the file
2. Navigate to each warning location
3. Apply the fix pattern from the documentation
4. Move to the next warning in the file

**Fix patterns by check (quick reference):**

| Check | Fix Pattern | Level |
|-------|-------------|-------|
| `container-anti-pattern` | Replace `.values()`, `.keys()`, `.toList()` with direct iteration or appropriate API | level2 |
| `connect-not-normalized` | Normalize SIGNAL/SLOT signatures: remove `const`, `&`, extra spaces | level0 |
| `unused-non-trivial-variable` | Remove unused variable or use `Q_UNUSED()` if intentional | level1 |
| `use-static-qregularexpression` | Make the `QRegularExpression` object `static const` | level2 |
| `strict-iterators` | Replace `find()` with `constFind()`, `begin()`/`end()` with `cbegin()`/`cend()` | level2 |
| `connect-by-name` | Rename `on_*_*` slots or convert to explicit `connect()` calls | level2 |
| `qmap-with-pointer-key` | Replace `QMap<Pointer*, V>` with `QHash<Pointer*, V>` | level2 |
| `fully-qualified-moc-types` | Add namespace prefix to types in Q_PROPERTY, signal, slot, Q_INVOKABLE. **CAUTION**: Often false positives for global-scope types — investigate first. | level2 |
| `qproperty-without-notify` | Add `NOTIFY <prop>Changed` signal + emit in setter, or mark `CONSTANT` | level2 |
| `non-pod-global-static` | Wrap 5+ related globals in a struct + `Q_GLOBAL_STATIC`. Use function-local statics for QString/QStringList. Skip `CTK_SINGLETON_DECLARE_INITIALIZER` patterns. | level1 |
| `incorrect-emit` | Add missing `emit` keyword before signal calls, or remove `emit` from non-signal calls | level0 |
| `const-signal-or-slot` | Remove `const` qualifier from signal/slot declarations | level0 |
| `detaching-temporary` | Avoid calling non-const methods on temporary containers | level2 |
| `range-loop-detach` | Use `std::as_const()` (C++17, preferred) on container in range-for. **NOT** `qAsConst()` — deprecated in Qt 6.6+ | level1 |
| `range-loop-reference` | Use `const auto&` instead of `auto` in range-for loops | level1 |
| `global-const-char-pointer` | `const char* x` → `const char* const x` (pointer itself must be const) | level2 |
| `returning-void-expression` | **This is often a real bug**: `return void_func(); emit signal();` — the emit is dead code. Remove `return`. Check if signal emission was silently skipped. | level2 |
| `missing-qobject-macro` | Add `Q_OBJECT` to QAbstractItemModel subclasses and other Q_OBJECT-dependent classes. Required for signals, slots, qobject_cast, and Python scripting. | level2 |
| `function-args-by-ref` | `Type param` → `const Type& param` for non-trivially-copyable types (QString, QStringList, QVariant, QDateTime, QDomElement, etc.). Change BOTH header declaration AND cpp definition. Skip QSharedPointer/QWeakPointer (per clazy docs). | level2 |
| `function-args-by-value` | Pass-by-value instead of by-reference (opposite of above) — for trivially-copyable types like int, enum, small POD structs. | level2 |

**CRITICAL:** Be careful with `#if QT_VERSION` preprocessor guards — auto-fixes can break these. Always check for preprocessor conditionals near the warning location.

**std::as_const() vs qAsConst():** CTK builds with C++17. Always use `std::as_const()` (from `<utility>`, available since C++17 and included transitively by Qt headers). Do NOT use `qAsConst()` — it is deprecated in Qt 6.6+ and triggers `-Wdeprecated-declarations` warnings.

### Step 6: Clean rebuild to verify

**MANDATORY** — every commit must build cleanly. Use the superbuild target:

```bash
BLD_DIR=~/src/CTK/cmake-build-clazy-qt6/CTK-build
POST_BUILD_LOG="${BLD_DIR}/post-fix-build-$(date +%Y%m%d-%H%M%S).log"
cmake --build "${BLD_DIR}" --target clean 2>&1 > /dev/null
cmake --build ~/src/CTK/cmake-build-clazy --target CTK -j8 2>&1 | tee "${POST_BUILD_LOG}"
```

**Verify no new issues introduced:**
```bash
POST_ERRORS=$(grep -c ' error:' "${POST_BUILD_LOG}" || echo 0)
POST_WARNINGS=$(grep ' warning:' "${POST_BUILD_LOG}" | grep -v '\[-Wclazy' | wc -l | tr -d ' ')

if [ "${POST_ERRORS}" -gt "${BASELINE_ERRORS}" ]; then
  echo "ERROR: New build errors introduced!"
fi
if [ "${POST_WARNINGS}" -gt "${BASELINE_WARNINGS}" ]; then
  echo "WARNING: New compiler warnings introduced!"
fi
```

If the build fails or new warnings appear:
1. Read the errors
2. Fix them
3. Rebuild again
4. Repeat until clean

### Step 7: Run test suite to verify

**MANDATORY** — every commit must not introduce test regressions:

```bash
POST_TEST_LOG="${BLD_DIR}/post-fix-test-$(date +%Y%m%d-%H%M%S).log"
ctest --test-dir "${BLD_DIR}" --timeout 30 --output-on-failure 2>&1 | tee "${POST_TEST_LOG}"
```

Compare against baseline:
```bash
POST_TEST_FAILURES=$(grep -c 'Failed\|SEGFAULT\|SIGTRAP' "${POST_TEST_LOG}" || echo 0)

if [ "${POST_TEST_FAILURES}" -gt "${BASELINE_TEST_FAILURES}" ]; then
  echo "ERROR: New test failures introduced!"
fi
```

If new test failures appear:
1. Identify which tests are new failures (diff against baseline)
2. Fix the root cause
3. Rebuild and retest
4. Repeat until no new failures

### Step 8: Commit

Stage and commit with a descriptive message:

```bash
git add -A && git commit -m "$(cat <<'EOF'
STYLE: Fix clazy <check-name> warnings

<Brief description of what was changed and why, based on the check docs.>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

### Step 9: Report and offer next steps

After committing:
1. Report how many warnings were fixed and in how many files
2. Confirm build is clean (zero new errors/warnings)
3. Confirm test suite has no new failures
4. Show remaining check categories from the log
5. Note any **Slicer downstream impact** (see section below)
6. Offer to fix the next check category with `/clazy-fix`

### Step 10: Update the clazy fix rationale report

**MANDATORY** — after every successful commit, append an entry to the cumulative rationale report.

The report file lives at:
```
~/src/CTK/cmake-build-clazy-qt6/CTK-build/clazy-fix-report.md
```

If the file does not exist, create it with the header (see template below). If it already exists, append a new section for this fix.

**Report template (create on first invocation):**

```markdown
# CTK Clazy Fix Report

Cumulative record of clazy static analysis fixes applied to the CTK codebase.
Each entry documents the rationale, approach, references, and verification results
for one check category.

**Branch**: `apply_clazy_skills`
**Base**: `master`
**Clazy version**: 1.17
**Qt compatibility target**: Qt 5.15 + Qt 6.5+

---
```

**Per-fix entry template (append for each `/clazy-fix` invocation):**

```markdown
## <CHECK-NAME>

**Date**: YYYY-MM-DD
**Commit**: `<short-hash>` — `<commit subject line>`
**Files changed**: N files, +X/-Y lines

### What the check detects

<Summarize from the clazy documentation what this check catches and why it matters.
Include the key paragraph from the clazy README.>

### Warnings found

- **Total warnings in log**: N (M unique source locations)
- **Warnings fixed**: N
- **False positives identified**: N (describe if any)
- **Deliberately skipped**: N (describe if any, e.g. singleton patterns, test files)

### Approach and rationale

<Describe the fix strategy chosen and WHY it was chosen over alternatives.
Include:
- The specific code transformation pattern applied
- Why this pattern is correct for Qt5.15 + Qt6.5+
- Any alternative approaches considered and why they were rejected
- Edge cases encountered and how they were handled
- Any bugs found/fixed incidentally during the fix>

### Slicer downstream impact

<Note any changes that affect virtual method signatures, public API types, or
PythonQt-wrapped classes. Slicer overrides several CTK virtual methods
(e.g. ctkLayoutManager subclasses: qMRMLLayoutViewFactory,
qSlicerSingletonViewFactory). Flag these explicitly so PR reviewers know to
coordinate with the Slicer team.>

### References

- **Clazy documentation**: `/opt/homebrew/Cellar/clazy/1.17_1/share/doc/clazy/<level>/README-<check-name>.md`
- **Qt documentation**: <relevant Qt docs URLs or class names consulted>
- **C++ standard references**: <if applicable, e.g. C++11 magic statics, range-for semantics>
- **Other**: <any other resources consulted>

### Verification

| Metric | Baseline | Post-fix | Delta |
|--------|----------|----------|-------|
| Build errors | 0 | 0 | 0 |
| Build warnings (non-clazy) | 0 | 0 | 0 |
| Test failures | N | N | 0 |
| Total targets built | 942 | 942 | 0 |

---
```

**Guidelines for the report:**

1. **Be specific about rationale.** Don't just say "replaced X with Y." Explain *why* Y is better — performance, thread safety, startup time, Qt version compatibility, etc.

2. **Document false positives.** If a check produced warnings that were investigated and found to be incorrect or inapplicable, document this with the reasoning so future contributors know not to re-investigate.

3. **Document skipped warnings.** If some warnings were deliberately left unfixed (e.g., singleton patterns for `non-pod-global-static`), explain why fixing them would be incorrect or harmful.

4. **Include incidental bug discoveries.** If the fix process uncovered actual bugs (e.g., `return void_func(); emit signal()` making the signal dead code), note these prominently with `BUG:` prefix.

5. **Reference the clazy docs verbatim where helpful.** Quote the key explanation from the clazy README so readers don't need to install clazy to understand the fix.

6. **Keep entries self-contained.** Each entry should be understandable without reading the others.

## Arguments

Optional: the clazy check name to fix, plus optional flags.

- No argument: picks the highest-frequency fixable check
- Check name: fix that specific check
- `-a` or `--auto` prefix: use auto-fix YAMLs from `/clazy-check -f` instead of manual editing

Examples:
- `/clazy-fix` — fix the most common remaining check
- `/clazy-fix container-anti-pattern` — fix all container-anti-pattern warnings
- `/clazy-fix -a fully-qualified-moc-types` — apply auto-fixes for fully-qualified-moc-types
- `/clazy-fix connect-not-normalized` — fix all connect-not-normalized warnings

## Checks to skip by default

- **`overloaded-signal`** — requires signal renaming (API/ABI break). Inform and skip.
- **`no-module-include`** — risky; fix carefully one file at a time if user explicitly asks.
- **`fully-qualified-moc-types`** — investigate first; in CTK all ~490 warnings were confirmed false positives for global-scope types with no namespace (e.g. `ctkFoo`, `QList<ctkFoo*>`). Do not fix.

## Important notes

- Fix ONE check category per invocation. Each check gets its own commit.
- Always read the clazy documentation FIRST.
- Always do a CLEAN rebuild via the **superbuild target** after fixing to catch all issues.
- Always run the test suite after fixing to catch regressions.
- Always update the rationale report after committing.
- Watch for `#if QT_VERSION` guards near warning locations — auto-fixes can break these.
- Some warnings may be false positives. Use judgment and document in the report.
- When warnings come from header files included in many TUs, the log count is inflated. Count unique source locations, not total warnings.
- **Use `std::as_const()` not `qAsConst()`** — qAsConst is deprecated in Qt 6.6+.

## Parallel Agent Strategy (for large checks)

When a check has **100+ unique warnings across 20+ files**, use parallel agents for maximum throughput. Dispatch all agents in a **single message** (to run truly in parallel). Each agent gets a non-overlapping set of files.

**Suggested groupings for level2 checks:**
1. Agent 1: Core library files (`Libs/Core/`)
2. Agent 2: DICOM Core files (`Libs/DICOM/Core/`)
3. Agent 3: DICOM Widget files (`Libs/DICOM/Widgets/`)
4. Agent 4: Widget/Layout files (`Libs/Widgets/`)
5. Agent 5: PluginFramework + Test files

**Key rules for parallel agents:**
- Each agent gets the specific line numbers from the clazy log for its file set
- Agents must update BOTH header declaration AND cpp definition for public methods
- Agents must handle virtual method hierarchies together (base + all derived)
- For `function-args-by-ref`: agents must also check for SIGNAL/SLOT macro strings and update them if the method is a slot (Qt normalizes `const&` → value in signal signatures, so SIGNAL/SLOT strings need NOT change for Qt connection macros)
- After all agents complete, verify with a single clean rebuild

## Known Build Pitfalls

### PythonQt Wrapper Generator (ctkWrapPythonQt.py)

The script `CMake/ctkWrapPythonQt.py` generates PythonQt decorator wrappers. It has a regex to detect pure virtual methods and skip wrapping abstract classes:

**Original (buggy):** `r"virtual[\w\n\s\*\(\)]+\=[\s\n]*(0|NULL|nullptr)[\s\n]*\x3b"`
**Fixed:** `r"virtual[\w\n\s\*\&\(\),:<>]+\=[\s\n]*(0|NULL|nullptr)[\s\n]*\x3b"`

The original regex was missing `&`, `,`, `:`, `<`, `>` from the character class. If a pure virtual method uses `const Type&` parameters or template types (`QList<T>`), the regex fails to match, causing the generator to try `new AbstractClass(parent)` — a compile error. **This was fixed in commit `27c9ab3c`** during the `function-args-by-ref` fix. If the error resurfaces, check this file.

### Superbuild vs Inner Build for Clean Rebuilds

After `cmake --build ${BLD_DIR} --target clean`, always rebuild via:
```bash
cmake --build ~/src/CTK/cmake-build-clazy --target CTK -j8
```
NOT via:
```bash
cmake --build ${BLD_DIR} -j8  # WRONG for clean rebuilds
```
The superbuild re-runs PythonQt wrapper generation, which regenerates `generated_cpp/org_commontk_*/` files from the current headers. The inner build alone skips this step.

### CTK_SET_CPP_EMIT Macro

The macro `CTK_SET_CPP_EMIT` (defined in `ctkPimpl.h`) generates setter implementations that emit a change signal. Clazy cannot see through it, so setters using this macro may produce false-positive warnings. Do not attempt to fix clazy warnings inside `CTK_SET_CPP_EMIT`-generated code.

### Signals Must Keep Pass-by-Value Parameters

Qt signal declarations must use pass-by-value for non-pointer types — not `const&`. The MOC normalizes signal signatures, and changing `void mySignal(QString)` to `void mySignal(const QString&)` is safe for new-style connects but changes the normalized string that old-style SIGNAL() macros produce. **Do not change signal parameter types.**

### IDE/LSP False Positives (clangd "file not found" errors)

After clazy fixes, the IDE (VS Code, CLion, etc.) may show spurious errors like `'QObject' file not found` or `Unknown type name 'QString'`. These are **not real errors** — they are clangd not finding `compile_commands.json`.

**Root cause**: `compile_commands.json` is generated in the inner build directory (`cmake-build-clazy-qt6/CTK-build/`) but clangd searches upward from the source file and needs to find it at the repository root.

**Fix — run once per machine**:
```bash
# Symlink compile_commands.json to the repo root
ln -sf ~/src/CTK/cmake-build-clazy-qt6/CTK-build/compile_commands.json ~/src/CTK/compile_commands.json

# Create .clangd config at repo root
cat > ~/src/CTK/.clangd << 'EOF'
CompileFlags:
  CompilationDatabase: .
EOF

# Both files are already in .gitignore — do not commit them
```

After creating the symlink, restart the LSP server (VS Code: `Cmd+Shift+P` → "clangd: Restart language server").

**Verification**: The cmake builds are the authoritative check. If `cmake --build ... -j8` completes with 0 errors, the code is correct regardless of what the IDE shows.

## Slicer Downstream Impact

CTK is the primary upstream dependency for **3D Slicer**. Changes to public virtual method signatures require coordinated updates in Slicer. Known Slicer classes that override CTK virtual methods:

| CTK base class | CTK virtual method | Slicer override |
|---------------|-------------------|-----------------|
| `ctkLayoutManager` | `viewFromXML()` | `qMRMLLayoutManager::viewFromXML()` |
| `ctkLayoutViewFactory` | `createViewFromXML()` | `qMRMLLayoutViewFactory::createViewFromXML()`, `qSlicerSingletonViewFactory::createViewFromXML()` |
| `ctkLayoutViewFactory` | `isElementSupported()` | Slicer subclasses |
| `ctkDICOMDisplayedFieldGeneratorAbstractRule` | `registerEmptyFieldNames()` | Any Slicer DICOM field rules |

When a fix changes public virtual method signatures, note this explicitly in the commit message and rationale report so Slicer maintainers can coordinate.
