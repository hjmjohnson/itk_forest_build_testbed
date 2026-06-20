# Hardening pass — ITK modernization skills validated on BRAINSTools

Applied each modernization skill to BRAINSTools (`build_forest-itkv6_main/BRAINSTools`,
branch `braintools-vxl-master-itkv6_main` off `origin/main` `a8bdeae5`) with a
**per-file compile gate**, then verified the aggregate.

## Method

BRAINSTools' inner build cannot be reconfigured/linked standalone (superbuild-only
deps: ANTS install → `TBB::tbb`/`Threads::Threads` → …). So instead of a full
build, each transform was gated by compiling the affected translation units with
`-fsyntax-only` (which still performs template instantiation) using the real
compile commands from the existing build graph (`ninja -t compdb`) — no regen, no
link. Per skill: apply → compile affected TUs → commit on success (one clean
commit, retrying through the BRAINSTools pre-commit reformatter) / revert on failure.

**The gate must be warning-fatal, and prefer GCC.** A plain `-fsyntax-only` pass
checks instantiation but not dead code, so it passes regressions these transforms
introduce — an orphaned `using FooPointer = T::Pointer;` after its sole use becomes
`auto`, or a set-but-unused local. GCC raises these (`-Wunused-local-typedefs`) and
the `report_build_diagnostics.py` dashboards treat them as fatal; a Clang-only local
check with default flags does not (PR #608: the dead-typedef passed macOS CI as a
ccache hit and failed Ubuntu GCC). Use `skills/itk-compile-gate.sh <build-dir>
--changed <repo>`, which extracts each TU's real compile command, disables ccache,
selects the compiler-correct unused-typedef spelling, and makes the unused set
`-Werror`.

## Result: 6 skills applied (each compile-gated), aggregate green

| Commit | Skill | files | TUs gated |
|---|---|---:|---:|
| `d2cd0dd0` | itk-redundant-void-arg | 18 | 1 |
| `3e2f5548` | itk-ctad-iterator | 1 | 0\* |
| `539a938e` | itk-iterator-drop-withindex | 6 | 7 |
| `44691d90` | itk-prefer-prefix-increment | 95 | 35 |
| `176c1115` | itk-auto-for-new | 179 | 65 |
| `58b26f55` | itk-in-class-member-init | 96 | 39 |

\* changed file not in this build's TU set (applied, uncovered by the gate).

**Aggregate verification:** compiled every TU at the final HEAD → **114/114 existing
TUs OK** (3 reported failures are phantom build-graph entries for test files deleted
upstream since the build was generated; absent at HEAD).

## C++17 validity for BOTH ITKv5 and ITKv6

Every changed translation unit in the PR was recompiled with **`-std=c++17`**
against **both** ITK 5.4 *and* ITK v6 header sets (ITK includes swapped via each
forest's `find_package(ITK)`; syntax-only, so template instantiation still runs):

```
changed TUs in build graph: 50
-std=c++17 vs ITK v6 : OK 50  FAIL 0
-std=c++17 vs ITK 5.4: OK 50  FAIL 0
```

So the applied idioms are valid C++17 for both ITK versions. Constraint, now
stated in every modernization `SKILL.md`: **target C++17 idioms valid against
both ITK ≥5.4 and ITKv6; never require C++20+.** (The six applied idioms are all
≤ C++17 — CTAD is C++17; the rest are C++11/14.)

**No-op on BRAINSTools** (transform found nothing to change): itk-container-size-to-empty,
itk-string-find-presence-test, itk-emplace-back-construct.

**Review-only** (no safe auto-transform; detected & reported for manual application):
itk-cstyle-to-static-cast (30), itk-equals-default-special-members (33),
itk-constexpr-if-constant (2), itk-read-write-image-convenience (264),
itk-fillbuffer-over-iterate.

## Skill bugs the hardening caught and fixed

1. **itk-auto-for-new** — emitted invalid `typename auto x` for template declarations
   (`typename T::Pointer x = T::New();`). Fixed: the regex now consumes and drops a
   leading `typename`. Re-applied; lands clean.
2. **itk-in-class-member-init** — `transform.sh` only honored `--apply` as the *first*
   argument, so a `repo --apply` invocation silently dry-ran (the "798 detected / 0
   changed" symptom). Fixed: order-insensitive arg parsing matching the other skills.
3. **itk-auto-for-new** — rewriting `const FooPointer x = T::New();` to `const auto x`
   orphaned the local `using FooPointer = T::Pointer;` alias, which GCC flags as
   `-Wunused-local-typedefs` (the syntax-only gate and Clang missed it; surfaced as a
   CI failure on PR #608). Fixed two ways: `transform.sh` now sweeps the orphaned
   alias, and the gate (`skills/itk-compile-gate.sh`) is warning-fatal so any
   remaining case fails before commit rather than in CI.

## Caveats for review

- The compile gate covers only the ~117 TUs in BRAINSTools' build graph; changes in
  files no built TU includes are applied but not compile-covered (e.g. ctad-iterator's
  0-TU case). A full BRAINSTools superbuild would close that gap.
- `itk-auto-for-new` / `itk-in-class-member-init` commits include incidental
  pre-commit-hook reformatting of the touched files (BRAINSTools had style drift).
- BRAINSTools commits are local on the testbed worktree branch (not pushed). An
  upstream `ANTsX`-style PR would be a separate, explicit step.
