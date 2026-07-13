---
name: itk-gcc-warnings
version: 1.0.0
purpose: 'Fix common GCC-specific compiler warnings in ITK/Slicer/NAMIC C++ projects: -Wshadow (type alias shadows member), -Wmaybe-uninitialized (uninitialized class members), -Wunused-but-set-variable (variable assigned but never read), and -Wunused-result (see itk-nodiscard-return-value for the nodiscard variant).'
description: >-
  Fix common GCC-specific compiler warnings in ITK/Slicer/NAMIC C++ projects:
  -Wshadow (type alias shadows member), -Wmaybe-uninitialized (uninitialized
  class members), -Wunused-but-set-variable (variable initialized from a return
  value but never read — common after declare-then-assign refactoring), and
  -Wunused-result (see itk-nodiscard-return-value for the nodiscard variant).
  Use when GCC CI reports warnings that Apple Clang doesn't catch. Trigger on:
  "GCC warning", "-Wshadow", "-Wmaybe-uninitialized", "-Wunused-but-set-variable",
  "set but not used", "shadows a member", "may be used uninitialized",
  "fix GCC warnings", "CDash warnings".
triggers:
  - itk-gcc-warnings
  - /itk-gcc-warnings
user_invocable: true
cmd: false
argument_hint: "[-Wshadow | -Wmaybe-uninitialized | -Wunused-result]"
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

# ITK/GCC Warning Fixes

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-gcc-warnings — Fix GCC-specific warnings in ITK/Slicer/NAMIC C++

Usage:
  /itk-gcc-warnings                          Fix all GCC warning types
  /itk-gcc-warnings -Wshadow                 Fix type-alias-shadows-member
  /itk-gcc-warnings -Wmaybe-uninitialized    Fix uninitialized class members
  /itk-gcc-warnings -Wunused-result          Fix discarded return values
```

GCC often reports warnings that Apple Clang doesn't, particularly in template-
heavy ITK code.  This skill covers the most common patterns.

## -Wshadow: local `using` alias shadows class member

**Warning:**
```
BRAINSFitHelperTemplate.hxx:1150: warning: declaration of
'using IdentityTransformType = ...' shadows a member of
'BRAINSFitHelperTemplate<...>' [-Wshadow]
```

**Root cause:** A local `using` declaration inside a method body (often inside
`if`/`else`) reuses a name already declared as a member typedef.

**Fix:** Rename the local alias to something unique:
```cpp
// Before (shadows member IdentityTransformType):
using IdentityTransformType = itk::IdentityTransform<double, Dim>;
auto id = IdentityTransformType::New();

// After (no shadow):
using LocalIdentityTransformType = itk::IdentityTransform<double, Dim>;
auto id = LocalIdentityTransformType::New();
```

**Audit command:**
```bash
grep -rn 'using.*TransformType\|using.*FilterType\|using.*ImageType' \
  <src> | grep -v '^\s*//'
# Then check each one against the class member list
```

**Commit prefix:** `COMP: Fix -Wshadow in <File>`

---

## -Wmaybe-uninitialized: uninitialized class member

**Warning:**
```
itkDtiFastMarchingCostFilter.h:98: warning: 'node.m_Axis' may be
used uninitialized [-Wmaybe-uninitialized]
```

**Root cause:** A class member declared without an initializer. GCC tracks data
flow and warns when a code path reads the member before any `SetXxx()` call.
Clang typically doesn't warn because it trusts the programmer to initialize.

**Fix:** Add a C++11 in-class member initializer:
```cpp
// Before:
private:
  int m_Axis;

// After:
private:
  int m_Axis{ 0 };   // or = 0, or an appropriate sentinel value
```

For pointer members: `SomeType * m_Ptr{ nullptr };`
For bool members: `bool m_Flag{ false };`

**Important:** Choose the initializer value carefully:
- `0` / `false` / `nullptr` are safe defaults for most diagnostic/flag fields
- Use a meaningful sentinel (e.g., `-1` for "unset index") when 0 is valid data

**Commit prefix:** `COMP: Fix -Wmaybe-uninitialized in <File>`

---

## -Wshadow: local variable shadows function parameter

Less common but occurs in ITK filter implementations:
```
warning: declaration of 'value' shadows a parameter [-Wshadow]
```

**Fix:** Rename the local variable. Prefer `local_value` or a more descriptive name.

---

## -Wunused-but-set-variable: variable assigned but never read

**Warning:**
```
itkMatrixTest.cxx:90:20: warning: variable 'matrix3' set but not used
[-Wunused-but-set-variable]
   const MatrixType matrix3 = matrix.GetInverse();
                    ^~~~~~~
```

**Root cause:** A variable is initialized from a return value but never
subsequently read. Common after declare-then-assign refactoring: the old
pattern called a function for its side effect and discarded the result;
the new `const T x = func()` form captures the return, triggering GCC's
"set but not used" warning. Apple Clang and MSVC typically don't fire this.

**Fix — prefer test assertions over suppression:**
- **In test code:** add a meaningful test for the computed value. Tests
  should verify results, not just exercise code paths.
  ```cpp
  // Before (triggers -Wunused-but-set-variable):
  const MatrixType matrix3 = matrix.GetInverse();

  // After (tests the actual value):
  const MatrixType matrix3 = matrix.GetInverse();
  if (itk::Math::NotExactlyEquals(matrix3(0, 0), expected))
  {
    std::cerr << "Problem with GetInverse()" << std::endl;
    return EXIT_FAILURE;
  }
  ```
- **In production code** where the call is for its side effect and the
  return genuinely isn't needed: use `static_cast<void>(expr)` or
  restructure to call without capturing.
- **Never use `[[maybe_unused]]`** on test variables — it silences the
  warning but hides the fact that nothing is being tested.

**When this fires after STYLE: declare-then-assign refactoring:**
The `itk-declare-then-init` / declare-then-assign STYLE commits often
convert `T x; x = func();` to `const T x = func();`. If the original
code never read `x` after assignment (it was called for side effects),
the new form triggers this warning on GCC. Check whether the variable
is actually used downstream. If not, this is an opportunity to add a
test assertion rather than just suppressing.

**Commit prefix:** `COMP: Fix -Wunused-but-set-variable in <File>`

---

## CI vs local workflow

GCC warnings often appear only on Ubuntu CI (not macOS/Clang). Workflow:

1. Check CI logs for the warning lines (category and file:line)
2. Read the source file at that line
3. Apply the minimal fix above
4. Commit separately per warning category, per module
5. Push and verify CI is clean

**Commit structure for mixed warnings in a PR:**
```
COMP: Fix -Wshadow in BRAINSFitHelperTemplate.hxx
COMP: Fix -Wunused-result for TransformPhysical*To* in GTRACT
COMP: Fix -Wmaybe-uninitialized in itkDtiFastMarchingCostFilter.h
```

Each commit touches only the specific files implicated by that warning.

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
