---
name: itk-inline-destructors-fix
version: 1.0.0
purpose: Detect and fix inline `= default` destructor ABI problems in ITK and ITK-related C++ projects (VTK, CTK, Slicer, etc.).
description: >-
  Detect and fix inline `= default` destructor ABI problems in ITK and
  ITK-related C++ projects (VTK, CTK, Slicer, etc.). Use this skill whenever
  the user mentions: moving destructors to .cxx files, -fvisibility-inlines-hidden
  ABI issues, hidden D1Ev/D0Ev symbols, inline = default destructor problems,
  fixing exported class ABI, or auditing ITK classes for shared library
  visibility. Also trigger when a user asks to "find all classes where the
  destructor should move to the .cxx" or references ITK issue #6000 / PR #6002.
  The skill scans headers for the pattern, classifies matches as concrete /
  abstract / template (only concrete non-template classes need the fix),
  applies the mechanical change, and verifies the build.
triggers:
  - itk-inline-destructors-fix
  - /itk-inline-destructors-fix
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

# Fix Inline `= default` Destructor ABI — ITK / VTK Projects

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-inline-destructors-fix — Move inline = default destructors to .cxx

Usage:
  /itk-inline-destructors-fix                Scan all headers in cwd project
  /itk-inline-destructors-fix Modules/IO     Restrict scan to one module path

Finds concrete non-template classes with inline = default destructors
that break ABI under -fvisibility-inlines-hidden.
```

## Why This Matters

ITK (and projects built like it) compile with `-fvisibility-inlines-hidden`
globally. This flag hides **all inline function definitions** from the shared
library export table, overriding the `ITK*_EXPORT` / `VTK_EXPORT` class-level
visibility attribute for inline members.

When `~Foo() override = default;` is written inline in the class body:

| Symbol | Effect |
|--------|--------|
| vtable | ✅ Exported (anchored by out-of-line `GetNameOfClass()`) |
| typeinfo | ✅ Exported |
| **D1Ev** (complete-object dtor) | ❌ **Hidden** — ABI break |
| **D0Ev** (deleting dtor) | ❌ **Hidden** — ABI break |

Pre-compiled consumers (`.so`, Python extensions, downstream DSOs) that were
linked against a version of ITK where these symbols were exported will **fail
to load at runtime** — silently, with no link error.

The fix is one mechanical change per class: declare the destructor in the
header, define it in the `.cxx`.

**References:** ITK issue #6000; PR #6002 (30-class batch fix); PR #5995
(original ABI report).

---

## Classification Rules

Before changing anything, classify each candidate hit:

| Class type | Action |
|------------|--------|
| **Concrete non-template** (`ITK*_EXPORT`, no pure virtuals, no `template <`) | ✅ **Fix it** |
| **Abstract** (has at least one `= 0` pure virtual) | ⏭ Skip — vtable lives in subclass TU |
| **Template** (`ITK_TEMPLATE_EXPORT` or `template <` in class declaration) | ⏭ Skip — cannot define dtor in `.cxx` without explicit instantiation boilerplate |
| **Non-exported** (no `*_EXPORT` macro on the class) | ⏭ Skip — not in the shared lib ABI |

> **Key pitfall:** A class having a `.cxx` file does NOT mean it is
> non-template. ITK template classes use `.cxx` files for explicit
> instantiation lists. Always grep the header for `template <` or
> `ITK_TEMPLATE_EXPORT` before treating a match as fixable.

---

## Step-by-Step Workflow

### Step 1 — Scan for candidates

Run this grep from the repo root (adjust `Modules/` to `src/` or `.` as
appropriate for the project):

```bash
grep -rn "~.*() override = default;" Modules/ \
  --include="*.h" \
  --exclude-path="*/ThirdParty/*" \
  -l
```

Then for each file, extract the class name and line number:

```bash
grep -n "~.*() override = default;" <file.h>
```

### Step 2 — Classify each hit

For each header file with a match:

1. **Template check** — is it a template class?
   ```bash
   grep -n "ITK_TEMPLATE_EXPORT\|^template\s*<" <file.h>
   ```
   If found → **skip**.

2. **Export macro check** — does the class have `*_EXPORT`?
   ```bash
   grep -n "_EXPORT" <file.h>
   ```
   If not found → **skip**.

3. **Abstract check** — does it have pure virtual methods?
   ```bash
   grep -n "= 0;" <file.h>
   ```
   If found → **skip**.

4. **`.cxx` file exists?**
   ```bash
   ls src/$(basename <file.h> .h).cxx   # adjust path as needed
   ```
   If not → **skip** (no translation unit to put the definition into).

Only classes that pass all four checks need the fix.

### Step 3 — Apply the fix

**In the header** — change the inline definition to a declaration:

```cpp
// BEFORE:
~FooClass() override = default;

// AFTER:
~FooClass() override;
```

**In the `.cxx` file** — inject the definition immediately after the
namespace opening brace, before any existing code:

```cpp
namespace itk          // (or itk::fem, itk::Statistics, etc.)
{
FooClass::~FooClass() = default;

// ... rest of file unchanged ...
```

> Use the exact namespace that the rest of the file uses. Check the `.cxx`
> file's existing namespace declaration — ITK uses `namespace itk`,
> `namespace itk::fem`, `namespace itk::Statistics`, etc.

### Step 4 — Verify

Build only the affected module(s) first to catch errors quickly:

```bash
# ITK with pixi:
cd build && ninja <ModuleName>

# Or CMake directly:
cmake --build build --target <ModuleName> -j8
```

If the build fails:
- **"unknown type name 'Foo'"** → the class is actually a template; revert and
  skip.
- **Redefinition error** → the `.cxx` already has an out-of-line destructor
  from somewhere else; revert the `.cxx` change only.
- **Namespace mismatch** → check what namespace the rest of the `.cxx` uses.

Then run the affected tests:

```bash
ctest -R <ModuleName> --timeout 120 -j8
```

### Step 5 — Commit

Use the `COMP:` prefix (compilation fix):

```
COMP: Move inline = default destructors to .cxx for N exported classes

Non-template exported classes with `~ClassName() override = default;`
inline in the header have hidden D1Ev/D0Ev destructor thunks under
-fvisibility-inlines-hidden, even when the class vtable and typeinfo
remain exported.  Moving the destructor definition out-of-line ensures
it is compiled in one TU with default (exported) visibility.

See: https://github.com/InsightSoftwareConsortium/ITK/issues/6000
```

---

## Automation Script

For large codebases (>10 classes), use the bundled Python script to apply
changes mechanically. Read `scripts/patch_destructors.py` for usage.

The script handles:
- Namespace detection (single-level `namespace itk {` and nested
  `namespace itk::fem {`)
- Skipping files that already have an out-of-line destructor in the `.cxx`
- Dry-run mode to preview changes before applying

After running the script, **always build immediately** — the script cannot
detect template false-positives; those only reveal themselves at compile time.
Revert any files that fail to compile.

---

## Common False Positives

| Pattern | Reason it looks fixable but isn't |
|---------|----------------------------------|
| `ITK_TEMPLATE_EXPORT` in class declaration | Template — cannot define dtor in `.cxx` |
| Class has `template <` anywhere in declaration | Same |
| `.cxx` file contains `template class ITK_EXPORT Foo<...>;` | Explicit-instantiation `.cxx` — putting a non-instantiated dtor here breaks the build |
| Class has `= 0` methods but you missed them | Abstract — skip |
| Header declares class with `_EXPORT` but it is actually a free helper struct | May not have vtable at all; check for virtual methods |

---

## Quick Reference: Expected Output After Fix

After the fix, verify with `nm` on the shared library:

```bash
nm -D libITKFoo.so | c++filt | grep "FooClass::~FooClass"
```

You should see `T` (exported text) for `D1Ev` and `D0Ev`, not `t` (hidden):

```
0000... T itk::FooClass::~FooClass()       # D1 complete-object dtor
0000... T itk::FooClass::~FooClass()       # D0 deleting dtor
```

If you still see `t` (lowercase), the definition is still being treated as
inline — double-check that the header change removed `= default` from the
declaration and that the `.cxx` definition is inside the namespace block.

## Enhanced by

- **serena** — Semantic symbol lookup for precise destructor identification
  and relocation. Falls back to regex when unavailable.

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

- **clangd-lsp** — LSP-based symbol resolution for accurate class hierarchy
  traversal. Requires compile_commands.json. Falls back to grep when unavailable.
