---
name: itk-nodiscard-return-value
version: 1.0.0
purpose: Fix [[nodiscard]] -Wunused-result warnings in ITK 5.x code by replacing two-argument output-parameter calls with the single-argument return-value form.
description: >-
  Fix [[nodiscard]] -Wunused-result warnings in ITK 5.x code by replacing
  two-argument output-parameter calls with the single-argument return-value form.
  Use when GCC reports -Wunused-result for TransformPhysicalPointToIndex,
  TransformPhysicalPointToContinuousIndex, or any other ITK function marked
  [[nodiscard]] in ITK 5+. Trigger on: "-Wunused-result", "nodiscard", "ignoring
  return value", "TransformPhysicalPoint migration".
triggers:
  - itk-nodiscard-return-value
  - /itk-nodiscard-return-value
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

# ITK [[nodiscard]] Return-Value Migration

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-nodiscard-return-value — Fix [[nodiscard]] -Wunused-result warnings

Usage:
  /itk-nodiscard-return-value                Scan and fix cwd project
  /itk-nodiscard-return-value Modules/IO     Restrict to one module path

Replaces two-arg output-parameter calls with single-arg return-value form.
```

ITK 5.x added `[[nodiscard]]` to several `ImageBase` methods that previously
returned void or had output parameters.  GCC reports `-Wunused-result` when the
return value is discarded.

## Affected ITK methods

| Method | Return type | Notes |
|--------|-------------|-------|
| `TransformPhysicalPointToIndex(point)` | `IndexType` | single-arg form added ITK 5 |
| `TransformPhysicalPointToContinuousIndex<T>(point)` | `ContinuousIndexType<T>` | template arg required |
| `TransformPhysicalPointToIndex(point, index)` | `bool` (in bounds?) | old two-arg form — discard triggers warning |
| `TransformPhysicalPointToContinuousIndex(point, index)` | `bool` | old two-arg form |

## Fix pattern

**Two-argument (old):**
```cpp
typename T::ContinuousIndexType idx;
image->TransformPhysicalPointToContinuousIndex(point, idx);
```

**Single-argument (new) — preferred:**
```cpp
auto idx = image->template TransformPhysicalPointToContinuousIndex<double>(point);
```

For `TransformPhysicalPointToIndex`:
```cpp
// old:
image->TransformPhysicalPointToIndex(point, index);

// new:
index = image->TransformPhysicalPointToIndex(point);
```

**When the bool return value matters** (bounds check):
```cpp
// old:
if (image->TransformPhysicalPointToIndex(point, index)) { /* in bounds */ }

// new (unchanged — return value IS used):
if (image->TransformPhysicalPointToIndex(point, index)) { /* still correct */ }
```
Only the *discarded* two-arg calls need fixing; calls inside `if` conditions
are already using the return value and do not trigger -Wunused-result.

## When to use [[maybe_unused]] instead

**Do NOT use `[[maybe_unused]]`** for these ITK cases unless you have manually
confirmed that the bounds check is genuinely irrelevant.  The return-value form
is always cleaner and avoids the question.

Only use `[[maybe_unused]]` when:
- The function is not in ITK (no single-arg overload exists), AND
- You have inspected the call site and confirmed bounds are guaranteed by context.

## Template argument for ContinuousIndex

`TransformPhysicalPointToContinuousIndex` is a function template. The explicit
template argument `<double>` (or `<float>`) is required when called without an
output parameter to deduce the index representation type:

```cpp
// Type of returned index depends on T:
auto idx = image->template TransformPhysicalPointToContinuousIndex<double>(point);
// If image is itk::Image<float,3>, idx is ContinuousIndex<double,3>
```

Check the variable's declared type in the surrounding scope to pick the right T.

## Audit

```bash
grep -rn --include='*.cxx' --include='*.hxx' --include='*.h' \
  'TransformPhysicalPoint' <source-dir> | grep -v '//\|if (' | \
  grep -v '= image\|= this\|= .*->Trans'   # already using return value
```

Lines that remain after filtering are discarding the return value.

## Commit message format

```
COMP: Fix -Wunused-result for TransformPhysical*To* in <Module>

ITK 5.x marks TransformPhysicalPointToIndex and
TransformPhysicalPointToContinuousIndex [[nodiscard]].  Replace
two-argument calls (discarded bool return) with the single-argument
overload that returns the index directly.
```

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
