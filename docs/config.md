# Node-specific config

Machine-specific build knobs live in **`config.sh`** (git-ignored), generated
from the tracked template **`config.json.in`** by `bin/config.py`. The engine
`source`s `config.sh` on every run, auto-generating it on first use.

## Precedence

```
environment variable  >  config.sh  >  built-in default
```

Each `config.sh` line is `: "${KEY:=default}"`, so a `KEY=...` set in the
environment before invocation always wins. Example:

```bash
QT6_DIR=/opt/Qt/6.10/macos pixi run build-Slicer   # one-off override
```

## Keys

| Key | Maps to | Meaning |
|---|---|---|
| `QT6_DIR` | `SLICER_QT_PREFIX` | Qt6 prefix for the Slicer SuperBuild (must contain `lib/cmake/Qt6`). **Required** for Slicer. |
| `BUILD_FOREST_ROOT` | `FOREST` | Artifact dir. Default `build_forest`; relative → repo root, absolute → as-is. |
| `SRC_ROOT` | `SRC_ROOT` | Canonical source repos + vxl (for worktree reuse). |
| `VXL_SRC` | `VXL_SRC` | vxl source under test. |
| `CCACHE_DIR` | `CCACHE_DIR` | ccache cache dir. |
| `JOBS` | `JOBS` | Parallel jobs; empty → auto-detect. |
| `CC` / `CXX` | `CC` / `CXX` | Compilers; empty → auto. |
| `HEAVY` | `HEAVY` | `1` includes CUDA/Java/wasm remotes. |

## How resolution works

`config.json.in` declares each key as either:

- **`candidates`** — a list of paths (globs allowed); the generator picks the
  first that exists. An optional **`verify`** sub-path must also exist (e.g.
  `QT6_DIR` requires `lib/cmake/Qt6`). If `required: true` and none match, the
  key is written as a commented placeholder and `config.py` warns — **set it
  manually** in `config.sh`.
- **`value`** — a literal default (env-expanded), no existence check.

## Commands

```bash
pixi run config                              # regenerate config.sh (--force)
python3 bin/config.py generate               # generate if missing (no clobber)
python3 bin/config.py generate --force       # overwrite
python3 bin/config.py --check                # exit 1 if a required key is unresolved
```

To add a knob: add it to `config.json.in`, run `pixi run config`, and consume
`$KEY` in `bin/setup-vxl-downstream-testbed.sh` (it's already sourced).
