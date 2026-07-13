#!/usr/bin/env python3
"""Consolidate multiple ITK remote module repos into a single category repo.

Usage:
    consolidate_repos.py <category> <output_dir> <module:url> [<module:url> ...]

    consolidate_repos.py Analysis /tmp/ITKRemoteAnalysis \
        TextureFeatures:https://github.com/InsightSoftwareConsortium/ITKTextureFeatures.git \
        BoneMorphometry:https://github.com/InsightSoftwareConsortium/ITKBoneMorphometry.git

For modules from an ITK PR branch (not yet in their own repo):
    StructuralSimilarity:itk-pr:<branch>:<path_prefix>

Options:
    --itk-source <path>   Path to ITK source tree (for extracting compliance reports
                          and ITK PR branches). Default: auto-detect from cwd.
    --work-dir <path>     Temp working directory. Default: <output_dir>/.consolidation-work
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, *, cwd=None, check=True, capture=False):
    """Run a shell command, printing it for visibility."""
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    kwargs = {"cwd": cwd, "check": check}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)


def parse_module_spec(spec):
    """Parse 'Module:url' or 'Module:itk-pr:branch:path' into a dict."""
    parts = spec.split(":", 1)
    if len(parts) != 2:
        sys.exit(
            f"ERROR: Invalid module spec '{spec}'. Expected Module:url or Module:itk-pr:branch:path"
        )
    name = parts[0]
    rest = parts[1]

    if rest.startswith("itk-pr:"):
        itk_parts = rest.split(":", 2)
        if len(itk_parts) != 3:
            sys.exit(f"ERROR: itk-pr spec needs 'itk-pr:<branch>:<path>': {spec}")
        return {"name": name, "type": "itk-pr", "branch": itk_parts[1], "path": itk_parts[2]}
    else:
        return {"name": name, "type": "git", "url": rest}


def clone_and_filter(module, work_dir):
    """Clone a module repo and rewrite history to subdirectory."""
    name = module["name"]
    clone_dir = work_dir / f"clone-{name}"

    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    if module["type"] == "git":
        print(f"\n{'='*60}")
        print(f"Cloning {name} from {module['url']}")
        print(f"{'='*60}")
        run(["git", "clone", "--no-tags", module["url"], str(clone_dir)])
    elif module["type"] == "itk-pr":
        print(f"\n{'='*60}")
        print(f"Extracting {name} from ITK branch {module['branch']}")
        print(f"{'='*60}")
        # Create a synthetic repo from the ITK PR files
        extract_from_itk_pr(module, clone_dir, work_dir)
    else:
        sys.exit(f"Unknown module type: {module['type']}")

    # Rewrite all paths to be under <ModuleName>/
    print(f"  Rewriting history: all paths -> {name}/")
    run(
        ["git", "filter-repo", "--to-subdirectory-filter", f"{name}/", "--force"],
        cwd=clone_dir,
    )

    # The commit-map is at .git/filter-repo/commit-map
    commit_map_path = clone_dir / ".git" / "filter-repo" / "commit-map"
    return clone_dir, commit_map_path


def extract_from_itk_pr(module, clone_dir, work_dir):
    """Extract module files from an ITK PR branch into a standalone repo."""
    name = module["name"]
    branch = module["branch"]
    path_prefix = module["path"].rstrip("/")

    # Find ITK source
    itk_source = find_itk_source()
    if not itk_source:
        sys.exit("ERROR: Cannot find ITK source tree. Pass --itk-source or run from ITK dir.")

    # Create a new repo with just the relevant files from the ITK PR branch
    clone_dir.mkdir(parents=True)
    run(["git", "init"], cwd=clone_dir)

    # Use git archive from the ITK repo to extract just the module files
    # First, fetch the PR branch if needed
    result = run(
        ["git", "rev-parse", "--verify", branch],
        cwd=itk_source,
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        # Try fetching from origin
        run(["git", "fetch", "origin", branch], cwd=itk_source, check=False)

    # Get the list of commits that touch the path prefix on that branch
    result = run(
        ["git", "log", "--format=%H", "--reverse", branch, "--", path_prefix],
        cwd=itk_source,
        capture=True,
    )
    commits = result.stdout.strip().split("\n")
    if not commits or commits == [""]:
        sys.exit(f"ERROR: No commits found on branch {branch} for path {path_prefix}")

    print(f"  Found {len(commits)} commits touching {path_prefix}")

    # For each commit, extract the files and replay as a new commit
    for commit_hash in commits:
        # Get commit metadata
        meta = (
            run(
                ["git", "log", "-1", "--format=%an%n%ae%n%at%n%s%n%b", commit_hash],
                cwd=itk_source,
                capture=True,
            )
            .stdout.strip()
            .split("\n", 4)
        )
        author_name = meta[0]
        author_email = meta[1]
        author_date = meta[2]
        subject = meta[3]
        body = meta[4] if len(meta) > 4 else ""

        # Extract files at this commit
        result = run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "-r",
                "--name-only",
                commit_hash,
                "--",
                path_prefix,
            ],
            cwd=itk_source,
            capture=True,
        )
        files = [f for f in result.stdout.strip().split("\n") if f]
        if not files:
            continue

        for filepath in files:
            # Strip the path prefix to get the relative path within the module
            rel_path = filepath[len(path_prefix) :].lstrip("/")
            dest = clone_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists at this commit (could be deleted)
            check = run(
                ["git", "cat-file", "-t", f"{commit_hash}:{filepath}"],
                cwd=itk_source,
                check=False,
                capture=True,
            )
            if check.returncode == 0:
                # Extract file content
                content = run(
                    ["git", "show", f"{commit_hash}:{filepath}"],
                    cwd=itk_source,
                    capture=True,
                )
                dest.write_text(content.stdout)
                run(["git", "add", str(rel_path)], cwd=clone_dir)
            else:
                # File was deleted
                if dest.exists():
                    run(["git", "rm", "-f", str(rel_path)], cwd=clone_dir, check=False)

        # Commit with original metadata
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_AUTHOR_DATE": f"@{author_date}",
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
            "GIT_COMMITTER_DATE": f"@{author_date}",
        }
        msg = f"{subject}\n\n{body}".strip() if body else subject
        # Check if there's anything to commit
        status = run(["git", "status", "--porcelain"], cwd=clone_dir, capture=True)
        if status.stdout.strip():
            subprocess.run(
                ["git", "commit", "-m", msg, "--allow-empty-message"],
                cwd=clone_dir,
                env=env,
                check=True,
            )


def find_itk_source():
    """Find ITK source tree."""
    candidates = [
        Path("/Users/johnsonhj/src/ITK"),
        Path.cwd(),
        Path.cwd().parent / "ITK",
    ]
    for p in candidates:
        if (p / "Modules" / "Remote").exists():
            return p
    return None


def extract_compliance_report(itk_source, module_name):
    """Extract the compliance grading report from .remote.cmake."""
    cmake_file = itk_source / "Modules" / "Remote" / f"{module_name}.remote.cmake"
    if not cmake_file.exists():
        return None

    lines = cmake_file.read_text().splitlines()
    report_lines = []
    for line in lines:
        if line.startswith("#--"):
            # Strip the "#-- " or "#--" prefix
            content = line[3:]
            if content.startswith(" "):
                content = content[1:]
            report_lines.append(content)

    if not report_lines:
        return None

    return "\n".join(report_lines) + "\n"


def merge_into_target(target_dir, clone_dir, module_name):
    """Merge a rewritten module repo into the target category repo."""
    print(f"\n  Merging {module_name} into target repo...")
    remote_name = f"source-{module_name}"

    # Add as remote and fetch
    run(["git", "remote", "add", remote_name, str(clone_dir)], cwd=target_dir)
    run(["git", "fetch", remote_name], cwd=target_dir)

    # Get the default branch of the source
    result = run(
        ["git", "rev-parse", "--abbrev-ref", f"{remote_name}/HEAD"],
        cwd=target_dir,
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        # Try common branch names
        for branch in ["main", "master"]:
            check = run(
                ["git", "rev-parse", "--verify", f"{remote_name}/{branch}"],
                cwd=target_dir,
                check=False,
                capture=True,
            )
            if check.returncode == 0:
                source_branch = f"{remote_name}/{branch}"
                break
        else:
            sys.exit(f"ERROR: Cannot find default branch for {module_name}")
    else:
        source_branch = result.stdout.strip()

    # Merge with allow-unrelated-histories
    run(
        [
            "git",
            "merge",
            source_branch,
            "--allow-unrelated-histories",
            "-m",
            f"Merge {module_name} history into ITKRemote category repo\n\n"
            f"Imported from: {clone_dir}\n"
            f"Original module: {module_name}",
        ],
        cwd=target_dir,
    )

    # Clean up remote
    run(["git", "remote", "remove", remote_name], cwd=target_dir)


def main():
    parser = argparse.ArgumentParser(description="Consolidate ITK remote modules")
    parser.add_argument("category", help="Category name (e.g., Analysis, IO, Filtering)")
    parser.add_argument("output_dir", help="Path for the new category repo")
    parser.add_argument(
        "modules", nargs="+", help="Module specs: Name:url or Name:itk-pr:branch:path"
    )
    parser.add_argument("--itk-source", help="Path to ITK source tree")
    parser.add_argument("--work-dir", help="Temp working directory")
    args = parser.parse_args()

    category = args.category
    output_dir = Path(args.output_dir).resolve()
    work_dir = (
        Path(args.work_dir).resolve()
        if args.work_dir
        else output_dir.parent / ".consolidation-work"
    )
    itk_source = Path(args.itk_source) if args.itk_source else find_itk_source()

    # Parse module specs
    modules = [parse_module_spec(spec) for spec in args.modules]

    print(f"Category: {category}")
    print(f"Output:   {output_dir}")
    print(f"Work dir: {work_dir}")
    print(f"ITK src:  {itk_source}")
    print(f"Modules:  {[m['name'] for m in modules]}")
    print()

    # Create work directory
    work_dir.mkdir(parents=True, exist_ok=True)

    # Create target repo
    if output_dir.exists():
        sys.exit(f"ERROR: Output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    run(["git", "init", "-b", "main"], cwd=output_dir)

    # Initial commit with LICENSE and .clang-format
    license_src = itk_source / "LICENSE" if itk_source else None
    if license_src and license_src.exists():
        shutil.copy2(license_src, output_dir / "LICENSE")
    else:
        (output_dir / "LICENSE").write_text(
            "Apache License 2.0\nSee https://www.apache.org/licenses/LICENSE-2.0\n"
        )

    clang_format_src = itk_source / ".clang-format" if itk_source else None
    if clang_format_src and clang_format_src.exists():
        shutil.copy2(clang_format_src, output_dir / ".clang-format")

    # Create README
    module_list = "\n".join(f"- **{m['name']}**" for m in modules)
    (output_dir / "README.md").write_text(
        f"# ITKRemote{category}\n\n"
        f"Consolidated ITK remote modules for the {category} domain.\n\n"
        f"## Modules\n\n{module_list}\n\n"
        f"## Building\n\n"
        f"These modules are designed to be built as part of ITK via:\n"
        f"```\n"
        f"cmake -DITKGroup_Remote_{category}=ON ...\n"
        f"```\n\n"
        f"Individual modules can be toggled with `Module_<name>=ON/OFF`.\n\n"
        f"## License\n\nApache 2.0\n"
    )

    run(["git", "add", "-A"], cwd=output_dir)
    run(
        [
            "git",
            "commit",
            "-m",
            f"Initial commit: ITKRemote{category} scaffold\n\n"
            f"Category repo for {len(modules)} consolidated remote modules.",
        ],
        cwd=output_dir,
    )

    # Process each module
    commit_maps_dir = output_dir / "commit-maps"
    commit_maps_dir.mkdir()
    combined_map = []

    for module in modules:
        name = module["name"]

        # Clone and rewrite history
        clone_dir, commit_map_path = clone_and_filter(module, work_dir)

        # Save commit map
        if commit_map_path.exists():
            map_dest = commit_maps_dir / f"{name}-commit-map.tsv"
            shutil.copy2(commit_map_path, map_dest)

            # Read and accumulate for combined map
            with open(commit_map_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        combined_map.append((name, parts[0], parts[1]))

        # Merge into target
        merge_into_target(output_dir, clone_dir, name)

        # Extract and add compliance report
        if itk_source:
            report = extract_compliance_report(itk_source, name)
            if report:
                compliance_file = output_dir / name / "COMPLIANCE.md"
                compliance_file.write_text(report)
                run(["git", "add", str(compliance_file.relative_to(output_dir))], cwd=output_dir)
                run(
                    [
                        "git",
                        "commit",
                        "-m",
                        f"DOC: Add compliance grading report for {name}\n\n"
                        f"Extracted from ITK Modules/Remote/{name}.remote.cmake",
                    ],
                    cwd=output_dir,
                )

    # Write combined commit map
    combined_path = commit_maps_dir / "combined-commit-map.tsv"
    with open(combined_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["module", "old_hash", "new_hash"])
        for row in combined_map:
            writer.writerow(row)

    # Commit the maps
    run(["git", "add", "commit-maps/"], cwd=output_dir)
    run(
        [
            "git",
            "commit",
            "-m",
            f"DOC: Add commit hash mappings for {len(modules)} consolidated modules\n\n"
            f"Maps original commit hashes to new hashes after history rewrite.\n"
            f"For tracing: old_hash -> new_hash per module.",
        ],
        cwd=output_dir,
    )

    # Summary
    result = run(["git", "log", "--oneline", "--graph", "--all"], cwd=output_dir, capture=True)
    total_commits = run(["git", "rev-list", "--count", "HEAD"], cwd=output_dir, capture=True)

    print(f"\n{'='*60}")
    print(f"SUCCESS: ITKRemote{category} created at {output_dir}")
    print(f"  Total commits: {total_commits.stdout.strip()}")
    print(f"  Modules: {len(modules)}")
    print(f"  Commit maps: {commit_maps_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
