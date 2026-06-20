---
name: itk-clang-format-align
version: 0.1.0
purpose: Align a consumer C++ project with the ITKv6 clang-format style (clang-format 19.1.7).
description: >
  Use when an ITK consumer project's C++ formatting should match ITKv6: detect
  whether a .clang-format exists and matches the ITKv6 (clang-format 19.1.7)
  style, add the canonical .clang-format if missing, run the exact clang-format
  version (via pixi/pipx/PATH), and wire up the ITKv6 pre-commit hook. This is a
  complement to the itk5to6 migration, not a migration step.
triggers:
  - "match ITKv6 clang-format"
  - "align clang-format with ITK"
  - "add an ITK .clang-format"
  - "format this project like ITK"
  - "ITK clang-format style"
  - "set up clang-format pre-commit like ITK"
user_invocable: true
cmd: Maintenance/itk-style/bin/align-clang-format.sh
argument_hint: "doctor | check [repo] | add-config [repo] | run [--apply] [repo] | hook [repo]"
contract:
  inputs: "A consumer git repo (defaults to CWD)."
  outputs: "Diagnosis, a staged .clang-format, staged reformatted files, and a pre-commit hook snippet."
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "<repo>/.clang-format"
      - "<repo> C/C++ sources reformatted by clang-format (only under run --apply)"
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
    - "clang-format 19.1.7 (via PATH, pixi, pipx, or uvx)"
    - "pre-commit (optional, for the hook)"
  python_packages: []
  scripts:
    - Maintenance/itk-style/bin/align-clang-format.sh
deployment:
  tier: project
  target_projects:
    - "ITK consumer C++ projects (ANTs, BRAINSTools, elastix, SimpleITK, remote modules, ...)"
  needs_loader_dir: false
  adapters:
    - claude-code
---

# itk-clang-format-align

Make a consumer project format identically to **ITKv6** (clang-format **19.1.7**
exactly). Standalone hygiene task — run it alongside, but independently of, an
itk5to6 migration. The tool never commits, branches, or opens PRs; it stages
changes and prints a suggested commit message for the human to review and commit.

## Workflow (drive one step at a time; stop at the commit gate after each)

1. **Locate the right clang-format.** Run `align-clang-format.sh doctor`. It
   searches PATH → pixi → pipx → uvx for clang-format 19.1.7. If none is found,
   provision one with pixi (preferred): copy `assets/pixi-clang-format.toml` to a
   `pixi.toml` and use `pixi run clang-format`, or fall back to
   `pipx run clang-format==19.1.7`. Confirm the version is exactly 19.1.7 — a
   different version reflows code differently and defeats the purpose.

2. **Diagnose.** Run `align-clang-format.sh check [repo]`. It reports:
   whether `.clang-format` exists and is pinned to 19.1.7, whether a runner is
   available, and how many files would change. Exit 2 means action is needed.

3. **Add the config if missing or divergent.** If `check` says the
   `.clang-format` is missing or not ITKv6, run `align-clang-format.sh
   add-config [repo]`. It writes the vendored ITKv6 `.clang-format` and stages
   it. If the project already had a different `.clang-format`, confirm with the
   developer before overwriting (the tool warns and overwrites; the diff is
   theirs to review). Surface the printed commit message and STOP for the human
   to commit.

4. **Reformat.** Run `align-clang-format.sh run [repo]` first (dry-run: lists the
   files that would change). When the developer agrees, run
   `align-clang-format.sh run --apply [repo]` to reformat and stage. Keep this a
   separate, self-contained `STYLE:` commit (no functional changes) so review is
   trivial. Surface the suggested commit message and STOP.

5. **Instrument pre-commit.** Run `align-clang-format.sh hook [repo]` to print
   the exact ITKv6 hook (`mirrors-clang-format@v19.1.7`, `--style=file`, scoped
   to `\.(c|cc|h|cxx|hxx)$` excluding ThirdParty/Data/pocketfft). Prompt the
   developer to merge it into their `.pre-commit-config.yaml`, then
   `pre-commit install` and `pre-commit run clang-format --all-files`. Using the
   pinned hook means contributors get clang-format 19.1.7 auto-provisioned by
   pre-commit, with no local install required.

## Hard constraints

- Never commit, never branch, never open a PR — stage and suggest only.
- Only `run --apply` modifies source; default is a dry-run diff.
- Match ITK's hook scope exactly; never reformat ThirdParty/Data/pocketfft.
- Insist on clang-format 19.1.7 — warn loudly on any other version.
