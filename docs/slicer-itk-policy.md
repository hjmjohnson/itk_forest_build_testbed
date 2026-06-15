# Slicer ITK policy — always vendor a dedicated `slicer-itk-*` branch

**Standard practice (non-negotiable): Slicer never consumes the forest's
system ITK.** It is always built against a dedicated *Slicer-vendored* ITK
branch on `hjmjohnson/ITK`, selected with an explicit
`-DSlicer_ITK_GIT_TAG=<branch>` override.

```
-DSlicer_ITK_GIT_REPOSITORY=https://github.com/hjmjohnson/ITK
-DSlicer_ITK_GIT_TAG=slicer-itk-<descriptor>
```

This applies to **Slicer and, transitively, SlicerExtensions** (extensions
build against the inner Slicer build, so they inherit its ITK).

## Why not `Slicer_USE_SYSTEM_ITK`

- Slicer requires ITK built **its** way — `Module_ITKVtkGlue=ON` against
  Slicer's VTK, Qt, specific module set, and a small stack of Slicer-carried
  ITK patches not (yet) in upstream `main`.
- A bleeding-edge bare `upstream/main` ITK routinely lacks those patches or
  has API churn Slicer hasn't absorbed. Pinning a curated branch keeps Slicer
  builds **reproducible** and decouples "is this ITK Slicer-ready?" from "did
  ITK main move?".

## Creating a new Slicer-vendored ITK (the procedure)

When testing a newer ITK with Slicer, **create a new vendored branch — do not
repoint Slicer at bare `upstream/main`:**

1. In `~/src/ITK`, branch from the ITK commit under test:
   ```bash
   git fetch upstream
   git checkout -B slicer-itk-$(date +%Y-%m-%d)-<shortsha> upstream/main
   ```
2. Apply / rebase the Slicer-carried ITK patches onto it (the delta between
   the previous `slicer-v*`/`slicer-itk-*` branch and its upstream base):
   ```bash
   git range-diff upstream/main...<previous-slicer-itk-branch>
   git cherry-pick <each Slicer patch>   # or rebase the prior branch onto the new base
   ```
3. Push to the fork:
   ```bash
   git push hj slicer-itk-$(date +%Y-%m-%d)-<shortsha>
   ```
4. Build Slicer with the override (the engine already reads these env vars):
   ```bash
   SLICER_ITK_GIT_REPOSITORY=https://github.com/hjmjohnson/ITK \
   SLICER_ITK_GIT_TAG=slicer-itk-<descriptor> \
   pixi run build-Slicer
   ```

`bin/setup-vxl-downstream-testbed.sh` honors `SLICER_ITK_GIT_REPOSITORY` and
`SLICER_ITK_GIT_TAG`; the default is the most recent published `slicer-v*`
branch. Override per run when validating a fresh vendored branch.

## Relationship to the latest-main-first rule

The forest's *system* ITK tracks `upstream/main` (ANTs, BRAINSTools, and the
ITK-remote modules build against it directly). Slicer is the deliberate
exception: "test the latest ITK with Slicer" means **mint a new
`slicer-itk-*` branch off that latest ITK and build Slicer against it**, then
upstream any Slicer-side fixes the new ITK requires.
