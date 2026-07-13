---
name: itk-sizetype-filled
version: 1.0.0
purpose: Scans the ITK codebase for two-line patterns where a FixedArray-based type (SizeType, IndexType, SpacingType, PointType, OffsetType, VectorType, etc.) is declared on one line and then either (a) populated via `.Fill(N)` with a compile-time constant or (b) assigned via `v = expr;` on the next line.
description: >-
  Scans the ITK codebase for two-line patterns where a FixedArray-based type
  (SizeType, IndexType, SpacingType, PointType, OffsetType, VectorType, etc.)
  is declared on one line and then either (a) populated via `.Fill(N)` with a
  compile-time constant or (b) assigned via `v = expr;` on the next line.
  Replaces (a) with `constexpr auto var = Type::Filled(N);` and (b) with
  `const auto var = expr;` when the variable is never mutated, or with
  `<Type> var = expr;` (explicit type, merge-only) when the variable is
  later mutated. Supports an optional pattern argument: `fill` (default)
  or `assign`. Discovery uses a hybrid clang-query + Python scanner: a
  clang-query AST matcher finds default-constructed class-type local
  vars via `varDecl(hasInitializer(cxxConstructExpr(argumentCountIs(0))))`,
  then Python pairs each with its first subsequent assignment, stepping
  over intervening declarations and comments. A pure-regex fallback is
  also documented. clang-tidy's `cppcoreguidelines-init-variables` was
  evaluated and found useless here (POD/scalar only). Creates a branch
  and PR on InsightSoftwareConsortium/ITK.

  Trigger when the user mentions: SizeType::Filled, IndexType::Filled, replace
  Fill() with Filled(), FixedArray::Filled, ITK constexpr size, declare-then-
  assign pattern, init-variables cleanup, or references N-Dekker's suggestion
  to use ::Filled() / AllocateInitialized() / const auto in ITK.
triggers:
  - itk-sizetype-filled
  - /itk-sizetype-filled
user_invocable: true
cmd: false
argument_hint: "[fill|assign]"
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

# ITK FixedArray initialization modernization

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-sizetype-filled — Replace declare+Fill with constexpr Filled()

Usage:
  /itk-sizetype-filled                  Run fill pattern (default)
  /itk-sizetype-filled fill             Type v; v.Fill(N) -> constexpr auto v = Type::Filled(N)
  /itk-sizetype-filled assign           Type v; v = expr -> const auto v = expr
```

Replace verbose two-line FixedArray declare-then-initialize patterns with
modern single-line `constexpr auto` / `const auto` declarations.

## Argument

The skill takes an optional pattern argument:

- `fill` (default) — `Type v; v.Fill(literal);` → `constexpr auto v = Type::Filled(literal);`
- `assign` — `Type v; v = expr;` → `const auto v = expr;`

Run only one pattern class per invocation to keep PRs focused and reviewable.
The two patterns produce different PR titles, different commit messages, and
require different validation (the `fill` case uses `constexpr`, the `assign`
case uses `const` because the RHS is a runtime expression).

## Background

`itk::FixedArray<T,N>::Filled(v)` is a static factory method that returns a
`FixedArray` with all elements set to `v`. It enables single-line `constexpr`
initialization instead of the legacy declare-then-Fill pattern. Types that
inherit from `FixedArray` (and thus support `::Filled()`) include:

- `SizeType` / `ImageType::SizeType`
- `IndexType`
- `OffsetType`
- `SpacingType` (via `FixedArray`)
- `PointType`
- `VectorType` (N-dim)
- `CovariantVectorType`
- Any `itk::FixedArray<T,N>` subclass

## Target patterns

### Pattern `fill`

```cpp
// BEFORE — two lines, runtime initialization
SomeType::SizeType size;
size.Fill(2);

// AFTER — one line, constexpr
constexpr auto size = SomeType::SizeType::Filled(2);
```

### Pattern `assign`

```cpp
// BEFORE — two lines, declare-then-assign
InputImageType::SizeType extentSize;
extentSize = reader->GetOutput()->GetLargestPossibleRegion().GetSize();

// AFTER — one line, const auto
const auto extentSize = reader->GetOutput()->GetLargestPossibleRegion().GetSize();
```

**Conditions that MUST be met to replace (both patterns):**
1. The variable is a local (stack) variable, NOT a member variable (`m_` prefix → skip)
2. The initializing call/assignment is on the very next non-blank, non-comment line
3. The variable is not used in any expression between its declaration and the initializer
4. **The variable is never reassigned or mutated anywhere later in its enclosing scope.**
   This is the critical check — see the "Reassignment check" section below.
5. The variable is not declared with `const` already
6. The type is in ITK's non-ThirdParty `Modules/` tree

**`fill`-only condition:** `N` must be a compile-time constant literal
(integer or float literal, not a variable).

**`assign`-only condition:** The RHS must be a simple expression (not a comma
operator, not an Eigen-style `v = 0, 1, 2` initializer, not inside a comment).

---

## Step 1: Locate ITK source tree

```bash
ITK_SRC=~/Dashboard/src/ITK
git -C "$ITK_SRC" branch --show-current
```

Confirm the repo is present and note the current branch.

---

## Step 2: Create a new branch from upstream/main

Branch name varies by pattern class:
- `fill` pattern → `style-sizetype-filled`
- `assign` pattern → `style-sizetype-filled-assign`

```bash
cd "$ITK_SRC"
git fetch upstream
# choose ONE of the following per invocation:
git checkout -b style-sizetype-filled        upstream/main   # for fill
git checkout -b style-sizetype-filled-assign upstream/main   # for assign
```

---

## Step 3: Discover candidate declarations

Two methods, tried in order. Method A is AST-based and catches things the
regex scan misses (qualified types, templates, commented-out code). Method B
is a fallback when no compile database is available.

### Method A: clang-query + Python pairing (PREFERRED)

**Works, and catches cases the regex scanner misses.** Uses `clang-query`
(ships with LLVM/clang toolchain) to find AST-verified declaration sites,
then pairs each with its first subsequent assignment using a small Python
script. Solves three of the regex scanner's weaknesses:

1. **No false positives from comments/strings/macros** — clang-query parses
   the AST, so `/* Type v; */` in a comment is never seen as a declaration.
2. **Handles intervening unrelated declarations** — if `Type1 v1; Type2 v2;
   v1 = expr;` appears, the scanner matches `v1` with `v1 = expr;` by
   stepping past the intervening `v2` declaration.
3. **Handles comments between decl and assignment** — same mechanism.

**Important caveat about `cppcoreguidelines-init-variables`:** the natural
choice of clang-tidy check does **not** work for this skill. Verified
empirically on 2026-04-05: it only flags POD/scalar types (`int x;`,
`float f;`). Class types like `SizeType`, `IndexType`, `PointType`,
`WeightsType` have implicit default constructors, so the AST represents
`IndexType idx;` as `IndexType idx = IndexType();` — the check sees this
as initialized and stays silent. The workaround below uses clang-query
(not clang-tidy) with a matcher that targets the zero-argument
constructor call directly.

**Key AST matcher:**

```
varDecl(
  isExpansionInMainFile(),
  hasInitializer(cxxConstructExpr(argumentCountIs(0))),
  unless(parmVarDecl()),
  unless(hasGlobalStorage()),
  hasType(qualType(unless(isConstQualified())))
).bind("decl")
```

The `hasInitializer(cxxConstructExpr(argumentCountIs(0)))` is the trick
that distinguishes `Type v;` (implicit default ctor, 0 args) from
`Type v = makeSomething();` (non-default ctor, ≥1 args or different
init expression). Note: `isConstQualified` must be wrapped in
`hasType(qualType(...))` because it's a `Matcher<QualType>`, not a
`Matcher<VarDecl>`.

**Prerequisites:**
- `clang-query` on PATH (`brew install llvm && export PATH=".../llvm/bin:$PATH"`)
- `compile_commands.json` at `~/Dashboard/src/ITK/build/` (cmake with
  `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`)

**Python driver script (AST-verified decl discovery + regex assignment pairing):**

```python
#!/usr/bin/env python3
"""
Hybrid assign-pattern scanner:
- clang-query finds decl sites (AST-verified, no comment/string false positives)
- Regex pairs each decl with its first subsequent assignment
- Handles intervening unrelated declarations and comments
Usage: python3 cq_assign_scan.py <source_file.cxx> <build_dir>
"""
import re, subprocess, sys
from pathlib import Path

SRC = Path(sys.argv[1])
BUILD = Path(sys.argv[2])

# Match any *SizeType, *IndexType, *OffsetType, *SpacingType, *PointType,
# *VectorType, *CovariantVectorType, WeightsType, FixedArray. The \w* prefix
# captures both the base form (e.g., PointType) and any prefixed alias
# (e.g., OutputPointType, InputPointType, MovingPointType, FixedImagePointType).
# Transforms expose many such aliases (OutputVectorType, OutputCovariantVectorType,
# OutputVnlVectorType, etc.) that are FixedArray-derived or behave equivalently.
# Using wildcards future-proofs the regex against new module-specific aliases.
FIXEDARRAY_RE = re.compile(
    r'\b(?:\w*(?:SizeType|IndexType|OffsetType|SpacingType|PointType|'
    r'VectorType|CovariantVectorType)|WeightsType|FixedArray)\b'
)

MATCHER = r'''set output diag
m varDecl(
  isExpansionInMainFile(),
  hasInitializer(cxxConstructExpr(argumentCountIs(0))),
  unless(parmVarDecl()),
  unless(hasGlobalStorage()),
  hasType(qualType(unless(isConstQualified())))
).bind("decl")
'''

script_path = Path("/tmp/cq_script.txt")
script_path.write_text(MATCHER)

result = subprocess.run(
    ["clang-query", "-p", str(BUILD), "-f", str(script_path), str(SRC)],
    capture_output=True, text=True
)

DECL_LINE_RE = re.compile(
    rf'^{re.escape(str(SRC))}:(\d+):\d+: note: "decl" binds here'
)

decl_lines = set()
for line in (result.stdout + result.stderr).splitlines():
    m = DECL_LINE_RE.match(line)
    if m:
        decl_lines.add(int(m.group(1)))

source_lines = SRC.read_text(errors="replace").splitlines()
ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(.+?)\s*;$')
DECL_VARNAME_RE = re.compile(r'^\s*\S.*?\b(\w+)\s*;\s*$')

pairs = []
for decl_ln in sorted(decl_lines):
    line = source_lines[decl_ln - 1]
    if not FIXEDARRAY_RE.search(line):
        continue
    m = DECL_VARNAME_RE.match(line)
    if not m:
        continue
    varname = m.group(1)
    decl_indent = len(line) - len(line.lstrip())
    # Scan forward up to 50 lines for first `varname = expr;` in same scope.
    # Stop at a closing brace at the decl's indent (rough scope end).
    for j in range(decl_ln, min(len(source_lines), decl_ln + 50)):
        cand = source_lines[j]
        if not cand.strip():
            continue
        am = ASSIGN_RE.match(cand)
        if am and am.group(1) == varname:
            pairs.append((decl_ln, j + 1, line.strip(), cand.strip(), varname))
            break
        if cand.strip() == "}" and (len(cand) - len(cand.lstrip())) <= decl_indent:
            break

for dl, al, dtxt, atxt, var in pairs:
    print(f"{SRC.name}:{dl} -> :{al}   (var: {var})")
    print(f"  DECL: {dtxt}")
    print(f"  INIT: {atxt}")
    print()
print(f"Total pairs: {len(pairs)}")
```

Run per-file: `python3 cq_assign_scan.py <file.cxx> ~/Dashboard/src/ITK/build`.

For a codebase-wide sweep, wrap in a shell loop over files that grep finds
to contain `SizeType|IndexType|...` (to avoid running clang-query on files
that can't possibly match). clang-query is slow (~1s per file on ITK) so
pre-filtering is important.

**Do NOT use `clang-tidy --fix`:** the autofix for
`cppcoreguidelines-init-variables` adds `= {}` or `= NAN` to the declaration
— it does **not** merge the declare-then-assign into a single line. Use
clang-query (this section) for discovery only; apply all replacements
manually per Step 4.

### Method B: regex scan (primary, and only practical method today)

Key design point: the scanner must **skip over blank lines AND `//` comment
lines** between the declaration and the initializer. Earlier versions of
this scanner skipped only blank lines, which caused false negatives for
the common pattern:

```cpp
PointType outputPoint;

// point within the grid support region
outputPoint = transform->TransformPoint(inputPoint);
```

The `SKIP_RE` pattern below catches both. Block comments (`/* */`) are
not handled; they're rare enough in the target pattern space to ignore.

```python
#!/usr/bin/env python3
"""Scan for the two-line declare-then-initialize pattern.

Pattern class is selected by the sole argument: 'fill' or 'assign'.
Skips blank lines AND // comment lines between the declaration and the
initializer so cases like `PointType p;\\n // comment\\n p = expr;` match.
"""
import re, sys
from pathlib import Path

PATTERN = sys.argv[2] if len(sys.argv) > 2 else 'fill'
assert PATTERN in ('fill', 'assign'), f"Unknown pattern: {PATTERN}"

DECL_RE = re.compile(
    r'^(?P<indent>\s*)'
    r'(?!.*(?:static|extern|return|throw|delete))'
    r'(?P<type>(?:\w+::)*(?:\w*(?:SizeType|IndexType|OffsetType|SpacingType|PointType|'
    r'VectorType|CovariantVectorType)|WeightsType|FixedArray\b)[^;*&\[]*?)'
    r'\s+(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)\s*;'
)

FILL_RE = re.compile(r'^\s*(?P<var>\w+)\.Fill\(([^)]+)\)\s*;')
ASSIGN_RE = re.compile(r'^\s*(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?P<rhs>.+?)\s*;$')

# Skip blank and // comment-only lines between the decl and the init
SKIP_RE = re.compile(r'^\s*(?://.*)?$')

ITK_ROOT = Path(sys.argv[1]) / "Modules"
results = []

for f in sorted(ITK_ROOT.rglob("*")):
    if f.suffix not in (".cxx", ".hxx", ".h"):
        continue
    if "ThirdParty" in f.parts:
        continue
    lines = f.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines[:-1]):
        dm = DECL_RE.match(line)
        if not dm:
            continue
        varname = dm.group("var")
        if varname.startswith("m_"):
            continue
        # Skip blank AND comment-only lines
        j = i + 1
        while j < len(lines) and SKIP_RE.match(lines[j]):
            j += 1
        if j >= len(lines):
            continue

        if PATTERN == 'fill':
            fm = FILL_RE.match(lines[j])
            if fm and fm.group("var") == varname:
                value = fm.group(2).strip()
                if re.fullmatch(r'[\d.]+[fFlLuU]*', value):
                    results.append((f, i+1, j+1, line, lines[j], varname, value))
        else:  # assign
            am = ASSIGN_RE.match(lines[j])
            if am and am.group("var") == varname:
                rhs = am.group("rhs")
                # Skip compound assigns, comma-operator initializers
                if rhs.startswith("0,") or ",  " in rhs:
                    continue
                results.append((f, i+1, j+1, line, lines[j], varname, rhs))

for f, dl, al, decl, init, var, val in results:
    rel = f.relative_to(Path(sys.argv[1]))
    print(f"{rel}:{dl} -> :{al}")
    print(f"  DECL: {decl.strip()}")
    print(f"  INIT: {init.strip()}")
    print()
print(f"Total: {len(results)}")
```

Run: `python3 scan.py ~/Dashboard/src/ITK fill` or `... assign`.

### Step 3b: Whole-function-scope use check (CRITICAL)

Neither Method A nor Method B tells you whether the variable is
**read, reassigned, or mutated later in its enclosing function scope**.
This is the single most important validation and the most common source
of wasted PR cycles — and the failure mode is not always "variable is
written later." It is often **"variable is used by a sibling loop later
in the same function."**

For each candidate, run a **whole-function grep** for the variable name
and inspect every match:

```bash
grep -n "\b${varname}\b" path/to/file.cxx
```

Classify every match as:

1. The declaration site (the match at the decl line)
2. The first assignment (the match at the init line — expected)
3. Reads within the same local scope as the first assignment
   (e.g. inside the same `while`/`for` loop body)
4. **Any match outside that local scope** → **SKIP the candidate entirely.**

**The sub-case B / scope-shrink transformation is only safe if every
reference to the variable is inside the single contained block where the
initial assignment lives** (or the same straight-line code path if no
loop is involved). If there is ANY read, reassignment, or mutation
outside that block, the transformation will either:
- Cause a compile error (variable used outside its new narrower scope), or
- Silently break test semantics (variable was holding state across the
  block boundary).

**Neither condition has to be "write" — a later READ is equally fatal**
because after the scope-shrink the variable no longer exists at the
read point.

**Common false positives the whole-function-scope check catches:**

1. **Same variable reused by multiple independent loops in one function.**
   `itkImageLinearIteratorTest.cxx`, `itkImageSliceIteratorTest.cxx`,
   and similar iterator tests declare `IndexType index0;` once at
   function scope and then use it inside each of several sequential
   `while (!it.IsAtEnd())` loops. The scope-shrink looks safe if you
   only examine the first loop, but the variable is referenced again
   dozens of lines later.

2. **Post-loop element mutation.** `itkPathFunctionsTest.cxx` and
   `itkPathIteratorTest.cxx` use `pixelIndex` in a while loop for reads,
   then later write `pixelIndex[0] = 32; pixelIndex[1] = 32;` outside
   the loop. The loop-body const-auto would compile but the later
   writes would then be to a different (undeclared) variable.

3. **Scratch variable reused for serial measurements.**
   `itkAnnulusOperatorGTest.cxx` declares `annulusSize` once and
   reassigns it 3+ times across sequential `SetX() / CreateOperator()`
   calls in the same function. The first pair looks convertible; the
   later reassignments break.

4. **Indexed / compound mutation immediately after first assignment.**
   `itkImageLinearIteratorTest.cxx` has `testIndex = start; testIndex[1] += 2;`
   — `operator[]` on a const variable is a compile error.

5. **Serial reassignment (different values, same name).**
   `itkImageFunctionTest.cxx` has `index = startIndex; ... index = endIndex;`
   in the same function body — the second assignment fails under const.

**Heuristic for rapid triage:** if the variable name is generic
(`index`, `idx`, `size`, `tempIndex`, `value`, `pt`), assume it's
reused until the whole-function grep proves otherwise. Names like
`extentSize`, `readerOrigin3D`, `normalizedSpacing`, `transformedPoint`
are usually write-once and survive the check.

**Observed success rate:** of 48 candidates found by the codebase-wide
clang-query scan on 2026-04-05, only ~18% (8/48) survived the
whole-function-scope check. Budget accordingly.

---

## Step 4: Apply replacements

Only proceed with candidates that **passed the reassignment check in
Step 3b**. For each such hit, replace the two lines with a single line.

### Pattern `fill` — `constexpr auto`

- Extract the full type from the declaration line
- Preserve the original indentation
- New line: `<indent>constexpr auto <varname> = <Type>::Filled(<literal>);`

```cpp
// Before:
  ImageType::SizeType size;
  size.Fill(2);

// After:
  constexpr auto size = ImageType::SizeType::Filled(2);
```

### Pattern `assign` — two sub-cases

The `assign` pattern splits into two sub-cases based on whether the
variable is mutated later in its scope.

#### Sub-case A — `const auto` (variable never mutated after init)

- Extract the RHS from the assignment line
- Preserve the original indentation
- New line: `<indent>const auto <varname> = <rhs>;`

```cpp
// Before:
  InputImageType::SizeType extentSize;
  extentSize = reader->GetOutput()->GetLargestPossibleRegion().GetSize();

// After:
  const auto extentSize = reader->GetOutput()->GetLargestPossibleRegion().GetSize();
```

#### Sub-case B — Explicit type, mutable (variable IS mutated later)

When the reassignment check shows the variable is passed by non-const
reference, mutated via `[i] =`, or otherwise written to after the
initial assignment, `const auto` produces a compile error. But the
declare-then-assign pattern is STILL worth merging for readability per
C++ Core Guidelines ES.22. Keep the explicit type:

- Remove the declaration line entirely
- Replace the assignment `var = expr;` with `<OriginalType> var = expr;`
- Preserve the original indentation

```cpp
// Before (from itkBSplineInterpolationWeightFunctionTest.cxx):
  WeightsType weights;
  IndexType   startIndex;

  weights = function->Evaluate(position);
  // ... later ...
  function->Evaluate(position, weights, startIndex);  // weights mutated here

// After:
  IndexType   startIndex;
  WeightsType weights = function->Evaluate(position);
  // ... later ...
  function->Evaluate(position, weights, startIndex);  // unchanged
```

**Why explicit type and not `auto`?** Using `auto` would deduce the
return type of the RHS expression, which may differ from the original
explicit type if there are implicit conversions involved. Keeping
`WeightsType` guarantees bit-for-bit semantic equivalence with the
original declaration.

**Why `const auto` and not `constexpr auto`?** The RHS is a runtime
expression (function call, method chain, variable reference). `constexpr`
requires a compile-time-constant initializer; attempting it would produce
a compile error.

#### Choosing between sub-case A and sub-case B

Run the reassignment check from Step 3b. If the grep for the variable
shows ANY of:
- `var = ...;` (reassignment)
- `var[i] = ...;` (indexed mutation)
- `var += / -= / *= ...` (compound op)
- `foo(var)` where `foo` takes `var` by non-const reference

then use **sub-case B** (merge keeping explicit type). Otherwise use
**sub-case A** (`const auto`). Neither sub-case is more or less safe
than the other — they're both semantically preserving transformations;
they differ only in which const qualifier the merged declaration carries.

### Dead typedef cleanup

After applying `assign` replacements, some `using IndexType = ...` /
`using SizeType = ...` aliases may become unused if the replaced variable
declaration was the only reference. Check each modified file:

```bash
for f in $(git diff --name-only); do
  for alias in IndexType SizeType PointType VectorType; do
    if grep -q "using $alias = " "$f" && [ "$(grep -c "\b$alias\b" "$f")" = "1" ]; then
      echo "$f: dead alias '$alias' (1 remaining use = the declaration itself)"
    fi
  done
done
```

Remove any dead aliases in the same commit — this keeps the diff minimal
for reviewers and eliminates the `-Wunused-local-typedef` warning that
clang would otherwise emit.

Use the Edit tool per-file for all replacements. Do NOT use `sed` across
multiple files — the reassignment check must be validated per-hit, and a
bulk sed cannot distinguish safe from unsafe hits.

---

## Step 5: Local build + test verification (REQUIRED)

Before committing, do a full local build of the affected test drivers and
run their ctest targets. This catches the most common failure modes that
the scan and reassignment checks can miss:
- Pre-existing compile errors in the file that the scan accidentally matched
- Non-const-ref API usage that makes the variable effectively non-const
- Platform-specific type deduction failures

### 5a. Identify the target driver for each modified file

```bash
cd ~/Dashboard/src/ITK/build
for cxx in $(git -C .. diff --name-only | grep -oE '[^/]+\.cxx$' | sed 's/\.cxx$//'); do
  echo "=== $cxx ==="
  ninja -t targets all 2>/dev/null | grep "${cxx}\.cxx\.o" | head -1
done
```

Each match line shows the path
`Modules/.../CMakeFiles/<TargetDriver>.dir/<file>.cxx.o` — the
`<TargetDriver>` is what you pass to `ninja`.

### 5b. Force rebuild and build the drivers

`ninja` is mtime-based and may consider the files up-to-date from an
earlier build, so `touch` each modified file first:

```bash
cd ~/Dashboard/src/ITK/build
touch $(git diff --name-only | sed "s|^|../|")
ninja <list of target drivers from 5a> 2>&1 | tee /tmp/build-verify.log | tail -40
```

**Required result:** zero warnings, zero errors, and the link step
succeeds for every driver. Grep the full log for `warning:` and `error:`
to be thorough — ninja's tail may not show everything:

```bash
grep -E '(warning:|error:)' /tmp/build-verify.log
```

If any diagnostics appear — even in files you didn't modify that were
triggered by a header change — investigate before committing.

### 5c. Run the ctest targets

```bash
cd ~/Dashboard/src/ITK/build
ctest -R "<pipe-separated test names>" --output-on-failure
```

All affected tests must pass. A stylistic refactor should never change
runtime behavior; if a test fails after the change, the conversion is
incorrect (most likely a subtle const-correctness or type-deduction bug).

### 5d. Build-disabled modules

Some modules (e.g. `IODCMTK`, `BridgeOpenCV`, `VideoBridgeVXL`) may be
disabled in the local CMake config. Files in those modules cannot be
verified locally — note this in the PR description so reviewers know CI
is the first verification for those specific files.

### 5e. Diff review

```bash
git -C ~/Dashboard/src/ITK diff --stat
git -C ~/Dashboard/src/ITK diff
```

Final sanity check: confirm only whitespace/style changes, no semantic
changes.

---

## Step 6: Commit and create PR

Stage only the modified files by name (avoid `git add -A` — the build may
have created untracked files):

```bash
cd ~/Dashboard/src/ITK
git add <each modified file>
git status   # verify nothing unexpected is staged
```

### Pattern `fill` commit + PR

```bash
git commit -m "STYLE: Replace Fill(N) with ::Filled(N) for FixedArray-based types

Replace the two-line declare-then-Fill pattern with the modern single-line
constexpr factory method ::Filled(N) available on all itk::FixedArray subclasses
(SizeType, IndexType, SpacingType, OffsetType, etc.).

Suggested by N-Dekker in ITK PR #6003."

gh pr create --draft --repo InsightSoftwareConsortium/ITK \
  --title "STYLE: Replace Fill(N) with ::Filled(N) for FixedArray-based types" \
  --body "$(cat <<'EOF'
Mechanical replacement of the two-line declare-then-Fill pattern with the single-line constexpr factory method `::Filled(N)`. Pure readability — no semantic change. Suggested by @N-Dekker; same shape as #6010.

<details>
<summary>Pattern</summary>

Before:

\`\`\`cpp
SizeType size;
size.Fill(0);
\`\`\`

After:

\`\`\`cpp
constexpr auto size = SizeType::Filled(0);
\`\`\`

Applies to all `itk::FixedArray` subclasses: `SizeType`, `IndexType`, `SpacingType`, `OffsetType`, `PointType`, `VectorType`, etc., when the fill value is a compile-time constant.

</details>

<details>
<summary>Discovery method</summary>

Hybrid clang-query AST matcher + Python pairing scanner: `varDecl(hasInitializer(cxxConstructExpr(argumentCountIs(0))))` finds default-constructed class-type local vars; the Python step pairs each with its first subsequent `.Fill()` call. See SKILL.md for details.

</details>

<!--
provenance: itk-sizetype-filled skill, fill pattern
suggested_by: N-Dekker
reference_pr: #6010 (merged 2026-04-05)
mechanical_change: Type v; v.Fill(N); -> constexpr auto v = Type::Filled(N);
applies_to: FixedArray subclasses (SizeType, IndexType, SpacingType, OffsetType, PointType, VectorType, ...)
-->
EOF
)"
```

Reference PR for the `fill` case: **#6010** (merged 2026-04-05). The body above follows `~/.claude/rules/pr-message-format.md`.

### Pattern `assign` commit + PR

```bash
git commit -m "STYLE: Replace declare-then-assign with const auto for FixedArray-based types

Replace the two-line pattern:

  Type var;
  var = expr;

with the idiomatic single-line:

  const auto var = expr;

for local variables of FixedArray-based types (SizeType, IndexType,
PointType, VectorType) where the variable is not modified after
initialization. Cases where the variable was reassigned or mutated
later in scope were left unchanged."

gh pr create --draft --repo InsightSoftwareConsortium/ITK \
  --title "STYLE: Replace declare-then-assign with const auto for FixedArray-based types" \
  --body "$(cat <<'EOF'
Mechanical replacement of the two-line declare-then-assign pattern with the idiomatic single-line `const auto var = expr;` for local variables of FixedArray-based types where the variable is not later mutated. Suggested by @N-Dekker; same shape as #6014.

<details>
<summary>Pattern</summary>

Before:

\`\`\`cpp
Type var;
var = expr;
\`\`\`

After:

\`\`\`cpp
const auto var = expr;
\`\`\`

Applies only to local variables of `itk::FixedArray`-based types (`SizeType`, `IndexType`, `PointType`, `VectorType`, etc.) where the variable is *not* reassigned or mutated later in scope. Cases with subsequent mutation are left unchanged (or rewritten to explicit-type form `Type var = expr;` to preserve mutation but eliminate the declare-then-assign churn).

</details>

<details>
<summary>Discovery method</summary>

Hybrid clang-query AST matcher + Python pairing scanner. The matcher finds default-constructed class-type local vars; the Python step pairs each with its first subsequent assignment, stepping over intervening declarations and comments. The skill is careful to NOT collapse declarations that are later mutated.

</details>

<!--
provenance: itk-sizetype-filled skill, assign pattern
suggested_by: N-Dekker
reference_pr: #6014 (2026-04-05)
mechanical_change: Type v; v = expr; -> const auto v = expr;
preserves: cases where v is later mutated (left unchanged or rewritten to explicit-type form)
applies_to: FixedArray subclasses
-->
EOF
)"
```

Reference PR for the `assign` case: **#6014** (2026-04-05). The body above follows `~/.claude/rules/pr-message-format.md`.

---

## Tips

### General
- Skip `.hxx` template implementations where the Fill value comes from a template parameter
- Skip member initializer lists where `constexpr` cannot be used
- If the variable is `const` already, it's already covered — skip
- The type is in ITK's non-ThirdParty `Modules/` tree; BridgeOpenCV and other
  non-default modules are out of scope for this skill (handle separately)

### `fill`-specific
- `float` literals like `1.0` work fine as `Filled(1.0)` since
  `FixedArray<float,N>::Filled` takes a `const ValueType`
- Integer literals `2`, `0u`, `42L` are all fine — the `Filled` parameter
  type is deduced from the FixedArray value type

### `assign`-specific
- Use `const auto`, NOT `constexpr auto` — the RHS is a runtime expression
- Watch for Eigen-style comma-operator initializers: `vv = 0, 1, 2;` is not
  a simple assignment and cannot be converted. In ITK, this is sometimes
  used for small vectors and arrays via overloaded `operator,`.
- Watch for commented-out code: `/* vv = 0, 1, 2; */` will match the regex
  scan but is not actual code. Method A (clang-tidy) naturally skips this.
- After conversion, check for newly-unused `using Type = ...;` aliases
  (see Dead typedef cleanup in Step 4)

### Rescan-same-function-after-first-fix rule

When the scan finds one convertible variable in a function, **rescan the
same function body for sibling convertibles after applying the fix**.
Test functions frequently declare several variables of the same kind
together (one `index`, one `fixedPoint`, one `movingPoint`, one
`displacement`) and only some match the scan.

Observed on 2026-04-05: the scan found `index` in 5 BSpline transform
tests (`itkBSplineDeformableTransformTest{2,3}.cxx`,
`itkBSplineTransformTest{2,3}.cxx`, `itkBSplineTransformInitializerTest1.cxx`)
but missed the sibling `movingPoint` variable declared 1 line below
`index` in every case, because `OutputPointType` was not in the regex.
Fixing `index` alone leaves the identical declare-then-assign pattern
intact for `movingPoint` right next to it — a partial conversion that
re-invites the same review cycle.

**Mitigation in two parts:**

1. **Use wildcard prefix patterns** (already done — both `FIXEDARRAY_RE`
   and `DECL_RE` use `\w*` before each type-family suffix). This catches
   `OutputPointType`, `InputPointType`, `MovingPointType`,
   `OutputVectorType`, `OutputCovariantVectorType`, `OutputVnlVectorType`,
   `MeshSizeType`, `FixedImagePointType`, `VirtualPointType`, and any
   future module-specific alias — without listing each one explicitly.

2. **After applying a fix in a function, grep the enclosing function
   body for any other `TypeName varname;` / `varname = expr;`
   patterns** on variables in the same while/for loop. Apply the same
   transformation in the same commit. Reviewers strongly prefer a
   single coherent cleanup over a drip-feed.

### Wildcard type-family patterns — design note

Both `FIXEDARRAY_RE` and `DECL_RE` now use `\w*` prefix before each
type-family suffix (`SizeType`, `IndexType`, `OffsetType`, `SpacingType`,
`PointType`, `VectorType`, `CovariantVectorType`). This was needed because
ITK transforms expose dozens of aliases:

- `InputPointType` / `OutputPointType` → `itk::Point<>` (FixedArray)
- `OutputVectorType` → `itk::Vector<>` (FixedArray)
- `OutputCovariantVectorType` → `itk::CovariantVector<>` (FixedArray)
- `OutputVnlVectorType` → `vnl_vector_fixed<>` (not FixedArray, but `const auto` is still valid)
- `MeshSizeType`, `FixedImagePointType`, `VirtualPointType`, etc.

**Caveat for `\w*VectorType`:** also matches `LabelObjectVectorType`,
`MembershipFunctionVectorType` and similar `std::vector`-based types.
These are not FixedArray-derived, but `const auto` conversion is still
semantically valid for them if the variable is not mutated. The scope
check (Step 3b) applies equally — proceed normally.

In practice, the scan of ITK `Modules/` found these `assign` candidates:
- `\w*PointType`: 47 (OutputPointType×30, InputPointType×15, PointType×2)
- `\w*VectorType`: 35 (OutputVectorType×17, OutputVnlVectorType×17, + 1 each)
- `\w*CovariantVectorType`: 17 (OutputCovariantVectorType×17)
- `IndexType`, `SizeType`: 5 total
Total: **107 candidates** as of 2026-04-05.

### Common gotchas observed in practice (PRs #6010, #6014)

1. **Variable reused across multiple measurements.** In
   `itkAnnulusOperatorGTest.cxx`, a single `annulusSize` variable was
   declared once and reassigned 3+ times later in the same function as
   the annulus parameters were changed. A strict "next-line" pattern
   matcher will flag the first pair as a candidate, but applying the
   transform would produce a compile error on the subsequent reassignments.

   The same "one scratch variable, many reassignments" pattern shows up
   across ITK test files wherever a single test runs the same operation
   on multiple inputs and prints each result. Example
   (`itkBSplineDeformableTransformTest.cxx`, `itkBSplineTransformTest.cxx`):
   a single `PointType outputPoint;` is reassigned 6+ times, once per
   test point. These are particularly tricky because there's often a
   `// descriptive comment` between the declaration and the first
   assignment, so they only match with the comment-aware scanner.

2. **Variable mutated via indexed write.** In `itkImageLinearIteratorTest.cxx`,
   `testIndex = start; testIndex[1] += 2;` — the `operator[]` assignment
   is a write that invalidates `const auto`.

3. **Variable passed to a method that takes non-const reference.** Some
   ITK APIs take `SizeType &` parameters. Grep for `SetSomething(varname)`
   and inspect the method signature.

4. **Generic variable names are warning signs.** `index`, `size`,
   `tempIndex`, `idx` are commonly reused. Names like `readerOrigin3D`,
   `extentSize`, `normalizedAnnulusSize` tend to be write-once.

5. **Don't over-scope the initial PR.** The first `assign` PR (#6014)
   landed 5 conversions across 5 files. Aim for ~5-20 conversions per PR
   so reviewers can verify each one individually. Multiple small focused
   PRs merge faster than one sprawling one.

6. **Intervening unrelated declarations.** In
   `itkBSplineInterpolationWeightFunctionTest.cxx` the pattern was:
   ```cpp
   WeightsType weights;
   IndexType   startIndex;   // unrelated decl between weights and its first use

   weights = function->Evaluate(position);
   ```
   A line-based "next non-blank line" scanner misses this because line
   N+1 is an unrelated declaration, not the assignment. The hybrid
   clang-query + Python scanner (Method A) handles it because the Python
   pairing step scans forward for the first `varname = expr;` anywhere
   in the enclosing scope, stepping over intervening decls and comments.

7. **Merge-without-const is still worthwhile.** In the same BSpline test,
   `weights` is passed by non-const reference later:
   ```cpp
   function->Evaluate(position, weights, startIndex);   // mutates weights
   ```
   So `const auto` is invalid. But the merge is still valuable — replace
   with `WeightsType weights = function->Evaluate(position);` (explicit
   type preserved, mutable). Per C++ Core Guidelines ES.22, don't
   declare a variable until you have a value to initialize it with, even
   if the value will later change.

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
