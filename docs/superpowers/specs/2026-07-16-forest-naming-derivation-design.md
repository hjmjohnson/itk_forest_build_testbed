# Forest naming derivation (phase 1)

> **SUPERSEDED — engine-side derivation was ABANDONED (2026-07-16).** Do not
> implement this plan. Derivation, the reserved `itk-` prefix, the refusal gate
> and the identity gate were dropped after eight review rounds; the salvaged
> keepers (`refslug()`, the manifest recording resolved truth, `compare`, the
> suffix-key validator, `ITK_REF_EXPLICIT`) landed on `feat/forest-manifest-truth`.
> `FOREST_REFERENCE_SUFFIX` is a plain free-form suffix and `itk-<refslug>` is a
> convention you type. Kept as the design record only — see `docs/workflow.md`
> and `docs/config.md` for how forest naming actually works, and
> `.superpowers/sdd/salvage-report.md` for what was kept and dropped.

**Status:** design, approved for spec
**Date:** 2026-07-16
**Repo:** `hjmjohnson/itk_forest_build_testbed` (kit)
**Phase:** 1 of 3 — see *Out of scope* for phases 2 (`[toolchain]` contract) and 3 (`shared_resources/`).

## Problem

A forest's name does not tell you what it contains, and neither does its manifest.

Observed on 2026-07-16 across the seven live forests:

| forest | manifest `ref` | actual ITK SHA | actual branch |
|---|---|---|---|
| `build_forest` | `origin/main` | `57b7c6e5b2` | `reenable-vr-gaussian-ncc-3d-macos` |
| `build_forest-base` | `origin/main` | `129c231bda` | `itk-downstream-base` |
| `build_forest-itkv5` | `origin/main` | `c8721a5c93` | **actually `release-5.4`** |
| `build_forest-itkv6_main` | `origin/main` | `6707e4c192` | |
| `build_forest-linpackref` | `origin/main` | `bcc43b3d91` | `fix-dcmtk-build-export-namespace` |
| `build_forest-svdc` | `origin/main` | `f386a36bbe` | |

Two independent defects produce this:

1. **The name is a free-form promise.** `FOREST_REFERENCE_SUFFIX` is an arbitrary
   string. Nothing ties it to the ITK ref actually checked out, so
   `build_forest-itkv5` drifted onto `release-5.4` and no mechanism noticed.
2. **The manifest records the declared default, not the resolved truth.**
   `cmd_manifest` (`bin/config.py:316`) reads `spec.get("ref", "origin/main")`
   from `versions.toml` rather than resolving the worktree, so **every** forest
   reports `ref = "origin/main"` regardless of what it holds.

Defect 2 is the same class as `CMAKE_CXX_COMPILER = "$env{CXX}"`: the manifest
records the *recipe* and calls it a *record*. `docs/config.md` claims the
manifest is "a human-readable record of exactly what was built". For the ITK
ref, it is not.

The cost is concrete: the common task is "compare `release-5.4` against PR
#NNNN", and today neither the directory name nor the manifest can confirm which
forest holds which ref.

## Goals

- A forest's name is **derived** from its ITK ref, so it cannot drift.
- The manifest records the **resolved** ref, SHA, and ITK version.
- "Build against `<ref>`" and "compare `<refA>` vs `<refB>`" are mechanical and
  re-runnable.
- Renaming-driven silent behaviour changes are impossible (see *Suffix-keyed
  config*).

## Non-goals

- Changing what gets built, or the dependency graph.
- Enforcing the toolchain (phase 2).
- `shared_resources/` (phase 3).
- Renaming demo branches on forks (e.g. `demo-itkv6_main` on
  `hjmjohnson/elastix`) — that is a remote ref, out of scope.

## Design

### 1. `refslug()` — the primitive

A pure function in `bin/config.py`. Input: any ITK ref. Output: a slug that is
simultaneously a legal git branch component and a legal path component.

| input | output |
|---|---|
| `origin/release-5.4`, `upstream/release-5.4`, `release-5.4` | `release-5.4` |
| `origin/main`, `main` | `main` |
| `v5.4.6` | `v5.4.6` |
| `pr/6250`, `pull/6250/head` | `pr6250` |
| `origin/v6-integration` | `v6-integration` |
| `9a3f1c2b8d…` (bare SHA, ≥7 hex) | `sha9a3f1c2` |

Rules, applied in order:

1. `pr/<N>` or `pull/<N>/head` → `pr<N>`.
2. A string matching `^[0-9a-f]{7,40}$` → `sha<first7>`.
3. Otherwise strip a leading `<remote>/` component if `<remote>` is a configured
   git remote name (`origin`, `upstream`, a fork name); keep the remainder
   verbatim.
4. Validate the result: must match `^[A-Za-z0-9._-]+$`, must not start with `.`
   or `-`, must not contain `..`, must not end with `.lock`. Reject otherwise
   with a clear error rather than emitting a name that breaks git or the
   filesystem.

**Accepted ambiguity (rule 2):** `refslug()` is pure — it does not consult git —
so a branch or tag whose name is itself 7–40 lowercase hex chars (e.g. a branch
literally named `deadbeef`) is slugged as a SHA. Resolving this would require a
git lookup and make the function impure and untestable in isolation. ITK has no
such ref, and the cost if one ever appears is a misleading forest name, not a
wrong build — the resolved SHA in the manifest remains authoritative. Accepted.

**Accepted assumption:** rule 3 collapses `origin/release-5.4` and
`upstream/release-5.4` to one forest. Today those resolve to the same commit
(`c8721a5c`), and collapsing them is what makes compare re-runnable. If the two
remotes ever diverge for the same branch name, this is wrong — the resolved SHA
recorded in the manifest is the detection mechanism.

`refslug()` is pure and is unit-tested directly (see *Testing*).

### 2. Forest naming

- Derived name: `build_forest-itk-<refslug(ITK_REF)>`.
- Examples: `build_forest-itk-release-5.4`, `build_forest-itk-pr6250`,
  `build_forest-itk-main`, `build_forest-itk-v5.4.6`.
- The engine computes the forest directory from `ITK_REF`.
  `FOREST_REFERENCE_SUFFIX` becomes an override for free-form experiment
  forests only.
- **`itk-` is reserved.** A hand-passed `FOREST_REFERENCE_SUFFIX` beginning with
  `itk-` that does not equal `itk-<refslug(ITK_REF)>` is refused:

  ```
  [err] 'itk-' is reserved for derived ref forests (got: itk-foo,
        ITK_REF=origin/main derives itk-main). Set ITK_REF, or choose a
        suffix that does not start with 'itk-'.
  ```
- Free-form suffixes (`svdc`, `base`, `linpackref`) remain legal and unmanaged.
- **The bare `build_forest` is retired.** With no `ITK_REF`, the configured
  default (`components.ITK.ref` = `origin/main`) derives `build_forest-itk-main`.
  Every forest is therefore either derived or explicitly named.

**Consequence: one forest per ref.** Two forests on the same ITK ref require a
free-form suffix. This is intentional — it is what makes a ref map to a
predictable location — but it means a same-ref A/B experiment (e.g. proving
cross-forest ccache reuse) must use a free-form name.

The suffix continues to be used **verbatim** for the forest directory, git
branch names (`itk-downstream-<suffix>`, `<consumer>-itk-downstream-<suffix>`),
log tags, and scenario keys. This yields redundant-looking branch names such as
`itk-downstream-itk-release-5.4`. That redundancy is accepted deliberately: the
suffix is the single forest identity, and introducing a separate branch-name
mapping would reintroduce exactly the name/content drift this spec removes.

### 3. Manifest records resolved truth

`cmd_manifest` (`bin/config.py:316`) currently emits:

```python
"ref": spec.get("ref", "origin/main"),   # declared default -- wrong
```

It must instead record what the worktree actually holds, plus enough to identify
it without a git call:

```toml
[components.ITK]
url          = "https://github.com/InsightSoftwareConsortium/ITK.git"
ref          = "origin/release-5.4"   # the REQUESTED ref, as resolved
slug         = "release-5.4"          # refslug(ref) -- ties name to content
branch       = "itk-downstream-itk-release-5.4"
sha          = "c8721a5c93c78f4c03928898d3d4ed6a23954c9f"
kind         = "consumer"

[forest]
name         = "build_forest-itk-release-5.4"   # directory BASENAME, not a path
derived_from = "origin/release-5.4"    # empty for free-form forests
itk_version  = "5.4.6"                 # resolved after checkout
```

- `ref` is the requested ref for this forest, persisted per-forest (not read
  back from the global `versions.toml` default).
- `[forest].name` is the directory **basename**, so the manifest stays valid if
  the whole testbed is relocated (`BUILD_FOREST_ROOT` may be an absolute path
  elsewhere).
- `itk_version` is parsed from the checked-out ITK source after checkout, by
  reading `ITK_VERSION_MAJOR`/`MINOR`/`PATCH` from `<ITK>/CMakeLists.txt`. If it
  cannot be parsed, the field is omitted and a warning is emitted — an
  unparseable version must not block a build. It is recorded, never encoded in
  the name — a name must be computable *before* checkout, and `itk-main` must
  not rot when `main` becomes v7.
- `[forest].derived_from` empty ⇒ free-form forest; the engine does not enforce
  the name/ref relationship for those.

A consistency check (`config.py --check` extension) reports any forest whose
`[forest].name` disagrees with `build_forest-itk-<slug>` while `derived_from` is
non-empty.

### 4. Suffix-keyed config (silent-breakage guard)

Two **tracked** config values are keyed by the suffix string. Renaming a forest
without updating them changes build behaviour with no error:

| key | current value | must become | if missed |
|---|---|---|---|
| `subbuild.ANTs.skip_suffix` (`versions.toml`; engine L478/L495) | `itkv5` | `itk-release-5.4` | ANTs fork skip silently stops applying |
| `[scenarios.itkv6_main.elastix]` (`versions.toml:268`) | key `itkv6_main` | key `itk-main` | elastix silently drops the PR #1452 MatrixExponential fork |

Migration MUST update both. Additionally, the engine gains a validation step:
on startup, any `[scenarios.<key>]` or `skip_suffix` naming a key that begins
with `itk-` but is not a well-formed `itk-<refslug>` is a hard error. A scenario
key that matches no existing forest is a warning, not an error (a scenario may
legitimately precede its forest).

### 5. Migration — wipe and remake

Decision: delete all seven forests and remake them, properly named, on demand.

Preconditions (already satisfied):

- Uncommitted work preserved to `.devlocal/preserved-20260716/` — 9 patches,
  52 K. Includes `build_forest-svdc_Slicer.patch`, verified to contain the SUV
  work (`ADDITIONAL_SRCS itkDCMTKFileReader.cxx`; BRAINSTools repointed to
  `hjmjohnson/BRAINSTools` @ `bfbd9bce`). Caveat: `.devlocal/` is gitignored and
  machine-local; the patches cover tracked-file edits only.

Steps:

1. `rm -rf build_forest build_forest-base build_forest-itkv5
   build_forest-itkv6_main build_forest-linpackref build_forest-svdc
   build_forest-pr-to-merge-into-release5.4` (~94 G reclaimed).
2. **`git worktree prune`** in every clone under `forest_git_repos/`. Without
   this the clones retain stale worktree registrations and re-adding the same
   branch fails with *"already checked out"*. This is mandatory, not hygiene.
3. Leave the now-unreferenced per-forest branches (`itk-downstream-itkv5`,
   `ants-itk-downstream-itkv5`, …) in the central clones. They cost nothing,
   and they are the only remaining record of what those forests held — which
   makes them the fallback if a preserved patch in step 0 turns out to be
   incomplete. Prune them in a separate, deliberate cleanup, never as a side
   effect of this migration.
4. Update `versions.toml`: `skip_suffix` and the `[scenarios.*]` key per §4.
5. Remake on demand: `ITK_REF=origin/release-5.4 pixi run checkout` →
   `build_forest-itk-release-5.4`.

**Known loss:** `build_forest-svdc` held a Slicer/VTK SuperBuild that 43
manifest entries in other forests pointed at (`VTK_DIR` →
`build_forest-svdc/Slicer/build/VTK-build`). Deleting it means the next forest
needing VTK rebuilds it. This cross-forest borrowing contradicts `CLAUDE.md`'s
"each forest is a self-contained build tree" and is precisely what phase 3
(`shared_resources/`) replaces with an explicit, named provider. Until phase 3
lands, a forest needing VTK builds its own.

## Error handling

All failures are loud and immediate; none may fall back to a default.

| condition | behaviour |
|---|---|
| `refslug()` input yields an invalid slug | die with the input and the rule violated |
| `FOREST_REFERENCE_SUFFIX=itk-*` not matching derivation | die; show derived name |
| derived forest name ≠ `[forest].name` in an existing manifest | die; instruct to use the correct `ITK_REF` or a free-form suffix |
| `skip_suffix` / scenario key is a malformed `itk-*` | die at startup |
| scenario key matches no forest | warn |

## Testing

Extends the existing suite (`bin/tests/`, alongside `test_resolve_preset.py`,
`test_manifest_config.py`, `test_compare.py`).

1. **`test_refslug.py`** — table-driven over every row in §1, plus rejection
   cases: empty, `..`, leading `-`, leading `.`, trailing `.lock`, embedded
   space, `refs/heads/x` forms.
2. **`test_forest_name.py`** — `ITK_REF` → forest directory; reserved-prefix
   refusal; free-form passthrough; bare-`build_forest` retirement.
3. **`test_manifest_config.py`** (extend) — manifest records resolved `ref`,
   `slug`, `sha`, `itk_version`, `[forest]`; assert the `spec.get("ref", …)`
   regression cannot return (a fixture worktree on `release-5.4` must not report
   `origin/main`).
4. **`test_compare.py`** (extend) — comparing two forests surfaces a ref/slug
   delta, which today it cannot.
5. **Suffix-keyed config validation** — malformed `itk-*` scenario key dies;
   unmatched key warns.

Each is a pure-function or fixture test; none requires a build.

## Out of scope (later phases)

- **Phase 2 — `[toolchain]` contract.** Manifest records resolved compiler
  id/version, `CONDA_PREFIX`, ccache hash policy; preflight + per-package
  enforcement; hard fail + `retoolchain` on drift. Already designed; blocked
  only on this spec landing.
- **Phase 3 — `shared_resources/`.** Takeover of `common-support-builds`:
  adopt its `<PKG>/{src,bld,installed}_<refslug>[_<FEATURE>]` grammar and its
  ABI-suffix test; build under the pinned toolchain (dropping `-march=native`);
  retire `~/src/common_support_versions` (12 G), the six `csv_*` scripts, and
  the `-workspace` scaffolding; repoint
  `~/src/BRAINSTools/CMakeUserPresets.json` **after** its ITK/VTK are rebuilt
  under the pinned toolchain.
