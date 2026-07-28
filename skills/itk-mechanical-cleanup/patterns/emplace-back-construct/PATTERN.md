---
pattern: emplace-back-construct
clang_tidy_check: modernize-use-emplace
itk_main_status: merged
itk_main_ref: PR #5824
scope: downstream-and-new-code
---

## Overview

Core principle: **never build a named/temporary element just to copy or move it
into a container.** When the argument to `push_back` / `push_front` is a
temporary of the container's element type, `emplace_back` / `emplace_front`
constructs the element directly in the container's storage, eliding one
temporary and one move per insertion. In ITK's mesh, point, and run-length
encoding loops these insertions run per-voxel/per-edge, so the saving is real.

This is a mature, zero-risk modernization (clang-tidy `modernize-use-emplace`).
The check verifies the temporary's type matches the container element type
before rewriting, so it correctly handles multi-arg value-type constructors.

## When to use

- A `push_back`/`push_front` argument is a constructor-style temporary of the
  element type: `c.push_back(T(a, b))`, `p->push_back(T(seed, 0))`.
- Hot insertion loops in mesh/point/run-length code where the temporary + move
  is measurable.

## When NOT to use

- The argument is already an lvalue or an existing variable (`c.push_back(x)`):
  no temporary to elide; `emplace_back(x)` is a lateral change, skip it.
- The argument type is NOT the container's element type (an implicit conversion
  is intended) — `modernize-use-emplace` deliberately skips these; do not force.
- `{}`-braced init lists into containers of aggregates can change overload
  resolution; let clang-tidy decide, do not hand-edit those.
- ThirdParty/ trees — never modify vendored code.

## Before / after

```cpp
- m_LineContainer.push_back(LineType(newIdx, newLength));
+ m_LineContainer.emplace_back(newIdx, newLength);

- m_Front->push_back(FrontAtom(seed, 0));
+ m_Front->emplace_back(seed, 0);

- runs.push_back(RunLength(length, idx));
+ runs.emplace_back(length, idx);
```

## Detection

`detect.sh <repo>` (default `.`) uses `git grep` with pathspecs (glob-safe,
ThirdParty excluded) to find constructor-style temporaries passed to
`push_back`/`push_front`:

```bash
bash skills/itk-emplace-back-construct/detect.sh /path/to/ITK
```

It prints `file:line` hits and a count. The heuristic matches
`.push_back(` / `.push_front(` / `->push_back(` / `->push_front(` immediately
followed by an `Uppercase...(` constructor-style call. This over-matches
slightly (e.g. a free function returning the element type); clang-tidy makes the
final type-correct decision.

## Transformation approach

Use clang-tidy — do **not** hand-roll a regex rewrite. The check confirms the
temporary type equals the container element type, which a regex cannot.

```bash
# Needs a compile_commands.json for the tree (the forest build produces one).
clang-tidy -p <build-dir> \
  -checks='-*,modernize-use-emplace' -fix <file.cxx>
# then re-format the touched files:
clang-format -i <file.cxx>
```

`transform.sh` wraps this: dry-run by default (lists candidate files), `--apply`
to write. It never commits.

```bash
bash skills/itk-emplace-back-construct/transform.sh <repo> <build-dir>          # dry-run
bash skills/itk-emplace-back-construct/transform.sh <repo> <build-dir> --apply  # write fixes
```

## Verification (pattern-specific)

`emplace_back` constructs the same element; the only difference is the elided
temporary. Diff hunks must be `push_back(T(...))` -> `emplace_back(...)` only.

## Common mistakes

- **Regex-rewriting instead of clang-tidy** — a regex cannot confirm the
  temporary type matches the element type, and will mangle implicit-conversion
  and free-function-return cases. Always use `modernize-use-emplace -fix`.
- **Forgetting clang-format** after `-fix` — the rewrite can shift line length;
  re-run clang-format so the change is style-clean (pre-commit requirement).
- **Applying without a matching `compile_commands.json`** — clang-tidy needs the
  build's compile flags; point `-p` at the consumer's build dir.
- **Editing ThirdParty/** — detect.sh excludes it; don't add it back.
