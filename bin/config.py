#!/usr/bin/env python3
"""Generate the node-specific config.sh from config.json.in.

The template (config.json.in, tracked) declares each build knob; this script
resolves it on THIS machine and writes config.sh (git-ignored), which the bash
engine `source`s. Resolution is dependency-heavy (globbing, path existence) so
it lives here in Python and runs once; the generated config.sh is plain shell.

Usage:
  python3 bin/config.py generate [--force]   # write config.sh (default cmd)
  python3 bin/config.py --check              # exit 1 if a required key is unresolved
"""
import sys, os, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "config.json.in")
OUT = os.path.join(ROOT, "config.sh")
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


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args and "generate" not in args:
        sys.exit(check_only(warn=True))
    sys.exit(generate(force="--force" in args))
