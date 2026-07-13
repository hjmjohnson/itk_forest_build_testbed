---
name: itk-declare-then-init
version: 1.0.0
purpose: Find and fix ITK C++ declare-then-initialize patterns one class at a time (fill_zero, fill_nonzero, elem_same, elem_diff, elem_zero, assign, setsize_fill), following N-Dekker's incremental per-commit methodology.
description: Find and fix C++ declare-then-initialize patterns where a variable is declared and then initialized on a subsequent line. Addresses ONE pattern class at a time following N-Dekker's incremental methodology. Use when refactoring ITK source to prefer initialization at declaration.
triggers:
  - itk-declare-then-init
  - /itk-declare-then-init
  - declare then init
  - MakeFilled refactor
  - N-Dekker style refactor
user_invocable: true
cmd: false
argument_hint: "<pattern> [--varname NAME] [--vartype REGEX]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/**/*.cxx"
      - "Modules/**/*.h"
      - "Modules/**/*.hxx"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
  determinism: deterministic
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
  external_tools:
    - git
    - python3
    - clang-format
    - ninja
  python_packages: []
  scripts:
    - find_declare_then_init.py
deployment:
  tier: project
  target_projects:
    - itk
    - brainstools
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Declare-Then-Initialize Pattern Finder

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-declare-then-init — Fix declare-then-init patterns, one class at a time

Usage:
  /itk-declare-then-init fill_zero          Type v; v.Fill(0) -> Type v{}
  /itk-declare-then-init fill_nonzero       Type v; v.Fill(N) -> MakeFilled<Type>(N)
  /itk-declare-then-init elem_same          Type v; v[i]=x -> Type::Filled(x)
  /itk-declare-then-init elem_diff          Type v; v[0]=x; v[1]=y -> Type v{x,y}
  /itk-declare-then-init assign             Type v; v = expr -> Type v = expr
  /itk-declare-then-init setsize_fill       SetSize+Fill -> Type v(N, V)
  /itk-declare-then-init <pat> --varname size   Filter by variable name
```

Finds C++ variables declared on one line and initialized on a subsequent line.
**Addresses exactly ONE pattern class per invocation** — matching N-Dekker's
commit methodology where each commit targets one regex pattern class.

## Script

`~/.claude/skills/itk-declare-then-init/find_declare_then_init.py`

## Pattern Classes (--pattern)

| Pattern | Before | After |
|---------|--------|-------|
| `fill_zero` | `Type v; v.Fill(0);` | `Type v{};` |
| `fill_nonzero` | `Type v; v.Fill(N);` | `auto v = MakeFilled<Type>(N);` |
| `elem_same` | `Type v; v[0]=x; v[1]=x; v[2]=x;` | `auto v = Type::Filled(x);` |
| `elem_diff` | `Type v; v[0]=x; v[1]=y; v[2]=z;` | `Type v{ x, y, z };` |
| `elem_zero` | `Type v; v[0]=0; v[1]=0;` | `Type v{};` |
| `assign` | `Type v; v = expr;` | `Type v = expr;` |
| `setsize_fill` | `Type v; v.SetSize(N); v.Fill(V);` | `Type v(N, V);` |

## Filters

| Flag | Purpose | Example |
|------|---------|---------|
| `--varname NAME` | Only match this variable name | `--varname size` |
| `--vartype REGEX` | Only match types matching regex | `--vartype SizeType` |
| `--tests-only` | Only scan `*Test*.cxx` files | |
| `--max-gap N` | Max unrelated lines between decl and init (default 9999) | |
| `--exclude PATTERN` | Exclude paths matching regex (repeatable) | |
| `--apply` | Apply fixes in-place (skips forward-ref hazards) | |

## Reproducing N-Dekker's Commits

Each command below corresponds to one of N-Dekker's historical commits:

```bash
SCRIPT=~/.claude/skills/itk-declare-then-init/find_declare_then_init.py
EXCL="--exclude Remote/ --exclude VectorMean --exclude BridgeOpenCV --exclude BridgeVXL"

# 9962e2f9: size[i]=x -> Filled (same value, tests, SizeType only)
python3 $SCRIPT --pattern elem_same --varname size --vartype SizeType \
    --tests-only --apply -r Modules/

# 03941e42: size[i] brace-init (different values, tests, SizeType only)
python3 $SCRIPT --pattern elem_diff --varname size --vartype SizeType \
    --tests-only --apply -r Modules/

# 6cb6bf98: T var; var.Fill(x) -> MakeFilled (non-zero, all files)
python3 $SCRIPT --pattern fill_nonzero $EXCL --apply -r Modules/

# fill_zero: T var; var.Fill(0) -> T var{} (all files)
python3 $SCRIPT --pattern fill_zero $EXCL --apply -r Modules/
```

After each `--apply`, run `clang-format --style=file -i` on modified files.

## Applying Fixes

The preferred workflow is `--apply` which modifies files in-place:

```bash
SCRIPT=~/.claude/skills/itk-declare-then-init/find_declare_then_init.py

# Apply fill_nonzero across all buildable modules
python3 $SCRIPT --pattern fill_nonzero --apply \
    --exclude "Remote/" --exclude "VectorMean" \
    --exclude "BridgeOpenCV" --exclude "BridgeVXL" \
    -r Modules/
```

**`--apply` automatically:**
- Skips findings with **forward-reference hazards** (Fill arg defined
  between decl and init) — prints them for manual review
- Processes multi-match files correctly (init_line descending order)
- Uses `itk::MakeFilled<>` in test files, `MakeFilled<>` in `.hxx`/`.txx`
  (which are already inside `namespace itk`)

**After `--apply`, always run:**
1. `clang-format --style=file -i` on all modified files
2. Build verification (see below)

### Manually fixing skipped findings

Forward-ref hazards require reordering: move the variable/typedef that
defines the Fill argument **above** the new `MakeFilled` line. Example:

```cpp
// BEFORE (script skips this — dimLength defined after size)
SizeType      size;
constexpr int dimLength{ 3 };
size.Fill(dimLength);

// AFTER (manual fix — swap the two declarations)
constexpr int dimLength{ 3 };
auto          size = itk::MakeFilled<SizeType>(dimLength);
```

## Constraints (matching N-Dekker's regex methodology)

- Declaration and init MUST have the **same indentation**
- For `elem_*`: all `[i]=` lines must be consecutive with same indent
- Search stops at block boundaries (`{`/`}`) — no matching inside
  nested `for`/`while`/`if` blocks
- The init must be the **next use** of that variable
- ThirdParty directories are always excluded
- The `--fix` flag shows suggestions but does NOT modify files
- The `--apply` flag modifies files in-place (skips hazards)

## N-Dekker Convention Reference

| Commit | Pattern | Scope | Regex documented in commit message |
|--------|---------|-------|------------------------------------|
| 6cb6bf98 | `fill_nonzero` | `Modules/*.h;*.hxx;*.cxx` | `^( [ ]+)([^ ].*)[ ]+(\w+);[\r\n]+\1\3\.Fill\(` |
| 9962e2f9 | `elem_same` | `Test*.cxx`, var=size | `^( [ ]+)(\w+)[ ]+size;\r\n\1size\[0\] = (\w+);\r\n\1size\[1\] = \3;\r\n\1size\[2\] = \3;` |
| 03941e42 | `elem_diff` | `Test*.cxx`, type=SizeType | `^([ ]+)(.*SizeType)[ ]+size;[\r\n]+\1size\[0\] = (\w+);\r\n\1size\[1\] = (\w+);\r\n\1size\[2\] = (\w+);$` |
| 8b6bc5a5 | `elem_same` | `Test*.cxx`, type=SizeType | same as 9962e2f9 but with SizeType filter |
| e1e06b50 | (eliminate var) | `Test*.cxx` | Extended search (not regex) — out of scope |
| 7fc9f615 | (style pref) | all | `auto[ ]+(\w+) = ([\w:]+){};` → `$2 $1{};` — out of scope |
| c77f9f8d | (add constexpr) | non-test | `^( [ ]+)(auto \w+[ ]+= .+::Filled\(\d+\);)` → `constexpr` — out of scope |

**Important**: When a commit message documents a regex but the diff shows
additional manual changes not matching that regex, those are manual fixups
where the regex substitution produced incorrect results (e.g.,
`VariableLengthVector` not supporting `MakeFilled`, or mismatched
template parameters). Always review suggestions before applying.

## Pitfalls (from PR #6010 experience)

### 1. `itk::` namespace qualification

`MakeFilled` lives in `namespace itk`. Files that are NOT inside the
`itk` namespace (most test `.cxx` files) **must** use `itk::MakeFilled<>`.
Template implementation files (`.hxx`, `.txx`) are inside `namespace itk`
and should use plain `MakeFilled<>`.

The `--apply` flag handles this automatically. If using `--json` output
with a custom apply script, check for `using namespace itk` or file
extension to decide.

### 2. Forward-reference hazards (gap > 0)

When the Fill() argument is a variable **defined in the gap** between
the declaration and the Fill call, moving the init to the declaration
line creates a use-before-declaration error:

```cpp
SizeType      size;          // line N
constexpr int dimLength{3};  // line N+1 — defines the Fill argument
size.Fill(dimLength);        // line N+2
```

The script now detects these and flags them as `*** FORWARD-REF HAZARD ***`.
`--apply` skips them. Fix manually by reordering declarations.

### 3. Multi-match file line shifting

When a file has multiple findings, applying fixes top-down shifts line
numbers for later fixes. The `--apply` mode handles this by processing
`init_line` in **descending** order. If writing a custom apply script,
always sort by init_line descending.

### 4. `using` / `typedef` ordering in `.hxx` files

Template files may have `using ValueType = typename T::ValueType;`
between the declaration and Fill. If the Fill argument uses `ValueType`,
moving the init above the `using` breaks compilation. The forward-ref
detector catches this case.

### 5. Unbuildable module separation

Changes to modules requiring special hardware/libraries MUST be in a
separate PR. The standard exclusion set for ITK is:

```bash
--exclude "Remote/" --exclude "BridgeOpenCV" --exclude "BridgeVXL"
```

Also exclude `VectorMean` for `fill_nonzero` (VariableLengthVector
doesn't support MakeFilled).

## Build Verification (BLOCKING)

**A PR MUST NOT be created or updated until ALL of the following pass locally:**
- All affected files compile with **zero errors and zero warnings**
- All affected module tests pass with **zero failures**

**This is not optional.** Do not `git push`, `gh pr create`, or `gh pr` update
until verification is complete. If a build or test fails, fix the issue or
revert the change before proceeding.

### Step 1: Identify affected modules

```bash
# From the --json output, extract unique module paths:
python3 $SCRIPT --pattern <pattern> --json -r Modules/ | \
  python3 -c "import json,sys,re; [print(m.group(1)) for f in json.load(sys.stdin) if (m:=re.match(r'Modules/([^/]+/[^/]+)',f['file']))]" | sort -u
```

### Step 2: Ensure modules are enabled in the build

Check `build/CMakeCache.txt` for the affected modules. If a module is
disabled, enable it before building:

```bash
cd build
# Enable specific modules
cmake -DModule_ITKFEM:BOOL=ON -DModule_ITKReview:BOOL=ON .
# Enable examples
cmake -DBUILD_EXAMPLES:BOOL=ON .
```

### Step 3: Build affected object files

Build the specific files that were changed (not the full build):

```bash
cd build
# Build individual .o files to check for errors/warnings
ninja Modules/Core/SpatialObjects/src/CMakeFiles/ITKSpatialObjects.dir/itkContourSpatialObject.cxx.o
# Or build the whole module library
ninja ITKSpatialObjects
```

Verify **zero errors and zero warnings** in the output.

### Step 4: Run affected tests

```bash
cd build
ctest -R <module_pattern> --output-on-failure
```

### Step 5: Triage unbuildable modules

Some modules cannot be built locally:

| Module | Reason | Action |
|--------|--------|--------|
| `GPU*` | Requires OpenCL GPU | Separate PR, request manual compilation |
| `BridgeOpenCV` | Requires OpenCV | Separate PR if OpenCV not installed |
| `BridgeVXL` | Requires VXL | Separate PR |
| `DCMTK` | Requires DCMTK | Separate PR |
| `Remote/*` | Not tracked in ITK repo | Skip; file issues in remote module repos |

**Changes to unbuildable modules MUST be in a separate PR** with a comment
requesting manual compilation by someone with the required environment.
Never mix buildable and unbuildable module changes in the same commit.

### Step 6: Verify no new warnings

After building, check for warnings in the build output. If the pattern
replacement introduces a new warning (e.g., `-Wmissing-braces` from `{}`
on certain compilers), revert and investigate before committing.

### GATE: All checks must pass before proceeding

**STOP HERE if any of the following are true:**
- Any changed file produced a compiler error → fix or revert
- Any changed file produced a new compiler warning → fix or revert
- Any test in an affected module failed → fix or revert
- Any changed file is in an unbuildable module and was not separated out

**Only after all builds are warning-free and all tests pass** may you
proceed to commit, push, or create/update a PR.

## Commit Message Generation

When committing changes from this skill:

1. **Check memory first**: Read `reference_declare_then_init_commits.md` from
   the project memory to find the most relevant prior commit for the pattern
   class being addressed. The memory is organized by pattern class and includes
   scope, known exclusions, and commit hashes.

2. **Verify the commit still exists** (memory may be stale):
   ```bash
   git log --oneline -1 <hash_from_memory>
   ```

3. **Reference it in the commit message**:
   ```
   STYLE: Replace declare-then-Fill(N) with ::Filled(N) in Filtering tests

   Using find_declare_then_init.py --pattern elem_same --varname size
   --vartype SizeType --tests-only, replaced per-element size[i]=N
   assignments (all same value) with auto size = SizeType::Filled(N).

   Follow-up to commit 9962e2f971 by N-Dekker
   "STYLE: Replace assignments to `size[i]` with `Filled` calls, in tests"
   ```

4. **Update the memory** after committing: add the new commit hash to
   `reference_declare_then_init_commits.md` under the appropriate pattern
   class so future invocations can reference it.

### Quick reference by pattern class

| Pattern | Look up in memory section |
|---------|--------------------------|
| `fill_nonzero` | "fill_nonzero" — primary: `6cb6bf9823` |
| `fill_zero` | "elem_zero / fill_zero" and hjmjohnson `427df79d1ea2` |
| `elem_same` | "elem_same" — primary: `9962e2f971` |
| `elem_diff` | "elem_diff" — primary: `03941e42d8` |
| `elem_zero` | "elem_zero / fill_zero" — multiple commits |
| `assign` | (no prior commits in memory yet) |
| `setsize_fill` | "Other Fill-related" — `4f14f45a8c`, `27a1d7b587` |

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
