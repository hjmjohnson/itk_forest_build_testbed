# Maintenance — ITK-consumer maintenance toolkits

Self-contained tooling that helps a project that *consumes* ITK move cleanly onto
**ITKv6**. Two independent toolkits live here; each has its own README with full
usage.

| Toolkit | Purpose | Entry point |
|---------|---------|-------------|
| [`itk5to6/`](itk5to6/README.md) | Semi-automated **ITKv5.4.6 → v6.1 API migration**, one task at a time | `itk5to6/itk-migrate.sh` |
| [`itk-style/`](itk-style/README.md) | Align a project with the **ITKv6 code style** (clang-format, black) | `itk-style/bin/align-clang-format.sh`, `itk-style/bin/align-black.sh` |

These solve **orthogonal** problems: `itk5to6` changes *API usage* to compile and
run against ITKv6; `itk-style` changes *formatting* to match ITK. Style is a
common thing to fix alongside a version bump, but it is **not** part of the
migration — run the two independently.

## Shared philosophy

Both toolkits follow the same contract:

- **One task at a time.** Each step is a single, reviewable change with a
  suggested commit message that explains *why* it is beneficial.
- **Never commit, branch, or open a PR.** The tools edit and `git add`; the
  human reviews, validates (pre-commit), and commits. (Per the project's
  no-unsolicited-PR rule.)
- **One clean commit per task.** An editing task refuses to run on a dirty
  working tree — commit or stash existing modifications first — so its staged
  output is an isolated, single committable change. `itk-migrate.sh level`
  stops after the first task that stages changes. Override with `--allow-dirty`
  (`MC_ALLOW_DIRTY=1` / `STYLE_ALLOW_DIRTY=1`).
- **Dry-run / safety first.** Destructive or wide-reaching actions default to a
  dry-run and require an explicit flag to apply; ambiguous cases are reported
  for human judgement, never silently changed.
- **Report relative to the primary branch.** Both toolkits fetch the primary
  repo's primary branch (`origin/HEAD` → `origin/main`) and report the checkout
  against it, warning loudly when it is behind — updates are only valid against
  the current primary branch. Flags: `--no-fetch` skips the fetch
  (`MC_NO_FETCH=1` / `STYLE_NO_FETCH=1`); `--no-base-check` skips the report
  entirely (`MC_NO_BASE_CHECK=1` / `STYLE_NO_BASE_CHECK=1`) when intentionally
  working off-primary.
- **Self-contained & portable.** POSIX-leaning bash + a little Python; portable
  across macOS (gsed) and Linux. Pinned external-tool versions where exactness
  matters (clang-format 19.1.7, black 24.2.0).
- **`ThirdParty/` and vendored data are always excluded.**
- **Tested.** Each toolkit ships fixture-based bash tests runnable with no
  external framework: `bash <toolkit>/tests/run_tests.sh`.

## itk5to6 — API migration

The recommended path to v6.1 funnels through **ITKv5.4.6**:

```
ITKv4 code ──[prep-v5]──▶ idiomatic on v5.4.6 ──[drop-itk-before-v5]──▶ v5.4.6 floor
                                                                            │
                                              [migrate-v6: L1 → L2 → L3]────┤
                                                                            ▼
                                  ──[drop-itk-v5]──▶ ITKv6.1-only, no compat scaffolding
```

Leveled conversions run mandatory changes first, then opt-in
`ITK_LEGACY_REMOVE` (L2) and `ITK_FUTURE_LEGACY_REMOVE` (L3) instrumentation;
the `drop-*` scripts prune dead `#if ITK_VERSION_MAJOR …` / feature-guard
branches once a version floor is committed to. Driver:
`itk-migrate.sh list | status | run <task> | level <L>`. See
[`itk5to6/README.md`](itk5to6/README.md).

## itk-style — code-style alignment

Two thin plug-ins over a shared core (`itk-style/lib/style_common.sh`):
`align-clang-format.sh` (C/C++, clang-format 19.1.7) and `align-black.sh`
(Python, black 24.2.0). Both expose `doctor | check | add-config | run | hook`,
provision the pinned formatter (PATH → pixi → pipx → uvx), and **classify an
existing config before overwriting** (none → add, outdated-ITK → update,
different project style → refuse without `--accept-restyle`). See
[`itk-style/README.md`](itk-style/README.md).

## Destination

This tree is staged here for development and is intended to move, as a single
PR, into ITK's `Utilities/Maintenance/` ahead of the ITK v6.1 release. When
upstreamed, the `itk5to6` toolkit supersedes the prototype
`Utilities/Maintenance/migrate-itk6-code-recommendations.sh`.
