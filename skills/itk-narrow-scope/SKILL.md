---
name: itk-narrow-scope
version: 1.0.0
purpose: Move a local declaration into the narrowest nested block, if/for/switch init-statement, or loop body that holds every use of it.
description: Unattended stage 5 of the init-over-assign refactor. Finds local declarations with clang-query, scans the enclosing block's text for every use, and moves the declaration (with its comments) into the single nested scope that holds all of them. Loop bodies take only trivially constructible values that are written before they are read; static locals, address-taken or escaping values, moves into a try block, and moves across labels, case labels, preprocessor directives, or a try whose catch or later code reads the value are skipped. Writes a manifest of kind narrow-scope. Never commits.
triggers:
  - itk-narrow-scope
  - /itk-narrow-scope
  - narrow variable scope
  - declare variables in the narrowest scope
  - move declaration to first use
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
    - clang-apply-replacements
    - clang-format
    - git
  python_packages: []
  scripts:
    - narrow_scope.py
    - scopes.py
    - matchers/var_uses.cq
deployment:
  tier: project
  target_projects:
    - itk
    - brainstools
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Narrow Scope (init-over-assign stage 5)

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-narrow-scope: int t = 0; if (c) { t = c; f(t); }  ->  if (c) { int t = 0; t = c; f(t); }

Usage:
  narrow_scope.py --graph <build-dir> --repo <path> --manifest <path>      plan only
  narrow_scope.py ... --apply                                              edit + manifest

  --graph      directory holding compile_commands.json, or a build root above it
  --repo       repository root
  --manifest   JSON manifest written with --apply
  --apply      edit the working tree; without it, print "<class> <file> <count>"
               lines and write nothing

Class:     narrow-scope (notes: block, init-statement, loop-body)
Skips:     static-local, loop-carried (notes address-taken, escapes), costly-construct
           (notes call, non-trivial, nontrivial-dtor, side-effect), goto-or-case, try-read-after,
           preprocessor, comment-stranded, gate-failed
```

The tools come from `$CONDA_PREFIX/bin` (the kit's pixi env, LLVM 19.1.7),
falling back to `PATH`. Run through `pixi run` so `CONDA_PREFIX` is set.

## What it does

1. Runs `matchers/var_uses.cq` with `ioa.query.run_query` over every in-scope
   translation unit, once per TU. It binds every `varDecl` that is the only
   declaration of a `declStmt` directly inside a compound statement (`local`),
   the static and `thread_local` ones (`static`), and those whose type is
   trivially default-constructible (`trivial`): arithmetic, pointer, enum,
   arrays of those, or a record whose default constructor is not
   user-provided, with no virtual method, no user-provided destructor, no
   in-class field initializer, only such fields, and only such bases. That covers `itk::FixedArray` and the
   classes derived from it (Point, Vector, CovariantVector, RGBPixel), Size,
   and Index. A template local counts as trivial only when every
   instantiation's type is. clang-query has no triviality matcher, so this is
   built from `isUserProvided`, `hasInClassInitializer`, `isVirtual`, and
   `isDerivedFrom`. A fourth binding (`ctor`) marks initializers that pass
   arguments to a user-provided constructor.
2. Uses are found by a text scan of the enclosing block after the
   declaration, with comments and literal contents masked (`ioa.source.mask`):
   every whole-word occurrence of the name that is not a member access, a
   qualified name, or a scope qualifier. A scan sees uses inside macro
   arguments that clang-query drops, and any extra occurrence only makes the
   move less likely. A use that looks like a redeclaration of the same name
   means no move.
3. `scopes.py` parses the enclosing block into statements (`if`/`else`,
   `for`, range `for`, `while`, `do`, `switch`, `try`/`catch`, labels,
   directives, plain statements) and descends while one statement holds every
   use: into a braced block, a braced branch of an `if`, a braced `catch`
   block, a braced loop body, or a `try` block (whose targets are then all
   refused, below). The descent passes through a `switch` body but never
   targets it; a braced case block inside it is a candidate that always
   crosses its case label, so it is recorded `goto-or-case`. When the first use is
   in the condition of an `if`, `switch`, or `for` that holds every use, the
   target is that statement's init-statement, if it has none yet (for a `for`,
   the init slot is empty). Uses in two sibling statements end the descent;
   with no target found, nothing is recorded.
4. Each target, deepest first, is checked; the first that passes wins, and if
   none passes the deepest one's reason is recorded:
   - `try-read-after`: the target is a `try` block or any block nested in
     one. A declaration never moves into a `try` block.
   - `preprocessor`: a directive between the declaration and the target.
   - `goto-or-case`: a label or case label between them.
   - `loop-carried`, note `address-taken`: a use takes the address (`&x`),
     binds a reference (`T & r = x`), or sits in a lambda that captures by
     reference.
   - `loop-carried`, note `escapes`: a statement in the target assigns a name
     declared outside the target and mentions the variable in a way that can
     yield its address: any mention for a type that is not trivially
     constructible, a member call for any type (`p = s.c_str();`,
     `p = pt.GetDataPointer();`), or a bare array name that decays
     (`p = buf;`). The variable's lifetime would end earlier. A plain value
     copy of a trivial variable (`sum += v;`) is not an escape. The same note
     applies, checked last, when a member-call result on the variable is a
     whole argument of a call in the target (`Use(x.Data());`), or the
     variable itself is (`h.Set(x);`) and its type is not trivially
     constructible or it is an array; casts and control heads are not calls,
     and `g(x + 1)` is not an escape.
   - `costly-construct`, note `nontrivial-dtor`: outside loops, a type that is
     not trivially destructible (a user-provided or virtual destructor, or a
     field or base that is not a builtin, pointer, enum, or array of those)
     never moves, since the move would run its destructor earlier.
   - In a loop body, or any block inside a loop: a declaration with a call
     (`f()`, `T::New()`, `new`, `T{...}`, arguments to a user-provided
     constructor, or `(`/`{` arguments on a non-trivial type) is
     `costly-construct` note `call`; an initializer with `++`, `--`, or an
     assignment (including `<<=`, `>>=`) is `costly-construct` note `side-effect`;
     a type that is not trivially constructible is `costly-construct` note
     `non-trivial`; and the first statement of the target block that
     mentions the variable must be a plain `x = ...;` whose right side does
     not read it, else `loop-carried`. An init-statement inside a loop is
     `loop-carried` (its condition reads the value).
   - Outside loops: a declaration whose initializer calls a function,
     mutates (`++`, `--`, assignment), or reads a variable while the target does not assign it first, may only
     move into the immediately following bare block or `if`/`switch`/`for`
     init-statement, since crossing code would reorder or skip the call:
     `costly-construct`, note `side-effect`.
   - When uses span a `try` and the code after it, or the try block and a
     handler: `try-read-after`.
   - `static` or `thread_local` locals with a target: `static-local`.
5. The declaration must sit alone on its lines. The comment block directly
   above it (contiguous `//` lines, a `/* */` or Doxygen block) and its
   trailing comment move with it. Into a block, the lines go first in the
   block, re-indented; into an init-statement, the declaration is joined onto
   one line inside the parentheses and its comments go on lines above the
   statement. Only one declaration takes an init-statement per run, and a move
   whose edit overlaps an earlier move in the same file waits for the next run.
   Deletions that would leave a doubled blank line, or a blank line just inside
   a brace, take that blank line too.
6. Edits go through `ioa.tidy.apply_edits`, then `clang-format --style=file`
   runs on the changed lines widened to their blocks
   (`ioa.tidy.format_changed`). `ioa.comments.check_hunks` compares the
   pre-edit text with the result; a comment left behind reverts the file and
   records its moves `comment-stranded` with the comment as the note. A moved
   declaration that cannot be found after formatting reverts the file as
   `gate-failed`, note `moved-declaration-not-found`.

Template code is matched through its definition and its instantiations.

## Manifest

`kind` and `cls` are both `narrow-scope`. An applied site spans from the
post-edit line where the declaration was removed to the last line of the new
declaration, so the partitioner assigns both hunks to it; its note is the
target form (`block`, `init-statement`, or `loop-body`). Skipped sites carry
the original declaration lines.

## Limits

- A trivially constructible variable passed whole to a call that binds it by
  reference and stores its address (`h.Set(x)` with `void Set(int & v)`) is
  not caught; the move then shortens a lifetime the callee relies on. Calls
  are never moved past code; default construction is.
- Uses are matched by name within the block, so an unrelated local of the
  same name in a nested lambda or class blocks the move rather than enabling a
  wrong one.
- Uses are found in the block's own text; a macro whose body (not its
  arguments) names the local is not seen, and the move then fails to compile
  at the master's gate.
- A `case`, label, or directive anywhere between the old and new position
  blocks the move, even inside an unrelated statement.

## Tests

```bash
pixi run pytest skills/itk-narrow-scope/tests -v
```

`test_scopes.py` covers the statement parser, use scan, target choice, guards,
and edit rendering on source text alone. Each fixture under `tests/fixtures/`
is a small CMake project configured into a temporary build with
`CMAKE_EXPORT_COMPILE_COMMANDS=ON` and run through the real clang-query and
clang-format; it shares the member-init fixtures' `.clang-format`. The
`loop_trivial` fixture carries a stand-in `itk::FixedArray` and `itk::Point`.
