# build_forest/

The **artifact directory** for the testbed. Everything here except this README
is **git-ignored** and regenerated — never commit build output.

`pixi run checkout` populates it with one source tree per project (worktree of
the matching `~/src/<name>` checkout when present, else a shallow clone), and
the builds drop their trees alongside:

```
build_forest/
├── README.md            (tracked — this file)
├── ITK/        ITK-build/        ITK-install/
├── ANTs/       ANTs-build/
├── Slicer/     Slicer-build/     (SuperBuild: builds VTK/CTK + own ITK 6)
├── elastix/    elastix-build/
└── <project>/  <project>-build/  ...
```

Paths here are computed by `bin/setup-vxl-downstream-testbed.sh` as
`$FOREST/<name>` and `$FOREST/<name>-build`, where `FOREST` defaults to this
directory (override with the `FOREST` env var).

## Safe to delete

This whole tree (except the README) is disposable. To reclaim disk:

```bash
# from the repo root — wipe everything but the tracked README
git clean -xdf build_forest -e README.md      # dry-run first with -n
```

A fresh `pixi run checkout` + build regenerates it; ccache (`~/.ccache`) keeps
the rebuild fast.
