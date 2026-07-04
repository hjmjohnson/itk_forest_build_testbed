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
PRESETS_DIR = os.path.join(ROOT, "cmake", "presets")


def _cv_value(v):
    """cacheVariables value may be a plain string or {'type':..,'value':..}."""
    return v["value"] if isinstance(v, dict) else str(v)


def _load_all_presets(presets_dir):
    index = {}
    for path in sorted(glob.glob(os.path.join(presets_dir, "*.json"))):
        with open(path) as f:
            doc = json.load(f)
        for p in doc.get("configurePresets", []):
            index[p["name"]] = p
    return index


def resolve_preset(name, presets_dir, _index=None):
    """Flatten a configure preset's cacheVariables across its inherits chain.
    Base values first; the preset's own values win. Multiple inherits: earlier
    parent wins (CMake semantics)."""
    index = _index if _index is not None else _load_all_presets(presets_dir)
    if name not in index:
        raise KeyError(f"preset not found: {name}")
    p = index[name]
    inherits = p.get("inherits", [])
    if isinstance(inherits, str):
        inherits = [inherits]
    merged = {}
    for parent in reversed(inherits):            # earlier parent wins
        merged.update(resolve_preset(parent, presets_dir, index))
    for k, v in p.get("cacheVariables", {}).items():
        merged[k] = _cv_value(v)
    return merged


_OVERLAY_TOPLEVEL = ("generator", "installDir", "environment")


def resolve_preset_toplevel(name, presets_dir, _index=None):
    """Flatten the non-cacheVariables top-level fields (generator, installDir,
    environment) across the inherits chain; child wins, earlier parent wins."""
    index = _index if _index is not None else _load_all_presets(presets_dir)
    if name not in index:
        raise KeyError(f"preset not found: {name}")
    p = index[name]
    inherits = p.get("inherits", [])
    if isinstance(inherits, str):
        inherits = [inherits]
    merged = {}
    for parent in reversed(inherits):
        merged.update(resolve_preset_toplevel(parent, presets_dir, index))
    for f in _OVERLAY_TOPLEVEL:
        if f in p:
            merged[f] = p[f]
    return merged


def _parse_manifest(path):
    if not os.path.exists(path):
        return {}, {}
    if tomllib is None:
        sys.exit("config.py: needs Python >=3.11 (tomllib) to read/update manifest.toml")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("components", {}), data.get("config", {})


def _manifest_header(forest):
    from datetime import datetime, timezone
    hdr = [
        "# manifest.toml — what this forest has checked out AND how it was configured (GENERATED).",
        f"# forest: {forest}",
        f"# generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "# SHAs: python3 bin/config.py manifest <forest>;  [config.*]: written at configure time.",
        "",
    ]
    itk_ref_env = os.environ.get("ITK_REF", "")
    if itk_ref_env:
        hdr += [f"itk_ref_requested = {_toml_str(itk_ref_env)}  # ITK_REF env at generation", ""]
    return hdr


def _emit_manifest(forest, components, config):
    out = _manifest_header(forest)
    for name, spec in components.items():
        out.append(f"[components.{name}]")
        for k in ("url", "ref", "branch", "sha", "kind"):
            if k in spec:
                out.append(f"{k:<6} = {_toml_str(spec[k])}")
        out.append("")
    for name, rec in config.items():
        out.append(f"[config.{name}]")
        if "preset" in rec:
            out.append(f"preset = {_toml_str(rec['preset'])}")
        for k in sorted(rec):
            if k != "preset":
                out.append(f"{k} = {_toml_str(rec[k])}")
        out.append("")
    path = os.path.join(forest, "manifest.toml")
    os.makedirs(forest, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(out).rstrip() + "\n")
    return path


def _write_config_record(forest, consumer, preset, cache):
    forest = os.path.abspath(forest)
    path = os.path.join(forest, "manifest.toml")
    components, cfg = _parse_manifest(path)
    cfg[consumer] = {"preset": preset, **cache}
    _emit_manifest(forest, components, cfg)


def cmd_resolve_overlay(preset, src, binary_dir, forest, consumer, kvs):
    """Write a flattened, self-contained CMakeUserPresets.json into <src> and a
    matching [config.<consumer>] record into <forest>/manifest.toml, both from
    one resolved cacheVariables dict."""
    cache = resolve_preset(preset, PRESETS_DIR)
    for kv in kvs:
        if not kv:
            continue
        k, _, v = kv.partition("=")
        cache[k] = v
    top = resolve_preset_toplevel(preset, PRESETS_DIR)
    cfg_preset = {
        "name": f"forest-{consumer}-local",
        "binaryDir": binary_dir,
        "cacheVariables": cache,
    }
    cfg_preset.update(top)   # generator, installDir, environment from the chain
    doc = {
        "version": 8,
        "configurePresets": [cfg_preset],
    }
    out_path = os.path.join(src, "CMakeUserPresets.json")
    with open(out_path, "w") as f:
        f.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    _write_config_record(forest, consumer, preset, cache)
    print(f"wrote {out_path} (preset {preset}, {len(cache)} cache vars)")
    return 0


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
    """(Re)write <forest>/manifest.toml's [components.*] from live worktrees,
    preserving any [config.*] records already present."""
    forest = os.path.abspath(forest)
    vers = load_versions()
    path = os.path.join(forest, "manifest.toml")
    _, existing_cfg = _parse_manifest(path)
    components = {}
    for name, spec in vers.get("components", {}).items():
        d = os.path.join(forest, name)
        if not (os.path.isdir(os.path.join(d, ".git")) or os.path.exists(os.path.join(d, ".git"))):
            continue
        components[name] = {
            "url": _git(d, "remote", "get-url", "origin") or spec.get("url", ""),
            "ref": spec.get("ref", "origin/main"),
            "branch": _git(d, "rev-parse", "--abbrev-ref", "HEAD"),
            "sha": _git(d, "rev-parse", "HEAD"),
            "kind": spec.get("kind", "consumer"),
        }
    _emit_manifest(forest, components, existing_cfg)
    print(f"wrote {path} ({len(components)} components, {len(existing_cfg)} config records)")
    return 0


def cmd_compare(forest_a, forest_b):
    """Diff two forests' manifest.toml: ref/SHA deltas and [config.*] -D deltas."""
    ca, cfa = _parse_manifest(os.path.join(os.path.abspath(forest_a), "manifest.toml"))
    cb, cfb = _parse_manifest(os.path.join(os.path.abspath(forest_b), "manifest.toml"))
    print(f"# compare A={forest_a}  B={forest_b}")
    print("## refs/SHAs (A != B)")
    for n in sorted(set(ca) | set(cb)):
        sa = ca.get(n, {}).get("sha", "-"); sb = cb.get(n, {}).get("sha", "-")
        if sa != sb:
            print(f"  {n}: {sa[:12]} != {sb[:12]}")
    print("## config -D deltas (A != B)")
    for n in sorted(set(cfa) | set(cfb)):
        ra, rb = cfa.get(n, {}), cfb.get(n, {})
        for k in sorted(set(ra) | set(rb)):
            va, vb = ra.get(k, "<absent>"), rb.get(k, "<absent>")
            if va != vb:
                print(f"  {n}.{k}: {va} != {vb}")
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
    if cmd == "resolve-overlay":
        if len(args) < 6:
            sys.exit("usage: config.py resolve-overlay <preset> <src> <bin> <forest> <consumer> [KEY=VAL ...]")
        sys.exit(cmd_resolve_overlay(args[1], args[2], args[3], args[4], args[5], args[6:]))
    if cmd == "compare":
        if len(args) < 3:
            sys.exit("usage: config.py compare <forestA> <forestB>")
        sys.exit(cmd_compare(args[1], args[2]))
    if cmd == "manifest":
        if len(args) < 2:
            sys.exit("usage: config.py manifest <FOREST>")
        sys.exit(cmd_manifest(args[1]))
    if "--check" in args and "generate" not in args:
        sys.exit(check_only(warn=True))
    sys.exit(generate(force="--force" in args))
