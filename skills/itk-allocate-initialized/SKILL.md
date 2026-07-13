---
name: itk-allocate-initialized
version: 1.0.0
purpose: Scans the ITK codebase for `->Allocate(true)` and `.Allocate(true)` call sites (excluding ThirdParty and the definition in itkImageBase.h) and replaces them with the more readable `->AllocateInitialized()` / `.AllocateInitialized()` equivalent.
description: >-
  Scans the ITK codebase for `->Allocate(true)` and `.Allocate(true)` call sites
  (excluding ThirdParty and the definition in itkImageBase.h) and replaces them with
  the more readable `->AllocateInitialized()` / `.AllocateInitialized()` equivalent.
  Creates a branch and PR on InsightSoftwareConsortium/ITK.

  Trigger when the user mentions: AllocateInitialized, Allocate(true) replacement,
  ITK image allocation readability, or references N-Dekker's suggestion to use
  AllocateInitialized() instead of Allocate(true) in ITK.
triggers:
  - itk-allocate-initialized
  - /itk-allocate-initialized
user_invocable: true
cmd: false
argument_hint: null
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

# ITK `AllocateInitialized()` codebase modernization

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-allocate-initialized — Replace Allocate(true) with AllocateInitialized()

Usage:
  /itk-allocate-initialized             Scan ITK and replace all instances

Scans for ->Allocate(true) and .Allocate(true), creates branch + PR.
```

Replace `Allocate(true)` with the self-documenting `AllocateInitialized()` alias.

## Background

`itk::ImageBase::AllocateInitialized()` was added as an alias for `Allocate(true)`
to make zero-initialization intent explicit in code. From `itkImageBase.h`:

```cpp
/** Allocates the pixel buffer of the image, zero-initializing its pixels.
 *  AllocateInitialized() is equivalent to Allocate(true). It is just
 *  intended to make the code more readable. */
void AllocateInitialized() { return this->Allocate(true); }
```

`Allocate()` with no argument or `Allocate(false)` does NOT zero-initialize. The `true`
argument is easy to overlook. `AllocateInitialized()` is unambiguous.

## Target pattern

```cpp
// BEFORE
image->Allocate(true);
grid->Allocate(true);

// AFTER
image->AllocateInitialized();
grid->AllocateInitialized();
```

---

## Step 1: Locate ITK source tree

```bash
ITK_SRC=~/Dashboard/src/ITK
git -C "$ITK_SRC" branch --show-current
```

---

## Step 2: Create a new branch from upstream/main

```bash
cd "$ITK_SRC"
git fetch upstream
git checkout -b style-allocate-initialized upstream/main
```

---

## Step 3: Find all Allocate(true) call sites

```bash
grep -rn "Allocate(true)" "$ITK_SRC/Modules" \
  --include="*.cxx" --include="*.h" --include="*.hxx" \
  | grep -v "ThirdParty" \
  | grep -v "itkImageBase.h"
```

Review the list. The expected hits are:
- `Modules/IO/TransformMINC/src/itkMINCTransformIO.cxx` (2 occurrences)
- Any test files that use `->Allocate(true)` for zero-initialized test images

Also check the `Testing/` and `Examples/` trees if present:
```bash
grep -rn "Allocate(true)" "$ITK_SRC" \
  --include="*.cxx" --include="*.h" --include="*.hxx" \
  | grep -v ThirdParty \
  | grep -v "itkImageBase.h" \
  | grep -v "\.git/"
```

---

## Step 4: Apply replacements

For each confirmed call site, replace `->Allocate(true)` with `->AllocateInitialized()`
and `.Allocate(true)` with `.AllocateInitialized()`.

This is a pure mechanical text substitution — no semantic change, just readability.

Use the Edit tool per file, or apply via sed:
```bash
# Dry run first
grep -rln "Allocate(true)" "$ITK_SRC/Modules" \
  --include="*.cxx" --include="*.hxx" --include="*.h" \
  | grep -v ThirdParty | grep -v "itkImageBase.h" \
  | xargs sed -n 's/->Allocate(true)/->AllocateInitialized()/gp'

# Apply
grep -rln "Allocate(true)" "$ITK_SRC/Modules" \
  --include="*.cxx" --include="*.hxx" --include="*.h" \
  | grep -v ThirdParty | grep -v "itkImageBase.h" \
  | xargs sed -i '' 's/->Allocate(true)/->AllocateInitialized()/g'

# Handle dot-access version (rare)
grep -rln "\.Allocate(true)" "$ITK_SRC/Modules" \
  --include="*.cxx" --include="*.hxx" --include="*.h" \
  | grep -v ThirdParty | grep -v "itkImageBase.h" \
  | xargs sed -i '' 's/\.Allocate(true)/.AllocateInitialized()/g'
```

**IMPORTANT**: On macOS, `sed -i ''` is correct (BSD sed). On Linux, use `sed -i`.

---

## Step 5: Verify changes

```bash
git -C "$ITK_SRC" diff
```

Confirm:
- Only `Allocate(true)` → `AllocateInitialized()` changes
- No changes to `itkImageBase.h` (the definition stays as-is)
- No changes in ThirdParty

Also verify no remaining `Allocate(true)` call sites (excluding the definition):
```bash
grep -rn "Allocate(true)" "$ITK_SRC/Modules" \
  --include="*.cxx" --include="*.h" --include="*.hxx" \
  | grep -v ThirdParty | grep -v "itkImageBase.h"
# Should return empty
```

---

## Step 6: Commit and create PR

```bash
git -C "$ITK_SRC" add -p
git -C "$ITK_SRC" commit -m "STYLE: Replace Allocate(true) with AllocateInitialized() for readability

AllocateInitialized() is an alias for Allocate(true) introduced in itkImageBase.h
to make zero-initialization intent explicit. Replace all call sites outside of
ThirdParty and the definition itself.

Suggested by N-Dekker in ITK PR #6003."

gh pr create --draft --repo InsightSoftwareConsortium/ITK \
  --title "STYLE: Replace Allocate(true) with AllocateInitialized()" \
  --body "$(cat <<'EOF'
Mechanical replacement of `->Allocate(true)` with the self-documenting alias `->AllocateInitialized()` throughout the ITK `Modules/` tree. Pure readability — no semantic change. Suggested by @N-Dekker in https://github.com/InsightSoftwareConsortium/ITK/pull/6003#discussion_r3033225653.

<details>
<summary>Motivation</summary>

`Allocate(true)` zero-initializes the image buffer, but the `true` argument is easy to misread. `AllocateInitialized()` was added to `itkImageBase.h` exactly for this purpose:

> "AllocateInitialized() is equivalent to Allocate(true). It is just intended to make the code more readable."

</details>

<details>
<summary>Scope</summary>

Pure mechanical substitution. No semantic change. Only non-ThirdParty `Modules/` code is affected; the definition in `itkImageBase.h` is unchanged.

</details>

<!--
provenance: itk-allocate-initialized skill
suggested_by: N-Dekker (PR #6003 discussion r3033225653)
mechanical_change: Allocate(true) -> AllocateInitialized()
unchanged: itkImageBase.h definition, ThirdParty
-->
EOF
)"
```

**The PR body above follows `~/.claude/rules/pr-message-format.md`**: short visible summary up top, longer rationale collapsed into `<details>`, machine-readable provenance in HTML comments. Match this shape if you regenerate the body with different content.

---

## Notes

- `Allocate()` (no args) and `Allocate(false)` are NOT changed — they do NOT zero-initialize
- If a site uses `Allocate(true)` inside a comment or string literal, skip it
- Double-check the MINC transform IO changes since those are in a less-tested path

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
