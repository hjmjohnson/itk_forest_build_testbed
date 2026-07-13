#!/usr/bin/env python3
"""csv_resolve_deps.py — Resolve and display the dependency build order for a
package in common_support_versions.

Given a target package (e.g., ITK), walks the dependency graph and prints
a topologically sorted build plan. For each dependency, reports whether it
is already installed in common_support_versions, available via Pixi (conda-forge),
available via Homebrew, or needs to be built from source.

Resolution priority: installed CSV > pixi > homebrew > build from source.

Usage:
    # Show what ITK v5.4.2 needs (pixi preferred, homebrew fallback):
    python3 csv_resolve_deps.py --pkg ITK --tag v5.4.2

    # Disable pixi, only homebrew:
    python3 csv_resolve_deps.py --pkg ITK --tag v5.4.2 --no-pixi

    # Disable both pixi and homebrew (only CSV installs or build):
    python3 csv_resolve_deps.py --pkg ITK --tag v5.4.2 --no-pixi --no-homebrew

    # Show plan for BRAINSTools (recursive: BRAINSTools → ITK → Eigen, ZLIB, ...):
    python3 csv_resolve_deps.py --pkg BRAINSTools --tag main

    # Generate CMake cache vars for satisfied deps:
    python3 csv_resolve_deps.py --pkg ITK --tag v5.4.2 --emit-preset-vars

    # Full recursive build plan (dry-run):
    python3 csv_resolve_deps.py --pkg ITK --tag v5.4.2 --build-plan
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
GRAPH_PATH = SCRIPT_DIR.parent / "references" / "dependency-graph.json"
CSV_ROOT = Path(
    os.environ.get("CSV_ROOT", Path.home() / "src" / "common_support_versions")
).expanduser()


def load_graph() -> dict:
    with open(GRAPH_PATH) as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Provider checks
# ---------------------------------------------------------------------------


def find_pixi_prefix() -> str | None:
    """Find the Pixi environment prefix in common_support_versions.

    Checks for ~/src/common_support_versions/.pixi/envs/default/
    which is where `pixi install` materializes the environment.
    """
    candidate = CSV_ROOT / ".pixi" / "envs" / "default"
    if candidate.is_dir():
        return str(candidate)
    return None


def is_pixi_pkg_available(conda_pkg: str, pixi_prefix: str) -> str | None:
    """Check if a conda-forge package is installed in the Pixi environment.

    Returns the Pixi prefix if the package is present (its libs/headers
    are in the prefix's lib/ and include/ dirs).
    """
    if not pixi_prefix:
        return None

    prefix = Path(pixi_prefix)

    # conda packages install into the environment prefix directly.
    # Check for common indicators that the package is present.
    # Strategy: look for cmake config, pkg-config, or library files.
    pkg_lower = conda_pkg.lower().replace("-", "")

    # Check cmake config dirs
    cmake_dir = prefix / "lib" / "cmake"
    if cmake_dir.is_dir():
        for d in cmake_dir.iterdir():
            if pkg_lower in d.name.lower().replace("-", ""):
                return str(prefix)

    # Check pkg-config
    pc_dir = prefix / "lib" / "pkgconfig"
    if pc_dir.is_dir():
        for f in pc_dir.iterdir():
            if pkg_lower in f.name.lower().replace("-", ""):
                return str(prefix)

    # Check for libraries directly
    lib_dir = prefix / "lib"
    if lib_dir.is_dir():
        for f in lib_dir.iterdir():
            if f.name.startswith("lib") and pkg_lower in f.name.lower().replace("-", ""):
                return str(prefix)

    # Check for headers (header-only libs like eigen)
    include_dir = prefix / "include"
    if include_dir.is_dir():
        for d in include_dir.iterdir():
            if pkg_lower in d.name.lower().replace("-", ""):
                return str(prefix)

    # Special cases
    special = {
        "eigen": prefix / "include" / "eigen3",
        "swig": prefix / "bin" / "swig",
        "castxml": prefix / "bin" / "castxml",
        "gtest": prefix / "lib" / "cmake" / "GTest",
        "tbb-devel": prefix / "lib" / "cmake" / "TBB",
        "libjpeg-turbo": (
            prefix / "lib" / "libjpeg.dylib"
            if sys.platform == "darwin"
            else prefix / "lib" / "libjpeg.so"
        ),
        "double-conversion": prefix / "lib" / "cmake" / "double-conversion",
    }
    check = special.get(conda_pkg)
    if check and check.exists():
        return str(prefix)

    return None


def is_homebrew_available(homebrew_pkg: str) -> str | None:
    """Check if a Homebrew package is installed, return its prefix."""
    try:
        result = subprocess.run(
            ["brew", "--prefix", homebrew_pkg], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            prefix = result.stdout.strip()
            if Path(prefix).is_dir():
                return prefix
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


def resolve_deps(
    pkg: str,
    tag: str,
    graph: dict,
    use_pixi: bool = True,
    use_homebrew: bool = True,
    pixi_prefix: str | None = None,
    visited: set | None = None,
    order: list | None = None,
) -> list[dict]:
    """Recursively resolve dependencies in topological order (leaves first).

    Resolution priority: installed CSV > pixi > homebrew > build from source.
    """
    if visited is None:
        visited = set()
    if order is None:
        order = []

    if pkg in visited:
        return order
    visited.add(pkg)

    pkg_info = graph.get(pkg)
    if not pkg_info:
        return order

    for dep_name, dep_info in pkg_info.get("deps", {}).items():
        # Recurse into the dependency's own deps
        resolve_deps(dep_name, tag, graph, use_pixi, use_homebrew, pixi_prefix, visited, order)

        # Skip if already resolved from a different parent
        if any(e["pkg"] == dep_name for e in order):
            continue

        entry = {
            "pkg": dep_name,
            "parent": pkg,
            "use_system_var": dep_info["use_system_var"],
            "find_var": dep_info["find_var"],
            "category": dep_info["category"],
            "status": "build",
            "path": None,
        }

        # 1. Check installed in common_support_versions
        csv_pkg_dir = CSV_ROOT / dep_name
        if csv_pkg_dir.is_dir():
            for d in sorted(csv_pkg_dir.iterdir()):
                if d.name.startswith("installed_") and d.is_dir():
                    cmake_files = list(d.rglob("*Config.cmake")) + list(d.rglob("*-config.cmake"))
                    if cmake_files:
                        entry["status"] = "installed"
                        entry["path"] = str(d)
                        break

        # 2. Check Pixi environment (preferred over Homebrew)
        if entry["status"] == "build" and use_pixi and pixi_prefix:
            conda_pkg = dep_info.get("conda_pkg")
            if conda_pkg:
                pixi_path = is_pixi_pkg_available(conda_pkg, pixi_prefix)
                if pixi_path:
                    entry["status"] = "pixi"
                    entry["path"] = pixi_path

        # 3. Check Homebrew (fallback)
        if entry["status"] == "build" and use_homebrew:
            homebrew_pkg = dep_info.get("homebrew_pkg")
            if homebrew_pkg:
                brew_path = is_homebrew_available(homebrew_pkg)
                if brew_path:
                    entry["status"] = "homebrew"
                    entry["path"] = brew_path

        order.append(entry)

    return order


def emit_preset_vars(deps: list[dict]) -> dict:
    """Generate CMake cache variable dict for available deps."""
    variables = {}
    for dep in deps:
        if dep["status"] in ("installed", "pixi", "homebrew"):
            variables[dep["use_system_var"]] = {"type": "BOOL", "value": "ON"}
            if dep["path"] and dep["find_var"]:
                variables[dep["find_var"]] = {"type": "PATH", "value": dep["path"]}
    return variables


def main():
    parser = argparse.ArgumentParser(
        description="Resolve dependency build order for common_support_versions"
    )
    parser.add_argument("--pkg", required=True, help="Target package")
    parser.add_argument("--tag", required=True, help="Git tag")
    parser.add_argument("--no-pixi", action="store_true", help="Skip Pixi environment check")
    parser.add_argument("--no-homebrew", action="store_true", help="Skip Homebrew check")
    parser.add_argument(
        "--emit-preset-vars",
        action="store_true",
        help="Output CMake preset cacheVariables JSON for satisfied deps",
    )
    parser.add_argument(
        "--build-plan", action="store_true", help="Show full build plan with commands"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of table")
    args = parser.parse_args()

    graph = load_graph()

    use_pixi = not args.no_pixi
    use_homebrew = not args.no_homebrew
    pixi_prefix = find_pixi_prefix() if use_pixi else None

    if use_pixi and not pixi_prefix:
        print(
            f"(Pixi environment not found at {CSV_ROOT}/. Run csv_pixi_init.sh to create it.)",
            file=sys.stderr,
        )

    deps = resolve_deps(args.pkg, args.tag, graph, use_pixi, use_homebrew, pixi_prefix)

    if args.json:
        print(json.dumps(deps, indent=2))
        return

    if args.emit_preset_vars:
        variables = emit_preset_vars(deps)
        print(json.dumps(variables, indent=2))
        return

    # Print table
    print(f"\nDependency resolution for {args.pkg} {args.tag}")
    if pixi_prefix:
        print(f"  Pixi env: {pixi_prefix}")
    print(f"{'='*78}")
    print(f"{'Package':<20} {'Status':<12} {'Category':<12} {'Path/Action'}")
    print(f"{'-'*20} {'-'*12} {'-'*12} {'-'*34}")

    needs_build = []
    for dep in deps:
        status_icon = {
            "installed": "CSV",
            "pixi": "PIXI",
            "homebrew": "BREW",
            "build": "BUILD",
        }[dep["status"]]
        path_str = dep.get("path") or "(needs build)"
        print(f"{dep['pkg']:<20} {status_icon:<12} {dep['category']:<12} {path_str}")
        if dep["status"] == "build":
            needs_build.append(dep)

    print(f"\n{'='*78}")

    if needs_build:
        print(f"\n{len(needs_build)} package(s) need building:")
        for dep in needs_build:
            print(f"  - {dep['pkg']} ({dep['category']})")

        if args.build_plan:
            print("\nBuild plan (execute in order):")
            print(f"{'-'*50}")
            for i, dep in enumerate(needs_build, 1):
                dep_graph = graph.get(dep["pkg"], {})
                repo = dep_graph.get("repo", f"<unknown repo for {dep['pkg']}>")
                print(f"\n  Step {i}: Build {dep['pkg']}")
                print(f"    csv_scaffold.sh {dep['pkg']} <TAG> --repo {repo}")
                print(f"    csv_gen_presets.py --pkg {dep['pkg']} --tag <TAG> ...")
                print(f"    cmake --preset csv_{dep['pkg']}_<TAG>")
                print(f"    cmake --build --preset csv_{dep['pkg']}_<TAG>")
                print("    cmake --install <bld_dir>")
    else:
        print("\nAll dependencies satisfied! No builds needed.")
        print("\nTo generate CMake vars, run:")
        print(f"  python3 csv_resolve_deps.py --pkg {args.pkg} --tag {args.tag} --emit-preset-vars")


if __name__ == "__main__":
    main()
