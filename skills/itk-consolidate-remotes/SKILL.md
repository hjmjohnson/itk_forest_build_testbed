---
name: itk-consolidate-remotes
version: 0.2.0
purpose: Consolidate multiple ITK remote module repos into a single category repo
description: >
  Merges multiple ITK remote module git repositories into a single
  hierarchical category repository (e.g., ITKRemoteAnalysis) while
  preserving full git history, blames, and producing old-to-new hash
  mappings. Also generates the ITK .remote.cmake file and moves
  compliance grading reports into the new repo. Includes the ITK-side
  CMake changes needed to support the consolidated repos.
triggers:
  - consolidate remote modules
  - merge remote module repos
  - create category repo
  - ITKRemote consolidation
user_invocable: true
cmd: false
argument_hint: "<category_name> <module1:repo_url> [module2:repo_url ...]"
contract:
  inputs:
    - "category name (e.g., Analysis, IO, Filtering)"
    - "list of module names with their source git URLs"
    - "optional ITK PR branch for in-tree modules (e.g., SSIM)"
  outputs:
    - new git repo at specified path with merged histories
    - per-module commit-map files (old_hash -> new_hash)
    - combined commit-map.tsv for all modules
    - ITK .remote.cmake file
    - compliance reports moved into repo
  side_effects:
    writes_to_repo: false
    writes_outside_repo: true
    writes_outside_repo_paths:
      - "<workspace>/ITKRemote<Category>/"
      - "<workspace>/.consolidation-work/"
    modifies_working_tree: false
    network_required: true
    git_required: true
    user_confirmation_required: true
  determinism: deterministic
  cache:
    has_cache: false
  derivation:
    has_ai_derived_layer: false
dependencies:
  external_tools:
    - git
    - git-filter-repo
    - python3
  scripts:
    - consolidate_repos.py
    - gen_remote_cmake.py
deployment:
  tier: project
  target_projects:
    - ITK
    - REMOTE_MODULES
  needs_loader_dir: false
  adapters:
    - claude-code
---

# ITK Remote Module Consolidation Skill

## Purpose

Consolidates multiple single-module ITK remote repos into one
multi-module category repo, preserving full git history. Also handles
the ITK-side CMake changes (removing old .remote.cmake files, creating
the group .remote.cmake, verifying the build).

## Tracking

- Issue: https://github.com/InsightSoftwareConsortium/ITK/issues/6060
- WIP PR: https://github.com/InsightSoftwareConsortium/ITK/pull/6061

## Proven workflow (from Analysis prototype)

### Step 1: Create the category repo

```bash
python3 consolidate_repos.py <Category> <output_dir> \
  Module1:https://github.com/InsightSoftwareConsortium/ITKModule1.git \
  Module2:https://github.com/InsightSoftwareConsortium/ITKModule2.git \
  ...
  --itk-source /path/to/ITK
```

This:
- Clones each source repo
- Rewrites history with `git filter-repo --to-subdirectory-filter <Name>/`
- Merges into the target repo with `--allow-unrelated-histories`
- Extracts COMPLIANCE.md from ITK `.remote.cmake` grading reports
- Produces `commit-maps/` with old-to-new hash mappings

### Step 2: Handle in-tree modules (optional)

For modules that exist only as ITK PRs (not yet in their own repo),
manually create the module directory in the category repo:

1. Create `<ModuleName>/` with proper remote module structure:
   - `itk-module.cmake` (standalone, with EXCLUDE_FROM_DEFAULT and ENABLE_SHARED)
   - `CMakeLists.txt` (dual-mode: external + in-tree)
   - `include/`, `test/`, `wrapping/`
2. Add `\ingroup <ModuleName>` Doxygen tag to all class headers
3. Commit with original authorship preserved via GIT_AUTHOR_* env vars

### Step 3: ITK-side changes

On a WIP branch in ITK:

1. **Remove individual .remote.cmake files** for modules now in the group:
   ```bash
   git rm Modules/Remote/Module1.remote.cmake Modules/Remote/Module2.remote.cmake ...
   ```

2. **Create the group .remote.cmake**:
   ```bash
   python3 gen_remote_cmake.py <Category> <repo_url> <git_tag> \
     --repo-path <local_repo_path> \
     --output Modules/Remote/ITKRemote<Category>.remote.cmake
   ```

3. **Clear stale cache entries** before configuring:
   ```bash
   cd build
   for mod in Module1 Module2 ...; do
     cmake -U "Module_${mod}_REMOTE_COMPLIANCE_LEVEL" \
           -U "Module_${mod}" -U "Module_${mod}_GIT_TAG" .
   done
   ```

4. **Configure and build**:
   ```bash
   cmake -DITKGroup_Remote_<Category>=ON \
         -DModule_<ExcludedModule1>=ON \
         -DModule_<ExcludedModule2>=ON \
         ..
   ninja -j10
   ```

5. **Run tests**:
   ```bash
   ctest -R "Module1|Module2|..." --output-on-failure -j8
   ```

### Step 4: Push and PR

1. Push category repo to `InsightSoftwareConsortium/ITKRemote<Category>`
2. Update `.remote.cmake` GIT_REPOSITORY URL to point at GitHub
3. Push ITK WIP branch and create draft PR referencing #6060

## ITK CMake prerequisites

These changes are needed once (already in PR #6061):

| File | Change |
|------|--------|
| `CMake/ITKModuleEnablement.cmake:9` | Add 4-level glob: `/*/*/*/*/itk-module.cmake` |
| `CMake/ITKModuleRemote.cmake` | Add `itk_fetch_module_group()` function (~106 lines) |
| `CMake/ITKGroups.cmake` | Sub-group request propagation (~50 lines) |

## Gotchas discovered during prototype

1. **Stale cache**: Old `Module_<name>_REMOTE_COMPLIANCE_LEVEL` entries from
   individual `.remote.cmake` files persist in CMakeCache.txt. They cause
   the module option creation to be skipped (line 157 of ITKModuleEnablement).
   Must clear with `cmake -U` before reconfiguring.

2. **ITK_FREEZE_REMOTE_MODULES**: Only skips updates for already-cloned
   modules. For the first configure of a group, set `=OFF` so the repo
   is cloned. Subsequent configures can use `=ON`.

3. **EXCLUDE_FROM_DEFAULT**: Modules with this flag in their itk-module.cmake
   are discovered but not auto-built when the sub-group is enabled. Users
   must explicitly set `Module_<name>=ON`. This matches existing behavior.

4. **Doxygen \ingroup tag**: Every class header in a remote module must have
   `\ingroup <ModuleName>` or the `InDoxygenGroup` test fails.

5. **git filter-repo removes origin remote**: After `--to-subdirectory-filter`,
   the clone has no `origin`. The consolidate script handles this by adding
   the clone as a local remote to the target repo.

6. **gersemi**: ITK's CMake formatter will reformat new CMake code. Run
   hooks before committing (the pre-commit hook does this automatically).

## Output structure

```
ITKRemote<Category>/
  <Module1>/
    itk-module.cmake
    CMakeLists.txt
    include/
    src/
    test/
    wrapping/
    COMPLIANCE.md
  <Module2>/
    ...
  .clang-format
  LICENSE
  README.md
  commit-maps/
    <Module1>-commit-map.tsv
    combined-commit-map.tsv
```

## Category plan (#6060)

| Category | Modules | Status |
|----------|---------|--------|
| **Analysis** | TextureFeatures, BoneMorphometry, BoneEnhancement, Thickness3D, IsotropicWavelets, RANSAC, PerformanceBenchmarking, StructuralSimilarity | **Done** (local) |
| **IO** | AnalyzeObjectLabelMap, IOFDF, IOMeshMZ3, IOMeshSTL, IOMeshSWC, IOScanco, IOTransformDCMTK, MGHIO | Planned |
| **Filtering** | AnisotropicDiffusionLBR, FastBilateral, GenericLabelInterpolator, HigherOrderAccurateGradient, LabelErodeDilate, ParabolicMorphology, SimpleITKFilters, SmoothingRecursiveYvvGaussianFilter, SplitComponents, TotalVariation | Planned |
| **Mesh** | BSplineGradient, Cuberille, FPFH, MeshNoise, MeshToPolyData, PrincipalComponentsAnalysis, SubdivisionQuadEdgeMeshFilter | Planned |
| **Registration** | FixedPointInverseDisplacementField, GrowCut, LesionSizingToolkit, MinimalPathExtraction, PolarTransform, SkullStrip, TwoProjectionRegistration, VariationalRegistration, Montage | Planned |
| **Microscopy** | IOOpenSlide, (+ future) | Planned |
| **Kitware** | HASI, MorphologicalContourInterpolation, MultipleImageIterator, PhaseSymmetry, RLEImage, Strain, Ultrasound | Planned |

## Prerequisites

- `git-filter-repo` installed (`pip install git-filter-repo`)
- Network access to clone source repos
- Write access to target directory
- ITK source tree (for compliance report extraction and build testing)
