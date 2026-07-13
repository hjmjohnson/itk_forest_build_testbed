#!/usr/bin/env python3
"""csv_show_dep_tree.py — Display a visual dependency tree with resolution status.

Shows a tree diagram of package dependencies with color-coded status
indicators showing where each dependency was resolved from.

Usage:
    # Show ITK's resolved dependency tree:
    python3 csv_show_dep_tree.py --pkg ITK --tag v5.4.2

    # Show BRAINSTools recursive tree:
    python3 csv_show_dep_tree.py --pkg BRAINSTools --tag main

    # Skip pixi/homebrew checks:
    python3 csv_show_dep_tree.py --pkg ITK --tag v5.4.2 --no-pixi --no-homebrew

    # Plain text (no ANSI colors):
    python3 csv_show_dep_tree.py --pkg ITK --tag v5.4.2 --no-color
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# Import the resolver
sys.path.insert(0, str(SCRIPT_DIR))
from csv_resolve_deps import (
    find_pixi_prefix,
    load_graph,
    resolve_deps,
)

# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------


class Colors:
    """ANSI escape codes for terminal colors."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    # Status colors
    CSV = "\033[38;5;39m"  # blue — installed in CSV
    PIXI = "\033[38;5;35m"  # green — from Pixi/conda-forge
    BREW = "\033[38;5;214m"  # orange — from Homebrew
    BUILD = "\033[38;5;196m"  # red — needs building
    INTERNAL = "\033[38;5;240m"  # gray — built internally by parent
    # Tree structure
    TREE = "\033[38;5;245m"  # gray for tree lines
    PKG = "\033[38;5;255m"  # white for package names
    VERSION = "\033[38;5;250m"  # light gray for version info

    @classmethod
    def disable(cls):
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith("_"):
                setattr(cls, attr, "")


STATUS_LABELS = {
    "installed": ("CSV", "installed in common_support_versions"),
    "pixi": ("PIXI", "conda-forge via Pixi"),
    "homebrew": ("BREW", "Homebrew"),
    "build": ("BUILD", "needs building from source"),
    "internal": ("INTERNAL", "built internally by parent"),
}

STATUS_ICONS = {
    "installed": "●",  # filled circle
    "pixi": "◆",  # diamond
    "homebrew": "▲",  # triangle
    "build": "✗",  # x mark
    "internal": "○",  # empty circle
}

STATUS_COLORS = {
    "installed": "CSV",
    "pixi": "PIXI",
    "homebrew": "BREW",
    "build": "BUILD",
    "internal": "INTERNAL",
}


def colorize(text: str, color_attr: str) -> str:
    """Apply ANSI color to text."""
    color = getattr(Colors, color_attr, "")
    return f"{color}{text}{Colors.RESET}" if color else text


def format_status(status: str, path: str | None = None) -> str:
    """Format a status label with icon and optional path."""
    icon = STATUS_ICONS.get(status, "?")
    label, desc = STATUS_LABELS.get(status, (status.upper(), ""))
    color_attr = STATUS_COLORS.get(status, "RESET")

    parts = [colorize(f"{icon} {label}", color_attr)]
    if path and status != "build":
        # Show abbreviated path
        home = str(Path.home())
        display_path = path.replace(home, "~")
        # Truncate long paths
        if len(display_path) > 50:
            display_path = "..." + display_path[-47:]
        parts.append(colorize(f" ({display_path})", "DIM"))

    return "".join(parts)


def print_tree(
    pkg: str,
    tag: str,
    graph: dict,
    deps_resolved: list[dict],
    indent: str = "",
    is_last: bool = True,
    seen: set | None = None,
):
    """Recursively print the dependency tree."""
    if seen is None:
        seen = set()

    # Print the root package
    pkg_info = graph.get(pkg)
    if not pkg_info:
        return

    dep_list = list(pkg_info.get("deps", {}).items())

    for i, (dep_name, dep_info) in enumerate(dep_list):
        is_last_dep = i == len(dep_list) - 1

        # Tree connector characters
        connector = "└── " if is_last_dep else "├── "
        child_indent = "    " if is_last_dep else "│   "

        # Find resolution status
        resolved = None
        for d in deps_resolved:
            if d["pkg"] == dep_name:
                resolved = d
                break

        status = resolved["status"] if resolved else "internal"
        path = resolved.get("path") if resolved else None
        category = dep_info.get("category", "")

        # Format the line
        tree_part = colorize(connector, "TREE")
        name_part = colorize(dep_name, "PKG")
        cat_part = colorize(f" [{category}]", "DIM") if category else ""
        status_part = format_status(status, path)

        print(f"{indent}{tree_part}{name_part}{cat_part}  {status_part}")

        # Recurse into this dep's own deps (if it has any in the graph)
        if dep_name not in seen:
            seen.add(dep_name)
            dep_graph = graph.get(dep_name)
            if dep_graph and dep_graph.get("deps"):
                print_tree(
                    dep_name,
                    tag,
                    graph,
                    deps_resolved,
                    indent=indent + colorize(child_indent, "TREE"),
                    is_last=is_last_dep,
                    seen=seen,
                )


def print_legend():
    """Print the status legend."""
    print()
    print(colorize("Legend:", "BOLD"))
    for status, (label, desc) in STATUS_LABELS.items():
        icon = STATUS_ICONS[status]
        color_attr = STATUS_COLORS[status]
        print(f"  {colorize(f'{icon} {label:<10}', color_attr)} {desc}")
    print()


def print_summary(deps: list[dict]):
    """Print a summary of resolution counts."""
    counts = {}
    for d in deps:
        s = d["status"]
        counts[s] = counts.get(s, 0) + 1

    total = len(deps)
    parts = []
    for status in ["installed", "pixi", "homebrew", "build"]:
        n = counts.get(status, 0)
        if n > 0:
            color_attr = STATUS_COLORS[status]
            label = STATUS_LABELS[status][0]
            parts.append(colorize(f"{n} {label}", color_attr))

    print(colorize(f"Total: {total} dependencies  ", "BOLD") + "  ".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Display dependency tree with resolution status")
    parser.add_argument("--pkg", required=True, help="Target package")
    parser.add_argument("--tag", required=True, help="Git tag")
    parser.add_argument("--no-pixi", action="store_true", help="Skip Pixi check")
    parser.add_argument("--no-homebrew", action="store_true", help="Skip Homebrew check")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument("--no-legend", action="store_true", help="Skip legend")
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    graph = load_graph()
    use_pixi = not args.no_pixi
    use_homebrew = not args.no_homebrew
    pixi_prefix = find_pixi_prefix() if use_pixi else None

    deps = resolve_deps(args.pkg, args.tag, graph, use_pixi, use_homebrew, pixi_prefix)

    # Header
    print()
    header = f"{colorize(args.pkg, 'BOLD')} {colorize(args.tag, 'VERSION')}"
    if pixi_prefix:
        header += colorize("  (Pixi: ~/.../envs/default)", "DIM")
    print(header)

    # Tree
    print_tree(args.pkg, args.tag, graph, deps)

    # Summary
    print()
    print_summary(deps)

    if not args.no_legend:
        print_legend()


if __name__ == "__main__":
    main()
