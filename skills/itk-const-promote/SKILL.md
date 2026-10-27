---
name: itk-const-promote
version: 1.0.0
purpose: Promote the locals a prior init-over-assign stage initialized to const, and to constexpr when the initializer is a compile-time literal, using clang-tidy misc-const-correctness restricted to that stage's sites.
description: Unattended stage of the init-over-assign refactor that runs after local-init, container-list-init, and itk-helpers. Runs clang-tidy misc-const-correctness over the translation units holding a prior manifest's files, inserts const on never-mutated locals within or next to that manifest's applied sites, promotes literal and constexpr-helper initializers to constexpr, records static locals as skipped, and writes a manifest of kind local-const, container-const, or itk-helpers-constexpr. Never commits.
triggers:
  - itk-const-promote
  - /itk-const-promote
  - promote locals to const
  - promote locals to constexpr
  - misc-const-correctness
user_invocable: true
cmd: false
argument_hint: "--graph <build-dir> --repo <path> --manifest <path> --only-from <manifest> --kind <local-const|container-const|itk-helpers-constexpr> [--apply]"
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
    - const_promote.py
    - constexpr_rule.py
deployment:
  tier: project
  target_projects:
    - itk
    - brainstools
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Const Promotion (init-over-assign stage)

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-const-promote: newly initialized locals -> const -> constexpr

Usage:
  const_promote.py --graph <build-dir> --repo <path> --manifest <path> \
      --only-from <prior-manifest> --kind <kind>            plan only
  const_promote.py ... --apply                              edit + manifest

  --graph      directory holding compile_commands.json, or a build root above it
  --repo       repository root
  --manifest   JSON manifest written with --apply
  --only-from  manifest of the stage that initialized the locals
  --kind       local-const | container-const | itk-helpers-constexpr
  --apply      edit the working tree; without it, print "<class> <file> <count>"
               lines and write nothing

Classes:   const, constexpr
Skips:     static-local, preprocessor, gate-failed (auto-unanalyzed, declaration-not-found,
           multiple-declarators, unsupported-specifier)
```

The tools come from `$CONDA_PREFIX/bin` (the kit's pixi env, LLVM 19.1.7),
falling back to `PATH`. Run through `pixi run` so `CONDA_PREFIX` is set.

## What it does

1. Reads the `--only-from` manifest. Only files with applied sites there are
   analyzed: their own translation units, or for a header one including TU
   from the ninja deps (`ioa.compile_commands.including_tus`). The TUs are
   passed to `run-clang-tidy` as file arguments, spelled as the compile
   database spells them (symlinked build paths match), and a run that
   matches none of them raises.
2. Runs `misc-const-correctness` through `ioa.tidy.run_tidy` with
   `AnalyzeValues`, `AnalyzeReferences`, `TransformValues`, and
   `TransformReferences` on, and `WarnPointersAsValues` and
   `TransformPointersAsValues` off.
3. clang-tidy 19 never reports `auto` variables, and this stage does not
   analyze them: declare-then-init emits explicit types, and the ITK-helper
   stage emits `const auto` / `constexpr auto` itself. A plain `auto` local
   near a prior site is recorded `gate-failed` with note `auto-unanalyzed`
   and left unedited.
4. A diagnostic is kept only when its declaration lies within, or one line
   next to, an applied site range of the prior manifest for that file, so the
   const commit stays tied to the stage that enabled it. Others are ignored
   and not recorded.
5. `const ` (or `constexpr `) is inserted at the start of the declaration,
   west-const (`const int n`), which is ITK style, instead of clang-tidy's
   `int const n`. Nothing else on the line moves, so trailing comments stay.
   `clang-format --style=file` then runs on each changed line widened to its
   run of adjacent non-blank, non-brace lines (`ioa.tidy.widen_to_block`),
   because ITK aligns consecutive declarations; the partitioner formats its
   staged hunks the same way.
6. `constexpr` replaces `const` when the initializer is (`constexpr_rule.py`):
   - a literal: number, `true`/`false`, `nullptr`, or a character, for a
     builtin arithmetic type (pointer for `nullptr`); a string literal only
     for `const char *`;
   - `T::Filled(<literal>)` or `MakeFilled<T>(<literal>)`;
   - `std::numeric_limits<T>::f()` or `itk::NumericTraits<T>::f()` with no
     arguments, for a builtin result type;
   - a brace list of literals for a C array of a builtin type, `std::array`,
     `itk::Size`, `itk::Index`, or `itk::Offset`.

   A type naming `Pointer`, and any reference, stays `const`.
7. `static` and `thread_local` locals are recorded `static-local` and left
   unedited.
8. A conditional directive (`#if`, `#ifdef`, `#ifndef`, `#elif`, `#else`,
   `#endif`) between the declaration and the end of its scope records
   `preprocessor`: a branch clang-tidy did not compile may write the local.

clang-tidy does not report locals whose initializer depends on a template
parameter, so most locals in `.hxx` template code are not promoted.

## Manifest

Each site has the post-edit 1-based line range of the declaration, `kind` set
to `--kind`, and `cls` `const` or `constexpr`. Skipped sites carry `skipped`
and a `note`.

## Tests

```bash
pixi run pytest skills/itk-const-promote/tests -v
```

Each fixture under `tests/fixtures/` is a small CMake project configured into
a temporary build with `CMAKE_EXPORT_COMPILE_COMMANDS=ON` and run through real
clang-tidy; it shares the member-init fixtures' `.clang-format`.
`test_constexpr_rule.py` covers the constexpr rule on declaration text alone.
