---
name: itk-whitepaper
version: 1.0.0
purpose: Scaffold and manage an Insight Journal white paper in Hans Johnson's house style (MyST Markdown + Pixi + MECA), with reproducibility rules enforced and the submission flow documented.
description: >-
  Scaffold and drive an Insight Journal white paper the way Hans J. Johnson
  writes them: a MyST Markdown + Pixi project that builds a Typst PDF and submits
  a MECA archive, bootstrapped from InsightSoftwareConsortium/InsightJournalTemplate
  with pre-filled myst.yml and docs/index.md starters (author, Apache-2.0 code /
  CC-BY-4.0 content, IJ venue). Enforces the house reproducibility rules: every
  figure/table comes from a committed script in scripts/ reading a committed CSV
  in data/, every numeric claim traces to data/, prose reports honestly (parity
  is parity, not a win), and build artifacts (_build/ exports/ .pixi/) are never
  committed. Use this whenever the user wants to start, structure, build, or
  submit an ITK / Insight Journal paper or white paper -- including "write a
  whitepaper", "Insight Journal submission", "scaffold a paper", "build the
  manuscript PDF", "make the MECA archive", or turning a .devlocal findings
  report into a publishable draft -- even if they don't name the template or MyST.
triggers:
  - itk-whitepaper
  - /itk-whitepaper
  - insight journal paper
  - insight journal submission
  - scaffold a whitepaper
  - build the manuscript pdf
  - make the meca archive
user_invocable: true
cmd: false
argument_hint: "new <dir> | build | submit | (or describe the paper)"
contract:
  inputs:
    - argument
  outputs:
    - files
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - <paper-dir>/myst.yml
      - <paper-dir>/docs/**
      - <paper-dir>/data/**
      - <paper-dir>/scripts/**
      - <paper-dir>/src/**
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: true
    derivation_version: 1
dependencies:
  skills: []
  external_tools:
    - git
    - pixi
    - myst
    - typst
  python_packages:
    - matplotlib
  scripts:
    - new-paper.sh
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# Insight Journal White Paper

Scaffold and drive an Insight Journal (IJ) paper in Hans Johnson's house style.
The output is a **MyST Markdown + Pixi** project that builds a Typst PDF and
submits a **MECA archive** (not a PDF upload). The reference implementation this
skill is distilled from is `~/src/ITK/.devlocal/whitepaper/`.

The journal uses **open peer review and reviewers re-run your bundle**, so the
whole skill is organized around one idea: *every claim in the prose must be
mechanically reproducible from committed code and data.* That constraint is not
bureaucracy — it is what makes the paper survive review.

## Pick the mode

| The user wants to… | Do this |
|---|---|
| Start a new paper | **Scaffold** (below) |
| Add results / figures / sections | **Author** (below) |
| Produce the PDF | **Build** (below) |
| Package and submit | **Submit** (read `references/insight-journal-submission.md`) |

For anything about the submission mechanics (template tasks, MECA flow, Typst
cross-reference gotchas), read `references/insight-journal-submission.md` rather
than guessing — it is the distilled, verified recipe.

## Scaffold a new paper

Run the bundled bootstrap, which clones the official template, strips its git
history, drops in the pre-filled starters, and writes a build-artifact
`.gitignore`:

```bash
scripts/new-paper.sh <paper-dir>
```

Then fill the placeholders the script printed: title, ORCID, repo URL, and the
IJ id (left as `insight-journal-000` until the submission is created on the
site). The starters are `assets/myst.yml` and `assets/index.md`; copy any
existing findings report (e.g. a `.devlocal/*-report.md`) into the Results /
Discussion prose rather than starting from a blank page.

If the user prefers to wire it by hand, the directory contract is:

```
docs/index.md        manuscript (MyST frontmatter + body)
docs/references.bib   bibliography
docs/assets/          figures — only ever written by a script in scripts/
data/                 CSVs (+ raw stdout) behind every quantitative claim
scripts/              figure-gen + data-regen scripts (committed)
src/                  accompanying C++ built against ITK
myst.yml              project config (author, exports, venue, licenses)
```

## The house rules (why they exist)

These are the rules that keep an IJ paper honest and reproducible. Hold to them;
they are the difference between a paper that survives open review and one that
gets bounced for unreproducible numbers.

1. **Figures and tables are reproducible artifacts, never hand-placed binaries.**
   Anything in `docs/assets/` must have the script that generated it committed in
   `scripts/`. A reviewer (or future you) regenerates the figure from data, not
   from memory.
2. **`data/` is the single source for every figure and quantitative claim.** The
   figure script reads committed CSVs; it never re-runs benchmarks. Regenerating
   measurements is a separate, explicit step (a `scripts/regenerate_data.sh`),
   because measurement and presentation must not be entangled.
3. **Report honestly.** If the result is parity (e.g. 0.98–1.03×), say parity —
   not a speed win. Open review re-runs your bundle; overclaiming is caught and
   costs credibility. Every numeric sentence should trace to a CSV.
4. **State the measurement environment** next to any timing (CPU/arch, compiler,
   build type, thread count). Numbers differ across hardware; an unlabeled timing
   is not reproducible. Run timings single-threaded on an idle machine.
5. **Never commit build artifacts.** `_build/`, `_deps/`, `exports/`, `build/`,
   `.pixi/`, `*.meca.zip` stay git-ignored. Stage files explicitly (`git add
   <path>`), never `git add -A`, so generated trees don't leak in.

## Author

- Prose lives in `docs/index.md`; citations go in `docs/references.bib` and are
  referenced with `{cite}\`Key\``.
- New figure → write/extend a script in `scripts/` that reads `data/*.csv` and
  writes `docs/assets/fig_*.png`. Add the CSV first; the script second; the
  `{figure}` directive third.
- Tables that need a cross-reference use the `{table}` directive around a
  Markdown table with `:label:` — **not** `{list-table}` (see the submission
  reference for why it breaks Typst labels).
- Keep an `outline.md` (section plan) and a `findings.md` (the quotable,
  evidence-pointed findings) as working files if the paper is large; they are the
  source the Results/Discussion prose is written from.

## Build the manuscript PDF

```bash
# Preferred (template environment): Typst PDF, no LaTeX needed.
pixi run build-pdf            # -> exports/manuscript.pdf
# Or directly with the MyST + Typst CLIs (myst >= 1.10, typst installed):
myst build --typst
```

Live preview while writing: `pixi run start`.

## Submit (MECA)

Read `references/insight-journal-submission.md` for the full flow. The shape:
create the submission on insight-journal.org to get the id → set
`myst.yml:project.id` → **`pixi run verify-meca` (must reproduce cleanly)** →
`pixi run build-meca` → upload `exports/article.meca.zip`. Always run
`verify-meca` before `build-meca`: it unpacks and rebuilds the bundle the same
way a reviewer will, and catches an unreproducible result before submission
instead of after.

Per the no-unsolicited-publication norm, treat the actual on-site upload as a
human step — scaffold, build, and verify, then hand the verified `.meca.zip` to
the user.
