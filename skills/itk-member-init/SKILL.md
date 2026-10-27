---
name: itk-member-init
version: 1.0.0
purpose: Move constructor-body member assignments into initializer lists, then promote constant initializers to default member initializers, using clang-tidy fixes with an order guard and comment carrying.
description: Unattended stage of the init-over-assign refactor. Runs clang-tidy cppcoreguidelines-prefer-member-initializer and then modernize-use-default-member-init over a compile_commands.json graph, applies the fixes to the working tree, keeps initializer lists in declaration order, carries trailing comments with the moved code, and writes a member-init manifest. Never commits. Use when converting ITK-style constructors from assignment to initialization.
triggers:
  - itk-member-init
  - /itk-member-init
  - prefer member initializer
  - default member initializer
  - move constructor assignments into initializer list
user_invocable: true
cmd: false
argument_hint: "--graph <build-dir> --repo <path> --manifest <path> [--apply]"
contract:
  inputs:
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
    - clang-tidy
    - run-clang-tidy
    - clang-apply-replacements
    - clang-format
    - cmake
    - ninja
    - git
  python_packages: []
  scripts:
    - member_init.py
    - postfix.py
deployment:
  tier: project
  target_projects:
    - itk
    - brainstools
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Member Initialization (init-over-assign stage)

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-member-init — constructor assignments -> initializer lists -> default member initializers

Usage:
  member_init.py --graph <build-dir> --repo <path> --manifest <path>          plan only
  member_init.py --graph <build-dir> --repo <path> --manifest <path> --apply  edit + manifest

  --graph     directory holding compile_commands.json, or a build root above it
  --repo      repository root; only its files are edited (not ThirdParty/, build/, Utilities/)
  --manifest  JSON manifest, kind "member-init" (written only with --apply)
  --apply     edit the working tree; without it, print "<class> <file> <count>" lines

Classes:   prefer-member-initializer, use-default-member-init
Skips:     order-violation, comment-stranded, preprocessor,
           gate-failed (ctor-unparsed, class-not-found, unknown-initializer,
           internal-error:<ExceptionType>)
```

The tools come from `$CONDA_PREFIX/bin` (the kit's pixi env, LLVM 19.1.7), falling
back to `PATH`. Run through `pixi run` so `CONDA_PREFIX` is set.

## What it does

1. `run-clang-tidy -checks=-*,cppcoreguidelines-prefer-member-initializer
   -export-fixes <tmp>` over the graph, restricted to the repo root.
2. Groups the fixes by constructor and rebuilds each initializer list in ITK
   style (`: a(..)` then `, b(..)` one per line), instead of applying
   clang-tidy's per-member insertions, which conflict at one offset.
3. **Order guard.** Reads the class's member declaration order. The class body
   is found in the constructor's file, its sibling `<stem>.h` / `<stem>.hxx`
   (ITK `.hxx` files do not include their header), or the headers it includes.
   If any initializer reads a member declared after the one it initializes, the
   constructor is left alone and recorded `order-violation`. Otherwise the list
   is sorted into declaration order; base-class initializers stay first.
   A constructor that cannot be parsed, whose class is not found, or whose list
   would need an unknown entry moved is recorded `gate-failed` with the notes
   `ctor-unparsed`, `class-not-found`, or `unknown-initializer`. A qualified
   name may have spaces around `::` (`Foo ::Foo()`); a qualifier with no
   identifier, or unbalanced parentheses, is `ctor-unparsed`. A preprocessor
   line between the signature and the body skips it as `preprocessor`, and a
   directive on the line before or after a moved assignment skips that
   assignment as `preprocessor`.
4. **Comments travel.** A trailing `//` or `/* */` comment on a moved
   assignment goes with it to the initializer entry. An own-line comment above
   a moved assignment would be stranded, so that constructor is left alone and
   recorded `comment-stranded`.
5. Writes the replacements as a YAML fix file, applies it with
   `clang-apply-replacements`, and runs `clang-format --style=file
   --fallback-style=none` on the changed lines only.
6. Repeats with `modernize-use-default-member-init` on the result. A list
   entry's trailing comment moves to the end of the member declaration line.
   Members whose type names `Pointer`, `unique_ptr`, `shared_ptr`, or
   `SmartPointer` never get a brace initializer (ITK
   `compiler-cautions.md` 1a); their constructor entry stays. A default member
   initializer is added only when every constructor of the class in that file
   that writes the same initializer can drop it; if one of them cannot be
   parsed, the whole group is skipped as `gate-failed` (`ctor-unparsed`).
7. Every planning and applying step runs per site: an unexpected exception
   skips that constructor, initializer group, or file (with its partner
   files) as `gate-failed`, note `internal-error:<ExceptionType>`, prints
   one line to stderr with the file and line, and the stage goes on. A
   default-member-init group is recorded only after every constructor it
   touches renders, so a failure drops the header and source edits together;
   a failed file is restored byte for byte. The stage exits 1 only when every
   site failed that way. A qualified name whose last component differs from
   its class (`Foo::bar()`) is not a constructor.
8. Backstop: `ioa.comments.check_hunks` on `git diff -U0` of the touched files.
   A file with a stranded comment is restored, together with every file
   reachable from it through default-member-init fixes (header and
   constructor files, to a fixed point), and recorded `comment-stranded`.
8. A `run-clang-tidy` or `clang-apply-replacements` failure raises with the
   tool's stderr when no failing TU can be identified. TUs that fail to compile,
   or that clang-tidy reports as failed or killed (`tidy-crash`), are dropped
   and listed in the output.

clang-tidy itself declines to move an assignment that reads a member not yet
initialized, so the order guard mostly catches pre-existing list entries that
read a later member (`: m_A(m_B) { m_B = 2; }`).

## Manifest

Each site has the post-edit 1-based line range, `kind: member-init`, and `cls`
(`prefer-member-initializer` or `use-default-member-init`). Applied sites are
the changed hunks; skipped sites carry `skipped` and a `note`. The header
site and the source sites of one default-member-initializer move share a
`group` id, and so do a constructor's inserted initializer list and every
assignment it removed (`member-init:<token>:pmi-<n>`) (sites touched by several moves share one), so the master commits
and reverts them together without tying unrelated members of the same files. The master
(`itk-init-over-assign`) partitions the diff by content; this stage only edits
and reports.

## Tests

```bash
pixi run pytest skills/itk-member-init/tests -v
```

Each fixture under `tests/fixtures/` is a one-`.cxx`, one-`.h` CMake project
configured into a temporary build with `CMAKE_EXPORT_COMPILE_COMMANDS=ON`, run
through real clang-tidy.
