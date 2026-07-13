---
name: itk-compiler-matrix
version: 1.0.0
purpose: Generate the ITK Software Guide's "routinely tested" compiler/OS support matrix from live test infrastructure (CDash + GitHub Actions + Azure Pipelines) and emit it as a LaTeX table.
description: >-
  Query the ITK quality dashboard (CDash, project "Insight") and the
  continuous-integration matrix (GitHub Actions and Azure Pipelines) to
  determine which operating-system/compiler configurations are routinely tested
  AND pass all tests, then emit a LaTeX table (CompilerSupportMatrix.tex) for the
  ITK Software Guide. Use this skill whenever the user wants to update, refresh,
  or regenerate the compiler-support matrix / supported-compilers table /
  tested-platforms list in the ITK Software Guide, or asks "which compilers does
  ITK currently test", "rebuild the compiler matrix", or needs the
  Installation chapter's compiler table brought up to date. The list is
  deliberately dynamic — it changes as platforms evolve — so it should be
  regenerated from live data rather than edited by hand. Do NOT use it for
  choosing a compiler to build with, comparing compiler version schemes, fixing
  CDash build warnings or errors (that is cdash-build-analysis), scrubbing other
  Software Guide content, or setting up new CI pipelines.
triggers:
  - itk-compiler-matrix
  - /itk-compiler-matrix
  - update the compiler matrix
  - refresh the compiler support table
  - which compilers does ITK test
  - regenerate the supported compilers table
user_invocable: true
cmd: false
argument_hint: "[--days N] [--emit <path-to-CompilerSupportMatrix.tex>]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
    - file
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - SoftwareGuide/Latex/Introduction/CompilerSupportMatrix.tex
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: true
    git_required: false
    user_confirmation_required: false
  determinism: hybrid
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
    - gh
  python_packages: []
  scripts:
    - scripts/build_matrix.py
deployment:
  tier: always
  target_projects:
    - ITKSoftwareGuide
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK compiler/OS support matrix generator

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-compiler-matrix — Regenerate the ITK Software Guide compiler-support table

Usage:
  /itk-compiler-matrix                 Print the LaTeX table to stdout (dry run)
  /itk-compiler-matrix --emit <path>   Write CompilerSupportMatrix.tex into the guide
  /itk-compiler-matrix --days 14       Widen the look-back window (default 7)

Queries CDash + GitHub Actions (+ Azure best-effort) for configurations that
are routinely tested AND pass all tests, then emits a LaTeX table.
```

## Why this skill exists

The ITK Software Guide's Installation chapter used to hard-code a list of
minimum compiler versions (e.g. "GCC 7 and newer"). That list goes stale the
moment platforms move on, and it is not the authoritative record of what ITK
actually tests. The authoritative record lives in the test infrastructure:
CDash and CI know exactly which configurations ran and whether they passed.

This skill turns that live signal into the printed table, so the guide reports
*what is true today* rather than what was true when someone last edited the
`.tex`. The Installation chapter carries a seam for it:

```
%\input{Introduction/CompilerSupportMatrix.tex}
```

Running this skill produces that file; the seam is then uncommented in a
reviewed commit.

## Data sources and the "passes all tests" rule

A configuration is included only when it is **tested and green**:

| Source | What counts as passing |
|---|---|
| CDash (`open.cdash.org`, project `Insight`, id 2) | most recent build in the window with `buildErrorsCount == 0` and `testFailedCount == 0` |
| GitHub Actions (`InsightSoftwareConsortium/ITK`, branch `main`) | jobs with `conclusion == success` |
| Azure Pipelines | completed builds with `result == succeeded` (best-effort; skipped if not anonymously reachable) |

CDash is the primary authority for **which OS configurations are tested and
green** — it carries `operatingSystemName` plus `passedTestsCount` /
`failedTestsCount` per build. Important real-world caveat discovered against the
live dashboard: **ITK's CDash does not populate `compilerName`/`compilerVersion`**
(both are empty for every build), and the buildnames are CI run identifiers
(e.g. `Darwin-Build13399-main-Python`) that do not encode the toolchain. So:

- CDash reliably yields the **OS** dimension and the **tested-and-passing**
  gate, but usually **not the compiler**.
- The **compiler** dimension comes from **CI job names** (GitHub Actions, Azure),
  which are designed to name the toolchain (e.g. `build (ubuntu, gcc-13)`).

This is why the skill queries all three sources: CDash for OS coverage and
test-pass confirmation, CI for the compiler detail. When CDash rows have no
determinable compiler they are reported under `unclassified` (not dropped and
not guessed), so the gap is visible rather than papered over.

Azure is best-effort — many ITK Azure orgs are not anonymously queryable, and
the script degrades quietly when that is the case (it says so on stderr).

## How to run it

The work is done by `scripts/build_matrix.py`. Run it with `python3` (stdlib
only; the `gh` CLI is used for the GitHub source if present).

1. **Dry run first** to see the table and the source counts on stderr:
   ```bash
   python3 scripts/build_matrix.py --days 7
   ```
2. **Emit into the guide** and capture the raw evidence alongside it:
   ```bash
   python3 scripts/build_matrix.py --days 7 \
     --emit  <guide>/SoftwareGuide/Latex/Introduction/CompilerSupportMatrix.tex \
     --json-evidence <guide>/.devlocal/compiler-matrix-evidence.json
   ```
   `<guide>` is the ITKSoftwareGuide checkout root.
3. **Review the unclassified names.** CDash buildnames and CI job names are
   free-form, so the parser is heuristic. Any name it cannot map to an
   (OS, compiler) pair is reported on stderr and listed under `unclassified`
   in the evidence JSON — it is *not* silently dropped. If something important
   is unclassified, extend the `OS_PATTERNS` / `COMPILER_PATTERNS` tables in the
   script rather than hand-editing the generated table.

## Wiring it into the guide

The generated table is auto-generated content, so:

- The file begins with an `% AUTO-GENERATED ... DO NOT EDIT BY HAND` banner.
- Do not hand-edit `CompilerSupportMatrix.tex`; change the script and rerun.
- After the first good generation, uncomment the
  `\input{Introduction/CompilerSupportMatrix.tex}` line in
  `SoftwareGuide/Latex/Introduction/Installation.tex` in a reviewed commit.
- Because the table reflects a point-in-time snapshot, regenerate it as part of
  preparing each new edition (and whenever the CI matrix changes materially).

## Why heuristic parsing, and how to trust the output

CDash buildnames like `Linux-x86_64-gcc11` or `macOS-AppleClang` are conventions,
not a schema, so classification is pattern-based. The design choice that keeps
this honest is **never drop silently**: unclassifiable rows surface on stderr and
in the evidence JSON. That way a parser gap shows up as a missing-but-reported
configuration, not as a confident-looking table that quietly omits a platform.
Treat a non-empty `unclassified` list as a prompt to extend the patterns.

## Scope and guardrails

- This skill only *generates and writes* the table; committing it and
  uncommenting the `\input` are reviewed steps (the guide's edition work, not
  this skill). Follow the repo's no-unsolicited-PR and local-build rules.
- Network is required (CDash GraphQL; `gh` for Actions). With no network the
  script exits non-zero rather than emit an empty or fabricated table.
