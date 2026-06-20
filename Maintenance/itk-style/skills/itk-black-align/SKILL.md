---
name: itk-black-align
version: 0.1.0
purpose: Align a consumer Python project with the ITKv6 black style (black 24.2.0).
description: >
  Use when an ITK consumer project's Python formatting should match ITKv6: detect
  whether pyproject.toml has an ITKv6 [tool.black] config, add or update it
  (prompting before overriding a project's own different style), run the exact
  black version (via pixi/pipx/PATH), and wire up the ITKv6 pre-commit hook. This
  is a complement to the itk5to6 migration, not a migration step.
triggers:
  - "match ITKv6 black"
  - "align black with ITK"
  - "format Python like ITK"
  - "ITK black style"
  - "set up black pre-commit like ITK"
  - "itk-style-black"
user_invocable: true
cmd: Maintenance/itk-style/bin/align-black.sh
argument_hint: "doctor | check [repo] | add-config [--accept-restyle] [repo] | run [--apply] [repo] | hook [repo]"
contract:
  inputs: "A consumer git repo (defaults to CWD)."
  outputs: "Diagnosis, a staged [tool.black] in pyproject.toml, staged reformatted .py files, and a pre-commit hook snippet."
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "<repo>/pyproject.toml ([tool.black] section)"
      - "<repo> Python sources reformatted by black (only under run --apply)"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: true
  determinism: deterministic
  cache:
    has_cache: false
    cache_root: ""
    schema_version: 1
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 1
dependencies:
  skills: []
  external_tools:
    - git
    - "black 24.2.0 (via PATH, pixi, pipx, or uvx)"
    - "pre-commit (optional, for the hook)"
  python_packages: []
  scripts:
    - Maintenance/itk-style/bin/align-black.sh
    - Maintenance/itk-style/lib/style_common.sh
deployment:
  tier: project
  target_projects:
    - "ITK consumer Python projects (SimpleITK, ITK Python packages, remote modules, ...)"
  needs_loader_dir: false
  adapters:
    - claude-code
---

# itk-black-align

Make a consumer project's Python format identically to **ITKv6** (black **24.2.0**,
`line-length = 88`, `target-version py310`). Standalone hygiene task — runs
independently of an itk5to6 migration. Shares all common machinery with
`itk-clang-format-align` via `lib/style_common.sh`. The tool never commits,
branches, or opens PRs; it stages changes and prints a suggested commit message.

## Workflow (drive one step at a time; stop at the commit gate after each)

1. **Locate the right black.** `align-black.sh doctor` searches PATH → pixi →
   pipx → uvx for black 24.2.0. If none, provision with pixi (copy
   `assets/pixi-black.toml` to `pixi.toml`) or `pipx run black==24.2.0`. Insist
   on exactly 24.2.0 — other versions reflow differently.

2. **Diagnose.** `align-black.sh check [repo]` reports whether pyproject.toml has
   the ITKv6 `[tool.black]`, whether a runner is available, and how many files
   would change (exit 2 if action needed). For an existing `[tool.black]` that
   differs (e.g. a different `line-length`), it reports it as a *different project
   style*.

3. **Add / update the config.** `align-black.sh add-config [repo]`:
   - **absent** → adds the ITKv6 `[tool.black]` to pyproject.toml and stages it.
   - **already ITKv6** → no-op.
   - **different project style** → the tool REFUSES and explains that adopting
     ITK's style is a significant restyle. Confirm with the developer; only then
     re-run with `add-config --accept-restyle [repo]` to replace it.
   Surface the printed commit message and STOP for the human to commit.

4. **Reformat.** `align-black.sh run [repo]` (dry-run list) then, on agreement,
   `align-black.sh run --apply [repo]` (reformat + stage). Keep it a separate
   `STYLE:` commit. Surface the message and STOP.

5. **Instrument pre-commit.** `align-black.sh hook [repo]` prints the exact ITKv6
   hook (`psf/black@24.2.0`, `--target-version py310`, excluding build/ThirdParty/
   Data). Prompt the developer to merge it, then `pre-commit install` and
   `pre-commit run black --all-files`.

## Hard constraints

- Never commit, never branch, never open a PR — stage and suggest only.
- Only `run --apply` modifies source; default is a dry-run diff.
- Never overwrite a project's own `[tool.black]` without `--accept-restyle`.
- Insist on black 24.2.0 — warn loudly on any other version.
