---
pattern: container-size-to-empty
clang_tidy_check: readability-container-size-empty
itk_main_status: merged
itk_main_ref: PR #4985
scope: downstream-and-new-code
---

## Overview

Replace size-against-zero emptiness tests with `empty()`:

- `c.size() == 0` / `c.size() <= 0` → `c.empty()`
- `c.size() != 0` / `c.size() > 0` / `c.size() >= 1` → `!c.empty()`

Core principle: `empty()` is **semantic** (says "is this empty?"), and for some
containers (e.g. `std::list`) **cheaper** than `size()`. This is the stock
`readability-container-size-empty` check — safe, pervasive in STL-using ITK
consumer code, and only fires on types that actually expose `empty()`.

## When to use / when NOT

Use when:

- A method body or condition compares a container's `size()`/`length()` to 0.
- You want a low-risk readability cleanup with an automatic, type-aware fix.

Do NOT use when:

- The `size()` value is used arithmetically (not just compared to 0).
- The expression is on a type that does NOT expose `empty()` (a raw count, a
  custom API). clang-tidy already skips these; the regex grep does not, so
  treat raw-grep hits as candidates, not guarantees.
- Code in `ThirdParty/` (excluded by `detect.sh`).

## Before / after

```cpp
- if (m_Information.size() == 0)
+ if (m_Information.empty())

- while (queue.size() != 0)
+ while (!queue.empty())
```

## Detection

```bash
bash skills/itk-container-size-to-empty/detect.sh [repo-path]   # default .
```

Greps (via `git grep`, ThirdParty excluded) for `.size()`/`.length()` compared
to `0`/`1`, printing `file:line` hits and a count. These are *candidates* — the
authoritative fire-set is decided by clang-tidy below.

## Transformation approach

Preferred (type-aware, correct): clang-tidy. It knows which types expose
`empty()` and chooses `empty()` vs `!empty()` based on the operator.

```bash
# Requires a compile_commands.json (compilation database) for the build tree.
clang-tidy -p <build-dir> \
  -checks='-*,readability-container-size-empty' -fix \
  $(git -C <repo> grep -lE '\.(size|length)\(\)\s*(([=!]=|<=|>=?)\s*0|(<|>=)\s*1)\b' \
        -- ':!*ThirdParty*' ':!*thirdparty*')
```

`transform.sh` wraps this (dry-run by default, `--apply` to write):

```bash
bash skills/itk-container-size-to-empty/transform.sh <repo> <build-dir>          # dry-run
bash skills/itk-container-size-to-empty/transform.sh <repo> <build-dir> --apply  # write
```

Regex fallback (only the `== 0` / `!= 0` cases, review every hunk — no type
awareness, will mis-fire on non-container `size()`):

```bash
# == 0  ->  empty()        (illustrative; clang-tidy is preferred)
perl -i -pe 's/(\b[\w.()\->]+)\.size\(\)\s*==\s*0\b/$1.empty()/g' file.cxx
```

## Verification (pattern-specific)

Nothing beyond the shared gate in `SKILL.md`.

## Common mistakes

- Trusting the regex grep as the fire-set — it has no type info; a `.size()` on
  a non-container (a custom struct returning a count) is a false positive.
  clang-tidy is the source of truth.
- Rewriting `size() > 0` to `empty()` instead of `!empty()` — note the negation
  flips for `!=`, `>`, `>=`. clang-tidy gets this right; hand-edits often don't.
- Running clang-tidy without a `compile_commands.json` (`-p <build-dir>`) — the
  check needs the type of the receiver to fire.
- Touching `ThirdParty/` — never modernize vendored code.
