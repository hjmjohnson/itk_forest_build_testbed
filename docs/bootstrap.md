# Bootstrap on a fresh machine

The repo is a *kit* — scripts + pixi config + docs. Cloning gives you the kit;
`pixi run checkout` materializes the source trees and builds under
`build_forest/`.

```bash
git clone git@github.com:hjmjohnson/itk_forest_build_testbed.git ~/src/itk_forest_build_testbed
cd ~/src/itk_forest_build_testbed

pixi run checkout        # clone/worktree every consumer + remote module
pixi run build-ITK       # build the ITK under test (default ITK_REF=origin/main)
pixi run build-elastix   # -> ITK, then elastix (any consumer pulls ITK first)
```

## Prerequisites

- **pixi** (provides cmake/ninja/ccache/compilers/fftw/qt5 — see `pixi.toml`).
- **macOS Slicer only:** a real Qt6 at `~/Qt/<ver>/macos` (default `6.9.1`).
  See [slicer-macos.md](slicer-macos.md).
- **Windows:** Visual Studio 2022 (or Build Tools) with the *Desktop development
  with C++* workload — MSVC is the only ABI Slicer and Qt's official binaries
  link against — plus Git for Windows (supplies the bash the engine runs under).
  For Slicer, Qt6 `msvc2022_64` from the official installer under `C:\Qt`.
  Forests default to `C:\S-<suffix>` rather than the repo, for MAX_PATH
  headroom. See [windows.md](windows.md).

## Node-specific config

On first run the engine generates `config.sh` (git-ignored) from the tracked
`config.json.in`, resolving machine paths (Qt6, ccache, src root, …) for this
node. Regenerate with `pixi run config`. Details in [config.md](config.md).

## Relocation / env overrides

Env vars override `config.sh`, which overrides built-in defaults. If the kit
lives elsewhere, export to match (or edit `config.sh`):

| Var | Default | Meaning |
|---|---|---|
| `SRC_ROOT` | `~/src` | optional clone-speedup source (`--reference-if-able`) |
| `FOREST_GIT_REPOS` | `$TESTBED/forest_git_repos` | central full clones (worktree origin) |
| `TESTBED` | repo root (parent of `bin/`) | the kit root |
| `FOREST` | `$TESTBED/build_forest` | per-forest worktrees + build trees |
| `ITK_REF` | `origin/main` | ITK ref under test (PR/branch/tag/SHA) |
| `ITK_PR_REMOTE` | `origin` | remote to fetch `pr/NNNN` shorthand from |
| `JOBS` | `nproc` | parallel build jobs |
| `HEAVY` | `0` | `1` includes CUDA/Java/wasm remote modules |

`checkout` makes a **full clone** of each repo under `forest_git_repos/<name>`
(reusing `~/src/<name>` objects via `--reference-if-able --dissociate` when
present, purely as a download speedup), then adds each `build_forest/<name>` as
a **git worktree** off that clone. No shallow clones.
