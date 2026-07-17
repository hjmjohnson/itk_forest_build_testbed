# Integration branches — testing cross-project fixes while upstream reviews

Most of what this testbed uncovers is a defect **at the intersection of projects
we do not fully control**: an ITK change that breaks a consumer, a consumer whose
build glue assumes one ITK version, a shared dependency with a latent bug. The
fix becomes one or more upstream PRs — and those can take **months** to review.
We must keep testing the *fixed* state in the meantime. Integration branches are
how.

This is expected to be the **most prevalent pattern** in this repo. Treat it as a
first-class convention, not an ad-hoc per-case hack.

## The shape

For each consumer we have an in-flight fix for, keep a branch named
**`itk-forest-integration`** on our fork:

    itk-forest-integration  =  upstream/main
                             +  the in-flight fix(es) for this repo
                             +  testing-only wiring that must NOT go upstream
                                (e.g. a dependency pin repointed at our fork)

The forest consumes it through a **per-forest scenario override** in
`versions.toml`; the `[components.<Name>]` entry stays on the true upstream, so
removing the scenario restores upstream-tracking automatically.

```toml
[components.Foo]                       # unchanged: the post-merge / upstream state
url = "https://github.com/UPSTREAM/Foo.git"
ref = "origin/main"

[scenarios.itk-main.Foo]               # the override: this forest tests the fix
url    = "https://github.com/hjmjohnson/Foo.git"
branch = "itk-forest-integration"
```

## Two branches, not one: PR branch vs integration branch

Keep them **separate**:

- **PR branch** (e.g. `fix-itk5-target-portability`) — exactly the fix, clean, for
  upstream review. Nothing forest-specific.
- **`itk-forest-integration`** — the PR fix **plus** anything needed to test it
  here that must never be proposed upstream: most importantly a **dependency pin
  repointed at our fork**. Example: ITKTractographyTRX pins trx-cpp by
  repo+SHA, so its integration branch bumps `TRX_CPP_GIT_TAG` to
  `hjmjohnson/trx-cpp@itk-forest-integration`. That bump is a testing artifact,
  not part of the upstream PR.

When several fixes for one repo are in flight, they accumulate on the single
`itk-forest-integration` branch.

## Per-forest, on purpose

Scenario overrides are keyed by forest suffix because **a fix can be correct for
one forest and wrong for another**. The canonical case is BRAINSTools#616: it
regenerates MIH baselines to match ITK's *corrected* JointHistogramMutualInformation
metric (ITK#6569). Those baselines pass on ITK 6.0.0 and **fail** on ITK 5.4.6,
whose metric still produces the old answer. So it is wired for `itk-main` only;
`itk-release-5.4` falls through to the upstream 2018 baselines that still pass
there. One override, not two — the per-forest keying does the rest.

A fix incompatible with a forest is simply **not wired into that forest**.

## Registry of active integration branches

Keep this current. When a PR merges, do the retirement steps and delete its row.

| consumer | forests wired | fork branch | upstream PR(s) | retire when |
|---|---|---|---|---|
| TractographyTRX | itk-main, itk-release-5.4 | `hjmjohnson/ITKTractographyTRX@itk-forest-integration` | tee-ar-ex/ITKTractographyTRX#30 **and** tee-ar-ex/trx-cpp#52 | both merge; bump module `TRX_CPP_GIT_TAG` to a merged trx-cpp SHA; drop both scenarios |
| trx-cpp *(via TractographyTRX pin)* | — (fetched by the module) | `hjmjohnson/trx-cpp@itk-forest-integration` (11d0c81) | tee-ar-ex/trx-cpp#52 | #52 merges |
| BRAINSTools | itk-main only | `hjmjohnson/BRAINSTools@itk-forest-integration` | BRAINSia/BRAINSTools#616 | #616 merges; drop the itk-main scenario |
| ANTs | non-itkv5 forests | `hjmjohnson/pin-seed-affinescalemasks` *(pre-convention; wired via `components.ANTs.ref` + `subbuild.ANTs.fork_ref`, not a scenario)* | ANTsX/ANTs#2008 | #2008 merges; restore `components.ANTs.ref = origin/main`, delete `subbuild.ANTs.fork_ref` |

ITK#6655 (NrrdIO `sampleIO.c`) needed no integration branch — it **merged** into
`upstream/main`, so every forest tracking main already has it.

## Retiring one (do not skip)

When an upstream PR merges:

1. Remove its `[scenarios.<suffix>.<Name>]` block(s) from `versions.toml`.
2. If the integration branch carried a **dependency pin repointed at our fork**,
   bump that pin to the merged upstream SHA (or delete the override that set it).
3. Re-checkout the affected consumer so the forest returns to upstream.
4. Delete its row from the registry table above.
5. Leave the `itk-forest-integration` fork branch in place until the merge is
   confirmed reachable, then it can be deleted.

Skipping step 1/2 leaves a forest silently pinned to a fork after upstream has the
fix — the failure mode this registry exists to prevent.

## Gotchas (all hit at least once)

- **`remote`-kind modules drop the component `ref`.** `config.py remotes` emits
  only `url|heavy`, so setting `[components.<Name>].ref` to a fork branch does
  nothing for a remote — it checks out the fork's default branch. Use a scenario
  override, which carries `url|branch` and is honored for both consumers and
  remotes.
- **Quote dotted forest suffixes.** `[scenarios.itk-release-5.4.Foo]` parses the
  dot in `5.4` as a key separator and silently never matches. Write
  `["scenarios"."itk-release-5.4"."Foo"]`.
- **Interdependent pins.** If repo A pins repo B and both have in-flight fixes,
  A's integration branch must bump its pin to B's integration branch — neither
  fix alone makes the forest green (the TractographyTRX ⇄ trx-cpp case).
- **Verify through the engine, not just a hand build.** Run
  `FOREST_REFERENCE_SUFFIX=<suffix> pixi run build-<Name>` and confirm the
  scenario line fires and the artifact lands — that proves the checkout plumbing,
  not just the fix.

## Related

- `versions.toml` — `[components.*]` (upstream baseline) + `[scenarios.<suffix>.*]` (overrides)
- `bin/config.py scenario <suffix> <Component>` — resolve the override (`url|branch`)
- `bin/setup-itk-downstream-testbed.sh` `checkout_one()` — the scenario-override checkout path
- `docs/slicer-itk-policy.md` — a related per-forest override (Slicer's vendored ITK)
