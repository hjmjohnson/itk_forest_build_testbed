# Slicer ITK policy — vendor a variant of *this forest's* ITK base

Two rules, both non-negotiable.

**Rule 1 — Slicer never consumes the forest's system ITK.** It always builds a
dedicated *Slicer-vendored* ITK branch, selected with an explicit
`-DSlicer_ITK_GIT_TAG=<branch>`.

**Rule 2 — that branch derives from THIS FOREST'S ITK base.** One variant per
forest. Never point two forests at one branch.

| forest | Slicer's internal ITK |
|---|---|
| `build_forest-itk-release-5.4` | `ITK/release-5.4` **+ itk5 Slicer patches** |
| `build_forest-itk-main` | `ITK/main` **+ itk6 Slicer patches** |
| `build_forest-itk-pr<N>` | that PR's base **+ the patches for its ITK major** |

Rule 2 is what makes the forest meaningful: a forest exists to answer *"does ITK
ref X break its consumers?"* If Slicer builds some other ITK, the Slicer column
of that forest answers a question nobody asked.

## Where it is declared (per-forest, machine-enforced)

`versions.toml`, one block per forest — **not** a global tag:

```toml
["scenarios"."itk-release-5.4"."Slicer"]
ITK_GIT_TAG = "slicer-v5.4.6-2026-07-17-9cd63da191e"

[scenarios.itk-main.Slicer]
ITK_GIT_TAG = "slicer-v6.0.0-2026-07-17-350ae6b0897"
```

Resolve it with:

```bash
python3 bin/config.py subbuild-get <forest-suffix> Slicer ITK_GIT_TAG
```

**A forest with no declared variant exits non-zero.** That is deliberate: there
is no global default to fall back to, because falling back silently builds the
wrong ITK (see "How this fails silently" below).

> **TOML gotcha:** quote any suffix containing a dot.
> `[scenarios.itk-release-5.4.Slicer]` parses as
> `scenarios → itk-release-5 → 4 → Slicer` and silently never matches.
> Write `["scenarios"."itk-release-5.4"."Slicer"]`.

## Naming

    slicer-v<ITK version>-<YYYY-MM-DD>-<base short sha>

e.g. `slicer-v5.4.6-2026-07-17-9cd63da191e`. The base sha is the point of the
name — it says *which* ITK this variant is a variant **of**, so a stale variant
is visible without reading the log.

## Minting a variant (the recipe)

```bash
cd ~/src/ITK
git fetch upstream

# 1. Branch from THIS FOREST'S base -- release-5.4 or main, at its TIP.
BASE=upstream/release-5.4                       # or upstream/main
SHA=$(git rev-parse --short=11 $BASE)
VER=$(git show $BASE:CMake/itkVersion.cmake | grep -E 'ITK_VERSION_(MAJOR|MINOR|PATCH)' \
      | sed -E 's/.*"([0-9]+)".*/\1/' | paste -sd. -)
git checkout -B slicer-v${VER}-$(date +%F)-${SHA} $BASE

# 2. Cherry-pick the Slicer patches, oldest first, from the previous variant of
#    the SAME ITK major (git log --oneline <prev-base>..<prev-variant>).
git cherry-pick <namespace-patch> <itkFileTools-patch>   # see "The patch set"

# 3. Push to the fork and declare it in versions.toml (block above).
git push -u origin slicer-v${VER}-$(date +%F)-${SHA}
```

**On `release-5.4`, cherry-pick needs `PRE_COMMIT_ALLOW_NO_CONFIG=1`** — that
branch predates ITK's `.pre-commit-config.yaml`, so the `prepare-commit-msg`
hook aborts the commit *after* applying the patch cleanly. This is the one
documented place that escape is correct:

```bash
PRE_COMMIT_ALLOW_NO_CONFIG=1 git cherry-pick <sha>
```

### Expect patches to go empty — that is the recipe working

A patch that cherry-picks **empty** has landed upstream; **drop it, do not force
it**. Verify before assuming:

```bash
git log --oneline <base> --grep="^<exact subject>$"    # in the base already?
```

Worked example (2026-07-17):

| patch | itk5 (release-5.4) | itk6 (main) |
|---|---|---|
| `COMP: Add support for customizing ITK namespace (draft)` | applied | applied |
| `COMP: Fix itkFileTools build error when testing enabled` | applied | **empty — already upstream** |
| 3 × `[backport] …` (NRRD 5D, short direction vector, DCMTK namespace) | **obsolete — all 3 now in release-5.4** | n/a |

The previous itk5 variant carried 5 patches; a fresh one off the release-5.4
**tip** needs 2, because the 3 backports have since merged
(`767cef70220`, `12203bc094b`, `83a1c530ada`). Re-derive the set each time — do
not copy the last variant's patch count.

### The patch set (as of 2026-07-17)

Genuinely Slicer-only — present in neither `release-5.4` nor `main`:

1. `COMP: Add support for customizing ITK namespace (draft)`
2. `COMP: Fix itkFileTools build error when testing enabled` *(itk5 only now)*

Confirm before minting; the set shrinks as patches land upstream:

```bash
for s in "COMP: Add support for customizing ITK namespace (draft)" \
         "COMP: Fix itkFileTools build error when testing enabled"; do
  echo "$(git log --oneline upstream/main --grep="^${s}$" | wc -l) $s"
done   # 0 => still needed
```

### Do not vendor experiments

A variant contains **the base + Slicer patches, nothing else.** The old
`slicer-v6.0.0-svdc-c1a4cecfab7` also carried an in-flight `vnl_svd` LINPACK
port and a DCMTK export fix — the `-svdc-` in the name is the tell. That is a
*test* branch. Building Slicer on it silently tested those experiments too, and
attributed any breakage to "Slicer".

If you want a forest to test ITK ref X **and** an experiment, the experiment
belongs in the forest's ITK ref, not smuggled into Slicer's vendored branch.

## How this fails silently (why the rules are rigid)

`SLICER_ITK_GIT_TAG` / `-DSlicer_ITK_GIT_TAG` reaches CMake **only at configure
time**. The engine skips configure when `build.ninja` already exists
(`bin/setup-itk-downstream-testbed.sh`), so **on an already-configured tree the
override is silently dropped** and the stale `CMakeCache.txt` value wins.

Observed 2026-07-17: a build launched with
`SLICER_ITK_GIT_TAG=slicer-v5.4.6-…` built **ITK 6.0.0**, then failed with an
*unrelated* zlib link error. Nothing said the override was ignored. The only
tells were library sonames (`libITKznz-6.0.1.dylib`) and the cache.

**Verify the tag took, every time — before reading any error:**

```bash
grep Slicer_ITK_GIT_TAG <forest>/Slicer/build/CMakeCache.txt
git -C <forest>/Slicer/build/ITK log -1 --oneline
git -C <forest>/Slicer/build/ITK show HEAD:CMake/itkVersion.cmake | grep ITK_VERSION_
```

If it disagrees with `config.py subbuild-get`, force a reconfigure (or wipe the
Slicer build tree) — do not debug the error you were handed; it is an error
about the wrong ITK.

## Relationship to the latest-main-first rule

The forest's *system* ITK tracks the ref under test (ANTs, BRAINSTools, and the
ITK remote modules build against it directly). Slicer is the deliberate
exception — but Rule 2 keeps it honest: "test ITK ref X with Slicer" means
**mint a variant off X** and build Slicer against that, then upstream any
Slicer-side fixes X requires.

## Why not `Slicer_USE_SYSTEM_ITK`

- Slicer requires ITK built **its** way — `Module_ITKVtkGlue=ON` against
  Slicer's VTK, Qt, a specific module set, and Slicer-carried ITK patches not
  (yet) upstream.
- A bare `upstream/main` ITK routinely lacks those patches or has API churn
  Slicer hasn't absorbed. Vendoring a variant keeps builds **reproducible** and
  decouples "is this ITK Slicer-ready?" from "did ITK main move?".

## Related

- `docs/slicer-macos.md` — Qt6 / ccache / conda-flag specifics
- `versions.toml` — `[subbuild.Slicer]` (repo) + `[scenarios.<suffix>.Slicer]` (per-forest tag)
- `bin/config.py subbuild-get <suffix> Slicer ITK_GIT_TAG` — the resolver
