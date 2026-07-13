---
name: itk-locale-safe-migration
version: 1.0.0
purpose: Migrate locale-dependent C/C++ parsing calls (std::stod, std::stof, std::stoi, atof, atoi, std::atoi) to locale-safe wrappers.
description: >-
  Migrate locale-dependent C/C++ parsing calls (std::stod, std::stof, std::stoi,
  atof, atoi, std::atoi) to locale-safe wrappers. Use when auditing or fixing
  international locale bugs in ITK-based projects (BRAINSTools, Slicer modules,
  NAMIC tools). Trigger on: "locale bug", "comma decimal separator", "std::stod
  migration", "safe_stod", "#403 migration", or whenever std::stod/stof/stoi/atof
  calls need to be replaced with a locale-neutral wrapper.
triggers:
  - itk-locale-safe-migration
  - /itk-locale-safe-migration
user_invocable: true
cmd: false
argument_hint: "[path/to/module]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: false
    writes_to_repo_paths: []
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: false
    network_required: false
    git_required: false
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
  external_tools: []
  python_packages: []
  scripts: []
deployment:
  tier: always
  target_projects: []
  needs_loader_dir: true
  adapters:
    - claude-code
---

# ITK Locale-Safe Parsing Migration

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-locale-safe-migration — Replace std::stod/atof with locale-safe wrappers

Usage:
  /itk-locale-safe-migration                 Scan and migrate cwd project
  /itk-locale-safe-migration Modules/IO      Restrict to one module path

Replaces: std::stod, std::stof, std::stoi, atof, atoi -> safe_stod etc.
```

Replaces `std::stod`, `std::stof`, `std::stoi`, `atof`, `atoi` with locale-safe
wrappers so that users with `LC_NUMERIC=de_DE` (comma decimal separator) do not
get silent data corruption or parse failures.

## The problem

`std::stod("3.14")` returns garbage when the process locale uses `,` as decimal.
`atof` is always locale-sensitive.  Any file that parses numbers from strings
(landmark files, config files, DICOM tags, command-line args) is affected.

## Prerequisite

The project must have a header providing the safe wrappers — e.g.
`BRAINSCommonLib/LocaleSafeConversions.h` in BRAINSTools (PR #569), or an
equivalent using `std::istringstream` imbued with `std::locale::classic()`.

If the header does not exist, create it first:
```cpp
// LocaleSafeConversions.h
#include <locale>
#include <sstream>
#include <stdexcept>
#include <string>
namespace ProjectNS {
inline double safe_stod(const std::string & s) {
  std::istringstream iss(s); iss.imbue(std::locale::classic());
  double v{}; iss >> v;
  if (iss.fail() || !iss.eof()) throw std::invalid_argument("safe_stod: '" + s + "'");
  return v;
}
// ... safe_stof, safe_stoi, safe_stoui similarly
} // namespace ProjectNS
```

## Audit step

Find all call sites before touching any file:
```bash
grep -rn --include='*.cxx' --include='*.cpp' --include='*.h' --include='*.hxx' \
  -E '\b(std::stod|std::stof|std::stoi|std::stoui|atof|atoi|std::atof|std::atoi)\s*\(' \
  <source-dir> | grep -v ThirdParty | grep -v build/
```

Group by module directory and count — plan one commit per module.

## Migration rules

| Old call | New call | Notes |
|----------|----------|-------|
| `std::stod(x)` | `NS::safe_stod(x)` | direct |
| `std::stod(x.c_str())` | `NS::safe_stod(x)` | strip .c_str() |
| `atof(x.c_str())` | `NS::safe_stod(x)` | strip .c_str() |
| `std::atof(x.c_str())` | `NS::safe_stod(x)` | strip .c_str() |
| `std::stoi(x)` | `NS::safe_stoi(x)` | direct |
| `atoi(x.c_str())` | `NS::safe_stoi(x)` | strip .c_str() |
| `std::atoi(x.c_str())` | `NS::safe_stoi(x)` | strip .c_str() |

**CRITICAL**: Apply `std::atoi` / `std::atof` patterns BEFORE bare `atoi` / `atof`
patterns, otherwise `std::atoi(x)` → `std::NS::safe_stoi(x)` (orphaned `std::`).

## Correct regex ordering (Python)

```python
SUBS = [
    # stod patterns (specific before general)
    (re.compile(r'\bstd::stod\s*\(([^)]+?)\.c_str\(\)\s*\)'),  r'NS::safe_stod(\1)'),
    (re.compile(r'\bstd::atof\s*\(([^)]+?)\.c_str\(\)\s*\)'),  r'NS::safe_stod(\1)'),  # std:: first!
    (re.compile(r'\batof\s*\(([^)]+?)\.c_str\(\)\s*\)'),        r'NS::safe_stod(\1)'),
    (re.compile(r'\bstd::stod\s*\(([^)]+?)\)'),                 r'NS::safe_stod(\1)'),
    (re.compile(r'\batof\s*\(([^)]+?)\)'),                      r'NS::safe_stod(\1)'),
    # stoi patterns (specific before general)
    (re.compile(r'\bstd::stoi\s*\(([^)]+?)\.c_str\(\)\s*\)'),  r'NS::safe_stoi(\1)'),
    (re.compile(r'\bstd::atoi\s*\(([^)]+?)\.c_str\(\)\s*\)'),  r'NS::safe_stoi(\1)'),  # std:: first!
    (re.compile(r'\batoi\s*\(([^)]+?)\.c_str\(\)\s*\)'),        r'NS::safe_stoi(\1)'),
    (re.compile(r'\bstd::stoi\s*\(([^)]+?)\)'),                 r'NS::safe_stoi(\1)'),
    (re.compile(r'\batoi\s*\(([^)]+?)\)'),                      r'NS::safe_stoi(\1)'),
]
```

After substitution, do a second pass to strip any residual `.c_str()` inside
`safe_std*` calls (for cases with nested parentheses):
```python
CSTR = re.compile(r'(NS::safe_st(?:od|of|oi))\((.+?)\.c_str\(\)\s*\)')
```

## Post-migration checks

1. `grep -rn 'std::BRAINSTools::\|std::NS::' <files>` — must be zero (orphaned `std::`)
2. `grep -rn '\bstd::stod\|\batof\b\|\batoi\b' <files>` — must be zero
3. Build the affected modules: `ninja -C build <ModuleName>`
4. Add `#include "LocaleSafeConversions.h"` after last `#include` in each file

## Commit structure

One commit per module directory (keeps diffs reviewable):
```
ENH: Migrate BRAINSCommonLib to locale-safe parsing (#403)   — 15 calls
ENH: Migrate BRAINSConstellationDetector to locale-safe parsing (#403)
ENH: Migrate GTRACT to locale-safe parsing (#403)
...
```

## strtok() special case

`strtok()` returns `char *`. The safe wrappers take `const std::string &`,
so `char *` implicitly constructs `std::string`. This is correct and efficient:
```cpp
// old:  std::stod(strtok(buf, " "))
// new:  NS::safe_stod(strtok(buf, " "))   ← char* → string implicit
```

## Enhanced by

- **serena** — When installed, this skill can use semantic code analysis
  (`find_symbol`, `replace_symbol_body`) for precise refactoring instead
  of regex-based text matching. Falls back to pattern-based rewriting
  when serena is not available.

  **Strongly recommended:** If the Serena MCP plugin is available in
  your Claude Code environment, enable it before running this skill.
  Serena's symbol-level tools save up to 70 % in token costs by
  indexing the codebase instead of reading every file line-by-line.

  Serena is available as an official Claude Code plugin. You do not
  need to install or start it manually — Claude Code launches the MCP
  server automatically as a subprocess. Setup:

  1. **Enable the plugin** — in Claude Code, run `/plugins` and enable
     **serena** from the official marketplace (or confirm it is already
     enabled in `~/.claude/settings.json` under `plugins`).
  2. **Run onboarding** — on the first session in a new project, say
     *"start Serena onboarding"* in the Claude Code chat. This triggers
     the initial indexing pass where Serena maps the codebase symbols
     and writes memory files so future sessions start with full context.

  After onboarding, Serena's context optimizer automatically disables
  its own file-search tools that would duplicate Claude Code's built-in
  features, avoiding conflicts and redundant work.
