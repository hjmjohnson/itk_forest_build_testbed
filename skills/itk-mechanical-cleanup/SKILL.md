---
name: itk-mechanical-cleanup
version: 1.0.0
purpose: Apply one of fourteen mechanical C++ modernization patterns across ITK and its downstream consumers, each with a detector, an optional transformer, and a shared verification gate.
description: >-
  Mechanical C++ cleanup for ITK and its ecosystem (ANTs, BRAINSTools, Slicer,
  elastix, remote modules). Fourteen patterns, each with a glob-safe detect.sh
  and — where safely automatable — a transform.sh: T::Pointer p = T::New() to
  auto; drop redundant iterator template args (C++17 CTAD); if (Dim == N) to
  if constexpr; c.size() == 0 to c.empty(); push_back(T(...)) to
  emplace_back(...); empty-body ctor/dtor to = default; in-class member
  initializers; (void) parameter lists to (); C-style casts to static_cast;
  x++ to ++x in discarded-value contexts; iterator fill loops to FillBuffer();
  drop WithIndex when GetIndex is unused; reader/writer boilerplate to
  itk::ReadImage/WriteImage; and the legacy str.find(s) < str.length() presence
  test. Use when applying a mechanical cleanup sweep, when a reviewer asks for
  one of these idioms, or when another skill needs a payload detector. Trigger
  on: "itk-mechanical-cleanup", "/itk-mechanical-cleanup", "mechanical cleanup",
  "modernize ITK", "clang-tidy cleanup", and any pattern name listed above.
triggers:
  - itk-mechanical-cleanup
  - /itk-mechanical-cleanup
  - mechanical cleanup
  - modernize ITK
  - clang-tidy cleanup
user_invocable: true
cmd: false
argument_hint: "<pattern> [repo-path] | list"
contract:
  inputs:
    - argument
    - cwd
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/**"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: false
  determinism: hybrid
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools:
    - git
    - clang-format
  python_packages: []
  scripts:
    - list-patterns.sh
    - patterns/*/detect.sh
    - patterns/*/transform.sh
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Mechanical Cleanup

Fourteen mechanical C++ patterns, one payload interface. Each pattern owns a
directory under `patterns/<name>/`:

| File | Role |
|---|---|
| `PATTERN.md` | before/after, detection notes, pattern-specific caveats |
| `detect.sh` | candidate scanner (see the detector contract below) |
| `transform.sh` | dry-run by default, `--apply` writes, never commits (9 of 14) |

> **Constraint — C++17, ITKv5 + ITKv6:** target C++17 idioms valid against both
> ITK >= 5.4 and ITKv6; never require C++20+. Verify transformed output by
> compiling against both ITK header sets with `-std=c++17`
> (see `skills/BRAINSTOOLS_HARDENING.md`).

## Usage

```bash
bash list-patterns.sh                              # the eligible set
bash patterns/<name>/detect.sh <repo>              # scan
bash patterns/<name>/transform.sh <repo>           # dry-run
bash patterns/<name>/transform.sh <repo> --apply   # write (never commits)
```

Read `patterns/<name>/PATTERN.md` before applying — it holds the before/after
shape, the false positives the detector deliberately over-reports, and the
caveats that decide whether a hit is real.

To sweep a pattern across many sites one class per commit, use
`itk-incremental-refactor-loop` with this skill's pattern name as the payload.

## The patterns

`scope` matters: seven of these wrap a clang-tidy check that has **already been
applied and merged to ITK main**. Those remain useful for downstream consumers
and for ITK code added since the merge, but running them against a clean ITK
tree will correctly report zero.

| Pattern | clang-tidy check | ITK main | Transform |
|---|---|---|---|
| `auto-for-new` | `modernize-use-auto` | merged `de713e7` | ✔ |
| `constexpr-if-constant` | — | — | review |
| `container-size-to-empty` | `readability-container-size-empty` | merged #4985 | ✔ |
| `cstyle-to-static-cast` | `cppcoreguidelines-pro-type-cstyle-cast` | merged #5394 | review |
| `ctad-iterator` | — | — | ✔ |
| `emplace-back-construct` | `modernize-use-emplace` | merged #5824 | ✔ |
| `equals-default-special-members` | `modernize-use-equals-default` | merged `bc66259` | review |
| `fillbuffer-over-iterate` | — | — | review |
| `in-class-member-init` | `modernize-use-default-member-init` | merged `b21dbbb` | ✔ |
| `iterator-drop-withindex` | — | — | ✔ |
| `prefer-prefix-increment` | — | — | ✔ |
| `read-write-image-convenience` | — | — | review |
| `redundant-void-arg` | `modernize-redundant-void-arg` | merged (DONE) | ✔ |
| `string-find-presence-test` | `readability-container-contains` (C++20, N/A) | — | ✔ |

`itk-clang-tidy-refactor` holds the authoritative Approved / Rejected /
Not-Easy rule lists; no pattern here wraps a Rejected check.

## Detector contract

Every `detect.sh` takes a repo path (default `.`) and ends on a `----` rule
followed by exactly one machine-readable line:

```
----
match_count: <N>
```

`match_count: 0` with **exit 0** means the tree is clean — that is a result,
not a failure. **Exit 2** means the scan could not run (bad path, not a git
work tree). Shared plumbing lives in `lib/detect-common.sh`
(`itk_detect_init` / `_grep` / `_count` / `_report`) and defines the canonical
pathspecs, so every pattern scans the same file set and spells the ThirdParty
exclusion the same way.

## Verification gate (every pattern)

Run all five after applying any pattern. `PATTERN.md` adds only what is
specific to that pattern.

1. **Re-detect** — `detect.sh` count drops by the number of accepted edits.
2. **Rebuild** the touched module or consumer — `pixi run build-ITK`, or
   `build-<consumer>`. ccache keeps it fast.
3. **Confirm the artifact on disk** (the library or binary exists), not a zero
   pipe exit. `… | tee/tail` masks failures.
4. **Read the diff** — every hunk is a true instance of the pattern, nothing
   else rode along.
5. **`pre-commit run --all-files`** clean, and run the module's tests if it has
   any.

## Common mistakes

Pattern-specific; see the `## Common mistakes` section of each `PATTERN.md`.
The one that generalizes: a detector that **over-reports by design** (the
review-mode patterns) is not a to-do list — each hit must be read before it is
touched.

## Enhanced by

- **serena** — When installed, this skill can use semantic code analysis
  (`find_symbol`, `replace_symbol_body`) for precise refactoring instead
  of regex-based text matching. Falls back to pattern-based rewriting
  when unavailable.
