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
  python3 bin/config.py refslug <ref>        # conventional forest slug for an ITK ref
  python3 bin/config.py compare <A> <B>      # what each forest actually holds
  python3 bin/config.py manifest <FOREST>    # write <FOREST>/manifest.toml from live worktrees
"""
import sys, os, json, glob, subprocess, re

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

# Remote names refslug() strips by default. The engine passes the ITK clone's
# real list; these two cover every ref used without a clone present.
DEFAULT_REMOTES = ("origin", "upstream")

_SLUG_OK = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_PR_RE = re.compile(r"^pr/(\d+)$")
_PULL_RE = re.compile(r"^pull/(\d+)/head$")


def refslug(ref, remotes=DEFAULT_REMOTES):
    """Map an ITK ref to a git- and filesystem-safe slug. Pure: no git, no I/O.

    A ref that is 7-40 lowercase hex chars is treated as a SHA even if a branch
    of that name exists; resolving that would require git and make this impure.
    The manifest's resolved SHA stays authoritative.
    """
    if not isinstance(ref, str):
        raise ValueError(f"refslug: expected str, got {type(ref).__name__}")
    ref = ref.strip()
    if not ref:
        raise ValueError("refslug: empty ref")
    m = _PR_RE.match(ref) or _PULL_RE.match(ref)
    if m:
        return f"pr{m.group(1)}"
    if _SHA_RE.match(ref):
        return f"sha{ref[:7]}"
    for r in remotes:
        if ref.startswith(f"{r}/"):
            ref = ref[len(r) + 1:]
            break
    _validate_slug(ref)
    return ref


def _validate_slug(slug):
    if not slug or not _SLUG_OK.match(slug):
        raise ValueError(
            f"refslug: {slug!r} is not a valid forest slug "
            "(allowed: A-Z a-z 0-9 . _ -; a '/' means the leading component "
            "is not a known remote)")
    if slug.startswith(".") or slug.startswith("-"):
        raise ValueError(f"refslug: {slug!r} must not start with '.' or '-'")
    if ".." in slug:
        raise ValueError(f"refslug: {slug!r} must not contain '..'")
    if slug.endswith("."):
        raise ValueError(f"refslug: {slug!r} must not end with '.' "
                         "(git rejects a ref component with a trailing dot)")
    if slug.endswith(".lock"):
        raise ValueError(f"refslug: {slug!r} must not end with '.lock'")


def validate_suffix_keys(vers):
    """Config keyed by the forest suffix must stay well-formed.

    A rename that misses these changes the build with no error:
    subbuild.ANTs.skip_suffix gates the ANTs fork, and [scenarios.<suffix>]
    selects consumer overrides. Only 'itk-' keys -- the documented
    itk-<refslug> convention -- are checked; free-form experiment suffixes are
    unconstrained by design.
    """
    errs = []

    def _check(where, value):
        if not isinstance(value, str) or not value.startswith("itk-"):
            return
        try:
            _validate_slug(value[len("itk-"):])
        except ValueError as e:
            errs.append(f"{where}: {value!r} follows the 'itk-' convention but is not a "
                        f"valid itk-<refslug> ({e})")

    for key in (vers.get("scenarios") or {}):
        _check("scenarios", key)
    for pkg, rec in (vers.get("subbuild") or {}).items():
        if isinstance(rec, dict) and "skip_suffix" in rec:
            _check(f"subbuild.{pkg}.skip_suffix", rec["skip_suffix"])
    return errs


def warn_unmatched_scenarios(vers, testbed_root):
    """Scenario keys with no corresponding forest on disk.

    A WARNING, never an error: a scenario may legitimately precede its forest
    (and every forest is disposable). Returns a list of message strings.
    """
    out = []
    root = os.environ.get("BUILD_FOREST_ROOT") or "build_forest"
    for key in sorted((vers.get("scenarios") or {})):
        forest = f"{expand(root)}-{key}" if os.path.isabs(expand(root)) \
            else os.path.join(testbed_root, f"{root}-{key}")
        if not os.path.isdir(expand(forest)):
            out.append(f"scenarios.{key}: no {os.path.basename(forest)} on disk "
                       "(harmless if the forest has not been created yet)")
    return out


def cmd_refslug(ref, itk_clone=None):
    """Print refslug(ref). Discovers real remotes from itk_clone when given."""
    remotes = DEFAULT_REMOTES
    if itk_clone and os.path.isdir(itk_clone):
        out = _git(itk_clone, "remote")
        if out:
            remotes = tuple(x for x in out.split("\n") if x.strip())
    try:
        print(refslug(ref, remotes))
    except ValueError as e:
        sys.exit(f"config.py: {e}")
    return 0


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
    """-> (components, config, forest_meta). Empty dicts when absent."""
    if not os.path.exists(path):
        return {}, {}, {}
    if tomllib is None:
        sys.exit("config.py: needs Python >=3.11 (tomllib) to read/update manifest.toml")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("components", {}), data.get("config", {}), data.get("forest", {})


def _itk_version(itk_src):
    """ITK version 'MAJOR.MINOR.PATCH' from <itk_src>/CMake/itkVersion.cmake.

    That file is where ITK declares it, and where the engine's forest_itk_major()
    already reads it -- one fact, one location. CMakeLists.txt mentions
    ITK_VERSION_* but never sets it, so reading there silently returned None.
    Falls back to CMakeLists.txt only for a tree that predates the split.
    """
    for rel in (os.path.join("CMake", "itkVersion.cmake"), "CMakeLists.txt"):
        cml = os.path.join(itk_src, rel)
        if not os.path.exists(cml):
            continue
        try:
            with open(cml, errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if re.search(r'set\s*\(\s*ITK_VERSION_MAJOR\s+"?(\d+)"?\s*\)', text):
            break
    else:
        return None
    parts = []
    for field in ("MAJOR", "MINOR", "PATCH"):
        m = re.search(rf'set\s*\(\s*ITK_VERSION_{field}\s+"?(\d+)"?\s*\)', text)
        if not m:
            return None
        parts.append(m.group(1))
    return ".".join(parts)


def _remotes_of(d):
    out = _git(d, "remote")
    return tuple(x for x in (out or "").split("\n") if x.strip()) or DEFAULT_REMOTES


def _resolved_ref(d):
    """The ref this worktree actually tracks: its upstream (e.g.
    'origin/release-5.4') when set, else the current branch name."""
    up = _git(d, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if up:
        return up
    return _git(d, "rev-parse", "--abbrev-ref", "HEAD")


def _manifest_header(forest):
    from datetime import datetime, timezone
    hdr = [
        "# manifest.toml — what this forest has checked out AND how it was configured (GENERATED).",
        f"# forest: {forest}",
        f"# generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "# SHAs: python3 bin/config.py manifest <forest>;  [config.*]: written at configure time.",
        "",
    ]
    return hdr


def _emit_manifest(forest, components, config, forest_meta=None):
    out = _manifest_header(forest)
    if forest_meta:
        out.append("[forest]")
        for k in ("name", "itk_version"):
            if forest_meta.get(k) is not None:
                out.append(f"{k:<12} = {_toml_str(forest_meta[k])}")
        out.append("")
    for name, spec in components.items():
        out.append(f"[components.{name}]")
        for k in ("url", "ref", "slug", "branch", "sha", "kind"):
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
    components, cfg, forest_meta = _parse_manifest(path)
    cfg[consumer] = {"preset": preset, **cache}
    _emit_manifest(forest, components, cfg, forest_meta)


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
        # Version 3 is the minimum that supports installDir; its floor is cmake
        # 3.21, so the presets read on cmake 3.22+ without needing a 3.28 build.
        "version": 3,
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
    vers = load_versions()
    for e in validate_suffix_keys(vers):
        rc = 1
        if warn:
            print(f"  [!] {e}", file=sys.stderr)
    for w in warn_unmatched_scenarios(vers, ROOT):
        if warn:
            print(f"  [i] {w}", file=sys.stderr)   # informational: never sets rc
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


def _requested_sha(d, ref):
    """The commit `ref` names in this worktree, or "" if it does not resolve.
    PR shorthand has no local ref name; it is checked out from FETCH_HEAD, so
    that is where it resolves."""
    if _PR_RE.match(ref) or _PULL_RE.match(ref):
        return _git(d, "rev-parse", "FETCH_HEAD^{commit}")
    return _git(d, "rev-parse", f"{ref}^{{commit}}")


def _toml_str(v):
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def cmd_manifest(forest):
    """(Re)write <forest>/manifest.toml's [components.*] from live worktrees,
    preserving any [config.*] records already present."""
    forest = os.path.abspath(forest)
    vers = load_versions()
    path = os.path.join(forest, "manifest.toml")
    _, existing_cfg, existing_meta = _parse_manifest(path)
    # The engine knows the ITK ref the user REQUESTED (ITK_REF_EXPLICIT, captured
    # before ITK_REF is defaulted); the worktree alone cannot say, since
    # repoint-itk checks a PR out from FETCH_HEAD onto a local branch with no
    # upstream. A merely-defaulted ITK_REF is not a request and must not be
    # recorded as one.
    requested_ref = os.environ.get("ITK_REF_EXPLICIT") or None
    components = {}
    for name, spec in vers.get("components", {}).items():
        d = os.path.join(forest, name)
        if not (os.path.isdir(os.path.join(d, ".git")) or os.path.exists(os.path.join(d, ".git"))):
            continue
        # Resolved ref, NOT the versions.toml default: the declared default is
        # what made every forest report ref="origin/main" regardless of content.
        resolved = _resolved_ref(d) or spec.get("ref", "")
        if resolved.startswith("itk-downstream"):
            resolved = ""  # our own worktree branch: not an ITK ref
        head_sha = _git(d, "rev-parse", "HEAD")
        # The resolved ref needs the same proof as a requested one. @{u} is
        # stale tracking info, not an observation: repoint-itk moves HEAD onto a
        # local branch and leaves the old upstream behind, so @{u} keeps naming
        # the ref this worktree used to be on. Recorded unchecked, that asserts a
        # ref the sha contradicts -- the exact defect this function exists to fix.
        if resolved and _requested_sha(d, resolved) not in (head_sha, None):
            print(f"warn: {name}: resolved ref {resolved!r} does not name "
                  f"{head_sha[:8]}; recording no ref (the sha is the record)",
                  file=sys.stderr)
            resolved = ""
        rec = {
            "url": _git(d, "remote", "get-url", "origin") or spec.get("url", ""),
            "ref": resolved,
            "branch": _git(d, "rev-parse", "--abbrev-ref", "HEAD"),
            "sha": head_sha,
            "kind": spec.get("kind", "consumer"),
        }
        try:
            rec["slug"] = refslug(resolved, _remotes_of(d))
        except ValueError:
            pass  # free-form / unsluggable ref: record no slug rather than fail
        # A request is only recorded once verified against reality: the SHA the
        # requested ref names must be the SHA the worktree is on. Unverified, the
        # manifest asserts a ref its own sha contradicts. Compare to the worktree,
        # never to another copy of the request -- that comparison is a tautology.
        # Never fatal: a manifest write rides on nearly every command, so an
        # unhonored request is recorded honestly and warned about, not refused.
        if name == "ITK" and requested_ref:
            want = _requested_sha(d, requested_ref)
            if want and want == rec["sha"]:
                rec["ref"] = requested_ref
                try:
                    rec["slug"] = refslug(requested_ref, _remotes_of(d))
                except ValueError:
                    # No slug beats a slug computed from the resolved branch: that
                    # pair (ref=requested, slug=other) reads as a drifted forest.
                    rec.pop("slug", None)
            else:
                print(f"warn: {name}: requested ref {requested_ref!r} resolves to "
                      f"{want[:8] if want else '<unresolvable>'} but the worktree "
                      f"is at {rec['sha'][:8]}; recording the worktree's ref "
                      f"({rec['ref'] or '<none>'}) instead", file=sys.stderr)
        components[name] = rec
    meta = dict(existing_meta or {})
    meta["name"] = os.path.basename(forest)
    if "ITK" in components:
        itk_ver = _itk_version(os.path.join(forest, "ITK"))
        if itk_ver:
            meta["itk_version"] = itk_ver
        else:
            print(f"warn: could not parse ITK version from {forest}/ITK/CMakeLists.txt",
                  file=sys.stderr)
    _emit_manifest(forest, components, existing_cfg, meta)
    print(f"wrote {path} ({len(components)} components, {len(existing_cfg)} config records)")
    return 0


def cmd_compare(forest_a, forest_b):
    """Diff two forests' manifest.toml: forest identity, ref/slug/SHA deltas,
    and [config.*] -D deltas. This is how you check which ITK a forest holds --
    the directory name is a convention, the manifest is the record."""
    ca, cfa, fma = _parse_manifest(os.path.join(os.path.abspath(forest_a), "manifest.toml"))
    cb, cfb, fmb = _parse_manifest(os.path.join(os.path.abspath(forest_b), "manifest.toml"))
    print(f"# compare A={forest_a}  B={forest_b}")
    print("## forest")
    for k in ("name", "itk_version"):
        va, vb = (fma or {}).get(k, "-"), (fmb or {}).get(k, "-")
        if va != vb:
            print(f"  {k}: {va} != {vb}")
    print("## refs/SHAs (A != B)")
    for n in sorted(set(ca) | set(cb)):
        ra, rb = ca.get(n, {}), cb.get(n, {})
        for k in ("ref", "slug"):
            va, vb = ra.get(k, "-"), rb.get(k, "-")
            if va != vb:
                print(f"  {n}.{k}: {va} != {vb}")
        sa, sb = ra.get("sha", "-"), rb.get("sha", "-")
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
    if cmd == "refslug":
        if len(args) < 2:
            sys.exit("usage: config.py refslug <ref> [itk_clone]")
        sys.exit(cmd_refslug(args[1], args[2] if len(args) > 2 else None))
    if cmd == "manifest":
        if len(args) < 2:
            sys.exit("usage: config.py manifest <FOREST>")
        sys.exit(cmd_manifest(args[1]))
    if "--check" in args and "generate" not in args:
        sys.exit(check_only(warn=True))
    sys.exit(generate(force="--force" in args))
