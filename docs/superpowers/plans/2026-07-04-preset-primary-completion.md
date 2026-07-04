# Preset-Primary Configuration Completion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the committed `cmake/presets/*.json` fragments the single authoring source of every `-D` option, and make each `build_forest-<X>` a self-contained, diffable A/B environment (flattened overlay + config-record + in-forest logs).

**Architecture:** Move all `-D` policy out of `bin/setup-itk-downstream-testbed.sh` into the fragments. A resolver in `bin/config.py` walks the preset `inherits` chain, flattens `cacheVariables`, injects per-forest dynamic values, and writes (1) a standalone `CMakeUserPresets.json` into the consumer source dir with **no include back to the kit**, and (2) a `[config.<consumer>]` record into `<forest>/manifest.toml`. A `compare` subcommand diffs two forests. All logs move to `${FOREST}/logs/`.

**Tech Stack:** Bash (setup engine), Python 3.14 (`config.py`, stdlib only — `tomllib` for reads, hand-emitted TOML, `json`), CMake presets schema v8.

## Global Constraints

- **Dependency-free Python:** stdlib only. No `pytest`, no `tomli-w`. Tests are plain `assert` scripts run with `python3 bin/tests/<file>.py` (exit 0 = pass).
- **JSON output:** every generated JSON uses `json.dumps(obj, indent=2, sort_keys=True) + "\n"`.
- **Overlay self-containment:** a forest's `CMakeUserPresets.json` MUST NOT contain the string `itk_forest_build_testbed` or any `include` key.
- **binaryDir:** `build_dir()` returns `${FOREST}/<name>/build`; overlays keep that value.
- **Single computation, two sinks:** the overlay and the manifest `[config.*]` record are written from the *same* resolved dict in one call — they cannot disagree.
- **State repo + forest** for every action (kit CLAUDE.md). This plan touches only the *kit* repo (`hjmjohnson/itk_forest_build_testbed`); no testbed artifact is committed into a consumer worktree.
- **Verify by artifact, not pipe exit** (kit CLAUDE.md).
- **No PR** is opened by any task (global `pr-no-unsolicited` rule); commits stay local on `feat/cmake-presets-restructure`.
- **Commit trailer:** end commit messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` only if a human co-author applies; otherwise omit (mechanical work).

---

### Task 1: Preset resolver (pure function) in `config.py`

**Files:**
- Modify: `bin/config.py` (add `PRESETS_DIR`, `_cv_value`, `_load_all_presets`, `resolve_preset`)
- Create: `bin/tests/test_resolve_preset.py`
- Create: `bin/tests/fixtures/presets/00-base.json`
- Create: `bin/tests/fixtures/presets/20-thing.json`

**Interfaces:**
- Produces: `resolve_preset(name: str, presets_dir: str, _index: dict | None = None) -> dict[str, str]` — flattened cacheVariables (base→variant, child wins). Raises `KeyError` if `name` absent.
- Produces: `_load_all_presets(presets_dir: str) -> dict[str, dict]` — every preset by name across all `*.json` in the dir.

- [ ] **Step 1: Write fixtures**

`bin/tests/fixtures/presets/00-base.json`:
```json
{
  "version": 8,
  "configurePresets": [
    { "name": "base", "hidden": true,
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Release", "A": "1" } }
  ]
}
```

`bin/tests/fixtures/presets/20-thing.json`:
```json
{
  "version": 8,
  "include": ["00-base.json"],
  "configurePresets": [
    { "name": "thing", "hidden": true, "inherits": "base",
      "cacheVariables": { "A": "2", "B": "on" } },
    { "name": "thing-max", "hidden": true, "inherits": "thing",
      "cacheVariables": { "C": "yes" } }
  ]
}
```

- [ ] **Step 2: Write the failing test** — `bin/tests/test_resolve_preset.py`

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

FX = os.path.join(os.path.dirname(__file__), "fixtures", "presets")

def test_base_only():
    assert config.resolve_preset("base", FX) == {"CMAKE_BUILD_TYPE": "Release", "A": "1"}

def test_child_overrides_parent():
    r = config.resolve_preset("thing", FX)
    assert r == {"CMAKE_BUILD_TYPE": "Release", "A": "2", "B": "on"}

def test_two_hop_inherit():
    r = config.resolve_preset("thing-max", FX)
    assert r == {"CMAKE_BUILD_TYPE": "Release", "A": "2", "B": "on", "C": "yes"}

def test_missing_raises():
    try:
        config.resolve_preset("nope", FX); assert False, "expected KeyError"
    except KeyError:
        pass

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 3: Run it — expect failure**

Run: `python3 bin/tests/test_resolve_preset.py`
Expected: `AttributeError: module 'config' has no attribute 'resolve_preset'`

- [ ] **Step 4: Implement in `bin/config.py`** — insert after the `VERSIONS`/`SENTINEL` constants (near line 30):

```python
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
```

- [ ] **Step 5: Run the test — expect pass**

Run: `python3 bin/tests/test_resolve_preset.py`
Expected: four `ok test_*` lines then `PASS`

- [ ] **Step 6: Verify against real fragments**

Run: `python3 -c "import sys; sys.path.insert(0,'bin'); import config; print(config.resolve_preset('itk-forest-ants', config.PRESETS_DIR))"`
Expected: a dict containing `'ANTS_SUPERBUILD': 'OFF'`, `'CMAKE_BUILD_TYPE': 'Release'`, `'USE_SYSTEM_ITK': 'ON'`.

- [ ] **Step 7: Commit**

```bash
git add bin/config.py bin/tests/test_resolve_preset.py bin/tests/fixtures/presets/
git commit -m "ENH: Add preset resolver that flattens inherits chain in config.py"
```

---

### Task 2: `resolve-overlay` subcommand — flattened self-contained overlay

**Files:**
- Modify: `bin/config.py` (add `cmd_resolve_overlay`, dispatch)
- Create: `bin/tests/test_resolve_overlay.py`

**Interfaces:**
- Consumes: `resolve_preset` (Task 1), `_write_config_record` (Task 3 — for this task, stub it as a no-op function that Task 3 fills in).
- Produces CLI: `config.py resolve-overlay <preset> <src> <bin> <forest> <consumer> [KEY=VAL ...]`
- Produces: `cmd_resolve_overlay(preset, src, binary_dir, forest, consumer, kvs: list[str]) -> int` — writes `<src>/CMakeUserPresets.json` (flattened, no include) and calls `_write_config_record`.

- [ ] **Step 1: Write the failing test** — `bin/tests/test_resolve_overlay.py`

```python
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

def test_overlay_is_flat_and_self_contained():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "ANTs"); os.makedirs(src)
        forest = d
        rc = config.cmd_resolve_overlay(
            "itk-forest-ants", src, os.path.join(src, "build"),
            forest, "ANTs", ["ITK_DIR=/x/ITK/build"])
        assert rc == 0
        doc = json.load(open(os.path.join(src, "CMakeUserPresets.json")))
        assert "include" not in doc
        p = doc["configurePresets"][0]
        assert p["name"] == "forest-ANTs-local"
        assert p["binaryDir"] == os.path.join(src, "build")
        cv = p["cacheVariables"]
        assert cv["ANTS_SUPERBUILD"] == "OFF"          # from fragment
        assert cv["ITK_DIR"] == "/x/ITK/build"          # injected kv wins
        assert cv["CMAKE_BUILD_TYPE"] == "Release"      # from base

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run it — expect failure**

Run: `python3 bin/tests/test_resolve_overlay.py`
Expected: `AttributeError: module 'config' has no attribute 'cmd_resolve_overlay'`

- [ ] **Step 3: Implement in `bin/config.py`** — add after `resolve_preset`:

```python
def _write_config_record(forest, consumer, preset, cache):
    """Filled in by the manifest-record task. No-op placeholder."""
    return None


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
    doc = {
        "version": 8,
        "configurePresets": [{
            "name": f"forest-{consumer}-local",
            "binaryDir": binary_dir,
            "cacheVariables": cache,
        }],
    }
    out_path = os.path.join(src, "CMakeUserPresets.json")
    with open(out_path, "w") as f:
        f.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    _write_config_record(forest, consumer, preset, cache)
    print(f"wrote {out_path} (preset {preset}, {len(cache)} cache vars)")
    return 0
```

- [ ] **Step 4: Wire the dispatch** — in the `__main__` block (near line 231, before the `manifest` clause), add:

```python
    if cmd == "resolve-overlay":
        if len(args) < 6:
            sys.exit("usage: config.py resolve-overlay <preset> <src> <bin> <forest> <consumer> [KEY=VAL ...]")
        sys.exit(cmd_resolve_overlay(args[1], args[2], args[3], args[4], args[5], args[6:]))
```

- [ ] **Step 5: Run the test — expect pass**

Run: `python3 bin/tests/test_resolve_overlay.py`
Expected: `ok test_overlay_is_flat_and_self_contained` then `PASS`

- [ ] **Step 6: Commit**

```bash
git add bin/config.py bin/tests/test_resolve_overlay.py
git commit -m "ENH: Add resolve-overlay subcommand writing flattened self-contained presets"
```

---

### Task 3: Manifest `[config.<consumer>]` record (single-file self-describing forest)

**Files:**
- Modify: `bin/config.py` (replace `_write_config_record` stub; add `_parse_manifest`, `_manifest_header`, `_emit_manifest`; rework `cmd_manifest` to preserve config sections)
- Create: `bin/tests/test_manifest_config.py`

**Interfaces:**
- Consumes: `cmd_resolve_overlay` (Task 2).
- Produces: `_parse_manifest(path) -> tuple[dict, dict]` (components, config); `_emit_manifest(forest, header_lines, components, config)`; real `_write_config_record`.

- [ ] **Step 1: Write the failing test** — `bin/tests/test_manifest_config.py`

```python
import os, sys, tempfile, tomllib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

def test_config_record_written_and_preserved():
    with tempfile.TemporaryDirectory() as forest:
        config._write_config_record(forest, "ANTs", "itk-forest-ants-max-modules",
                                    {"USE_VTK": "ON", "ITK_DIR": "/x"})
        path = os.path.join(forest, "manifest.toml")
        data = tomllib.load(open(path, "rb"))
        assert data["config"]["ANTs"]["preset"] == "itk-forest-ants-max-modules"
        assert data["config"]["ANTs"]["USE_VTK"] == "ON"
        # a second consumer must not clobber the first
        config._write_config_record(forest, "BRAINSTools", "itk-forest-brainstools",
                                    {"USE_VTK": "OFF"})
        data = tomllib.load(open(path, "rb"))
        assert set(data["config"]) == {"ANTs", "BRAINSTools"}

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run it — expect failure**

Run: `python3 bin/tests/test_manifest_config.py`
Expected: `KeyError: 'config'` (the stub writes nothing).

- [ ] **Step 3: Implement in `bin/config.py`** — replace the `_write_config_record` stub and refactor `cmd_manifest`. Insert these helpers above `cmd_manifest`:

```python
def _parse_manifest(path):
    if not os.path.exists(path) or tomllib is None:
        return {}, {}
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
```

Then replace the body of `cmd_manifest` (lines ~172-213) so it builds `components` into a dict, preserves existing config, and emits via `_emit_manifest`:

```python
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
```

- [ ] **Step 4: Run the manifest-config test — expect pass**

Run: `python3 bin/tests/test_manifest_config.py`
Expected: `ok test_config_record_written_and_preserved` then `PASS`

- [ ] **Step 5: Re-run the overlay test (regression — it now writes a real record)**

Run: `python3 bin/tests/test_resolve_overlay.py`
Expected: `PASS`

- [ ] **Step 6: Verify config-record + SHA-preservation on a real forest**

```bash
python3 bin/config.py resolve-overlay itk-forest-ants \
  build_forest-base/ANTs build_forest-base/ANTs/build build_forest-base ANTs ITK_DIR=/tmp/x
python3 bin/config.py manifest build_forest-base
grep -A2 '\[config.ANTs\]' build_forest-base/manifest.toml
```
Expected: `[config.ANTs]` survives the `manifest` regen; `[components.*]` present. Then discard the scratch overlay: `rm build_forest-base/ANTs/CMakeUserPresets.json` and `git checkout build_forest-base/manifest.toml 2>/dev/null || true` (forest is gitignored; this is just cleanup).

- [ ] **Step 7: Commit**

```bash
git add bin/config.py bin/tests/test_manifest_config.py
git commit -m "ENH: Record resolved -D config in manifest.toml [config.*], preserved across regen"
```

---

### Task 4: `compare` subcommand — forest-to-forest A/B diff

**Files:**
- Modify: `bin/config.py` (add `cmd_compare`, dispatch)
- Create: `bin/tests/test_compare.py`

**Interfaces:**
- Consumes: `_parse_manifest` (Task 3).
- Produces CLI: `config.py compare <forestA> <forestB>` → prints ref/SHA deltas and `[config.*]` `-D` deltas; returns 0.
- Produces: `cmd_compare(forest_a, forest_b) -> int`.

- [ ] **Step 1: Write the failing test** — `bin/tests/test_compare.py`

```python
import os, sys, tempfile, io, contextlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

def _forest(tmp, name, sha, cfg):
    d = os.path.join(tmp, name); os.makedirs(d)
    config._emit_manifest(d, {"ITK": {"sha": sha, "kind": "consumer"}}, {"ITK": cfg})
    return d

def test_compare_reports_sha_and_config_deltas():
    with tempfile.TemporaryDirectory() as tmp:
        a = _forest(tmp, "A", "aaaaaaaaaaaa", {"preset": "itk-forest-itk-v5", "ITK_USE_FFTWD": "ON"})
        b = _forest(tmp, "B", "bbbbbbbbbbbb", {"preset": "itk-forest-itk-v6", "ITK_USE_FFTWD": "OFF"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert config.cmd_compare(a, b) == 0
        out = buf.getvalue()
        assert "ITK" in out and "aaaaaaaaaaaa" in out          # sha delta
        assert "ITK_USE_FFTWD" in out and "ON" in out and "OFF" in out  # config delta

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run it — expect failure**

Run: `python3 bin/tests/test_compare.py`
Expected: `AttributeError: module 'config' has no attribute 'cmd_compare'`

- [ ] **Step 3: Implement in `bin/config.py`** — add after `cmd_manifest`:

```python
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
```

- [ ] **Step 4: Wire the dispatch** — in `__main__`, after the `resolve-overlay` clause:

```python
    if cmd == "compare":
        if len(args) < 3:
            sys.exit("usage: config.py compare <forestA> <forestB>")
        sys.exit(cmd_compare(args[1], args[2]))
```

- [ ] **Step 5: Run the test — expect pass**

Run: `python3 bin/tests/test_compare.py`
Expected: `ok test_compare_reports_sha_and_config_deltas` then `PASS`

- [ ] **Step 6: Commit**

```bash
git add bin/config.py bin/tests/test_compare.py
git commit -m "ENH: Add config.py compare for forest-to-forest ref+config A/B diff"
```

---

### Task 5: Add variant presets to the fragments

**Files:**
- Modify: `cmake/presets/10-itk-v6.json` (add `itk-forest-itk-v6-vtkglue`)
- Modify: `cmake/presets/10-itk-v5.json` (add `itk-forest-itk-v5-dcmtk`)
- Modify: `cmake/presets/20-ANTs.json` (add `itk-forest-ants-max-modules`)
- Modify: `cmake/presets/30-BRAINSTools.json` (add `itk-forest-brainstools-max-modules`, `itk-forest-brainstools-no-ants`)
- Create: `bin/tests/test_variants.py`

**Interfaces:**
- Consumes: `resolve_preset` (Task 1).
- Produces preset names: `itk-forest-itk-v6-vtkglue`, `itk-forest-itk-v5-dcmtk`, `itk-forest-ants-max-modules`, `itk-forest-brainstools-max-modules`, `itk-forest-brainstools-no-ants` (consumed by Tasks 6b/6c).

- [ ] **Step 1: Write the failing test** — `bin/tests/test_variants.py`

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

P = config.PRESETS_DIR

def test_ants_max_modules():
    r = config.resolve_preset("itk-forest-ants-max-modules", P)
    assert r["ANTS_SUPERBUILD"] == "OFF"   # inherited
    assert r["USE_VTK"] == "ON"            # variant override
    assert r["BUILD_ALL_ANTS_APPS"] == "ON"

def test_itk_v6_vtkglue():
    r = config.resolve_preset("itk-forest-itk-v6-vtkglue", P)
    assert r["Module_ITKVtkGlue"] == "ON"
    assert r["BUILD_TESTING"] == "OFF"
    assert r["ITK_USE_FFTWD"] == "OFF"     # inherited v6 policy

def test_brainstools_variants():
    m = config.resolve_preset("itk-forest-brainstools-max-modules", P)
    assert m["USE_VTK"] == "ON" and m["USE_DWIConvert"] == "ON"
    n = config.resolve_preset("itk-forest-brainstools-no-ants", P)
    assert n["USE_ANTS"] == "OFF"

def test_itk_v5_dcmtk():
    r = config.resolve_preset("itk-forest-itk-v5-dcmtk", P)
    assert r["Module_ITKDCMTK"] == "ON" and r["Module_ITKIODCMTK"] == "ON"

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run it — expect failure**

Run: `python3 bin/tests/test_variants.py`
Expected: `KeyError: preset not found: itk-forest-ants-max-modules`

- [ ] **Step 3: Add the variant to `cmake/presets/20-ANTs.json`** — add a second object to `configurePresets` (keep array sorted only if the file already is; append is fine):

```json
    {
      "cacheVariables": {
        "BUILD_ALL_ANTS_APPS": "ON",
        "USE_VTK": "ON"
      },
      "hidden": true,
      "inherits": "itk-forest-ants",
      "name": "itk-forest-ants-max-modules"
    }
```

- [ ] **Step 4: Add the variant to `cmake/presets/10-itk-v6.json`** — append to `configurePresets`:

```json
    {
      "cacheVariables": {
        "BUILD_EXAMPLES": "OFF",
        "BUILD_TESTING": "OFF",
        "ITK_USE_BRAINWEB_DATA": "OFF",
        "Module_ITKVtkGlue": "ON"
      },
      "hidden": true,
      "inherits": "itk-forest-itk-v6",
      "name": "itk-forest-itk-v6-vtkglue"
    }
```

- [ ] **Step 5: Add the variant to `cmake/presets/10-itk-v5.json`** — append to `configurePresets`:

```json
    {
      "cacheVariables": {
        "Module_ITKDCMTK": "ON",
        "Module_ITKIODCMTK": "ON"
      },
      "hidden": true,
      "inherits": "itk-forest-itk-v5",
      "name": "itk-forest-itk-v5-dcmtk"
    }
```

- [ ] **Step 6: Add both variants to `cmake/presets/30-BRAINSTools.json`** — append to `configurePresets`:

```json
    {
      "cacheVariables": {
        "BRAINSTools_BUILD_DICOM_SUPPORT": "ON",
        "BRAINSTools_REQUIRES_VTK": "ON",
        "BUILD_FOR_DASHBOARD": "ON",
        "USE_DWIConvert": "ON",
        "USE_GTRACT": "ON",
        "USE_VTK": "ON"
      },
      "hidden": true,
      "inherits": "itk-forest-brainstools",
      "name": "itk-forest-brainstools-max-modules"
    },
    {
      "cacheVariables": {
        "USE_ANTS": "OFF"
      },
      "hidden": true,
      "inherits": "itk-forest-brainstools",
      "name": "itk-forest-brainstools-no-ants"
    }
```

- [ ] **Step 7: Run the test — expect pass**

Run: `python3 bin/tests/test_variants.py`
Expected: four `ok test_*` lines then `PASS`

- [ ] **Step 8: Validate JSON well-formedness**

Run: `for f in cmake/presets/*.json; do python3 -c "import json,sys; json.load(open('$f'))" || echo "BAD $f"; done; echo done`
Expected: only `done` (no `BAD` lines).

- [ ] **Step 9: Commit**

```bash
git add cmake/presets/10-itk-v5.json cmake/presets/10-itk-v6.json cmake/presets/20-ANTs.json cmake/presets/30-BRAINSTools.json bin/tests/test_variants.py
git commit -m "ENH: Add ITK/ANTs/BRAINSTools variant presets for env-gated -D bundles"
```

---

### Task 6a: Route `do_overlay` through the resolver; drop the vestigial FRAGMENT arg

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` — replace `write_overlay`/`do_overlay` (lines ~341-377) and every `do_overlay` call site in `configure_one` (lines ~914-1026).

**Interfaces:**
- Consumes: `config.py resolve-overlay` (Task 2).
- Produces: `do_overlay NAME PRESET SRC BIN [KEY=VAL ...]` — new 4-fixed-arg signature (FRAGMENT removed).

- [ ] **Step 1: Replace `write_overlay` + `do_overlay`** — delete the whole `write_overlay(){…}` heredoc block and its `do_overlay(){…}` (lines ~341-377); replace with:

```bash
# do_overlay NAME PRESET SRC BIN [KEY=VAL ...]
#   Resolve the kit preset chain into a flattened, self-contained
#   CMakeUserPresets.json in SRC (no include back to the kit) and a matching
#   [config.NAME] record in the forest manifest, then configure via cmake.
do_overlay(){
  local name="$1" preset="$2" src="$3" bin="$4"; shift 4
  cfg resolve-overlay "${preset}" "${src}" "${bin}" "${FOREST}" "${name}" "$@"
  cmake -S "${src}" --preset "forest-${name}-local"
}
```

- [ ] **Step 2: Update every `do_overlay` call site** — drop the 3rd (FRAGMENT) argument. Apply these exact edits in `configure_one`:

- ANTs (line ~914): `do_overlay ANTs itk-forest-ants 20-ANTs.json "$s" "$b" "${ants_kvs[@]}"` → `do_overlay ANTs itk-forest-ants "$s" "$b" "${ants_kvs[@]}"` (the preset name is corrected in Task 6c).
- BRAINSTools (line ~932): `do_overlay BRAINSTools itk-forest-brainstools 30-BRAINSTools.json "$s" "$b" "${bt_kvs[@]}"` → `do_overlay BRAINSTools itk-forest-brainstools "$s" "$b" "${bt_kvs[@]}"` (preset corrected in Task 6c).
- Slicer (line ~946): remove `40-Slicer.json` arg.
- SlicerExtensions (line ~966): remove `00-base.json` arg; preset stays `itk-forest-base`.
- MITK (line ~973): remove `00-base.json`.
- elastix (line ~975), c3d (line ~976): remove `00-base.json`.
- Plastimatch (line ~980): remove `50-Plastimatch.json`.
- SimpleITK (line ~986): remove `51-SimpleITK.json`.
- RTK (line ~988), Ultrasound (line ~990): remove `00-base.json`.
- OpenIGTLink (line ~993): remove `60-OpenIGTLink.json`.
- OpenIGTLinkIO (line ~998), vtkAddon (line ~1003), IGSIO (line ~1008), PlusLib (line ~1016), VkFFTBackend (line ~1025): remove `00-base.json`.
- default `*)` (line ~1026): remove `00-base.json`.

- [ ] **Step 3: Syntax check**

Run: `bash -n bin/setup-itk-downstream-testbed.sh && echo "syntax OK"`
Expected: `syntax OK`

- [ ] **Step 4: Verify a lightweight consumer configures self-contained** — elastix is fast and only needs ITK_DIR. Requires a built ITK in `build_forest-base`; if absent, use whichever forest already has `build_forest-*/ITK/build/ITKConfig.cmake`.

```bash
FOREST_REFERENCE_SUFFIX=base pixi run bash bin/setup-itk-downstream-testbed.sh configure elastix
grep -L itk_forest_build_testbed build_forest-base/elastix/CMakeUserPresets.json
grep -c '"include"' build_forest-base/elastix/CMakeUserPresets.json
```
Expected: the overlay path is printed by `grep -L` (no kit reference in it), and the include count is `0`.

- [ ] **Step 5: Commit**

```bash
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: Route do_overlay through the resolver; emit self-contained overlays"
```

---

### Task 6b: Convert the ITK branch to preset selection + resolver

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` — the ITK branch of `configure_one` (lines ~797-892).

**Interfaces:**
- Consumes: `do_overlay` (Task 6a), preset names `itk-forest-itk-v5[-dcmtk]`, `itk-forest-itk-v6[-vtkglue]` (Task 5).
- Produces: an ITK configure that carries **no inline `-DModule_*`/FFTW/brainweb/testing/examples**; only preset selection, procedural steps, and `VTK_DIR` injection.

- [ ] **Step 1: Replace the ITK branch body.** Keep the `_itk_major` detection and the FFTW-comment removed (FFTW now lives in the fragments). Replace lines ~797-892 (`if [ "$name" = ITK ]; then … return; fi`) with:

```bash
  if [ "$name" = ITK ]; then
    local _itk_major
    _itk_major="$(grep -oE 'ITK_VERSION_MAJOR[^0-9]*[0-9]+' "${s}/CMake/itkVersion.cmake" 2>/dev/null | grep -oE '[0-9]+$' | head -1)"
    _overlay_vnl_headers
    if [ "${_itk_major:-6}" -lt 6 ]; then
      # v5 policy (module set, FFTW-on, testing/examples) lives in 10-itk-v5.json.
      local v5_preset="itk-forest-itk-v5"
      [ "${ITK_WITH_DCMTK:-0}" = 1 ] && v5_preset="itk-forest-itk-v5-dcmtk"
      do_overlay ITK "${v5_preset}" "$s" "${ITK_BUILD}"
      return
    fi
    # v6 policy (ALL_MODULES + excluded-from-all modules, FFTW-off/pocketFFT,
    # brainweb/testing/examples) lives in 10-itk-v6.json. VtkGlue is a variant
    # selected when a VTK exists; VTK_DIR is the only injected value.
    local itk_preset="itk-forest-itk-v6" itk_kvs=()
    local _itk_vtk; _itk_vtk="$(itk_vtk_dir)"
    if [ -n "${_itk_vtk}" ]; then
      itk_preset="itk-forest-itk-v6-vtkglue"
      itk_kvs+=("VTK_DIR=${_itk_vtk}")
    fi
    # Two-pass: first configure fetches remote modules (may fail on one whose
    # examples/ dir is absent); stub those, then reconfigure for real.
    cfg resolve-overlay "${itk_preset}" "$s" "${ITK_BUILD}" "${FOREST}" ITK "${itk_kvs[@]}"
    cmake -S "$s" --preset "forest-ITK-local" || true
    _stub_remote_examples
    cmake -S "$s" --preset "forest-ITK-local"
    return
  fi
```

- [ ] **Step 2: Confirm the old inline arrays are gone**

Run: `grep -nE 'Module_AdaptiveDenoising|ITK_USE_FFTWD|ITK_BUILD_ALL_MODULES' bin/setup-itk-downstream-testbed.sh`
Expected: no matches (all such policy now lives only in the fragments).

- [ ] **Step 3: Syntax check**

Run: `bash -n bin/setup-itk-downstream-testbed.sh && echo "syntax OK"`
Expected: `syntax OK`

- [ ] **Step 4: Configure ITK v6 via the preset and diff the resolved module set.** Use a forest with a v6 ITK checked out (`build_forest-itkv6_main`).

```bash
FOREST_REFERENCE_SUFFIX=itkv6_main pixi run bash bin/setup-itk-downstream-testbed.sh configure ITK 2>&1 | tail -5
grep -q '"include"' build_forest-itkv6_main/ITK/CMakeUserPresets.json && echo "FAIL: include present" || echo "self-contained OK"
grep -E 'ITK_USE_FFTWD|ITK_BUILD_ALL_MODULES|Module_AdaptiveDenoising' build_forest-itkv6_main/ITK/build/CMakeCache.txt | head
```
Expected: `self-contained OK`; `ITK_USE_FFTWD:BOOL=OFF`, `ITK_BUILD_ALL_MODULES:BOOL=ON`, `Module_AdaptiveDenoising:BOOL=ON` present in the cache — proving the fragment policy reached CMake.

- [ ] **Step 5: Commit**

```bash
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: Make ITK configure preset-primary (policy in 10-itk-* fragments)"
```

---

### Task 6c: Variant selection for ANTs and BRAINSTools

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` — ANTs case (lines ~896-914) and BRAINSTools case (lines ~915-932).

**Interfaces:**
- Consumes: variant preset names (Task 5), `do_overlay` (Task 6a).
- Produces: ANTs/BRAINSTools configures where the env-gated `-D` bundle is chosen by *preset name*, not inline `-D` assembly.

- [ ] **Step 1: Rewrite the ANTs case.** Replace the `ANTS_MAX_MODULES` inline `USE_VTK/BUILD_ALL_ANTS_APPS` additions with variant selection; keep the genuinely dynamic VTK wiring as kvs:

```bash
    ANTs)
                 local ants_preset="itk-forest-ants" ants_kvs=("ITK_DIR=$(itk_dir)")
                 if [ "${ANTS_MAX_MODULES:-0}" = 1 ]; then
                   ants_preset="itk-forest-ants-max-modules"
                   if [ -n "${ANTS_VTK_DIR:-}" ]; then
                     ants_kvs+=("USE_SYSTEM_VTK=ON" "VTK_DIR=${ANTS_VTK_DIR}")
                   else
                     ants_kvs+=("USE_SYSTEM_VTK=OFF" "CMAKE_C_FLAGS=-Wno-error=implicit-function-declaration")
                   fi
                 fi
                 do_overlay ANTs "${ants_preset}" "$s" "$b" "${ants_kvs[@]}" ;;
```

- [ ] **Step 2: Rewrite the BRAINSTools case.** Select `-max-modules` for the bundle; inject the archive flag, no-ants, fork wiring, and ants_system_args as kvs:

```bash
    BRAINSTools)
                 local bt_preset="itk-forest-brainstools"
                 local bt_kvs=("ITK_DIR=$(itk_dir)"
                   "BRAINSTools_ANTs_GIT_REPOSITORY=${BRAINSTools_ANTs_GIT_REPOSITORY:-$(cfg get subbuild.BRAINSTools.ANTs_GIT_REPOSITORY)}"
                   "BRAINSTools_ANTs_GIT_TAG=${BRAINSTools_ANTs_GIT_TAG:-$(cfg get subbuild.BRAINSTools.ANTs_GIT_TAG)}")
                 if [ "${BRAINSTOOLS_MAX_MODULES:-0}" = 1 ]; then
                   bt_preset="itk-forest-brainstools-max-modules"
                   [ "${BRAINSTOOLS_BUILD_ARCHIVE:-0}" = 1 ] && bt_kvs+=("BUILD_ARCHIVE=ON")
                 fi
                 [ "${BRAINSTOOLS_NO_ANTS:-0}" = 1 ] && bt_kvs+=("USE_ANTS=OFF")
                 local _asa; for _asa in $(ants_system_args); do bt_kvs+=("${_asa#-D}"); done
                 local _bte; for _bte in ${BRAINSTOOLS_EXTRA:-}; do bt_kvs+=("${_bte#-D}"); done
                 do_overlay BRAINSTools "${bt_preset}" "$s" "$b" "${bt_kvs[@]}" ;;
```

- [ ] **Step 3: Syntax check**

Run: `bash -n bin/setup-itk-downstream-testbed.sh && echo "syntax OK"`
Expected: `syntax OK`

- [ ] **Step 4: Verify variant selection lands in the manifest.** Requires a built ITK6 forest with ANTs checked out.

```bash
ANTS_MAX_MODULES=1 FOREST_REFERENCE_SUFFIX=itkv6_main \
  pixi run bash bin/setup-itk-downstream-testbed.sh configure ANTs 2>&1 | tail -3
grep -A3 '\[config.ANTs\]' build_forest-itkv6_main/manifest.toml
grep -E 'USE_VTK|BUILD_ALL_ANTS_APPS' build_forest-itkv6_main/ANTs/build/CMakeCache.txt
```
Expected: `preset = "itk-forest-ants-max-modules"` in the manifest; `USE_VTK:BOOL=ON` and `BUILD_ALL_ANTS_APPS:BOOL=ON` in the cache.

- [ ] **Step 5: Commit**

```bash
git add bin/setup-itk-downstream-testbed.sh
git commit -m "ENH: Select ANTs/BRAINSTools max-modules bundles via variant presets"
```

---

### Task 7: Empirical v5 probe — verify, then adopt

**Files:**
- Possibly modify: `cmake/presets/10-itk-v5.json` (only if the probe fails).

**Interfaces:** none (empirical decision task).

- [ ] **Step 1: Point a scratch forest's ITK at `release-5.4` and configure via the v5 preset.** Use a disposable suffix so no real A/B forest is disturbed.

```bash
ITK_REF=release-5.4 FOREST_REFERENCE_SUFFIX=v5probe \
  pixi run bash bin/setup-itk-downstream-testbed.sh checkout ITK 2>&1 | tail -5
ITK_REF=release-5.4 FOREST_REFERENCE_SUFFIX=v5probe \
  pixi run bash bin/setup-itk-downstream-testbed.sh configure ITK 2>&1 | tee build_forest-v5probe/logs/itk-configure.log | tail -20
```
(If `build_forest-v5probe/logs/` does not yet exist, create it: `mkdir -p build_forest-v5probe/logs` — Task 8 makes this automatic.)

- [ ] **Step 2: Decide from the artifact.**
  - **Clean configure** (`ITKConfig.cmake` written under `build_forest-v5probe/ITK/build/`): keep `10-itk-v5.json` unchanged — v5 == full set. Record the outcome in the commit message; no file change.
  - **Configure fails** (remote-example `find_package(ITK COMPONENTS ITKImageIO)` or missing `ITKData` target): edit `10-itk-v5.json` — set `ITK_BUILD_ALL_MODULES` to `OFF`, `BUILD_TESTING`/`BUILD_EXAMPLES`/`ITK_USE_BRAINWEB_DATA` to `OFF`, and remove the `Module_*` entries that only apply to v6-ingested remotes; keep `ITK_BUILD_DEFAULT_MODULES=ON` and the FFTW-on block. Re-run Step 1 to confirm clean.

- [ ] **Step 3: Tear down the probe forest**

```bash
rm -rf build_forest-v5probe
```

- [ ] **Step 4: Commit the outcome**

```bash
# If the fragment was edited:
git add cmake/presets/10-itk-v5.json
git commit -m "ENH: Correct 10-itk-v5.json to the empirically-clean release-5.4 module set"
# If no edit was needed, record the verification instead:
git commit --allow-empty -m "DOC: Verify 10-itk-v5.json full module set configures clean on release-5.4"
```

---

### Task 8: Route all logs to `${FOREST}/logs/`

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` (add `forest_log_dir`; ensure `${FOREST}/logs` exists at startup)
- Modify: `bin/run-matrix.sh` (replace `/tmp/...` log paths with `${FOREST}/logs/...`)

**Interfaces:**
- Produces: `forest_log_dir()` → prints `${FOREST}/logs`, creating it.

- [ ] **Step 1: Add the helper to `bin/setup-itk-downstream-testbed.sh`** — after the `FOREST` resolution block (after line ~69):

```bash
# All logs for a forest live inside that forest (never the kit root).
forest_log_dir(){ mkdir -p "${FOREST}/logs"; echo "${FOREST}/logs"; }
```

- [ ] **Step 2: Repoint `run-matrix.sh` log paths.** In `bin/run-matrix.sh`:
  - After line ~22 (`TB="${FOREST}"`), add: `LOGDIR="${FOREST}/logs"; mkdir -p "${LOGDIR}"`
  - Line ~60: `log="/tmp/ctest-${n}${LOG_TAG}.log"` → `log="${LOGDIR}/ctest-${n}${LOG_TAG}.log"`
  - Line ~103: `>"/tmp/matrix-${n}${LOG_TAG}.log"` → `>"${LOGDIR}/matrix-${n}${LOG_TAG}.log"`
  - Line ~109: `(/tmp/ctest-${n}${LOG_TAG}.log)` → `(${LOGDIR}/ctest-${n}${LOG_TAG}.log)`
  - Lines ~114-115: both `/tmp/matrix-${n}${LOG_TAG}.log` → `${LOGDIR}/matrix-${n}${LOG_TAG}.log`

- [ ] **Step 3: Syntax check both scripts**

Run: `bash -n bin/setup-itk-downstream-testbed.sh && bash -n bin/run-matrix.sh && echo "syntax OK"`
Expected: `syntax OK`

- [ ] **Step 4: Confirm no `/tmp/` log paths remain in run-matrix.sh**

Run: `grep -n '/tmp/' bin/run-matrix.sh || echo "no /tmp logs"`
Expected: `no /tmp logs`

- [ ] **Step 5: Sweep pre-existing kit-root logs into their forest (one-time).** These stray files (`matrix-*.log`, `svdc-linpackref-validation-*.log`, `itk-forest-*.log`) are the anti-pattern; move the ones that map to a known forest, delete the rest after inspection.

```bash
ls matrix-*.log svdc-linpackref-validation-*.log itk-forest-*.log 2>/dev/null
mkdir -p build_forest-itkv6_main/logs
git mv 2>/dev/null || true   # they are untracked (kit root logs are gitignored); use plain mv
mv matrix-Slicer-itkv6_main-*.log matrix-SlicerExtensions-itkv6_main-*.log build_forest-itkv6_main/logs/ 2>/dev/null || true
```
(Adjust the mapping by the `-<suffix>-` embedded in each filename. Files with no clear forest may be deleted after a glance.)

- [ ] **Step 6: Commit**

```bash
git add bin/setup-itk-downstream-testbed.sh bin/run-matrix.sh
git commit -m "ENH: Write all forest logs under \${FOREST}/logs instead of kit root or /tmp"
```

---

### Task 9: Full regression + self-containment audit

**Files:** none (verification only).

- [ ] **Step 1: Run every unit test**

Run: `for t in bin/tests/test_*.py; do echo "== $t"; python3 "$t" || exit 1; done`
Expected: each file ends `PASS`.

- [ ] **Step 2: Self-containment audit across all forests**

Run: `find build_forest-* -maxdepth 2 -name CMakeUserPresets.json -exec grep -l itk_forest_build_testbed {} + || echo "all self-contained"`
Expected: `all self-contained` (no overlay references the kit).

- [ ] **Step 3: A/B smoke test of the compare utility** (whichever two forests both have a `manifest.toml`)

Run: `python3 bin/config.py compare build_forest-itkv5 build_forest-itkv6_main`
Expected: a `## config -D deltas` section showing at least `ITK.ITK_USE_FFTWD: ON != OFF` once both forests have been reconfigured through the resolver.

- [ ] **Step 4: Final commit (empty marker if nothing changed)**

```bash
git commit --allow-empty -m "TEST: Preset-primary completion — unit tests pass, forests self-contained"
```

---

## Self-Review Notes

- **Spec coverage:** Change 1 (ITK routing) → Task 6b; Change 2 (variants) → Tasks 5 + 6c; Change 3 (v5 verify) → Task 7; flattened overlay → Tasks 2 + 6a; manifest `[config.*]` → Task 3; `${FOREST}/logs/` → Task 8; compare utility → Task 4; self-containment audit → Task 9. All spec sections map to a task.
- **Sequencing:** Tasks 1→4 build the Python core (each unit-tested); Task 5 supplies variant names consumed by 6b/6c; Task 6a must precede 6b/6c (shared `do_overlay`); Task 8 is independent and may run anytime after 6a.
- **Type consistency:** `resolve_preset(name, presets_dir, _index)`, `cmd_resolve_overlay(preset, src, binary_dir, forest, consumer, kvs)`, `_write_config_record(forest, consumer, preset, cache)`, `_parse_manifest(path)->(components,config)`, `_emit_manifest(forest, components, config)`, `cmd_compare(forest_a, forest_b)` — names/arities are consistent across tasks and dispatch.
- **Out of scope (unchanged):** `_patch_*` functions, `workflowPresets`/`run-matrix.sh` reduction, consumer upstream changes, and the run-matrix `${name}-build` vs nested-`build` inconsistency (pre-existing; not introduced here).
