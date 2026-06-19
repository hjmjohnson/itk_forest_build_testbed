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
| `SRC_ROOT` | `SRC_ROOT` | Canonical source repos (for worktree reuse). |
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
`$KEY` in `bin/setup-itk-downstream-testbed.sh` (it's already sourced).

## `versions.toml` — the build-version source of truth (tracked, portable)

`config.sh` above is *node-local* (paths, compilers). **What** to build — every
component's git URL, default ref, and worktree branch, plus SuperBuild
dependency pins and the Slicer Qt version — lives in the tracked, human-readable
`versions.toml` at the repo root. Edit versions here, not in the engine shell.

```toml
[components.ITK]
url    = "https://github.com/InsightSoftwareConsortium/ITK.git"
ref    = "origin/main"            # ITK_REF env var overrides this one
branch = "itk-downstream"

[components.BioCell]              # ITK remote module
url   = "https://github.com/InsightSoftwareConsortium/ITKBioCell.git"
kind  = "remote"
heavy = false

[subbuild.BRAINSTools]           # passed as -DBRAINSTools_ANTs_GIT_* overrides
ANTs_GIT_REPOSITORY = "https://github.com/ANTsX/ANTs.git"
ANTs_GIT_TAG        = "d2fbf8bd525f0b9f907b9c6ebd35ab26a4d8927a"

[toolchain]
slicer_qt_version = "6.9.1"
```

Precedence is unchanged: **env var > versions.toml > built-in fallback**. The
engine reads it through `bin/config.py`:

```bash
python3 bin/config.py consumers              # name|url|branch rows (engine arrays)
python3 bin/config.py remotes                # name|url|heavy rows
python3 bin/config.py get subbuild.Slicer.ITK_GIT_TAG
python3 bin/config.py manifest <FOREST>      # write <FOREST>/manifest.toml
```

### `manifest.toml` — what a forest actually has

Every `checkout`/`build`/`repoint-itk` (re)writes `<FOREST>/manifest.toml`: the
repo, requested ref, branch, and **resolved git SHA** of each component present
in that forest — a human-readable record of exactly what was built. Regenerate
on demand: `bash bin/setup-itk-downstream-testbed.sh manifest`.

### Cross-forest ccache (`BUILD_FOREST_ROOT`)

`CCACHE_BASEDIR` defaults to the per-forest root (`$FOREST`), so each compile
rewrites its forest-absolute paths to forest-relative before hashing. Two
forests at **any** two `BUILD_FOREST_ROOT` locations (siblings, or unrelated
absolute paths) therefore share compiled objects: the second forest is ~100%
cache hits and only recompiles the TUs its ITK ref actually changed.
