#!/usr/bin/env python3
"""Generate the node-specific config.sh from config.json.in.

The template (config.json.in, tracked) declares each build knob; this script
resolves it on THIS machine and writes config.sh (git-ignored), which the bash
engine `source`s. Resolution is dependency-heavy (globbing, path existence) so
it lives here in Python and runs once; the generated config.sh is plain shell.

Usage:
  python3 bin/config.py generate [--force]   # write config.sh (default cmd)
  python3 bin/config.py --check              # exit 1 if a required key is unresolved

Version-manifest subcommands (read versions.toml, the source of truth):
  python3 bin/config.py consumers            # emit  name|url|branch  rows
  python3 bin/config.py remotes              # emit  name|url|heap(0/1)  rows
  python3 bin/config.py get <dotted.key>     # print one scalar, e.g. subbuild.Slicer.ITK_GIT_TAG
  python3 bin/config.py manifest <FOREST>    # write <FOREST>/manifest.toml from live worktrees
"""
import sys, os, json, glob, subprocess

try:
    import tomllib
except ModuleNotFoundError:  # py<3.11
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "config.json.in")
OUT = os.path.join(ROOT, "config.sh")
VERSIONS = os.path.join(ROOT, "versions.toml")
SENTINEL = "__SET_MANUALLY__"


def expand(s):
    return os.path.expanduser(os.path.expandvars(s))


def resolve(key, spec):
    """Return (value, ok). ok=False means a required key could not be resolved."""
    if "value" in spec:
        return expand(spec["value"]), True
    verify = spec.get("verify")
    for cand in spec.get("candidates", []):
        for hit in sorted(glob.glob(expand(cand))):
            if not verify or os.path.exists(os.path.join(hit, verify)):
                return hit, True
    # nothing existed
    if spec.get("required"):
        return SENTINEL, False
    # best-effort default: first expanded candidate (may not exist yet)
    cands = spec.get("candidates", [])
    return (expand(cands[0]) if cands else ""), True


def shquote(v):
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")


def load_template():
    with open(TEMPLATE) as f:
        data = json.load(f)
    return [(k, v) for k, v in data.items() if not k.startswith("_")]


def generate(force):
    if os.path.exists(OUT) and not force:
        print(f"config.sh exists; not overwriting (use --force to regenerate): {OUT}", file=sys.stderr)
        return check_only(warn=True)
    lines = [
        "# config.sh — node-specific build config (GENERATED, git-ignored).",
        "# Regenerate: pixi run config   (or: python3 bin/config.py generate --force)",
        "# Edit the tracked template config.json.in for portable changes.",
        "# Env vars set before sourcing win (each line uses ${KEY:=default}).",
        "",
    ]
    missing = []
    for key, spec in load_template():
        val, ok = resolve(key, spec)
        doc = spec.get("doc", "")
        if not ok:
            missing.append(key)
            lines.append(f"# {key}: NOT FOUND on this node — set manually. {doc}")
            lines.append(f'#   {key}="/path/to/value"   # then re-source')
            lines.append("")
            continue
        if val == "":
            lines.append(f"# {key} (auto/unset): {doc}")
            continue
        if doc:
            lines.append(f"# {key}: {doc}")
        lines.append(f': "${{{key}:={shquote(val)}}}"')
        lines.append("")
    with open(OUT, "w") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print(f"wrote {OUT}")
    for k in missing:
        print(f"  [!] {k} unresolved — edit config.sh to set it manually", file=sys.stderr)
    return 1 if missing else 0


def check_only(warn=False):
    rc = 0
    for key, spec in load_template():
        _, ok = resolve(key, spec)
        if not ok:
            rc = 1
            if warn:
                print(f"  [!] required key unresolved: {key}", file=sys.stderr)
    return rc


## --- versions.toml: the build-version source of truth ----------------------

def load_versions():
    if tomllib is None:
        sys.exit("config.py: needs Python >=3.11 (tomllib) to read versions.toml")
    if not os.path.exists(VERSIONS):
        sys.exit(f"config.py: versions.toml not found: {VERSIONS}")
    with open(VERSIONS, "rb") as f:
        return tomllib.load(f)


def components(kind):
    """Yield (name, spec) for components of the given kind, in file order.
    'consumer' is the default when a component omits the kind key."""
    for name, spec in load_versions().get("components", {}).items():
        if spec.get("kind", "consumer") == kind:
            yield name, spec


def cmd_consumers():
    for name, spec in components("consumer"):
        print(f"{name}|{spec['url']}|{spec.get('branch', '')}")


def cmd_remotes():
    for name, spec in components("remote"):
        print(f"{name}|{spec['url']}|{1 if spec.get('heavy') else 0}")


def cmd_scenario(suffix, component):
    """Print 'url|branch' for a per-scenario consumer override, else nothing.
    Reads [scenarios.<suffix>.<component>] from versions.toml."""
    spec = load_versions().get("scenarios", {}).get(suffix, {}).get(component)
    if isinstance(spec, dict) and spec.get("url") and spec.get("branch"):
        print(f"{spec['url']}|{spec['branch']}")


def cmd_get(dotted):
    node = load_versions()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            sys.exit(f"config.py get: key not found: {dotted}")
        node = node[part]
    if isinstance(node, bool):
        print("true" if node else "false")
    else:
        print(node)


def _git(dirpath, *args):
    try:
        return subprocess.run(["git", "-C", dirpath, *args],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _toml_str(v):
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def cmd_manifest(forest):
    """Write <forest>/manifest.toml describing the repo + resolved ref of every
    component worktree that exists under <forest>. Human-readable record of what
    was actually checked out / built."""
    from datetime import datetime, timezone
    forest = os.path.abspath(forest)
    vers = load_versions()
    itk_ref_env = os.environ.get("ITK_REF", "")
    out = [
        "# manifest.toml — what this forest actually has checked out (GENERATED).",
        f"# forest: {forest}",
        f"# generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "# Records resolved git SHAs; regenerate with: python3 bin/config.py manifest <forest>",
        "",
    ]
    if itk_ref_env:
        out.append(f"itk_ref_requested = {_toml_str(itk_ref_env)}  # ITK_REF env at generation")
        out.append("")
    present = 0
    for name, spec in vers.get("components", {}).items():
        d = os.path.join(forest, name)
        if not os.path.isdir(os.path.join(d, ".git")) and not os.path.exists(os.path.join(d, ".git")):
            continue
        present += 1
        sha = _git(d, "rev-parse", "HEAD")
        branch = _git(d, "rev-parse", "--abbrev-ref", "HEAD")
        url = _git(d, "remote", "get-url", "origin") or spec.get("url", "")
        out += [
            f"[components.{name}]",
            f"url    = {_toml_str(url)}",
            f"ref    = {_toml_str(spec.get('ref', 'origin/main'))}",
            f"branch = {_toml_str(branch)}",
            f"sha    = {_toml_str(sha)}",
            f"kind   = {_toml_str(spec.get('kind', 'consumer'))}",
            "",
        ]
    path = os.path.join(forest, "manifest.toml")
    os.makedirs(forest, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(out).rstrip() + "\n")
    print(f"wrote {path} ({present} components)")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "consumers":
        sys.exit(cmd_consumers())
    if cmd == "remotes":
        sys.exit(cmd_remotes())
    if cmd == "get":
        if len(args) < 2:
            sys.exit("usage: config.py get <dotted.key>")
        sys.exit(cmd_get(args[1]))
    if cmd == "scenario":
        if len(args) < 3:
            sys.exit("usage: config.py scenario <suffix> <component>")
        sys.exit(cmd_scenario(args[1], args[2]))
    if cmd == "manifest":
        if len(args) < 2:
            sys.exit("usage: config.py manifest <FOREST>")
        sys.exit(cmd_manifest(args[1]))
    if "--check" in args and "generate" not in args:
        sys.exit(check_only(warn=True))
    sys.exit(generate(force="--force" in args))
