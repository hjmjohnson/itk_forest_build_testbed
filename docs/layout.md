# Repository layout

Three directories + pixi config at the root. **Only the kit is git-tracked**
(see `.gitignore`); the artifact tree is regenerated.

```
itk_forest_build_testbed/
├── CLAUDE.md            entry point + routing tables (tracked)
├── pixi.toml            toolchain + task graph (tracked)
├── pixi.lock            locked deps (tracked)
├── config.json.in      node-config template (tracked)
├── config.sh           generated node config (git-ignored)
├── bin/                 scripts — the build engine + helpers (tracked)
├── docs/                this md library (tracked)
└── build_forest/        source checkouts + *-build trees (git-ignored,
    └── README.md        except this README)
```

## bin/ — the scripts

| Script | Role |
|---|---|
| `setup-itk-downstream-testbed.sh` | the build engine — `checkout`/`configure`/`build`/`repoint-itk`/`remotes`/`list`/`status` |
| `run-matrix.sh` | build every consumer, score PASS/FAIL **by artifact** (not exit code) |
| `config.py` | generate `config.sh` from `config.json.in` (node-specific paths). See [config.md](config.md). |

The engine resolves `TESTBED` (repo root) from its own location, sources the
node-specific `config.sh`, and puts every artifact under `FOREST`
(`$BUILD_FOREST_ROOT`, default `$TESTBED/build_forest`). pixi tasks invoke it as
`bash ./bin/setup-itk-downstream-testbed.sh <cmd>`.

## build_forest/ — artifacts

Disposable. `pixi run checkout` populates it; builds drop `<name>-build/` trees
beside each `<name>/` source tree. Reclaim disk with
`git clean -xdf build_forest -e README.md`. See `build_forest/README.md`.

## What is NOT tracked

`.pixi/` (the env), `.remember/` `.memsearch/` `.devlocal/` (Claude scratch),
and everything under `build_forest/` except its README. The top-level `/*`
ignore rule means new files at the root are ignored unless explicitly
whitelisted — so a stray checkout can never be accidentally committed.

> Note (2026-06): the project's *global* gitignore excludes `CLAUDE.md`; this
> repo force-tracks it (`git add -f`) and the local `.gitignore` re-includes it.
