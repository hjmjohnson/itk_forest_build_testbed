---
name: itk-abi-namespace
version: 1.0.0
purpose: Wrap ITK's `namespace itk` blocks in the ITK_ABI_NAMESPACE_BEGIN/END inline-namespace guards, module by module, verifying each module under both the default (no-op) and a non-default namespace.
description: >-
  Drive the ITK ABI inline-namespace refactor (ITK issue #6786): annotate every
  `namespace itk { ... }` block with ITK_ABI_NAMESPACE_BEGIN/END so ITK symbols
  can be mangled into a configured inline namespace, letting independently
  distributed ITK builds coexist in one process. Handles the C++17 nested form
  `namespace itk::Sub`, multi-block files, and configured `.cxx.in` sources;
  adds `#include "itkABINamespace.h"` to the headers that cannot reach the
  macros by any include path, using the compiler to enumerate them. Enforces the
  rule that a default-configuration build proves nothing -- every module must be
  built with a non-default ITK_ABI_NAMESPACE_NAME, because that is the only
  configuration in which a half-migrated file fails. Use whenever working on the
  ITK ABI namespace, the inline-namespace migration, ITK_ABI_NAMESPACE_BEGIN/END
  annotation, "mangle ITK symbols", "two ITKs in one process", or issue #6786.
triggers:
  - itk-abi-namespace
  - /itk-abi-namespace
  - abi namespace annotation
  - inline namespace migration
  - ITK_ABI_NAMESPACE_BEGIN
  - mangle itk symbols
  - two itks in one process
  - issue 6786
user_invocable: true
cmd: false
argument_hint: "<module-path>... | --status | (or describe the module to annotate)"
contract:
  inputs:
    - argument
    - files
  outputs:
    - files
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - Modules/**/*.h
      - Modules/**/*.hxx
      - Modules/**/*.cxx
      - Modules/**/*.in
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: false
    git_required: true
    user_confirmation_required: false
  determinism: deterministic
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
    - python3
    - cmake
    - ninja
    - castxml
  python_packages: []
  scripts:
    - annotate_abi_namespace.py
    - fix_abi_includes.py
deployment:
  tier: project
  target_projects:
    - itk
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK ABI Inline Namespace

Annotate ITK so its symbols can be placed in a configured inline namespace,
letting several independently distributed ITK builds coexist in one process
(PyPI `itk`, SimpleITK, Slicer). Tracks ITK issue #6786, which chose this
mechanism over `#define itk <name>`.

The prerequisite is `itkABINamespace.h` and the `ITK_ABI_NAMESPACE_NAME` CMake
option in `Modules/Core/Common`. Without them the macros are undefined and
every annotated file fails to compile.

## The one rule that matters

**A default-configuration build proves nothing.** With no ABI namespace the
macros expand to nothing, so a half-migrated file compiles perfectly. Every
module must be built with a non-default namespace before it is called done:

```bash
cmake -S <src> -B <bld> -DITK_ABI_NAMESPACE_NAME=py_itk
ninja -C <bld> <Module>
```

Both defects found during the ITKCommon migration were invisible in the default
build and immediate in the `py_itk` build.

## Workflow per module

```bash
# 1. Dry run. Read the SKIP lines before applying anything.
python3 scripts/annotate_abi_namespace.py Modules/<Group>/<Module>

# 2. Apply.
python3 scripts/annotate_abi_namespace.py --apply Modules/<Group>/<Module>

# 3. Build under a NON-DEFAULT namespace, letting the compiler enumerate the
#    headers that cannot reach the macros, until it converges.
for i in 1 2 3 4 5 6; do
    ninja -C <bld> <Module> > build.log 2>&1 && break
    python3 scripts/fix_abi_includes.py build.log
done

# 4. Confirm coverage: every symbol moved, none left behind.
nm <bld>/lib/lib<Module>-6.0.a | c++filt | grep -c 'itk::py_itk::'
nm <bld>/lib/lib<Module>-6.0.a | c++filt | grep -oE '\bitk::[A-Za-z]+::' | grep -v py_itk | sort -u

# 5. Reconfigure to the default and run the module's tests for regressions.
cmake -S <src> -B <bld> -DITK_ABI_NAMESPACE_NAME='<DEFAULT>'
```

Step 4's second command must print nothing. Anything it prints is a block the
annotation missed.

## Rebasing onto a new upstream base

The annotation is reproducible from the script; the include list is **not**. It
is discovered empirically from compiler errors, it differs by platform (macOS
needed 3 rounds where Linux needed 0), and nothing in the source records it.

So a rebase regenerates two artifacts with different provenance, and running
only the first leaves a tree that cannot compile:

```bash
# 1. Rebase only the LOGICAL commits onto the new base. Do not replay the
#    mechanical commits -- they are generated, and their diffs conflict with
#    every upstream edit to an annotated file.
git rebase --onto <new-base> <old-base> <last-logical-commit>

# 2. Regenerate the annotation.
python3 scripts/annotate_abi_namespace.py --apply Modules

# 3. MANDATORY, and the step that is easy to skip: re-run the include fixer
#    against a real build, on THIS platform, until it converges. Step 2 alone
#    does not restore the includes the previous branch had accumulated.
for i in $(seq 1 12); do
    ninja -C <bld> > build.log 2>&1 && break
    python3 scripts/fix_abi_includes.py build.log
done
```

Skipping step 3 fails identically in both configurations, because an
unreachable macro is undefined whether or not a namespace is configured. That
symmetry is the tell: a failure present in the default build is never the
namespace.

## What the scripts handle

`annotate_abi_namespace.py` wraps **every** `namespace itk` block in a file,
not just the first, and expands the C++17 nested form:

```cpp
namespace itk::Math          →   namespace itk
{                                {
  ...                            ITK_ABI_NAMESPACE_BEGIN
} // namespace itk::Math         namespace Math
                                 {
                                   ...
                                 } // namespace Math
                                 ITK_ABI_NAMESPACE_END
                                 } // namespace itk
```

It skips files already carrying `ITK_ABI_NAMESPACE_BEGIN` in a given block, so
re-running it is safe and incremental. Files whose shape it does not recognize
are printed as `SKIP (unmatched shape)` and left untouched for manual review —
read those lines rather than assuming a clean run.

`fix_abi_includes.py` parses a build log for `unknown type name
'ITK_ABI_NAMESPACE_*'` and inserts `#include "itkABINamespace.h"` into each
named file. `itkMacro.h` includes the header and carries it to most of the
tree; only the headers with no path to it need their own include (11 of 606
files in ITKCommon).

## Traps, all of them observed

**Multi-block files.** `itkPrintHelper.h` opens `namespace itk` twice.
Annotating only the first leaves the second in the plain namespace while its
callers move into the inline one. The current script handles this; a
hand-rolled regex pass will not.

**Configured sources.** `itkBuildInformation.cxx.in` opens `namespace itk` and
is configured into the build tree. A scan restricted to `.cxx`/`.h` misses it
and the generated file then contradicts its own annotated header. `.in` is in
the script's extension set for this reason.

**Unreachable headers.** Roughly 35 ITK headers reach neither `itkConfigure.h`
nor any `*Export.h` by any include path. With an inline namespace this is a
hard compile error rather than a silent mismatch, which is why step 3 converges
instead of guessing.

**Export headers do not carry the macros in ITK.** VTK appends its ABI header
to each generated module export header. ITK generates `<Module>Export.h` only
when `ITK_MODULE_<Module>_ENABLE_SHARED`, so header-only modules get none;
`itkMacro.h` is the carrier instead.

## Verifying Python wrapping still works

An inline namespace is transparent to CastXML, so the 1,001 `.wrap` files
naming `"itk::ClassName"` keep matching. Confirm on a module built with a
non-default namespace:

```bash
echo '#include "itkObject.h"' > probe.cxx
castxml --castxml-cc-gnu "$CXX" --castxml-output=1 -std=c++17 $INCLUDE_FLAGS \
    -o probe.xml probe.cxx
```

The XML must report `itk::Object` and contain no namespace named after the
configured ABI name, while `nm` on the library shows `itk::py_itk::Object`.
Measured on ITKCommon under `py_itk`: 5,721 symbols mangled, 0 left in bare
`itk::`, CastXML reporting `itk` only.

Note `--castxml-cc-gnu <compiler>` is required; `--castxml-cc-clang++` is not a
valid id, and without a compiler id CastXML cannot find the standard library.

## Scope

Annotating ITK is a large mechanical change (~3,481 sites) whose adoption is a
maintainer decision on #6786. The `ITK_ABI_NAMESPACE_NAME` option is additive
and defaults to a no-op, so it can land ahead of the annotation; downstream
projects can adopt guarded forward declarations before ITK is annotated at all.
