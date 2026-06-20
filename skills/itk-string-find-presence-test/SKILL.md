---
name: itk-string-find-presence-test
description: >-
  Use when ITK (or ITK-ecosystem) C++ source tests substring presence with the
  unidiomatic legacy idiom str.find(sub) < str.length() (or < str.size()) —
  a pattern copied verbatim across ImageIO and parameter-file readers. This
  construct is subtly wrong (it conflates "not found" with a real position only
  by luck of npos being huge) and should read str.find(sub) != std::string::npos.
  Keywords: string find presence test, find < length, find < size, std::string::npos,
  ImageIO substring check, npos idiom, find return value misuse, parameter file reader.
---

> **Constraint — C++17, ITKv5 + ITKv6:** target C++17 idioms valid against both ITK >=5.4 and ITKv6; never require C++20+. Verify transformed output by compiling against both ITK header sets with `-std=c++17` (see skills/BRAINSTOOLS_HARDENING.md).

# itk-string-find-presence-test

## Overview

The legacy idiom `str.find(sub) < str.length()` is an unidiomatic way to ask
"does `sub` occur in `str`?". `std::string::find` returns `std::string::npos`
(a very large `size_t`) on no-match, so `< length()` *happens* to be false then —
but the expression reads as a position comparison, hides the real contract, and
is fragile. The idiomatic, correct form is:

```cpp
str.find(sub) != std::string::npos
```

**Core principle:** rewrite presence tests to the `!= std::string::npos` form
**only when both member-call receivers are the same identifier** (the `find`
receiver and the `length()`/`size()` receiver). Different receivers (e.g.
`a.find(x) < b.length()`) are a genuinely different comparison and MUST be left
alone — `sed` cannot tell these apart, so a receiver-aware pass is required.

## When to use / when NOT

Use when:
- Auditing ITK / BRAINSTools / Slicer / elastix IO and parameter-file readers
  for the `find(...) < ....length()` / `.size()` presence idiom.
- Modernizing copied-verbatim presence tests with zero behavior change on the
  success path.

Do NOT use when:
- The two receivers differ (`x.find(s) < y.size()`) — not a presence test.
- The RHS is a literal or arithmetic, not a `.length()`/`.size()` call on the
  same string — out of scope.
- ThirdParty/ trees — excluded by detection.

## Before / after

```cpp
// before
if (fname.find("numDim:") < fname.length() || fname.find("dim:") < fname.length())
// after
if (fname.find("numDim:") != std::string::npos || fname.find("dim:") != std::string::npos)
```

## Detection

`detect.sh <repo-path>` (default `.`) uses `git grep` with pathspecs (glob-safe,
ThirdParty excluded) to print `file:line` hits plus a count:

```bash
bash skills/itk-string-find-presence-test/detect.sh /path/to/ITK
```

Regex core:
`\.find\([^)]*\)\s*<\s*[A-Za-z_][A-Za-z0-9_.]*\.(length|size)\(\)`

clang-query equivalent (AST, receiver-agnostic — still verify receivers):
```
binaryOperator(hasOperatorName("<"),
  hasLHS(cxxMemberCallExpr(callee(cxxMethodDecl(hasName("find"))))),
  hasRHS(cxxMemberCallExpr(callee(cxxMethodDecl(anyOf(hasName("length"), hasName("size")))))))
```

## Transformation approach

Run `transform.sh` (dry-run by default, `--apply` to write; never commits):

```bash
bash skills/itk-string-find-presence-test/transform.sh /path/to/ITK            # dry-run
bash skills/itk-string-find-presence-test/transform.sh /path/to/ITK --apply    # write
```

It is a Python pass (regex-captured, receiver-checked): for each
`RECV1.find(ARG) < RECV2.(length|size)()`, it rewrites to
`RECV1.find(ARG) != std::string::npos` **only if `RECV1 == RECV2`**; otherwise
the site is reported as SKIPPED (receiver mismatch) and left untouched. ARG may
contain nested parentheses-free content; sites with awkward nesting are reported
for manual review rather than mis-rewritten.

Header note: the result uses `std::string::npos`; the rewritten TU already uses
`std::string`/`<string>` (it called `.find`/`.length`), so no include change is
needed.

## Verification

1. `detect.sh` count should drop to the number of legitimate receiver-mismatch
   sites (ideally 0) after `--apply`.
2. Build the affected modules — the rewrite is type-identical (`size_t !=
   size_t`), so a clean build confirms no regression.
3. Spot-read 2-3 rewritten sites to confirm receiver identity was preserved.

## Common mistakes

- **Blind `sed`** — cannot verify the two receivers match; will corrupt
  `a.find(x) < b.size()`. Always use the receiver-aware `transform.sh`.
- **Rewriting `<=`** — only `<` is the presence idiom; `<=` changes meaning.
- **Touching ThirdParty/** — excluded on purpose; never modernize vendored code.
- **Assuming zero sites differ** — a few genuine receiver-mismatch comparisons
  exist; `transform.sh` reports them as SKIPPED, not failures.
