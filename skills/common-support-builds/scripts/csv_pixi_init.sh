#!/usr/bin/env bash
# csv_pixi_init.sh — Initialize or update the Pixi environment in common_support_versions.
#
# Creates ~/src/common_support_versions/pixi.toml with conda-forge deps needed
# by the dependency graph, then runs `pixi install` to materialize them.
#
# Packages that fail to resolve (e.g., not available on this platform) are
# automatically retried without the failing package.
#
# Usage:
#   csv_pixi_init.sh                    # install all known deps
#   csv_pixi_init.sh --pkg ITK          # install only ITK's deps
#   csv_pixi_init.sh --pkg BRAINSTools  # install ITK+VTK deps recursively
#   csv_pixi_init.sh --update           # re-run pixi install on existing toml

set -euo pipefail

CSV_ROOT="${CSV_ROOT:-${HOME}/src/common_support_versions}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAPH="${SCRIPT_DIR}/../references/dependency-graph.json"
PIXI_TOML="${CSV_ROOT}/pixi.toml"

PKG=""
UPDATE_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pkg)        PKG="$2"; shift 2 ;;
        --update)     UPDATE_ONLY=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--pkg PKG] [--update]"
            exit 0 ;;
        *)  echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "${CSV_ROOT}"

if $UPDATE_ONLY && [[ -f "$PIXI_TOML" ]]; then
    echo ">>> Running pixi install on existing ${PIXI_TOML} ..."
    cd "${CSV_ROOT}" && pixi install
    exit 0
fi

# Detect current platform for pixi
PLATFORM=""
case "$(uname -s)-$(uname -m)" in
    Darwin-arm64)  PLATFORM="osx-arm64" ;;
    Darwin-x86_64) PLATFORM="osx-64" ;;
    Linux-x86_64)  PLATFORM="linux-64" ;;
    Linux-aarch64) PLATFORM="linux-aarch64" ;;
    *) echo "Unknown platform: $(uname -s)-$(uname -m)"; exit 1 ;;
esac
echo ">>> Detected platform: ${PLATFORM}"

# Extract conda package names from the dependency graph
echo ">>> Resolving conda-forge packages from dependency graph ..."
CONDA_PKGS=$(python3 -c "
import json, sys
graph = json.load(open('${GRAPH}'))
graph = {k:v for k,v in graph.items() if not k.startswith('_')}
pkgs = set()
def collect(pkg_name):
    info = graph.get(pkg_name, {})
    for dep_name, dep_info in info.get('deps', {}).items():
        conda = dep_info.get('conda_pkg')
        if conda:
            pkgs.add(conda)
        collect(dep_name)

if '${PKG}':
    collect('${PKG}')
else:
    for p in graph:
        collect(p)
for p in sorted(pkgs):
    print(p)
")

if [[ -z "$CONDA_PKGS" ]]; then
    echo "No conda-forge packages found in graph."
    exit 0
fi

echo "Packages to install:"
echo "$CONDA_PKGS" | sed 's/^/  - /'

# --- Generate pixi.toml and install with retry on failed packages ---

generate_toml() {
    local pkgs_to_install="$1"
    cat > "${PIXI_TOML}" << EOF
[workspace]
name = "common-support-versions"
description = "Pre-built dependencies for ITK/VTK/BRAINSTools/Slicer ecosystem"
channels = ["conda-forge"]
platforms = ["${PLATFORM}"]

[dependencies]
EOF
    while IFS= read -r pkg; do
        [[ -n "$pkg" ]] && echo "${pkg} = \"*\"" >> "${PIXI_TOML}"
    done <<< "$pkgs_to_install"

    # Build tools
    cat >> "${PIXI_TOML}" << 'TOOLS'

# Build tools
cmake = ">=3.22"
ninja = "*"
TOOLS
}

REMAINING_PKGS="$CONDA_PKGS"
FAILED_PKGS=""
MAX_RETRIES=5

for attempt in $(seq 1 $MAX_RETRIES); do
    generate_toml "$REMAINING_PKGS"
    echo ""
    echo ">>> Generated ${PIXI_TOML} (attempt ${attempt})"
    echo ">>> Running pixi install ..."

    # Remove lockfile to force fresh resolution
    rm -f "${CSV_ROOT}/pixi.lock"

    INSTALL_RC=0
    INSTALL_OUTPUT=$(cd "${CSV_ROOT}" && pixi install 2>&1) || INSTALL_RC=$?
    if [[ $INSTALL_RC -eq 0 ]]; then
        echo "$INSTALL_OUTPUT"
        echo ""
        echo "=== Pixi environment ready ==="
        echo "Prefix: ${CSV_ROOT}/.pixi/envs/default"
        if [[ -n "$FAILED_PKGS" ]]; then
            echo ""
            echo "WARNING: The following packages were unavailable on ${PLATFORM} and excluded:"
            echo "$FAILED_PKGS" | sed 's/^/  - /'
            echo "These will fall back to Homebrew or build-from-source in the resolver."
        fi
        exit 0
    else
        echo "$INSTALL_OUTPUT"
        # Extract the failing package name from the error
        FAIL_PKG=$(echo "$INSTALL_OUTPUT" | grep -oE 'No candidates were found for [a-zA-Z0-9_-]+' | head -1 | sed 's/No candidates were found for //')
        if [[ -z "$FAIL_PKG" ]]; then
            echo "ERROR: pixi install failed but could not identify failing package."
            echo "Check ${PIXI_TOML} manually."
            exit 1
        fi
        echo ""
        echo ">>> Package '${FAIL_PKG}' not available on ${PLATFORM}, removing and retrying..."
        FAILED_PKGS="${FAILED_PKGS}${FAILED_PKGS:+$'\n'}${FAIL_PKG}"
        REMAINING_PKGS=$(echo "$REMAINING_PKGS" | grep -v "^${FAIL_PKG}$")
        if [[ -z "$REMAINING_PKGS" ]]; then
            echo "ERROR: No packages remaining after removing failures."
            exit 1
        fi
    fi
done

echo "ERROR: Exceeded max retries (${MAX_RETRIES})."
exit 1
