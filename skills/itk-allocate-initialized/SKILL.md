---
name: itk-allocate-initialized
version: 1.1.0
purpose: Replace `->Allocate(true)` and `.Allocate(true)` call sites (excluding ThirdParty and the AllocateInitialized definition) with the more readable `AllocateInitialized()` equivalent.
description: >-
  Replaces `->Allocate(true)` and `.Allocate(true)` call sites (excluding
  ThirdParty and the definition in itkImageBase.h) with the more readable
  `AllocateInitialized()` equivalent. `allocate_initialized.py` does it
  unattended (`--graph --repo --manifest [--apply]`), writing an itk-helpers
  manifest for the itk-init-over-assign master; it records `itk-version`
  skips when the graph's ITK is older than 5.3, edits the working tree, and
  never commits.

  Trigger when the user mentions: AllocateInitialized, Allocate(true) replacement,
  ITK image allocation readability, or references N-Dekker's suggestion to use
  AllocateInitialized() instead of Allocate(true) in ITK.
triggers:
  - itk-allocate-initialized
  - /itk-allocate-initialized
user_invocable: true
cmd: false
argument_hint: "--graph <build-dir> --repo <path> --manifest <path> [--apply]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "**/*.cxx"
      - "**/*.h"
      - "**/*.hxx"
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "<manifest path given by --manifest>"
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: false
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
  skills:
    - itk-init-over-assign
  external_tools:
    - clang-format
    - git
  python_packages: []
  scripts:
    - allocate_initialized.py
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
  /itk-allocate-initialized             Scan the repo and replace all instances

Scans for ->Allocate(true) and .Allocate(true) and rewrites them; never commits.
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

## Running it

```bash
python3 allocate_initialized.py --graph <build-dir> --repo <path>   # dry run
python3 allocate_initialized.py --graph <build-dir> --repo <path> \
    --manifest m.json --apply
```

The dry run prints the call count per file and writes nothing. The script
scans the git-tracked C++ sources of the repo outside `ThirdParty`, `build`,
and `Utilities`, ignores matches in comments and string literals and the
body of `AllocateInitialized()` itself, and rewrites the rest in place.

`--graph` is the build directory the repo is configured in. Its
`CMakeCache.txt` names `ITK_DIR`, whose `ITKConfig.cmake` gives
`ITK_VERSION_MAJOR`/`MINOR`. `AllocateInitialized()` needs ITK 5.3, so on an
older ITK every site is recorded as skipped (`itk-version`, note
`itk:<major>.<minor>`) and nothing is edited. When the version cannot be
read, the script says so, assumes a new enough ITK, and notes
`itk-version:unknown` on each site.

Each call is a site of class `allocate_true` in an `itk-helpers` manifest,
at its post-edit line. Edited lines are clang-formatted; a file whose edit
strands a comment is restored and its sites recorded as `comment-stranded`.
`--apply` requires `--manifest`.

## Verify

```bash
git -C <repo> diff
git -C <repo> grep -n "Allocate(true)" -- '*.cxx' '*.h' '*.hxx'
```

Only `Allocate(true)` to `AllocateInitialized()` changes; the remaining hits
are the definition, ThirdParty, comments, and string literals.

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
