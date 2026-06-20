---
name: itk-in-class-member-init
description: >-
  Use when an ITK (or ITK-consumer) class header declares data members
  (m_Foo) with no initializer, leaving them uninitialized until a
  constructor runs — the latent-uninitialized-read source behind MSVC
  C26495, Valgrind "uninitialised value", and GCC -Wmaybe-uninitialized
  warnings, and the blocker for Rule of Zero. Adds C++11 in-class member
  initializers (bare {} for default-zero, or a promoted constant from the
  constructor init-list). Keywords: in-class member initializer, default
  member initializer, uninitialized member, C26495, maybe-uninitialized,
  Valgrind uninitialised value, Rule of Zero, m_Foo;, member init list,
  bare braces {}, NSDMI.
---

> **Constraint — C++17, ITKv5 + ITKv6:** target C++17 idioms valid against both ITK >=5.4 and ITKv6; never require C++20+. Verify transformed output by compiling against both ITK header sets with `-std=c++17` (see skills/BRAINSTOOLS_HARDENING.md).

# itk-in-class-member-init

## Overview

C++11 lets a non-static data member carry an initializer in its
declaration (a non-static data member initializer, NSDMI). ITK headers
predating this convention declare members bare:

```cpp
int    m_WholeExtent[6];
double m_DataSpacing[3];
bool   m_UseImageSpacing;
```

Such members are **uninitialized** unless every constructor sets them.
That is the root of MSVC C26495, Valgrind "use of uninitialised value",
and GCC `-Wmaybe-uninitialized`, and it forces hand-written
constructors that block the Rule of Zero.

Core principle: **give every member a deterministic initial value at the
point of declaration.** For scalars/arrays that should start zeroed, add
`{}`. For a member the constructor sets to a *constant*, promote that
constant to the declaration and drop the constructor entry (avoid
double-init).

## When to use

- A header has `m_Foo;`-style member declarations with no `= …` and no `{}`.
- CDash / MSVC reports C26495; Valgrind flags an uninitialised read; GCC
  reports `-Wmaybe-uninitialized` on a class member.
- You want to delete a hand-written constructor whose only job is zeroing
  members (Rule of Zero).

## When NOT to use

- **static** data members (`static int m_Count;`) — initialized elsewhere.
- **reference** members (`Foo & m_Ref;`) — must be bound in the init-list.
- **const** members whose value is non-constant (depends on a ctor arg).
- A member whose constructor value is **not a compile-time constant**
  (computed from arguments / other members) — leave it in the init-list.
- ThirdParty/ trees — never modify vendored code.

## Before / after

```cpp
// before
  int    m_WholeExtent[6];
  double m_DataSpacing[3];
  bool   m_UseImageSpacing;   // ctor: m_UseImageSpacing(true)

// after
  int    m_WholeExtent[6]{};
  double m_DataSpacing[3]{};
  bool   m_UseImageSpacing{ true };   // ctor entry removed
```

The bare-`{}` case is purely mechanical. The constant-promotion case
also requires removing the matching `m_UseImageSpacing(true)` from the
constructor initializer list (or `m_UseImageSpacing = true;` from the
body) so the value is not initialized twice.

## Detection

`detect.sh <repo>` greps class headers for member declarations that have
no initializer, skipping `static`, `=`, `{`, and reference (`&`) lines,
and excluding ThirdParty/. It prints `file:line` hits plus a count.

```bash
bash skills/itk-in-class-member-init/detect.sh /path/to/ITK
```

For higher precision (AST-based), clang-query finds the same set:

```
clang-query> match fieldDecl(unless(hasInClassInitializer(anything())),
                             unless(isStaticDataMember()))
```

Cross-check the constructor init-list: a member set there to a constant
is a **promotion** candidate; a member set to a non-constant must stay in
the init-list.

## Transformation approach

This is **partly** automatable. `transform.sh` handles the safe,
high-volume bare-`{}` case only:

```bash
bash skills/itk-in-class-member-init/transform.sh /path/to/ITK          # dry-run
bash skills/itk-in-class-member-init/transform.sh --apply /path/to/ITK  # write
```

`transform.sh` appends `{}` before the trailing `;` of each detected
uninitialized member (C-arrays included). It does **not** touch
constructors, so it never creates a double-init.

**Constant promotion is review-only** (medium mechanizability): it
requires reading both the header and the constructor to confirm the
value is a literal constant, then editing two files. Do that by hand.

After any edit:

1. Re-run `clang-format` on touched headers.
2. Rebuild — a member type may lack a default constructor, in which case
   `{}` is wrong and the line must be reverted.

## Verification

```bash
# 1. The transform changed only intended lines:
git diff --stat
# 2. The tree still builds (some types lack a default ctor):
cmake --build <build-dir>
# 3. No remaining bare members of interest:
bash skills/itk-in-class-member-init/detect.sh .
```

A member whose `{}` broke the build (no default ctor, or an aggregate
that `{}` can't value-init) must be reverted individually.

## Common mistakes

- **Promoting a non-constant ctor value** (`m_Size(other.GetSize())`) into
  the declaration — wrong; that value isn't known at declaration. Leave it.
- **Adding `{}` and leaving the ctor entry** for the same member — harmless
  for `{}` but double-initializes when promoting a constant. Always drop
  the ctor entry when promoting.
- **Touching static / reference / const members** — skip them; `{}` is
  invalid or changes semantics.
- **Assuming `{}` always compiles** — a member whose type has no default
  constructor will fail; verify by building, not by grep alone.
- **Editing ThirdParty/** — excluded by detect/transform; keep it that way.
