#!/usr/bin/env python3
"""csv_gen_presets.py — Generate or update CMakeUserPresets.json for common_support_versions.

Creates a CMakeUserPresets.json in the source directory with a csv_base hidden
preset and a tag-specific (optionally feature-suffixed) configure preset.
Merges into an existing file without destroying other presets.

Usage:
    python3 csv_gen_presets.py \
        --pkg ITK --tag v5.4.2 \
        --source-dir ~/src/common_support_versions/ITK/src_v5.4.2 \
        --build-dir  ~/src/common_support_versions/ITK/bld_v5.4.2 \
        --install-dir ~/src/common_support_versions/ITK/installed_v5.4.2 \
        [--feature shared] \
        [--cache-var "BUILD_SHARED_LIBS:BOOL=ON"] \
        [--cache-var "ITK_WRAP_PYTHON:BOOL=ON"] \
        [--compiler /opt/homebrew/opt/llvm/bin/clang++]
"""

import argparse
import json
import platform
import re
import shutil
import sys
from pathlib import Path


def parse_cache_var(s: str) -> tuple[str, dict]:
    """Parse 'NAME:TYPE=VALUE' into (name, {"type": TYPE, "value": VALUE}).

    Also accepts 'NAME=VALUE' (type defaults to STRING).
    """
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(\w+)=(.*)$", s)
    if m:
        return m.group(1), {"type": m.group(2), "value": m.group(3)}
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", s)
    if m:
        return m.group(1), {"type": "STRING", "value": m.group(2)}
    raise ValueError(f"Cannot parse cache variable: {s!r}  (expected NAME:TYPE=VALUE)")


def detect_system_compiler() -> str:
    """Return the path to the system default C++ compiler."""
    if platform.system() == "Darwin":
        return "/usr/bin/clang++"
    # Linux: prefer g++, fall back to c++
    for candidate in ["/usr/bin/g++", "/usr/bin/c++", "/usr/bin/clang++"]:
        if Path(candidate).exists():
            return candidate
    return "c++"


def compiler_suffix(compiler_path: str) -> str:
    """Derive a feature suffix from a non-default compiler path.

    E.g., /opt/homebrew/Cellar/llvm/21.1.8/bin/clang++ → clang21
    E.g., /usr/bin/gcc-14 → gcc14
    """
    basename = Path(compiler_path).name
    # Try to extract name and version
    m = re.match(r"(clang\+\+|clang|g\+\+|gcc)[-.]?(\d+)?", basename)
    if m:
        name = m.group(1).replace("++", "").replace("clang", "clang").replace("gcc", "gcc")
        ver = m.group(2) or ""
        # Try to get version from parent path (e.g., llvm/21.1.8/bin/)
        if not ver:
            parts = Path(compiler_path).parts
            for part in parts:
                vm = re.match(r"(\d+)\.\d+", part)
                if vm:
                    ver = vm.group(1)
                    break
        return f"{name}{ver}"
    return "custom"


def detect_osx_deployment_target() -> str | None:
    """Detect a reasonable CMAKE_OSX_DEPLOYMENT_TARGET on macOS.

    Uses 15.0 as a modern floor — these are local-only native builds,
    not distribution packages, so we don't need to target old macOS.
    """
    if platform.system() != "Darwin":
        return None
    return "15.0"


def make_base_preset(compiler_path: str | None = None) -> dict:
    """Create the csv_base hidden preset."""
    preset = {
        "name": "csv_base",
        "hidden": True,
        "generator": "Ninja",
        "cacheVariables": {
            "CMAKE_BUILD_TYPE": {"type": "STRING", "value": "Release"},
            "CMAKE_CXX_FLAGS": {"type": "STRING", "value": "-mtune=native -march=native"},
            "CMAKE_C_FLAGS": {"type": "STRING", "value": "-mtune=native -march=native"},
            "BUILD_TESTING": {"type": "BOOL", "value": "OFF"},
            "BUILD_EXAMPLES": {"type": "BOOL", "value": "OFF"},
            "BUILD_SHARED_LIBS": {"type": "BOOL", "value": "OFF"},
            "CMAKE_EXPORT_COMPILE_COMMANDS": {"type": "BOOL", "value": "ON"},
        },
    }
    osx_target = detect_osx_deployment_target()
    if osx_target:
        preset["cacheVariables"]["CMAKE_OSX_DEPLOYMENT_TARGET"] = {
            "type": "STRING",
            "value": osx_target,
        }
    if compiler_path:
        c_compiler = (
            compiler_path.replace("++", "").replace("clang", "clang").replace("g", "gcc")
            if "g++" in compiler_path
            else compiler_path
        )
        # Smarter C compiler derivation
        if compiler_path.endswith("clang++"):
            c_compiler = compiler_path[:-2]  # strip ++
        elif compiler_path.endswith("g++"):
            c_compiler = compiler_path[:-2] + "cc"
        else:
            c_compiler = compiler_path
        preset["cacheVariables"]["CMAKE_CXX_COMPILER"] = {"type": "PATH", "value": compiler_path}
        preset["cacheVariables"]["CMAKE_C_COMPILER"] = {"type": "PATH", "value": c_compiler}
    return preset


def make_tag_preset(
    pkg: str,
    tag: str,
    build_dir: str,
    install_dir: str,
    feature: str | None,
    extra_vars: dict,
    inherits: str = "csv_base",
) -> dict:
    """Create a tag-specific configure preset."""
    suffix = f"_{feature}" if feature else ""
    name = f"csv_{pkg}_{tag}{suffix}"
    display_parts = [pkg, tag, "Release"]
    if feature:
        display_parts.append(feature)
    display_parts.append("native")

    preset = {
        "name": name,
        "inherits": inherits,
        "displayName": f"{' '.join(display_parts)}",
        "binaryDir": build_dir,
        "cacheVariables": {
            "CMAKE_INSTALL_PREFIX": {"type": "PATH", "value": install_dir},
        },
    }
    preset["cacheVariables"].update(extra_vars)
    return preset


def make_build_preset(configure_preset_name: str) -> dict:
    """Create a build preset linked to a configure preset.

    Uses the same name as the configure preset so that
    `cmake --build --preset csv_PKG_TAG` works naturally.
    """
    return {
        "name": configure_preset_name,
        "configurePreset": configure_preset_name,
    }


def load_or_create(presets_path: Path) -> dict:
    """Load existing CMakeUserPresets.json or create a skeleton."""
    if presets_path.exists():
        with open(presets_path) as f:
            return json.load(f)
    return {
        "version": 3,
        "cmakeMinimumRequired": {"major": 3, "minor": 22, "patch": 0},
        "configurePresets": [],
        "buildPresets": [],
    }


def upsert_preset(presets_list: list[dict], new_preset: dict) -> None:
    """Insert or replace a preset by name."""
    for i, p in enumerate(presets_list):
        if p.get("name") == new_preset["name"]:
            presets_list[i] = new_preset
            return
    presets_list.append(new_preset)


def main():
    parser = argparse.ArgumentParser(
        description="Generate CMakeUserPresets.json for common_support_versions"
    )
    parser.add_argument("--pkg", required=True, help="Package name (e.g., ITK)")
    parser.add_argument("--tag", required=True, help="Git tag (e.g., v5.4.2)")
    parser.add_argument("--source-dir", required=True, help="Source directory (worktree)")
    parser.add_argument("--build-dir", required=True, help="Build directory")
    parser.add_argument("--install-dir", required=True, help="Install prefix")
    parser.add_argument("--feature", default=None, help="Feature suffix (e.g., shared, asan)")
    parser.add_argument(
        "--cache-var", action="append", default=[], help="Extra cache variable (NAME:TYPE=VALUE)"
    )
    parser.add_argument(
        "--compiler", default=None, help="C++ compiler path (adds feature suffix if non-default)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print JSON to stdout instead of writing"
    )
    args = parser.parse_args()

    source_dir = str(Path(args.source_dir).expanduser())
    build_dir = str(Path(args.build_dir).expanduser())
    install_dir = str(Path(args.install_dir).expanduser())

    # Determine if compiler is non-default
    feature = args.feature
    if args.compiler:
        system_cxx = detect_system_compiler()
        if Path(args.compiler).resolve() != Path(system_cxx).resolve():
            auto_suffix = compiler_suffix(args.compiler)
            if feature:
                feature = f"{feature}_{auto_suffix}"
            else:
                feature = auto_suffix
            print(f"Non-default compiler detected → feature suffix: {feature}", file=sys.stderr)

    # Parse extra cache variables
    extra_vars = {}
    for cv in args.cache_var:
        name, val = parse_cache_var(cv)
        extra_vars[name] = val

    # Load or create
    presets_path = Path(source_dir) / "CMakeUserPresets.json"
    data = load_or_create(presets_path)

    # Ensure arrays exist
    data.setdefault("configurePresets", [])
    data.setdefault("buildPresets", [])

    # Upsert base preset
    base = make_base_preset(args.compiler)
    upsert_preset(data["configurePresets"], base)

    # Upsert tag preset
    tag_preset = make_tag_preset(args.pkg, args.tag, build_dir, install_dir, feature, extra_vars)
    upsert_preset(data["configurePresets"], tag_preset)

    # Upsert build preset
    build_preset = make_build_preset(tag_preset["name"])
    upsert_preset(data["buildPresets"], build_preset)

    # Write
    output = json.dumps(data, indent=2) + "\n"
    if args.dry_run:
        print(output)
    else:
        # Backup existing
        if presets_path.exists():
            backup = presets_path.with_suffix(".json.bak")
            shutil.copy2(presets_path, backup)
            print(f"Backed up existing presets to {backup}", file=sys.stderr)
        with open(presets_path, "w") as f:
            f.write(output)
        print(f"Wrote {presets_path}", file=sys.stderr)
        print(f"Configure with:  cmake --preset {tag_preset['name']}", file=sys.stderr)


if __name__ == "__main__":
    main()
