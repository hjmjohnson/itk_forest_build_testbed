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

### Forest naming (a convention, not a rule)

`FOREST_REFERENCE_SUFFIX` is a plain free-form suffix: the forest directory is
`BUILD_FOREST_ROOT[-FOREST_REFERENCE_SUFFIX]`, and with no suffix it is the bare
`build_forest`. Nothing derives the name and nothing enforces it.

The **recommended convention** for a forest holding a particular ITK ref is
`itk-<refslug>`, which you type yourself alongside the ref:

```bash
FOREST_REFERENCE_SUFFIX=itk-pr6250 ITK_REF=pr/6250 pixi run checkout
```

| `ITK_REF` | conventional forest |
|---|---|
| `origin/release-5.4` | `build_forest-itk-release-5.4` |
| `v5.4.6` | `build_forest-itk-v5.4.6` |
| `origin/main` | `build_forest-itk-main` |
| `pr/6250` | `build_forest-itk-pr6250` |
| `origin/v6-integration` | `build_forest-itk-v6-integration` |

`python3 bin/config.py refslug <ref> [itk_clone]` prints the slug to type.

Because the name is only a convention, it can drift from the contents. The
authority on what a forest holds is its `manifest.toml` (resolved ref, slug,
SHA, ITK version), and `python3 bin/config.py compare <A> <B>` is how you check
it. Ask the engine for the resolved directory with
`bash bin/setup-itk-downstream-testbed.sh --print-forest`.

**Suffix-keyed config.** `subbuild.ANTs.skip_suffix` and `[scenarios.<suffix>]`
in `versions.toml` are keyed by the forest suffix. Renaming a forest without
updating them changes the build with no error, so `config.py --check` rejects a
key that follows the `itk-` convention but is not a valid `itk-<refslug>`, and
notes any scenario key with no forest on disk.

## How resolution works

`config.json.in` declares each key as either:

- **`candidates`** — a list of paths (globs allowed); the generator picks the
  first that exists. An optional **`verify`** sub-path must also exist (e.g.
  `QT6_DIR` requires `lib/cmake/Qt6`). If `required: true` and none match, the
  key is written as a commented placeholder and `config.py` warns — **set it
  manually** in `config.sh`.
- **`value`** — a literal default (env-expanded), no existence check.

A key may also carry a **per-platform override block** (`macos`, `linux`,
`windows`) whose contents replace the top-level strategy on that host — this is
how `BUILD_FOREST_ROOT` becomes `C:/S` and `QT6_DIR` looks under
`C:/Qt/6.*/msvc2022_64` on Windows without affecting the other two platforms:

```json
"BUILD_FOREST_ROOT": { "value": "build_forest",
                       "windows": { "value": "C:/S" } }
```

Choosing `value` in an override drops an inherited `candidates` (and vice
versa), so the two strategies never compete. On Windows every resolved value is
normalized to forward slashes — `config.sh` is sourced by bash and its values
are handed to cmake, and `C:/x/y` is accepted verbatim by both.

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

The **SHA is the authority**, and a requested `ITK_REF` is recorded only once
verified against it: if the requested ref does not resolve, in that worktree, to
the SHA the worktree is on, the request is *not* recorded. The manifest instead
records the worktree's own ref and warns on stderr naming both SHAs. So `ref`
never asserts something the `sha` beside it contradicts — a forest holding a ref
other than the one asked for says so. This is detection, not refusal: an
unhonored request warns, never dies, since a manifest write rides on nearly
every command.

### Cross-forest ccache (`BUILD_FOREST_ROOT`)

`CCACHE_BASEDIR` defaults to the per-forest root (`$FOREST`), so each compile
rewrites its forest-absolute paths to forest-relative before hashing. Two
forests at **any** two `BUILD_FOREST_ROOT` locations (siblings, or unrelated
absolute paths) therefore share compiled objects: the second forest is ~100%
cache hits and only recompiles the TUs its ITK ref actually changed.

**`CCACHE_BASEDIR` is exported by the engine, not by pixi activation.** It has
to be, because sharing requires it to equal the *per-forest* root: point it at
the testbed root instead and the forest name survives inside the rewritten
path, which defeats the purpose. `[activation.env]` therefore carries only the
forest-independent knobs (`CCACHE_NOHASHDIR`, `CCACHE_MAXSIZE`,
`CCACHE_COMPILERCHECK`, `CCACHE_SLOPPINESS`).

The consequence: **a `pixi shell` alone does not warm the cache portably.**
Driving a build by hand from inside one —

```bash
pixi shell
ninja -C build_forest-itkv5/ITK/build      # base_dir empty -> keyed on absolute paths
```

— stores every object under its forest-absolute path, so another forest gets
zero reuse from it. Either build through the engine (`pixi run build-ITK`,
`pixi run bash bin/run-matrix.sh`), which exports the right basedir per
package, or export it yourself to match the engine's policy:

```bash
export CCACHE_BASEDIR="$PWD/build_forest-itkv5/ITK"   # ITK: per-package root
export CCACHE_BASEDIR="$PWD/build_forest-itkv5"       # any consumer/SuperBuild
```

Verify at any time with `ccache -p | grep base_dir` — an empty value inside a
build shell means the objects you are about to produce are forest-locked.
