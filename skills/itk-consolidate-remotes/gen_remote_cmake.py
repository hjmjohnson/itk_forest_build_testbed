#!/usr/bin/env python3
"""Generate an ITK .remote.cmake file for a consolidated category repo.

Usage:
    gen_remote_cmake.py <category> <repo_url> <git_tag> [--output <path>]

Example:
    gen_remote_cmake.py Analysis \
        https://github.com/InsightSoftwareConsortium/ITKRemoteAnalysis.git \
        abc123def456 \
        --output Modules/Remote/ITKRemoteAnalysis.remote.cmake
"""

import argparse
from pathlib import Path


def get_modules_in_repo(repo_path):
    """Discover modules by finding itk-module.cmake files."""
    repo = Path(repo_path)
    modules = []
    for cmake_file in sorted(repo.rglob("itk-module.cmake")):
        # Skip if it's in a nested build/test directory
        rel = cmake_file.relative_to(repo)
        parts = rel.parts
        if len(parts) == 2 and parts[1] == "itk-module.cmake":
            modules.append(parts[0])
    return modules


def main():
    parser = argparse.ArgumentParser(description="Generate .remote.cmake for category repo")
    parser.add_argument("category", help="Category name (e.g., Analysis)")
    parser.add_argument("repo_url", help="Git repository URL")
    parser.add_argument("git_tag", help="Git commit hash or tag")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--repo-path", help="Local repo path to discover modules")
    parser.add_argument("--modules", nargs="*", help="Explicit module list (if no local repo)")
    args = parser.parse_args()

    category = args.category
    repo_url = args.repo_url
    git_tag = args.git_tag

    # Discover or use explicit module list
    if args.repo_path:
        modules = get_modules_in_repo(args.repo_path)
    elif args.modules:
        modules = args.modules
    else:
        modules = []

    module_list = ", ".join(modules) if modules else "<modules>"

    content = f"""# ITKRemote{category} — consolidated remote module group
#
# This fetches the ITKRemote{category} category repository which contains
# multiple ITK remote modules: {module_list}
#
# Enable with: cmake -DITKGroup_Remote_{category}=ON
# Individual modules toggleable via Module_<name>=ON/OFF
#
# See https://github.com/InsightSoftwareConsortium/ITK/issues/6060

itk_fetch_module_group({category}
  "Consolidated remote modules for {category.lower()} domain: {module_list}"
  GIT_REPOSITORY {repo_url}
  GIT_TAG {git_tag}
)
"""

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        print(f"Written to {output_path}")
    else:
        print(content)


if __name__ == "__main__":
    main()
