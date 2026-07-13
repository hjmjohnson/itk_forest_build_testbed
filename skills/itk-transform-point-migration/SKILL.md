---
name: itk-transform-point-migration
version: 1.0.0
purpose: Use when migrating ITK-based C++ projects (BRAINSTools, Slicer, NAMIC tools, ITK itself) from the ITKv4 two-argument output-parameter form of image Transform* methods to the ITKv5 single-argument return-value form.
description: >-
  Use when migrating ITK-based C++ projects (BRAINSTools, Slicer, NAMIC tools,
  ITK itself) from the ITKv4 two-argument output-parameter form of image
  Transform* methods to the ITKv5 single-argument return-value form. Eliminates
  declare-then-use patterns. Trigger on: "TransformIndexToPhysicalPoint",
  "TransformContinuousIndexToPhysicalPoint", "output parameter migration",
  "declare then use", "ITKv4 to ITKv5", "pnt = TransformContinuousIndex".
triggers:
  - itk-transform-point-migration
  - /itk-transform-point-migration
user_invocable: true
cmd: false
argument_hint: "[path/to/module]"
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
    network_required: true
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

# ITK Transform*Point Migration (ITKv4 → ITKv5)

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-transform-point-migration — Migrate ITKv4 two-arg to ITKv5 return-value

Usage:
  /itk-transform-point-migration                 Scan and migrate cwd project
  /itk-transform-point-migration Modules/IO      Restrict to one module path

Migrates: TransformIndexToPhysicalPoint, TransformContinuousIndexToPhysicalPoint,
TransformPhysicalPointToIndex, TransformPhysicalPointToContinuousIndex.
```

Replaces two-argument output-parameter `Transform*` calls with the ITKv5
single-argument return-value form, eliminating pre-declared "declare then use"
variables and aligning with `[[nodiscard]]` API expectations.

**Related skill:** `itk-nodiscard-return-value` covers the GCC `-Wunused-result`
warning angle for `TransformPhysicalPoint*`. This skill covers the full
migration of all four Transform methods across both directions.

---

## The Two Function Families

These methods are defined in `itkImageBase.h` and mirrored in `itkImageAdaptor.h`.
Both classes need the same migration treatment.

### Family A — `*ToPhysicalPoint` (always safe to migrate)

ITKv4 returned `void`; ITKv5 returns the point. The two-arg form is deprecated.

| Method | Old signature | New signature |
|--------|--------------|---------------|
| `TransformIndexToPhysicalPoint` | `void (index, &point)` | `PointType (index)` |
| `TransformContinuousIndexToPhysicalPoint` | `void (cidx, &point)` | `PointType (cidx)` |

### Family B — `*FromPhysical` (bool return — check before migrating)

Both signatures coexist in ITKv5; the two-arg form is `[[nodiscard]]`.

| Method | Two-arg form | One-arg form |
|--------|--------------|--------------|
| `TransformPhysicalPointToIndex` | `bool (point, &index)` — is-in-bounds | `IndexType (point)` |
| `TransformPhysicalPointToContinuousIndex` | `bool (point, &cidx)` | `ContinuousIndex<T> (point)` |

**Rule:** If the `bool` return is captured (`const bool inside = ...`), keep the
two-arg form or restructure with an explicit `IsInsideBuffer` / `IsInside`
check. If the bool is discarded, migrate to the one-arg form.

---

## CRITICAL: Two Template Syntax Requirements (Current ITK)

> **Upstream fix pending:** ITK branch `enh/default-template-arg-transform-point`
> ([hjmjohnson/ITK](https://github.com/hjmjohnson/ITK/tree/enh/default-template-arg-transform-point))
> adds `= PointValueType` defaults to all three methods in both `itkImageBase.h`
> and `itkImageAdaptor.h`. Once merged, **both** requirements below go away and
> callers can write simply `image->TransformIndexToPhysicalPoint(idx)`.
> See the "Upstream Default Template Argument" section below for details.

### 1. Explicit `<double>` Template Argument Required

The ITK one-argument return-value forms are **function templates** where
`TCoordRep` appears **only in the return type** — it **cannot be deduced**
from the call arguments. Every call **must** include an explicit template
argument (typically `<double>`):

```cpp
// WRONG — won't compile: "couldn't infer template argument 'TCoordRep'"
const auto pnt = image->TransformIndexToPhysicalPoint(idx);

// CORRECT
const auto pnt = image->template TransformIndexToPhysicalPoint<double>(idx);
```

This applies to `TransformIndexToPhysicalPoint`, `TransformContinuousIndexToPhysicalPoint`,
and the one-arg `TransformPhysicalPointToContinuousIndex`. Use `<double>` unless the
original code used a different precision type (e.g. `<float>`).

For `TransformPhysicalPointToIndex`, `TCoordRep` is deducible from the `Point`
argument, so no explicit template argument is needed.

**Note:** `<double>` matches `SpacePrecisionType`, which is `double` by default
but can be `float` when ITK is configured with `ITK_USE_FLOAT_SPACE_PRECISION`.
A cross-project census (ITK, BRAINSTools, ANTs, Slicer — 158 call sites) found
94% use `double` (or aliases that resolve to `double`), and only 6% use `<float>`
(all intentional: ITK GTests for API contract verification, plus one BRAINSTools
site that is likely a historical artifact).

### 2. `template` Keyword Required (Always Add It)

When calling `->TransformIndexToPhysicalPoint<double>(...)` through a
**dependent type** (any expression whose type depends on a template parameter),
C++ requires the `template` keyword to disambiguate `<` from less-than:

```cpp
// Inside template<typename TImage> class or function:
// WRONG — GCC: "expected primary-expression before 'double'"
//         Clang: "use 'template' keyword to treat ... as a dependent template name"
const auto pnt = m_Image->TransformIndexToPhysicalPoint<double>(idx);

// CORRECT
const auto pnt = m_Image->template TransformIndexToPhysicalPoint<double>(idx);
```

**Best practice: always add `template` uniformly.** It is valid and harmless in
non-dependent contexts too, and avoids needing to classify each call site.
Most `.hxx` and template `.h` files in ITK projects are template contexts.

**Why both requirements are coupled:** The `template` keyword is only needed
because `<double>` introduces a `<` that the compiler must disambiguate. If
the upstream default is merged, callers omit `<double>`, there is no `<` to
disambiguate, and the `template` keyword becomes unnecessary.

---

## Migration Patterns

### Pattern 1 — Simple void-call (Family A, most common)

```cpp
// BEFORE: two-arg, variable already declared
ImageType::PointType pnt;
image->TransformIndexToPhysicalPoint(idx, pnt);

// AFTER: declare-and-init, drop the pre-declaration
const auto pnt = image->template TransformIndexToPhysicalPoint<double>(idx);
```

When the pre-declaration lives many lines above the call, delete the
declaration line and add `const auto` to the call site.

### Pattern 2 — Reused variable across iterations (Family A)

```cpp
// BEFORE
ImageType::PointType pnt;
for (...) {
    image->TransformIndexToPhysicalPoint(idx, pnt);
    use(pnt);
}

// AFTER — move declaration inside loop
for (...) {
    const auto pnt = image->template TransformIndexToPhysicalPoint<double>(idx);
    use(pnt);
}
```

If `pnt` is also read *after* the loop, keep it mutable:

```cpp
ImageType::PointType pnt;
for (...) {
    pnt = image->template TransformIndexToPhysicalPoint<double>(idx);
    use(pnt);
}
// pnt still accessible here
```

### Pattern 3 — Family B, bool discarded (safe to migrate)

```cpp
// BEFORE: bool return silently discarded — [[nodiscard]] warning on GCC
image->TransformPhysicalPointToIndex(pnt, idx);

// AFTER
const auto idx = image->template TransformPhysicalPointToIndex<double>(pnt);
```

### Pattern 4 — Family B, bool captured (DO NOT migrate)

```cpp
// KEEP AS-IS — two-arg form intentionally captures the bounds check
const bool isInside = image->TransformPhysicalPointToIndex(pnt, idx);
if (isInside) { ... }

// Also keep when used in if-condition directly:
if (image->TransformPhysicalPointToIndex(pnt, idx)) { ... }
```

### Pattern 5 — `TransformPhysicalPointToContinuousIndex` template arg

The one-arg form requires an explicit template argument to fix the index
precision type:

```cpp
// BEFORE
typename ImageType::ContinuousIndexType cidx;
image->TransformPhysicalPointToContinuousIndex(pnt, cidx);

// AFTER — pick <double> or <float> to match the original declared type
auto cidx = image->template TransformPhysicalPointToContinuousIndex<double>(pnt);
// or when called through a pointer that needs ::template disambiguation:
auto cidx = this->m_Image->template TransformPhysicalPointToContinuousIndex<double>(pnt);
```

---

## Step 0: Verify ITK Version Supports the One-Arg Form

**Before migrating any code**, confirm that the project's pinned ITK version
has the one-argument return-value overloads. These were added in ITK 5.x
(PR [#868](https://github.com/InsightSoftwareConsortium/ITK/pull/868)).

### Check the ITK signature

Find the project's ITK header (build tree or SuperBuild source):

```bash
# In a SuperBuild project (BRAINSTools, Slicer, etc.):
find build -name "itkImageBase.h" -path "*/include/ITK-*" | head -1
# Or in the ITK source tree:
find . -path "*/Core/Common/include/itkImageBase.h" | head -1
```

Then check for the one-arg overload:

```bash
grep "TransformIndexToPhysicalPoint(const IndexType" <path-to-itkImageBase.h>
```

You should see **two** matches: the two-arg `void` form and the one-arg
`[[nodiscard]]` return-value form. If only the two-arg form exists, the
ITK version is too old for this migration.

### Check for default template arguments

```bash
grep "= PointValueType" <path-to-itkImageBase.h>
```

This determines which call syntax to use:

| Default present? | Call syntax |
|:----------------:|------------|
| **Yes** (`= PointValueType`) | `image->TransformIndexToPhysicalPoint(idx)` — clean, no `<double>`, no `template` keyword |
| **No** | `image->template TransformIndexToPhysicalPoint<double>(idx)` — explicit `<double>` and `template` keyword both required |

The default was proposed in ITK branch
[`enh/default-template-arg-transform-point`](https://github.com/hjmjohnson/ITK/tree/enh/default-template-arg-transform-point).
Until merged, downstream projects must use the verbose form.

### For SuperBuild projects: check the pinned ITK commit

```bash
# BRAINSTools example:
grep -A2 "GIT_TAG" SuperBuild/External_ITKv5.cmake
```

Verify the pinned commit is recent enough to include the one-arg overloads.

---

## Step 1: Scan and Classify

Run `scan.py` (in this skill's directory) from the repo root or any subtree:

```bash
python3 ~/.claude/skills/itk-transform-point-migration/scan.py <source-dir>
```

Output groups call sites into:
- **MIGRATE (ToPhysical)** — Family A, two-arg, safe
- **MIGRATE (FromPhysical, bool-ignored)** — Family B, bool not used
- **KEEP (bool-captured)** — Family B, bool is used — leave unchanged
- **ALREADY NEW** — already using return-value form

---

## Step 2: Apply Changes File by File

For each file in the MIGRATE buckets:

1. Read the file around the call site.
2. Find the pre-declaration of the output variable (usually 1–10 lines above).
3. Decide Pattern 1 vs Pattern 2 (is the variable reused after the call?).
4. Apply with the Edit tool — do not use `sed -i` (macOS vs Linux incompatibility).
5. **Check for orphaned typedefs:** if the old declaration used a `using` alias
   (e.g. `using SamplePointType = ...`), grep for it — if no remaining uses,
   delete it. GCC `-Wunused-local-typedefs` will fail CI otherwise.
5. **Always use `->template TransformIndexToPhysicalPoint<double>(...)`** — the
   `template` keyword and explicit `<double>` are both mandatory.

---

## Step 3: Verify

```bash
# Confirm no old-style two-arg ToPhysical calls remain (excluding comments)
grep -rn \
  "TransformIndexToPhysicalPoint\|TransformContinuousIndexToPhysicalPoint" \
  <source-dir> \
  --include="*.cxx" --include="*.hxx" --include="*.h" \
  | grep -v "^\s*//" \
  | grep ", "   # two-arg calls have a comma in the args
```

For Family B, confirm only intentional bool-captures remain:

```bash
grep -rn "TransformPhysicalPoint" <source-dir> \
  --include="*.cxx" --include="*.hxx" --include="*.h" \
  | grep ", "             # two-arg form
  | grep -v "bool\|if ("  # remaining should be none (or reviewed)
```

Build and confirm no new warnings:

```bash
ninja -C <build-dir> 2>&1 | grep -i "TransformPhysicalPoint\|nodiscard\|unused-result"
```

---

## Commit Message Format

```
COMP: Migrate TransformIndexToPhysicalPoint to ITKv5 return-value form in <Module>

Replaces the ITKv4 two-argument output-parameter form with the ITKv5
single-argument return-value form for TransformIndexToPhysicalPoint and
TransformContinuousIndexToPhysicalPoint throughout <Module>:

  image->TransformIndexToPhysicalPoint(idx, pnt);
  → const auto pnt = image->template TransformIndexToPhysicalPoint<double>(idx);

Eliminates declare-then-use patterns.  TransformPhysicalPoint* calls where
the bool return value is captured are left unchanged.
```

Use `COMP:` prefix (compiler/API compatibility maintenance), not `ENH:` or `MAINT:`.

---

## Performance Impact

**None.** This is a zero-cost refactor. If asked whether performance is affected, the answer is no — here is why:

| Factor | Analysis |
|--------|----------|
| **C++17 mandatory copy elision** | ITKv5 requires C++17. The compiler is *required* to construct the returned `PointType` directly in the caller's destination slot (RVO/NRVO). No copy or move is emitted — identical assembly to the output-parameter form. |
| **`Point<double,N>` is a stack array** | `itk::Point<double, 3>` is three `double` values on the stack — no heap allocation, no vtable, trivially constructible/destructible. Moving the declaration inside a loop body is free. |
| **`const` improves optimization** | The two-arg form forced the compiler to assume the output variable could alias other memory. `const auto` lets the compiler prove non-aliasing, enabling better constant propagation and CSE. |
| **Mutable assignment form** | Where `auto pnt = img->TransformIndexToPhysicalPoint(idx)` replaces a two-arg call on an already-declared variable, the worst case is three `movsd` instructions for a 3D point — unmeasurable in any real workload. |

**The two-arg form was a C-style API predating C++11 value semantics.** The ITKv5 return-value form is the idiomatic modern equivalent — same or better codegen, clearer intent.

---

## Upstream Default Template Argument (ITK Enhancement)

An ITK enhancement on branch
[`enh/default-template-arg-transform-point`](https://github.com/hjmjohnson/ITK/tree/enh/default-template-arg-transform-point)
adds `= PointValueType` as the default template argument to all three
one-argument return-value overloads in `itkImageBase.h` **and** `itkImageAdaptor.h`:

```cpp
// itkImageBase.h — proposed change (3 lines)
template <typename TCoordinate = PointValueType>
TransformIndexToPhysicalPoint(const IndexType &) const;

template <typename TCoordinate = PointValueType, typename TIndexRep>
TransformContinuousIndexToPhysicalPoint(const ContinuousIndex<TIndexRep, N> &) const;

template <typename TIndexRep = PointValueType, typename TCoordinate>
TransformPhysicalPointToContinuousIndex(const Point<TCoordinate, N> &) const;
```

### Why `PointValueType`?

- `PointValueType` = `SpacePrecisionType` = `double` by default
- Tracks `float` when `ITK_USE_FLOAT_SPACE_PRECISION` is enabled at CMake time
- Matches the image's own coordinate precision — the natural default

### Effect on downstream projects

Once merged, callers can write:

```cpp
// Clean form — no <double>, no template keyword needed
const auto pnt = image->TransformIndexToPhysicalPoint(idx);
```

instead of:

```cpp
// Current verbose form
const auto pnt = image->template TransformIndexToPhysicalPoint<double>(idx);
```

Existing code that explicitly specifies `<double>` or `<float>` is unaffected.

### Cross-project census (158 call sites: ITK + BRAINSTools + ANTs + Slicer)

| Category | Count | % |
|----------|------:|--:|
| Could drop `<double>` (literal `<double>` or `<SpacePrecisionType>`) | 100 | 63% |
| Generic forwarding (aliases that resolve to `double` in practice) | 48 | 31% |
| Intentionally `<float>` | 10 | 6% |

The 10 `<float>` sites: 9 in ITK GTests (API contract / ImageAdaptor equivalence
tests), 1 in BRAINSTools (historical artifact — float intermediate immediately
widened to double). ANTs and Slicer have zero `<float>` usage.

### Why `auto f() -> T` (trailing return type) doesn't help

C++ template argument deduction works exclusively from function **arguments**
to template parameters — it never flows backwards from the return type or the
variable being assigned to. A trailing return type (`auto f(args) -> ReturnType`)
is purely syntactic sugar; it does not change deduction rules. Only a default
template argument solves the problem.

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| **Omitting `<double>` on return-value form** | `TCoordRep` is NOT deducible — `img->template TransformIndexToPhysicalPoint<double>(idx)` is required. Without it: *"couldn't infer template argument 'TCoordRep'"* |
| **Omitting `template` keyword in dependent context** | Always use `->template TransformIndexToPhysicalPoint<double>(...)`. Without `template`, GCC sees `<` as less-than: *"expected primary-expression before 'double'"*. Safe to add everywhere — harmless in non-dependent contexts. |
| Migrating a bool-captured call | Check surrounding lines; if result feeds an `if`, keep two-arg |
| Forgetting `template` keyword on `ToContinuousIndex` | `this->m_Img->template TransformPhysicalPointToContinuousIndex<double>(p)` |
| Leaving stale pre-declaration variable | Delete the declaration line when converting to `const auto` |
| **Leaving orphaned `using` typedefs** | When the old code had `using PointType = ...; PointType p; image->Func(idx, p);` and you replace the declaration+call with `const auto p = ...`, the `using` line may become unused. GCC `-Wunused-local-typedefs` will flag it. **Always grep for the typedef name after migration** — if it appears only once (the `using` line itself), delete it. Common victims: `SamplePointType`, `InputPointType`, `OutputPointType`. |
| Using `sed -i` without `''` on macOS | Use Edit tool or `perl -i -pe` for portability |
| Migrating inside `ARCHIVE/` without owner approval | Ask first; ARCHIVE code may be intentionally frozen |

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
