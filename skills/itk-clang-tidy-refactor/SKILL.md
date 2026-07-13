---
name: itk-clang-tidy-refactor
version: 1.0.0
purpose: Run approved clang-tidy modernization and readability checks on ITK source code, one rule per commit, using the project's established wrapper scripts and rule library.
description: >-
  Applies clang-tidy refactoring rules to ITK (and ITK-ecosystem projects like
  BRAINSTools, Slicer, CTK) using the curated rule set in
  ~/scripts/dev/cxx14_updates/. Knows which checks have been merged upstream,
  which are rejected or broken, and which are candidates awaiting evaluation.
  Produces one STYLE: commit per rule following ITK commit conventions.
  Can chain with other ITK refactoring skills (e.g. itk-declare-then-init
  enables const-correctness and auto checks that depend on initialized-at-
  declaration patterns).
triggers:
  - clang-tidy refactor
  - clang tidy ITK
  - modernize ITK code
  - run clang-tidy rule
  - apply clang-tidy check
  - readability refactor
  - performance clang-tidy
  - bugprone check
user_invocable: true
cmd: false
argument_hint: "[rule-name | --list-approved | --list-candidates | --list-rejected]"
contract:
  inputs:
    - "Rule name (clang-tidy check identifier, e.g. modernize-use-auto)"
    - "Optional: --file PATH to restrict to a single file"
    - "Optional: --diff-only to restrict fixes to changed lines only (uses clang-tidy-diff.py)"
    - "Optional: --dry-run to preview without applying"
  outputs:
    - "Modified source files with clang-tidy fixes applied"
    - "One git commit per rule with appropriate STYLE:/PERF:/BUG: prefix"
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/**/*.h"
      - "Modules/**/*.hxx"
      - "Modules/**/*.cxx"
      - "Examples/**/*.cxx"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
  determinism: hybrid
  cache:
    has_cache: false
    cache_root: ""
    schema_version: 0
    rebuildable: false
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills:
    - codebase-search
  external_tools:
    - clang-tidy
    - clang-apply-replacements
    - run-clang-tidy
    - cmake
    - ninja
    - git
  python_packages: []
  scripts:
    - "~/scripts/dev/cxx14_updates/hj-wrapper-clang-tidy.sh"
    - "~/scripts/dev/cxx14_updates/my_itk_clang22_darwin.sh"
deployment:
  tier: always
  target_projects:
    - ITK
    - BRAINSTools
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK clang-tidy Refactoring

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-clang-tidy-refactor — Apply clang-tidy rules to ITK, one per commit

Usage:
  /itk-clang-tidy-refactor modernize-use-auto      Apply one rule
  /itk-clang-tidy-refactor --list-approved          Show merged/approved rules
  /itk-clang-tidy-refactor --list-candidates        Show unevaluated rules
  /itk-clang-tidy-refactor --list-rejected          Show rejected/broken rules
  /itk-clang-tidy-refactor <rule> --dry-run         Preview only
  /itk-clang-tidy-refactor <rule> --file path       Restrict to one file
```

Apply clang-tidy modernization, readability, performance, and bugprone checks
to ITK source code using the project's established wrapper infrastructure.

## Prerequisites

1. A **compile_commands.json** must exist in the build directory. Either:
   - Use an existing clang-tidy build: `~/Dashboard/src/ITK/cmake-build-clangtidy-22/`
   - Or generate one: `cmake -G Ninja -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`

2. The **wrapper scripts** at `~/scripts/dev/cxx14_updates/` must be present:
   - `hj-wrapper-clang-tidy.sh` — main driver (env + rule + optional flags)
   - `my_itk_clang22_darwin.sh` — macOS environment config (Homebrew LLVM 22)
   - `rules/<check-name>.sh` — per-rule commit message definitions

3. **Homebrew LLVM** with clang-tidy 20+ at `/opt/homebrew/opt/llvm/bin/`

## How the Wrapper Works

```bash
# Apply one rule to the entire codebase and commit:
~/scripts/dev/cxx14_updates/hj-wrapper-clang-tidy.sh \
  ~/scripts/dev/cxx14_updates/my_itk_clang22_darwin.sh \
  rules/<check-name>.sh

# Test on a single file (no commit):
~/scripts/dev/cxx14_updates/hj-wrapper-clang-tidy.sh \
  ~/scripts/dev/cxx14_updates/my_itk_clang22_darwin.sh \
  rules/<check-name>.sh --file Modules/Core/Common/include/itkImage.h

# Preview without executing:
~/scripts/dev/cxx14_updates/hj-wrapper-clang-tidy.sh \
  ~/scripts/dev/cxx14_updates/my_itk_clang22_darwin.sh \
  rules/<check-name>.sh --dry-run
```

The wrapper:
1. Sources the environment config (compiler paths, build dir, header filters)
2. Sources the rule file (populates `commit_messages[<rule>]` associative array)
3. Copies `.clang-tidy` backup, injects the single rule via `sed`
4. Runs `run-clang-tidy` with `-fix -format` against the build dir
5. Restores `.clang-tidy` and commits with the rule's predefined message
6. Filters: excludes `ThirdParty/`, targets only ITK module headers

## Diff-Only Mode (Changed Lines Only)

When chaining clang-tidy after another refactoring skill, use **diff-only
mode** to restrict fixes to lines modified by the preceding commit. This
avoids touching unrelated code and keeps the diff reviewable.

Uses LLVM's `clang-tidy-diff.py` which reads a unified diff from stdin and
passes `--line-filter` to clang-tidy so only changed lines produce diagnostics
and fixes.

```bash
# Run all approved checks on only the lines that changed vs main:
CHECKS="-*,modernize-use-auto,misc-const-correctness,readability-qualified-auto"

git diff -U0 main...HEAD | python3 \
  /opt/homebrew/opt/llvm/share/clang/clang-tidy-diff.py \
  -clang-tidy-binary /opt/homebrew/opt/llvm/bin/clang-tidy \
  -p1 \
  -j12 \
  -path build \
  -checks="$CHECKS" \
  -fix

# Run on only the lines changed in the last commit:
git diff -U0 HEAD~1 | python3 \
  /opt/homebrew/opt/llvm/share/clang/clang-tidy-diff.py \
  -clang-tidy-binary /opt/homebrew/opt/llvm/bin/clang-tidy \
  -p1 \
  -j12 \
  -path build \
  -checks="$CHECKS" \
  -fix

# Run on only staged changes (pre-commit check):
git diff -U0 --cached | python3 \
  /opt/homebrew/opt/llvm/share/clang/clang-tidy-diff.py \
  -clang-tidy-binary /opt/homebrew/opt/llvm/bin/clang-tidy \
  -p1 \
  -j12 \
  -path build \
  -checks="$CHECKS" \
  -fix
```

### Whole-File Mode vs Diff-Only Mode

| | Whole-file (`run-clang-tidy`) | Diff-only (`clang-tidy-diff.py`) |
|---|---|---|
| **Scope** | All code in matched translation units | Only lines present in the diff |
| **Use case** | Codebase-wide sweep of one rule | Post-refactoring cleanup on touched lines |
| **Typical diff** | Large (hundreds of files) | Small (only files/lines you already changed) |
| **Risk** | May touch unrelated code | Stays within your change's footprint |
| **Commit pattern** | One rule per commit, whole codebase | One commit for all approved checks on changed lines |

### Known Pitfalls with Diff-Only Mode

- **`-checks` with leading `-*`** — must use `=` syntax (`-checks="-*,rule"`)
  because argparse interprets the leading dash as a flag otherwise.
- **Malformed auto-fixes** — clang-tidy occasionally produces invalid C++ when
  combining multiple fixes on the same line (e.g. `const Type & const var`).
  Always review the diff before committing. Build to verify.
- **`-U0` is required** — the diff must use zero context lines (`-U0`) so
  `clang-tidy-diff.py` can precisely identify changed line ranges.
- **Header fixes** — by default, only diagnostics in source files are fixed.
  To also fix headers, add `-header-filter=.*(Core/Common).*` or similar.

## Approved Rules (Merged to ITK main)

These rules have been applied, reviewed, and merged. They are safe to re-run
on new code or modules that were added after the original pass.

### Modernize

| Rule | PR | Commit message prefix |
|------|----|-----------------------|
| `modernize-use-override` | #5276, #5107, #5908 | `STYLE: Use override statements for C++11` |
| `modernize-use-using` | #5041 | `STYLE: Prefer c++11 'using' to 'typedef'` |
| `modernize-use-nullptr` | `dd6c829`, `e5ebb8c` | `COMP: Use nullptr instead of 0 or NULL` |
| `modernize-use-auto` | `de713e7`, #5570 | `STYLE: Use auto for variable type deduction` |
| `modernize-use-emplace` | #5824, `9c09f5a` | `STYLE: Replace push_back(T(...)) with emplace_back(...)` |
| `modernize-use-equals-default` | `bc66259`, `b21dbbb` | `STYLE: Use default member initialization` |
| `modernize-use-equals-delete` | `48ff882` | (part of C++11 modernization) |
| `modernize-use-bool-literals` | #4983 | `STYLE: Replace integer literals which are cast to bool` |
| `modernize-use-default-member-init` | `b21dbbb` | `STYLE: Use default member initialization` |
| `modernize-loop-convert` | #5038, `48daed0` | `STYLE: Use range-based loops from C++11` |
| `modernize-pass-by-value` | (rule file exists, applied) | `STYLE: modernize-pass-by-value` |
| `modernize-return-braced-init-list` | (rule file exists, applied) | `PERF: Replace explicit return calls of constructor` |
| `modernize-redundant-void-arg` | (marked DONE in order_suggestions) | `STYLE: modernize-redundant-void-arg` |
| `modernize-raw-string-literal` | (marked DONE in order_suggestions) | `STYLE: modernize-raw-string-literal` |
| `modernize-replace-disallow-copy-and-assign-macro` | (ITK-specific `ITK_DISALLOW_COPY_AND_ASSIGN`) | `STYLE: Replace DISALLOW macro with = delete` |
| `modernize-avoid-bind` | `75b9967` | `STYLE: Replace std::bind with lambda expression` |
| `modernize-macro-to-enum` | `1f88a09`, `a5329b3` | `STYLE: Replace preprocessor defines with enums` |
| `modernize-make-unique` | `22bce72` | `STYLE: Replace new by C++14 std::make_unique` |

### Readability

| Rule | PR | Commit message prefix |
|------|----|-----------------------|
| `readability-else-after-return` | #5108 | `STYLE: Reduce indentation else after return` |
| `readability-container-size-empty` | #4985 | `PERF: readability container size empty` |
| `readability-redundant-control-flow` | #5835 | `STYLE: remove redundant control flow` |
| `readability-redundant-casting` | #5807 | `STYLE: Remove redundant casting for same types` |
| `readability-isolate-declaration` | #4996 | `STYLE: One declaration per line for readability` |
| `readability-inconsistent-declaration-parameter-name` | (marked DONE) | `STYLE: Make prototype match definition names` |
| `readability-static-accessed-through-instance` | `45e93bb` | `STYLE: Don't call static functions via instances` |
| `readability-make-member-function-const` | (marked DONE) | (const-qualify member functions) |
| `readability-non-const-parameter` | (marked DONE) | (const-qualify non-mutated pointer params) |
| `readability-misleading-indentation` | (marked DONE) | `STYLE: readability-misleading-indentation` |
| `readability-qualified-auto` | `286996b` | `STYLE: Use auto * to declare variables initialized by pointer cast` |

### Performance

| Rule | PR | Commit message prefix |
|------|----|-----------------------|
| `performance-noexcept-swap` | #5066 | `STYLE: performance-noexcept-swap clang-tidy` |
| `performance-avoid-endl` | #5063 | `STYLE: performance-avoid-endl clang-tidy recommendation` |
| `performance-unnecessary-copy-initialization` | (rule file exists) | `PERF: Allow compiler to choose best way to construct a copy` |
| `performance-for-range-copy` | (rule file exists) | (avoid copies in range-for) |

### Bugprone

| Rule | PR | Commit message prefix |
|------|----|-----------------------|
| `bugprone-implicit-widening-of-multiplication-result` | #5057 | `STYLE: clang-tidy bugprone-implicit-widening-of-multiplication-result` |
| `bugprone-move-forwarding-reference` | #5946 | `BUG: Use std::forward instead of std::move on forwarding references` |

### Other

| Rule | PR | Commit message prefix |
|------|----|-----------------------|
| `misc-const-correctness` | #5025, #5103 | `STYLE: Prefer explicit const designation` |
| `misc-unused-parameters` | (marked DONE) | `STYLE: misc-unused-parameters` |
| `cppcoreguidelines-prefer-member-initializer` | `f46b4c9`, `3caea03` | `STYLE: Prefer member initializer to assignment` |
| `cppcoreguidelines-pro-type-cstyle-cast` | #5394 | `COMP: Prefer new style cast to old` |
| `google-explicit-constructor` | (rule file exists) | (mark single-arg constructors explicit) |

## Rejected / Broken Rules (DO NOT APPLY)

These checks have been evaluated and rejected for ITK. Do not apply them.

| Rule | Reason | Source |
|------|--------|--------|
| `modernize-use-trailing-return-type` | **Disabled in .clang-tidy.** ITK uses leading return types by convention. | Commit `89df941` |
| `readability-redundant-member-init` | **Disabled in .clang-tidy.** ITK prefers explicit base-class initialization. | Commit `89df941` |
| `llvmlibc-*` | **Disabled in .clang-tidy.** LLVM stdlib internals, never applicable to ITK. | Commit `89df941` |
| `readability-braces-around-statements` | **BROKEN.** Produces incorrect results in ITK templates. | `order_suggestions_rules.txt` |
| `readability-redundant-declaration` | **BROKEN.** False positives on ITK forward declarations. | `order_suggestions_rules.txt` |
| `cppcoreguidelines-init-variables` | **HIDES REAL PROBLEMS.** Masks uninitialized-variable bugs by inserting zero-init that suppresses compiler warnings without fixing the logic. | `order_suggestions_rules.txt` |
| `modernize-avoid-c-arrays` | **Impractical.** ITK's template infrastructure uses C arrays extensively in low-level image buffers and fixed-size coordinate arrays. The 53 MB error log (`avoid-c-arrays.logger`) demonstrates the scale of false positives. | Empirical testing |

## Not-Easy Rules (Require Manual Review)

These rules work but produce changes that need careful human review before merging.

| Rule | Why it's hard |
|------|---------------|
| `bugprone-implicit-widening-of-multiplication-result` | Requires understanding numeric intent; false positives in image dimension arithmetic |
| `misc-include-cleaner` | May remove includes that are transitively needed; breaks builds on some platforms |
| `performance-avoid-endl` | Safe in most cases, but `endl` is intentional in some flush-sensitive I/O paths |

## Candidate Rules (Awaiting Evaluation)

~100 candidate rules exist in `~/scripts/dev/cxx14_updates/rules/todo/` as
`candidate_<check-name>.sh` files. These have rule file stubs but have not yet
been tested against the ITK codebase.

**High-priority candidates** (likely safe, small diffs):
- `modernize-type-traits` — use C++17 `_v` / `_t` trait aliases
- `modernize-use-starts-ends-with` — use C++20 `starts_with()`/`ends_with()`
- `modernize-shrink-to-fit` — use `shrink_to_fit()` instead of swap idiom
- `modernize-unary-static-assert` — remove redundant message from `static_assert`
- `readability-container-contains` — use `.contains()` instead of `.find() != .end()`
- `readability-simplify-boolean-expr` — simplify boolean expressions
- `readability-redundant-string-cstr` — remove unnecessary `.c_str()` calls
- `performance-trivially-destructible` — add noexcept to trivially destructible types
- `bugprone-suspicious-semicolon` — find stray semicolons after if/for/while

**Medium-priority candidates** (larger diffs, need more review):
- `modernize-use-designated-initializers` — C++20 designated initializers
- `modernize-use-ranges` — C++20 ranges (large diff, C++20 requirement)
- `readability-implicit-bool-conversion` — make bool conversions explicit
- `performance-unnecessary-value-param` — pass by const reference

## Chaining with Other Skills

Several ITK refactoring skills produce code patterns that enable subsequent
clang-tidy rules:

| After running... | These clang-tidy rules become applicable |
|------------------|------------------------------------------|
| `itk-declare-then-init` | `modernize-use-auto` (initialized-at-declaration enables type deduction) |
| `itk-declare-then-init` | `misc-const-correctness` (initialized variables can be marked const) |
| `itk-sizetype-filled` | `readability-qualified-auto` (Filled() return types work with auto*) |
| `itk-nodiscard-return-value` | `modernize-use-auto` (return-value form enables auto deduction) |
| `itk-allocate-initialized` | (no direct chaining — API rename only) |
| `itk-transform-point-migration` | `modernize-use-auto` (return-value form enables auto deduction) |

**Recommended workflow:**
1. Run the semantic refactoring skill first (e.g. `itk-declare-then-init`)
2. Commit those changes
3. Run the enabled clang-tidy rule(s) as a separate commit
4. Each commit uses one rule, one `STYLE:`/`PERF:` prefix

## Pitfalls

- **Always exclude ThirdParty.** The wrapper handles this via `-source-filter`
  and the `.clang-tidy` `ExcludeHeaderFilterRegex`, but verify if running manually.
- **Template errors are verbose.** Focus on the first error in clang-tidy output.
- **Re-run clang-format after clang-tidy.** The wrapper passes `-format` but the
  pre-commit hook will also catch formatting issues.
- **One rule per commit.** Never combine multiple clang-tidy checks in one commit.
  This matches the established PR pattern (e.g. #5276 = override only, #5041 = using only).
- **Test after applying.** Build and run `ctest -R <module>` for affected modules.
- **macOS sed portability.** The wrapper uses `sed` to inject rules into `.clang-tidy`.
  If editing the script, avoid `sed -i` without `''` on macOS.

## Enhanced by

- **serena** — When installed, this skill can use semantic code analysis
  (`find_symbol`, `replace_symbol_body`) for precise refactoring instead
  of regex-based text matching. Falls back to pattern-based rewriting
  when serena is not available.

  **Strongly recommended:** If the Serena MCP plugin is available in
  your Claude Code environment, enable it before running this skill.
  Serena's symbol-level tools save up to 70 % in token costs by
  indexing the codebase instead of reading every file line-by-line.

  Serena is available as an official Claude Code plugin. You do not
  need to install or start it manually — Claude Code launches the MCP
  server automatically as a subprocess. Setup:

  1. **Enable the plugin** — in Claude Code, run `/plugins` and enable
     **serena** from the official marketplace (or confirm it is already
     enabled in `~/.claude/settings.json` under `plugins`).
  2. **Run onboarding** — on the first session in a new project, say
     *"start Serena onboarding"* in the Claude Code chat. This triggers
     the initial indexing pass where Serena maps the codebase symbols
     and writes memory files so future sessions start with full context.

  After onboarding, Serena's context optimizer automatically disables
  its own file-search tools that would duplicate Claude Code's built-in
  features, avoiding conflicts and redundant work.
