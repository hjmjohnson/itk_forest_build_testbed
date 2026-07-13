---
title: TITLE OF YOUR ARTICLE
subtitle: Optional subtitle
abstract: |
  Replace this with your abstract. State the problem, the method you
  implemented (in ITK or otherwise), and the result. Note explicitly that the
  paper is accompanied by source code, input data, parameters, and output data
  so that readers can reproduce the reported results -- this reproducibility
  statement is expected by the Insight Journal.

keywords:
  - reproducible research
  - image processing
  - ITK

abbreviations:
  ITK: Insight Toolkit
  FAIR: Findable, Accessible, Interoperable, and Reusable
---

## Introduction

Motivate the problem and state your contribution. Cite prior work like
{cite}`Popper2002`.

## Methods

Describe the algorithm. Reference your accompanying implementation in `src/`.

Inline code for method names reads like `SetNumberOfIterations()`, and fenced
blocks render full snippets:

```cpp
using ImageType = itk::Image<unsigned char, 3>;
auto image = ImageType::New();
```

A figure (place assets under `docs/assets/`; generate them with a committed
script in `scripts/`, never hand-place a binary):

```{figure} ./assets/fig_pipeline.png
:name: fig-pipeline
:width: 80%

Caption describing your pipeline.
```

An equation you can cross-reference:

```{math}
:label: eqn-example
E = \sum_{i} \left( f(x_i) - y_i \right)^2
```

A table that you can cross-reference (use the `{table}` directive wrapping a
Markdown table -- NOT `{list-table}`, which the lapreprint-typst template does
not label for Typst PDF cross-references):

```{table} Result summary. Every number here traces to a CSV in `data/`.
:label: tbl-results

| Method | Metric | Value |
|--------|--------|-------|
| A      | RMSE   | 0.012 |
| B      | RMSE   | 0.011 |
```

Refer back to {numref}`fig-pipeline`, {eq}`eqn-example`, and {numref}`tbl-results`
anywhere in the text.

## Results

Report results. Point at the exact data in `data/` and the parameters used so a
reviewer running `pixi run verify-meca` reproduces them. Every quantitative
claim must trace to a committed CSV.

## Discussion

Interpret, note limitations, and outline future work.

## Reproducibility

Source code: `src/` (built against ITK via `pixi run -e cxx build-src`).
Input data: `data/`. Parameters and expected outputs are included in the bundle
so the full result set regenerates from `pixi run build`.

```{bibliography}
```
