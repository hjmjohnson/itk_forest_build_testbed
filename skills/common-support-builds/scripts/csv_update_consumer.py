#!/usr/bin/env python3
"""csv_update_consumer.py — Update a consumer project's CMakeUserPresets.json
to use a pre-built package from common_support_versions.

Usage:
    python3 csv_update_consumer.py \
        --consumer-source ~/src/BRAINSTools \
        --preset-name base_language \
        --pkg ITK --tag v5.4.2 \
        [--feature shared] \
        [--use-system]

This adds/updates the ITK_DIR (or <PKG>_DIR) and optionally the
USE_SYSTEM_<PKG> variable in the named consumer preset.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# Map package names to their CMake config subdirectory under the install prefix.
# Glob patterns are resolved at runtime; first match wins.
PKG_CMAKE_SUBDIR = {
    "ITK": "lib/cmake/ITK-*",
    "VTK": "lib/cmake/vtk-*",
    "Eigen3": "share/eigen3/cmake",
    "DCMTK": "lib/cmake/dcmtk",
    "HDF5": "share/cmake/hdf5",
    "FFTW": "lib/cmake/fftw3",
    "TBB": "lib/cmake/TBB",
    "GDCM": "lib/gdcm-*",
    "ZLIB": "lib/cmake/zlib",
    "PNG": "lib/cmake/png",
    "JPEG": "lib/cmake/jpeg",
    "TIFF": "lib/cmake/tiff",
}

# Map package names to their USE_SYSTEM variable name (ITK-specific naming).
USE_SYSTEM_VAR = {
    "ITK": "USE_SYSTEM_ITK",
    "VTK": "USE_SYSTEM_VTK",
    "Eigen3": "ITK_USE_SYSTEM_EIGEN",
    "DCMTK": "ITK_USE_SYSTEM_DCMTK",
    "HDF5": "ITK_USE_SYSTEM_HDF5",
    "FFTW": "ITK_USE_SYSTEM_FFTW",
    "TBB": "USE_SYSTEM_TBB",
    "GDCM": "ITK_USE_SYSTEM_GDCM",
    "ZLIB": "ITK_USE_SYSTEM_ZLIB",
    "PNG": "ITK_USE_SYSTEM_PNG",
    "JPEG": "ITK_USE_SYSTEM_JPEG",
    "TIFF": "ITK_USE_SYSTEM_TIFF",
}

DIR_VAR = {
    "ITK": "ITK_DIR",
    "VTK": "VTK_DIR",
    "Eigen3": "Eigen3_DIR",
    "DCMTK": "DCMTK_DIR",
    "HDF5": "HDF5_DIR",
    "FFTW": "FFTW_DIR",
    "TBB": "TBB_DIR",
    "GDCM": "GDCM_DIR",
    "ZLIB": "ZLIB_ROOT",
    "PNG": "PNG_DIR",
    "JPEG": "JPEG_DIR",
    "TIFF": "TIFF_DIR",
}


def resolve_cmake_dir(install_dir: str, pkg: str) -> str:
    """Resolve the actual CMake config directory from the install prefix."""
    pattern = PKG_CMAKE_SUBDIR.get(pkg, f"lib/cmake/{pkg.lower()}")
    install_path = Path(install_dir)
    matches = sorted(install_path.glob(pattern))
    if matches:
        return str(matches[-1])  # latest version
    # Fallback: return the pattern as-is (user can fix later)
    return str(install_path / pattern)


def main():
    parser = argparse.ArgumentParser(
        description="Update consumer CMakeUserPresets.json to use a CSV package"
    )
    parser.add_argument(
        "--consumer-source", required=True, help="Consumer project source directory"
    )
    parser.add_argument(
        "--preset-name", required=True, help="Name of the consumer preset to update"
    )
    parser.add_argument("--pkg", required=True, help="Package name")
    parser.add_argument("--tag", required=True, help="Git tag of the installed package")
    parser.add_argument("--feature", default=None, help="Feature suffix")
    parser.add_argument("--use-system", action="store_true", help="Also set USE_SYSTEM_<PKG>=ON")
    parser.add_argument(
        "--csv-root",
        default=str(Path.home() / "src" / "common_support_versions"),
        help="Root of common_support_versions tree",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    consumer_dir = Path(args.consumer_source).expanduser()
    presets_path = consumer_dir / "CMakeUserPresets.json"

    if not presets_path.exists():
        print(f"ERROR: {presets_path} does not exist.", file=sys.stderr)
        print("Create a CMakeUserPresets.json in the consumer project first.", file=sys.stderr)
        sys.exit(1)

    with open(presets_path) as f:
        data = json.load(f)

    # Find the target preset
    target = None
    for p in data.get("configurePresets", []):
        if p.get("name") == args.preset_name:
            target = p
            break

    if target is None:
        print(f"ERROR: Preset '{args.preset_name}' not found in {presets_path}", file=sys.stderr)
        print(
            f"Available presets: {[p['name'] for p in data.get('configurePresets', [])]}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Determine install directory
    suffix = f"_{args.feature}" if args.feature else ""
    install_dir = Path(args.csv_root) / args.pkg / f"installed_{args.tag}{suffix}"

    if not install_dir.is_dir():
        print(f"WARNING: Install directory does not exist yet: {install_dir}", file=sys.stderr)

    # Resolve CMake config dir
    cmake_dir = resolve_cmake_dir(str(install_dir), args.pkg)
    dir_var = DIR_VAR.get(args.pkg, f"{args.pkg}_DIR")

    target.setdefault("cacheVariables", {})
    target["cacheVariables"][dir_var] = {"type": "PATH", "value": cmake_dir}
    print(f"  Set {dir_var} = {cmake_dir}", file=sys.stderr)

    if args.use_system:
        use_var = USE_SYSTEM_VAR.get(args.pkg, f"USE_SYSTEM_{args.pkg}")
        target["cacheVariables"][use_var] = {"type": "BOOL", "value": "ON"}
        print(f"  Set {use_var} = ON", file=sys.stderr)

    output = json.dumps(data, indent=2) + "\n"
    if args.dry_run:
        print(output)
    else:
        backup = presets_path.with_suffix(".json.bak")
        shutil.copy2(presets_path, backup)
        with open(presets_path, "w") as f:
            f.write(output)
        print(f"Updated {presets_path}", file=sys.stderr)
        print(f"Backup at {backup}", file=sys.stderr)


if __name__ == "__main__":
    main()
