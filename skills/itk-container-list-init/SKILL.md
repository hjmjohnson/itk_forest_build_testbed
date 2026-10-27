---
name: itk-container-list-init
version: 1.0.0
purpose: Rewrite a default-constructed std::vector, std::array, itk::Array, or vnl_vector local that is filled only by push_back/emplace_back calls or constant-index assignments into brace initialization.
description: Unattended stage 3 of the init-over-assign refactor. Finds default-constructed container locals with clang-query, scans the statements that follow at the same indent for a run of appends or constant-index assignments, skips runs that would narrow, select a different constructor, cover the indices partially, or cross a preprocessor directive, rewrites the rest to `T v{e0, e1, ...};`, verifies the element count by re-parsing, and writes a manifest of kind container-list-init. Never commits.
triggers:
  - itk-container-list-init
  - /itk-container-list-init
  - push_back to brace initialization
  - container list initialization
  - replace push_back run with initializer list
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
    - clang-query
    - clang-format
    - cmake
    - ninja
    - git
  python_packages: []
  scripts:
    - list_init.py
    - runs.py
    - matchers/push_back_run.cq
    - matchers/index_assign_run.cq
deployment:
  tier: project
  target_projects:
    - itk
    - brainstools
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Container List Initialization (init-over-assign stage 3)

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-container-list-init: T v; v.push_back(a); v.push_back(b);  ->  T v{ a, b };

Usage:
  list_init.py --graph <build-dir> --repo <path> --manifest <path>          plan only
  list_init.py ... --apply                                                  edit + manifest

  --graph      directory holding compile_commands.json, or a build root above it
  --repo       repository root
  --manifest   JSON manifest written with --apply
  --apply      edit the working tree; without it, print "<class> <file> <count>"
               lines and write nothing

Classes:   push_back_run, index_assign_run
Skips:     static-local, narrowing (also note partial-coverage), init-list-ctor (notes
           no-init-list, element-type-unknown), order-violation (index-order),
           preprocessor, comment-stranded, gate-failed (element-count)
```

The tools come from `$CONDA_PREFIX/bin` (the kit's pixi env, LLVM 19.1.7),
falling back to `PATH`. Run through `pixi run` so `CONDA_PREFIX` is set.

## What it does

1. Runs `matchers/push_back_run.cq` and `matchers/index_assign_run.cq`
   (concatenated into one script) with
   `clang-query -p <graph> -f <script> --extra-arg=-w <tu>` over every in-scope
   translation unit of `compile_commands.json`, in parallel
   (`ioa.query.run_query`). Both find a `varDecl` of `std::vector`,
   `std::array`, `itk::Array`, or `vnl_vector` initialized by a zero-argument
   construct expression, directly in a block that also holds an append call or
   a subscript assignment. Headers are covered through the TUs that include
   them. Matches are read from `set output dump` (file, line, column, name, and
   canonical type); macro-expanded declarations are dropped, and a template
   instantiated several times keeps every canonical type so a guard that fails
   for any of them skips the site. TUs that fail to parse are reported and
   skipped.
2. `runs.py` scans the statements after the declaration at the same indent:
   a run of only `v.push_back(e)` / `v.emplace_back(e)` (push_back_run), or of
   only `v[i] = e;` with an integer-literal `i` (index_assign_run). A blank
   line, a comment line, a different indent, any other statement, a second
   statement on a line, or any read of `v` ends the run. A run with no element
   is not a site.
3. Guards, in order (the first that fails for any instantiation decides):
   - `vnl_vector`: `init-list-ctor`, note `no-init-list`.
   - `emplace_back` with several arguments when the declaration does not spell
     the element type (a typedef such as `PairVec`): `init-list-ctor`, note
     `element-type-unknown`. Otherwise the element becomes `Elem(a, b)`.
   - `static` or `thread_local` locals: `static-local` (the matchers already
     require automatic storage; the text check is a backstop), because brace
     initialization would run once instead of appending on every call.
   - index runs whose indices are not exactly `0..n-1`, or whose count differs
     from a `std::array` size: `narrowing`, note `partial-coverage`. Indices out
     of order are sorted only when every element is a literal or a plain
     identifier; otherwise `order-violation`, note `index-order`.
   - `narrowing`: an integer element type receiving a floating literal or
     identifier; a signed integer type receiving an unsigned identifier
     (declared `unsigned`, `size_t`, `SizeValueType`, or `IdentifierType`;
     `IndexValueType` and `OffsetValueType` are signed) or a `u`-suffixed literal; an unsigned type receiving a
     signed identifier or a negative literal; a wider integer identifier; a
     floating type receiving an integer identifier or a wider floating
     identifier. An identifier's type is read from the last declaration of it
     earlier in the file. Elements whose type cannot be determined are allowed;
     the compile gate catches a real narrowing error.
   - `init-list-ctor`: a `std::vector` of an integral type with one or two
     elements, unless every element is known to be floating; or of a floating
     type with one or two elements of which any is an integer literal or
     integer identifier. A reader cannot tell `{3}` from the
     `(size_type, value)` constructor.
   - `preprocessor`: a directive inside the run (the next statement after the
     directive continues it).
   `std::array` brace initialization is aggregate initialization and needs no
   constructor guard. `itk::Array` has `Array(std::initializer_list)` since
   ITK 5.3.
4. Rewrites to `T v{e0, e1, ...};` with the elements verbatim and in order
   (multi-line elements joined by single spaces), on one line when it fits 120
   columns, else one element per line. The first trailing comment of the
   removed lines moves to the new declaration line; any further comment is
   dropped, and the `ioa.comments.check_hunks` backstop on `git diff -U0` then
   reverts that file and records its sites `comment-stranded`. An element that
   holds a comment is skipped as `comment-stranded`, note `comment-in-element`.
5. `clang-format --style=file` runs on each changed line widened to its block
   (`ioa.tidy.format_changed`), so the ITK style gives `v{ 1, 2, 3 }` and
   realigns neighboring declarations.
6. Each new declaration is re-parsed; its element count must equal the number
   of removed statements, else the file is reverted and the site recorded
   `gate-failed`, note `element-count:<n>`. Applied sites carry note
   `elements:<n>`.

Template code is matched only through its instantiations; a template never
instantiated in the graph is not seen.

## Manifest

Each site has the post-edit 1-based line range of the new declaration (the
original range for skipped sites), `kind` `container-list-init`, and `cls`
`push_back_run` or `index_assign_run`.

## Tests

```bash
pixi run pytest skills/itk-container-list-init/tests -v
```

`test_runs.py` covers the run scanner and guards on source text alone. Each
fixture under `tests/fixtures/` is a small CMake project configured into a
temporary build with `CMAKE_EXPORT_COMPILE_COMMANDS=ON` and run through the real
clang-query and clang-format; it shares the member-init fixtures'
`.clang-format`. The `vnl` fixture carries a stub `vnl_vector.h`.
