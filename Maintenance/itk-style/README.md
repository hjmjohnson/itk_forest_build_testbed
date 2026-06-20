# itk-style — align a project with the ITKv6 code style

Small, self-contained helpers that bring an **ITK consumer** project's formatting
in line with **ITKv6**:

| Tool | Formatter | Pinned version | Config |
|------|-----------|----------------|--------|
| `align-clang-format.sh` | clang-format (C/C++) | **19.1.7** | `.clang-format` |
| `align-black.sh`        | black (Python)       | **24.2.0** | `[tool.black]` in `pyproject.toml` |

These are a *complement* to the `itk5to6` migration toolkit, **not** a migration
step — code style is a common thing to fix alongside a version bump, but it is
orthogonal to the API changes. Nothing here commits, branches, or opens a PR: it
edits + stages and prints a suggested commit message for you to review and commit.

## Shared core

Both tools are thin plug-ins over **`lib/style_common.sh`**, which provides the
common behavior: git work-tree resolution, version-pinned runner discovery
(PATH → pixi → pipx → uvx), in-scope file discovery, dry-run diff counting,
staging, suggested commit messages, and the `doctor`/`check`/`add-config`/`run`/
`hook` subcommands. Each plug-in only declares what differs (binary, version,
file globs, exclude regex, config detection/classification, diff/apply commands).
Adding a third formatter is a ~40-line plug-in.

```
Maintenance/itk-style/
  lib/style_common.sh              # shared scaffold (the common core)
  bin/align-clang-format.sh        # clang-format plug-in
  bin/align-black.sh               # black plug-in
  assets/
    itkv6.clang-format             # vendored snapshot of ITK's .clang-format (19.1.7)
    black.pyproject.snippet.toml   # ITKv6 [tool.black] block
    pre-commit-clang-format.snippet.yaml
    pre-commit-black.snippet.yaml
    pixi-clang-format.toml         # provision clang-format 19.1.7 via conda-forge/pixi
    pixi-black.toml                # provision black 24.2.0 via conda-forge/pixi
  skills/itk-clang-format-align/   # agent-skill wrappers
  skills/itk-black-align/
  tests/                           # binary-independent bash tests
```

## Usage

Identical subcommands for both tools (`repo` defaults to CWD; must be a git work tree):

```bash
TOOL=Maintenance/itk-style/bin/align-clang-format.sh   # or .../align-black.sh

bash $TOOL doctor                       # find the pinned formatter (PATH/pixi/pipx/uvx)
bash $TOOL check   [repo]               # diagnose: config present? formatting drift?
bash $TOOL add-config [--accept-restyle] [repo]   # add/update the ITKv6 config + stage
bash $TOOL run     [repo]               # dry-run: list files that would change
bash $TOOL run --apply [repo]          # reformat + stage (keep as its own STYLE: commit)
bash $TOOL hook    [repo]               # print the ITKv6 pre-commit hook snippet to add
```

## Existing config — classify before clobbering

`add-config` never blindly overwrites a project's style. It classifies the
existing config and acts accordingly:

| Existing config | Action |
|-----------------|--------|
| **none** | add the ITKv6 config |
| **already ITKv6** | no-op |
| **outdated ITK** (ITK-flavored config for a different clang-format version) | **update** to the ITKv6 baseline |
| **different project style** (a non-ITK config, e.g. a different `BasedOnStyle` / `line-length`) | **refuse** and explain that adopting ITK's style is a significant whole-project restyle; replace only when re-run with `--accept-restyle` |

`check` reports the same classification so you know which case you are in before
acting.

## Formatter version (why pinned exactly)

ITKv6's `.clang-format` is valid only for **clang-format 19.1.7**, and ITK pins
**black 24.2.0** — a different version reflows code differently, so "formatted"
would mean something else. The tools refuse any other version. Provision the
right one:

- **pixi (recommended):** `cp assets/pixi-clang-format.toml ./pixi.toml && pixi run clang-format --version` (and likewise `pixi-black.toml`)
- **pipx:** `pipx run clang-format==19.1.7` / `pipx run black==24.2.0`
- **pre-commit:** the pinned hooks auto-install the exact versions.

## Scope (mirrors ITK's pre-commit hooks)

- clang-format: `\.(c|cc|h|cxx|hxx)$`, excluding `ThirdParty/`, `Data/`, `pocketfft_hdronly.h`.
- black: `*.py`, excluding `ThirdParty/`, `Data/`, and any `build` path.

## Refreshing the vendored configs

`assets/itkv6.clang-format` is a snapshot of ITK's `.clang-format`; refresh with
`cp <ITK>/.clang-format assets/itkv6.clang-format` (and bump the pinned versions
in the plug-ins / snippets if ITK changes them).
