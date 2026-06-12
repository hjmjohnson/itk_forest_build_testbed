# Bootstrap on a fresh machine

The repo is a *kit* — scripts + pixi config + docs. Cloning gives you the kit;
`pixi run checkout` materializes the source trees and builds under
`build_forest/`.

```bash
git clone git@github.com:hjmjohnson/itk_forest_build_testbed.git ~/src/vxl_downstream_tests
cd ~/src/vxl_downstream_tests

# The vnl source under test must exist at ~/src/vxl (the ITK fork of VXL):
git clone -b for/itk-vxl-master https://github.com/InsightSoftwareConsortium/vxl ~/src/vxl

pixi run checkout        # clone/worktree every consumer + remote module
pixi run build-ITK       # build ITK carrying the vendored/synced vnl
pixi run build-elastix   # -> ITK, then elastix (any consumer pulls ITK first)
```

## Prerequisites

- **pixi** (provides cmake/ninja/ccache/compilers/fftw/qt5 — see `pixi.toml`).
- **macOS Slicer only:** a real Qt6 at `~/Qt/<ver>/macos` (default `6.9.1`).
  See [slicer-macos.md](slicer-macos.md).

## Node-specific config

On first run the engine generates `config.sh` (git-ignored) from the tracked
`config.json.in`, resolving machine paths (Qt6, ccache, src root, …) for this
node. Regenerate with `pixi run config`. Details in [config.md](config.md).

## Relocation / env overrides

Env vars override `config.sh`, which overrides built-in defaults. If the kit or
vxl source live elsewhere, export to match (or edit `config.sh`):

| Var | Default | Meaning |
|---|---|---|
| `SRC_ROOT` | `~/src` | where canonical source repos + vxl live |
| `TESTBED` | repo root (parent of `bin/`) | the kit root |
| `FOREST` | `$TESTBED/build_forest` | source checkouts + build trees |
| `VXL_SRC` | `$SRC_ROOT/vxl` | the vnl source under test |
| `ITK_REF` | (script default) | ITK branch the testbed builds |
| `JOBS` | `nproc` | parallel build jobs |
| `HEAVY` | `0` | `1` includes CUDA/Java/wasm remote modules |

`checkout` prefers a **git worktree** of `~/src/<name>` (branch `<name>-vxl-master`)
when that canonical repo exists, else a shallow clone of the upstream URL.
