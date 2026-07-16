# Forest wipe + remake runbook (phase 1 migration)

Uncommitted work was preserved on 2026-07-16 to `.devlocal/preserved-20260716/`
(9 patches, 52 K). `build_forest-svdc_Slicer.patch` holds the SUV work
(`ADDITIONAL_SRCS itkDCMTKFileReader.cxx`; BRAINSTools repointed to
`hjmjohnson/BRAINSTools` @ `bfbd9bce`). `.devlocal/` is gitignored and
machine-local, and the patches cover tracked-file edits only.

```bash
cd ~/src/itk_forest_build_testbed

# 1. Confirm the preserved patches are still there BEFORE deleting anything.
ls -la .devlocal/preserved-20260716/*.patch | wc -l    # expect 9

# 2. Delete the forests (~94 G).
rm -rf build_forest build_forest-base build_forest-itkv5 \
       build_forest-itkv6_main build_forest-linpackref build_forest-svdc \
       build_forest-pr-to-merge-into-release5.4

# 3. MANDATORY: prune stale worktree registrations. Without this the central
#    clones still believe those worktrees exist and re-adding the same branch
#    fails with "already checked out".
for r in forest_git_repos/*/; do git -C "$r" worktree prune; done

# 4. Verify no stale registrations remain.
for r in forest_git_repos/*/; do
  git -C "$r" worktree list | grep -q "build_forest" && echo "STALE: $r"
done
echo "prune check done"

# 5. Remake on demand, named by the itk-<refslug> convention (you type the
#    suffix; `config.py refslug origin/release-5.4` prints the slug).
export FOREST_REFERENCE_SUFFIX=itk-release-5.4
ITK_REF=origin/release-5.4 pixi run checkout
ITK_REF=origin/release-5.4 pixi run build-ITK
```

**Leave the per-forest branches** (`itk-downstream-itkv5`, …) in the central
clones. They cost nothing and are the only remaining record of what those
forests held — the fallback if a preserved patch proves incomplete. Prune them
in a separate, deliberate cleanup, never as a side effect of this migration.

**Known loss:** `build_forest-svdc` held a Slicer/VTK SuperBuild that 43
manifest entries in other forests pointed at (`VTK_DIR` →
`build_forest-svdc/Slicer/build/VTK-build`). Until phase 3
(`shared_resources/`) lands, a forest needing VTK builds its own.
