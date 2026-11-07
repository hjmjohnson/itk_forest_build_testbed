---
name: itk-convert-conceptchecking
version: 1.1.0
purpose: Convert a code base built on ITK to the static_assert concept checks of ITK PR #7108, in reviewable phases that reproduce the PR's own conversion.
description: >-
  ITK PR #7108 reimplemented itk::Concept as std::bool_constant traits
  checked by static_assert, removed ITK_CONCEPT_NO_CHECKING,
  itkConceptConstraintsMacro and the Concept::Detail helpers, and made the
  ITK_USE_CONCEPT_CHECKING guards dead (the macro is no longer defined, so
  every check inside one never compiled). This skill brings any ITK
  consumer (remote modules, ANTs, BRAINSTools, elastix, MITK, Slicer, ...)
  to the same state. `convert_concept_checks.py` audits the code base, then
  runs three mechanical phases, one commit each: enable (drop the dead
  guards), static-assert (rewrite dimension, type, integer, signedness and
  zero checks as plain static_assert with #7108's conditions and no
  message), and comments (drop "Begin/End concept checking" markers and
  ITKModuleTemplate placeholders). On ITK itself its static-assert and
  comments phases reproduce #7108's commits 3 and 4 exactly. Removed-API
  uses and commented-out checks are reported for a hand rewrite. Dry run
  by default; never commits.

  Trigger when the user mentions: itk-convert-conceptchecking, concept
  checking, itkConceptMacro, ITK_USE_CONCEPT_CHECKING,
  ITK_CONCEPT_NO_CHECKING, itkConceptConstraintsMacro, Concept::SameDimension
  to static_assert, or porting a code base to ITK PR #7108.
triggers:
  - itk-convert-conceptchecking
  - /itk-convert-conceptchecking
  - convert ITK concept checks
  - ITK_USE_CONCEPT_CHECKING
  - itkConceptMacro to static_assert
user_invocable: true
cmd: false
argument_hint: "[audit|enable|static-assert|comments|all] [--root <repo>] [--apply]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "**/*.h"
      - "**/*.hxx"
      - "**/*.txx"
      - "**/*.cxx"
    writes_outside_repo: false
    writes_outside_repo_paths: []
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
  skills: []
  external_tools:
    - git
    - clang-format
    - jobslot
  python_packages: []
  scripts:
    - convert_concept_checks.py
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# itk-convert-conceptchecking

Ports a code base built on ITK to the concept checks of
[ITK #7108](https://github.com/InsightSoftwareConsortium/ITK/pull/7108)
("ENH: Implement concept checks with static_assert", dzenanz).

## What #7108 changed, and what it means downstream

| #7108 change | Downstream effect |
|---|---|
| `itkConceptMacro` is a `static_assert` of a trait | Existing uses keep compiling; every concept name is still defined |
| `ITK_USE_CONCEPT_CHECKING` no longer defined | Checks inside `#ifdef ITK_USE_CONCEPT_CHECKING` have never compiled |
| `ITK_CONCEPT_NO_CHECKING` removed | A `#define` of it no longer turns checks off |
| `itkConceptConstraintsMacro`, `Concept::Detail` removed | Custom concepts built on them stop compiling |
| Checks look at declarations only (SFINAE) | Function bodies are no longer instantiated by a check |
| `HasNumericTraits` rejects the primary template | A type with no `NumericTraits` specialization now fails |
| Primary `PixelTraits` is safe to probe | `HasPixelTraits<T>::value` is `false`, not a compile error, for a type without `Dimension` and `ValueType` |
| `itkConceptCheckingGTest.cxx` added | Every concept has passing and failing `static_assert` cases to copy from |

The mechanical phases (2 to 4 below) are plain C++17 (`std::is_same_v` and
friends). Every ITK release from v5.4rc01 on requires C++17 (commit
513507e4c70, 2023-03-17; ITK 5.3 was C++14), so a project that supports ITK
5.4.0 and later can take them at any time. The hand rewrites in phase 1 are what keep the project
compiling once #7108 is in the ITK it builds against.

## The script

```bash
S=~/.claude/skills/itk-convert-conceptchecking/convert_concept_checks.py
python3 $S audit --root <repo> [--exclude '*/ThirdParty/*']
python3 $S enable        --root <repo> [--diff] [--apply]
python3 $S static-assert --root <repo> [--diff] [--apply] [--no-add-includes]
python3 $S comments      --root <repo> [--diff] [--apply]
python3 $S all           --root <repo> [--apply]   # enable, static-assert, comments
```

Every phase is a dry run until `--apply`. Nothing is committed. Exclude
vendored code (`ThirdParty`, a vendored ITK) with `--exclude`; files named
`itkConceptChecking.h` are always skipped. `static-assert` adds
`#include <type_traits>` after the first include block when it introduces a
`std::` trait; `--no-add-includes` matches #7108, which relied on
transitive includes.

## Procedure

Work on a branch in the target repository. Build and test only through
`jobslot` (the machine is shared), and only the targets the change touches.

### 0. Audit

```bash
python3 $S audit --root . --exclude '*/ThirdParty/*'
```

It lists removed-API uses, dead guards, commented-out checks, CMake
references to the dropped options, the convertible checks by concept, the
checks that stay, and the marker comments.

### 1. Hand rewrites: removed APIs (only if the audit lists any)

- **`#define ITK_CONCEPT_NO_CHECKING`**: delete it. It was there to switch
  checks off, so expect the checks it hid to fail somewhere; build, and fix
  each failure (the code or the check), never by suppressing it.
  Example: BRAINSTools `ImageCalculator/ImageCalculatorTemplates.h:22`.
- **Custom concepts on `itkConceptConstraintsMacro` or `Concept::Detail`**:
  rewrite as a `std::bool_constant` trait (detection idiom for "has
  member/operator") checked by `static_assert`, or as a plain
  `static_assert` on a standard trait. Do not depend on ITK's new internal
  `Concept::Detail`. Give each rewritten trait a passing and a failing
  `static_assert` case in a test, as `itkConceptCheckingGTest.cxx` does
  (`static_assert(!MyTrait<std::string>::value);`); a trait tested only for
  success can start accepting everything unnoticed. The only external user #7108 found was dmritool's
  `utlITKConceptChecking.h`.
- **`ITK_USE_STRICT_CONCEPT_CHECKING` blocks**: never defined. Delete the
  block, or enable a check that still makes sense.
- **CMake `ITK_USE_CONCEPT_CHECKING` / `ITK_USE_STRICT_CONCEPT_CHECKING`**:
  ITK ignores both with a warning; drop the `set()` or option.

Commit as `COMP: Remove ITK concept-checking APIs that ITK 6 removed` (or the
project's equivalent prefix).

### 2. Enable the dead checks

```bash
python3 $S enable --root . --apply
```

A guard with `#else`/`#elif` is reported and left for a hand edit. Then
**build every target whose headers changed**. These checks never compiled
before, so a failure is usually a real bug the check was written to catch.
#7108 found `PhaseCorrelationImageRegistrationMethod` deriving
`MovingImageDimension` from the fixed image type. Fix the code; change a
check only when it is wrong for a supported instantiation, and say so in
the commit. #7108 removed one such check: `MaximumAbsoluteValueImageFilter`
required `GreaterThanComparable` on the raw pixels, which stopped
`std::complex` images compiling although the filter compares
`Math::Absolute` results. Read what the code does with the type before
trusting a check that was never compiled.

For each commented-out check the audit listed, decide: enable it as a real
check, or delete it.

Commit: `ENH: Enable concept checks guarded by ITK_USE_CONCEPT_CHECKING`.

### 3. Replace dimension and type checks with static_assert

```bash
python3 $S static-assert --root . --apply
# run the project's clang-format on the changed files (pre-commit if it has one)
```

Only these concepts are converted, exactly as #7108 did; every other
`itkConceptMacro` stays.

| Concept | `static_assert` condition |
|---|---|
| `SameDimension<A, B>` | `A == B` |
| `SameDimensionOrMinusOne<A, B>` | `B == A \|\| B == A - 1` |
| `SameDimensionOrMinusOneOrTwo<A, B>` | `B == A \|\| B == A - 1 \|\| B == A - 2` |
| `SameDimensionOrMinusOneOrTwo<3, B>` | `B > 0 && B <= 3` |
| `SameType<A, B>` | `std::is_same_v<A, B>` |
| `IsInteger<T>` | `std::is_integral_v<T>` |
| `IsUnsignedInteger<T>` | `!NumericTraits<T>::is_signed` |
| `Signed<T>` | `NumericTraits<T>::is_signed` |
| `HasZero<T>` | `std::is_default_constructible_v<T>` |

Three rules from N-Dekker's review of #7108 (2026-11-04):

- **No message.** `static_assert(VDimension == 3u);` already says what a
  message such as "VDimension must equal 3" would repeat.
- **No `Self::`.** The assertion sits in class scope, so
  `Self::InputImageDimension` becomes `InputImageDimension` (and
  `typename Self::PixelType` becomes `PixelType`).
- **A literal first argument becomes a range.** `<3, B>` reads
  `B > 0 && B <= 3`; in general `B >= low && B <= high`.

A literal second argument keeps its suffix (`3u`). `NumericTraits` takes the
qualification the concept had (`itk::Concept::` gives `itk::NumericTraits`).
Each condition is the old concept's own definition, so behavior does not
change. Where every check between a `// Begin concept checking` and
`// End concept checking` pair was converted, the phase deletes the pair
too, as #7108's commit 3 does; a block that keeps an `itkConceptMacro`
keeps its markers until phase 4. Build the changed targets.

Commit: `STYLE: Replace dimension and type concept checks with static_assert`.

### 4. Remove the marker comments

```bash
python3 $S comments --root . --apply
# run clang-format again: it restores the blank line before `protected:`
# where a marker used to sit
```

Deletes `// Begin concept checking`, `// End concept checking`, `/** Start
concept checking */` and similar lines, and ITKModuleTemplate's `// Add
concept checking such as` placeholder with its commented example, without
leaving double blank lines.

Commit: `STYLE: Remove "Begin/End concept checking" comments`.

### 5. Gate and hand-off

Run the project's pre-commit (`pre-commit run --all-files` where it has one),
build, and run the affected tests. Summarize the commits for the user. Do
**not** push or open a PR unless the user asks for that specific PR
(`pr-no-unsolicited.md`); PRs are drafts.

## Validation (2026-11-04)

Run on ITK itself against #7108's commits at head 0c0beb577b8, with
clang-format 19.1.7 after each phase:

- `static-assert` (with `--no-add-includes`) on the tree after commit 2
  gives a tree **identical** to commit 3 (0 files differ): 162 conversions
  in 115 files, and 756 `itkConceptMacro` uses kept. The PR text says 757;
  it predates the removal of the `MaximumAbsoluteValueImageFilter` check.
- `comments` on that result gives a tree identical to commit 4, the PR
  head: 62 lines in 28 files. `all` on the tree after commit 2 gives the
  same tree.
- `enable` on the tree after commit 1 removes all 53 guards and matches
  commit 2 in 45 of its 52 files; the other 7 are that commit's hand fixes
  (the `MovingImageDimension` bug, two new checks, the removed
  `GreaterThanComparable` check, a strict-checking block, and two template
  placeholders, which phase 4 removes).

Forest audit on the same day (dead guards / convertible / kept): ANTs 4 / 5
/ 7, BRAINSTools 14 / 12 / 32 plus one `ITK_CONCEPT_NO_CHECKING`, elastix 9
/ 5 / 9, MITK 7 / 5 / 8, ITK-SNAP 9 / 4 / 11, c3d 4 / 1 / 4, Plastimatch 6
/ 8 / 6, RTK 0 / 3 / 12, SimpleITK none.

## Tests

```bash
cd ~/src/itk_forest_build_testbed && pixi run python -m pytest -q skills/itk-convert-conceptchecking/tests
```

## Provenance

Hans Johnson, 2026-11-04: "make a github skill related to
https://github.com/InsightSoftwareConsortium/ITK/pull/7108 as
/itk-convert-conceptchecking to run on other code bases." The conversion
rules are read from #7108's commits, not reconstructed from memory.

Updated the same day to #7108 as force-pushed after review (3028a5c316d,
fc7ab89e45f, 2a1aa1513d4, 0c0beb577b8; the first version followed
d0dd3dffa36, 38efac06226, ad7e75b2a76, 1919d32a15a). N-Dekker asked for no
messages, no `Self::`, and `InputImageDimension > 0 && InputImageDimension
<= 3`; Greptile's findings led to the removed `MaximumAbsoluteValueImageFilter`
check, the probe-safe primary `PixelTraits`, and `itkConceptCheckingGTest`.
If the PR changes again before it merges, replay the validation above
before trusting the phases.
