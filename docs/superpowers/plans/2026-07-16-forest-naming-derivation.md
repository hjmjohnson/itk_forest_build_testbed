# Forest Naming Derivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive every ITK-ref forest's name from its ITK ref so a forest's name and manifest can never lie about what it contains.

**Architecture:** A pure `refslug()` in `bin/config.py` maps any ITK ref to a git- and filesystem-safe slug. The bash engine (`bin/setup-itk-downstream-testbed.sh`) calls it to compute `build_forest-itk-<slug>`, reserving the `itk-` prefix for derived names. `cmd_manifest` stops reporting the declared default (`spec.get("ref", "origin/main")`) and records the resolved ref/slug/SHA/ITK-version plus a `[forest]` section. Config keyed by the old suffix strings is migrated and validated at startup so a rename can never silently change build behaviour.

**Tech Stack:** Python 3.11+ (`tomllib`), bash, pixi (conda toolchain), git worktrees.

**Spec:** `docs/superpowers/specs/2026-07-16-forest-naming-derivation-design.md` (commit `bc9762a`)

## Global Constraints

- **Tests are self-running scripts, NOT pytest.** pytest is not installed in the pixi env or system. Every test file ends with the established `__main__` block and is run as `python3 bin/tests/test_x.py`, printing `ok test_<name>` per test then `PASS`, exit 0. Copy the block verbatim from `bin/tests/test_resolve_preset.py`.
- **No pre-commit config in this repo.** Commits are plain `git commit`; do not run `pre-commit run --all-files`.
- **`config.py` requires Python ≥3.11** (`tomllib`); it already `sys.exit`s otherwise.
- **Cross-platform (macOS BSD + Linux GNU):** `grep -E` not `-P`; no `sed -i`.
- **Never `git add -A`.** Stage files explicitly (`.devlocal/`, `.remember/`, `.serena/` must not enter history).
- **`refslug()` must stay pure** — no git calls, no filesystem access. Impure remote discovery lives in the CLI wrapper only.
- **Slug validity:** must match `^[A-Za-z0-9._-]+$`, not start with `.` or `-`, not contain `..`, not end with `.lock`.
- Existing engine behaviour outside naming (build order, dependency graph, patches) must not change.

---

### Task 1: `refslug()` — the pure primitive

**Files:**
- Modify: `bin/config.py` (add `DEFAULT_REMOTES`, `refslug`, `cmd_refslug`; wire CLI dispatch at the `if __name__ == "__main__":` block, currently line ~360)
- Test: `bin/tests/test_refslug.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `config.DEFAULT_REMOTES: tuple[str, ...]` = `("origin", "upstream")`
  - `config.refslug(ref: str, remotes: tuple[str, ...] = DEFAULT_REMOTES) -> str` — pure; raises `ValueError` on an unslugga­ble ref.
  - `config.cmd_refslug(ref: str, itk_clone: str | None = None) -> int` — impure wrapper; prints the slug; discovers remotes via `git -C <itk_clone> remote` when `itk_clone` is given, else uses `DEFAULT_REMOTES`.
  - CLI: `python3 bin/config.py refslug <ref> [itk_clone]`

**Why `remotes` is a parameter:** stripping a leading `<remote>/` requires knowing the remote names. This clone has four (`origin`, `upstream`, `hjfork`, `hjmjohnson`). Blindly stripping the first `/`-component would turn a `feature/foo` branch into `foo`. Keeping `remotes` an argument preserves purity and testability; the CLI supplies the real list.

- [ ] **Step 1: Write the failing test**

Create `bin/tests/test_refslug.py`:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

REMOTES = ("origin", "upstream", "hjfork", "hjmjohnson")


def test_remote_stripped():
    assert config.refslug("origin/release-5.4", REMOTES) == "release-5.4"
    assert config.refslug("upstream/release-5.4", REMOTES) == "release-5.4"
    assert config.refslug("origin/main", REMOTES) == "main"
    assert config.refslug("hjfork/some-branch", REMOTES) == "some-branch"


def test_bare_branch_and_tag_verbatim():
    assert config.refslug("release-5.4", REMOTES) == "release-5.4"
    assert config.refslug("main", REMOTES) == "main"
    assert config.refslug("v5.4.6", REMOTES) == "v5.4.6"
    assert config.refslug("v6-integration", REMOTES) == "v6-integration"
    assert config.refslug("origin/v6-integration", REMOTES) == "v6-integration"


def test_pr_forms():
    assert config.refslug("pr/6250", REMOTES) == "pr6250"
    assert config.refslug("pull/6250/head", REMOTES) == "pr6250"
    assert config.refslug("pr/1", REMOTES) == "pr1"


def test_bare_sha():
    assert config.refslug("9a3f1c2b8d4e5f60718293a4b5c6d7e8f9012345", REMOTES) == "sha9a3f1c2"
    assert config.refslug("9a3f1c2", REMOTES) == "sha9a3f1c2"


def test_non_remote_prefix_preserved():
    # 'feature' is not a remote: the slash must NOT be stripped, and the
    # resulting slug is invalid -> ValueError (rather than a silent 'foo').
    try:
        config.refslug("feature/foo", REMOTES)
    except ValueError:
        return
    raise AssertionError("expected ValueError for feature/foo")


def test_unknown_remote_not_stripped():
    try:
        config.refslug("someremote/main", REMOTES)
    except ValueError:
        return
    raise AssertionError("expected ValueError for someremote/main")


def test_rejects_invalid():
    for bad in ("", "..", "-lead", ".lead", "a..b", "x.lock", "has space", "a/b"):
        try:
            config.refslug(bad, REMOTES)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_default_remotes_cover_origin_upstream():
    assert config.refslug("origin/main") == "main"
    assert config.refslug("upstream/release-5.4") == "release-5.4"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_refslug.py`
Expected: FAIL — `AttributeError: module 'config' has no attribute 'refslug'`

- [ ] **Step 3: Write minimal implementation**

In `bin/config.py`, add after the imports/constants block (after `PRESETS_DIR`, ~line 31):

```python
import re

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
    if slug.endswith(".lock"):
        raise ValueError(f"refslug: {slug!r} must not end with '.lock'")


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
```

Note: `_git(d, *args)` already exists in this file (used by `cmd_manifest`); reuse it. If `re` is already imported at the top, do not import it twice.

Wire the CLI — in the `if __name__ == "__main__":` block, add before the `manifest` branch:

```python
    if cmd == "refslug":
        if len(args) < 2:
            sys.exit("usage: config.py refslug <ref> [itk_clone]")
        sys.exit(cmd_refslug(args[1], args[2] if len(args) > 2 else None))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_refslug.py`
Expected:
```
ok test_bare_branch_and_tag_verbatim
ok test_bare_sha
ok test_default_remotes_cover_origin_upstream
ok test_non_remote_prefix_preserved
ok test_pr_forms
ok test_rejects_invalid
ok test_remote_stripped
ok test_unknown_remote_not_stripped
PASS
```

- [ ] **Step 5: Verify the CLI wrapper by hand**

Run:
```bash
python3 bin/config.py refslug origin/release-5.4
python3 bin/config.py refslug pr/6250
python3 bin/config.py refslug hjfork/x forest_git_repos/ITK
python3 bin/config.py refslug feature/foo ; echo "exit=$?"
```
Expected: `release-5.4`, `pr6250`, `x` (real remotes discovered), then an error mentioning `feature/foo` with `exit=1`.

- [ ] **Step 6: Commit**

```bash
git add bin/config.py bin/tests/test_refslug.py
git commit -m "ENH: Add pure refslug() mapping an ITK ref to a forest slug

Remotes are a parameter, not discovered inside the function: stripping a
leading component requires knowing the remote names, and blindly stripping
the first '/' component would turn branch feature/foo into foo. The CLI
wrapper supplies the clone's real remotes; the core stays pure and testable."
```

---

### Task 2: Manifest records resolved truth

**Files:**
- Modify: `bin/config.py` — `_parse_manifest` (~line 90), `_emit_manifest` (~line 115), `_write_config_record` (~line 138), `cmd_manifest` (~line 316)
- Test: `bin/tests/test_manifest_config.py` (extend)

**Interfaces:**
- Consumes: `config.refslug` (Task 1).
- Produces:
  - `config._parse_manifest(path) -> tuple[dict, dict, dict]` — **signature change**: now returns `(components, config, forest_meta)`. All callers must be updated in this task.
  - `config._emit_manifest(forest, components, config, forest_meta=None) -> str`
  - `config._itk_version(itk_src: str) -> str | None` — parses `ITK_VERSION_MAJOR/MINOR/PATCH` from `<itk_src>/CMakeLists.txt`; returns `None` if unparseable.
  - Manifest gains `slug` in each `[components.*]` and a `[forest]` section with `name`, `derived_from`, `itk_version`.

- [ ] **Step 1: Write the failing test**

Append to `bin/tests/test_manifest_config.py` (keep the existing `__main__` block at the bottom — add these functions *above* it):

```python
def test_emit_and_parse_forest_section(tmpdir=None):
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        comps = {"ITK": {"url": "u", "ref": "origin/release-5.4",
                         "slug": "release-5.4", "branch": "b",
                         "sha": "c8721a5c93", "kind": "consumer"}}
        meta = {"name": "build_forest-itk-release-5.4",
                "derived_from": "origin/release-5.4",
                "itk_version": "5.4.6"}
        config._emit_manifest(d, comps, {}, meta)
        c, cfg, fm = config._parse_manifest(os.path.join(d, "manifest.toml"))
        assert c["ITK"]["ref"] == "origin/release-5.4", c["ITK"]
        assert c["ITK"]["slug"] == "release-5.4", c["ITK"]
        assert fm["name"] == "build_forest-itk-release-5.4", fm
        assert fm["derived_from"] == "origin/release-5.4", fm
        assert fm["itk_version"] == "5.4.6", fm
    finally:
        shutil.rmtree(d)


def test_parse_manifest_returns_three_values():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        config._emit_manifest(d, {}, {}, None)
        r = config._parse_manifest(os.path.join(d, "manifest.toml"))
        assert len(r) == 3, f"expected (components, config, forest_meta), got {len(r)}"
    finally:
        shutil.rmtree(d)


def test_parse_missing_manifest_returns_three_empties():
    r = config._parse_manifest("/nonexistent/manifest.toml")
    assert r == ({}, {}, {}), r


def test_itk_version_parsed():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "CMakeLists.txt"), "w") as f:
            f.write('set(ITK_VERSION_MAJOR "5")\n'
                    'set(ITK_VERSION_MINOR "4")\n'
                    'set(ITK_VERSION_PATCH "6")\n')
        assert config._itk_version(d) == "5.4.6"
    finally:
        shutil.rmtree(d)


def test_itk_version_unparseable_returns_none():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "CMakeLists.txt"), "w") as f:
            f.write("project(NotITK)\n")
        assert config._itk_version(d) is None
    finally:
        shutil.rmtree(d)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_manifest_config.py`
Expected: FAIL — `_parse_manifest` returns 2 values / `_itk_version` not defined.

- [ ] **Step 3: Write minimal implementation**

In `bin/config.py`, replace `_parse_manifest`:

```python
def _parse_manifest(path):
    """-> (components, config, forest_meta). Empty dicts when absent."""
    if not os.path.exists(path):
        return {}, {}, {}
    if tomllib is None:
        sys.exit("config.py: needs Python >=3.11 (tomllib) to read/update manifest.toml")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("components", {}), data.get("config", {}), data.get("forest", {})
```

Add `_itk_version` next to it:

```python
def _itk_version(itk_src):
    """ITK version 'MAJOR.MINOR.PATCH' from <itk_src>/CMakeLists.txt, or None."""
    cml = os.path.join(itk_src, "CMakeLists.txt")
    if not os.path.exists(cml):
        return None
    try:
        with open(cml, errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    parts = []
    for field in ("MAJOR", "MINOR", "PATCH"):
        m = re.search(rf'set\s*\(\s*ITK_VERSION_{field}\s+"?(\d+)"?\s*\)', text)
        if not m:
            return None
        parts.append(m.group(1))
    return ".".join(parts)
```

Replace `_emit_manifest` — add `slug` to the emitted keys and the `[forest]` section:

```python
def _emit_manifest(forest, components, config, forest_meta=None):
    out = _manifest_header(forest)
    if forest_meta:
        out.append("[forest]")
        for k in ("name", "derived_from", "itk_version"):
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
```

Replace `_write_config_record` in full — it must not drop `forest_meta` on rewrite:

```python
def _write_config_record(forest, consumer, preset, cache):
    forest = os.path.abspath(forest)
    path = os.path.join(forest, "manifest.toml")
    components, cfg, forest_meta = _parse_manifest(path)
    cfg[consumer] = {"preset": preset, **cache}
    _emit_manifest(forest, components, cfg, forest_meta)
```

Replace the `ref` line and add `slug` + `[forest]` in `cmd_manifest`:

```python
def cmd_manifest(forest):
    """(Re)write <forest>/manifest.toml's [components.*] from live worktrees,
    preserving any [config.*] records already present."""
    forest = os.path.abspath(forest)
    vers = load_versions()
    path = os.path.join(forest, "manifest.toml")
    _, existing_cfg, existing_meta = _parse_manifest(path)
    components = {}
    for name, spec in vers.get("components", {}).items():
        d = os.path.join(forest, name)
        if not (os.path.isdir(os.path.join(d, ".git")) or os.path.exists(os.path.join(d, ".git"))):
            continue
        # Resolved ref, NOT the versions.toml default: the declared default is
        # what made every forest report ref="origin/main" regardless of content.
        resolved = _resolved_ref(d) or spec.get("ref", "")
        rec = {
            "url": _git(d, "remote", "get-url", "origin") or spec.get("url", ""),
            "ref": resolved,
            "branch": _git(d, "rev-parse", "--abbrev-ref", "HEAD"),
            "sha": _git(d, "rev-parse", "HEAD"),
            "kind": spec.get("kind", "consumer"),
        }
        try:
            rec["slug"] = refslug(resolved, _remotes_of(d))
        except ValueError:
            pass  # free-form / unsluggable ref: record no slug rather than fail
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
```

Add the two helpers `cmd_manifest` now needs, next to `_itk_version`:

```python
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
```

`meta["derived_from"]` is written by the engine (Task 3), not here; `cmd_manifest` preserves whatever is already present.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_manifest_config.py`
Expected: every `ok test_*` line, then `PASS`.

- [ ] **Step 5: Verify no caller of `_parse_manifest` still unpacks 2 values**

Run: `grep -n "_parse_manifest(" bin/config.py`
Expected: every call site unpacks three values. `cmd_compare` (~line 340) unpacks two — fix it now:

```python
    ca, cfa, _ = _parse_manifest(os.path.join(os.path.abspath(forest_a), "manifest.toml"))
    cb, cfb, _ = _parse_manifest(os.path.join(os.path.abspath(forest_b), "manifest.toml"))
```

Then run the whole suite: `for t in bin/tests/test_*.py; do echo "-- $t"; python3 "$t" || exit 1; done`
Expected: `PASS` from each.

- [ ] **Step 6: Commit**

```bash
git add bin/config.py bin/tests/test_manifest_config.py
git commit -m "BUG: Record the resolved ITK ref in the manifest, not the default

cmd_manifest read spec.get(\"ref\", \"origin/main\") from versions.toml, so
every forest reported ref=\"origin/main\" no matter what it held --
build_forest-itkv5 claimed origin/main while sitting on release-5.4. Same
class as CMAKE_CXX_COMPILER=\"\$env{CXX}\": the recipe recorded as the record.

Resolve the ref from the worktree's upstream, add its slug, and add a
[forest] section carrying name/derived_from/itk_version. _parse_manifest now
returns a third value; all call sites updated."
```

---

### Task 3: Engine derives the forest name

**Files:**
- Modify: `bin/setup-itk-downstream-testbed.sh` (forest resolution block, lines 64-74)
- Test: `bin/tests/test_forest_name.py` (create)

**Interfaces:**
- Consumes: `python3 bin/config.py refslug <ref> [itk_clone]` (Task 1).
- Produces: shell behaviour — `FOREST` resolves to `<TESTBED>/build_forest-itk-<slug>` when `FOREST_REFERENCE_SUFFIX` is unset; `itk-`-prefixed suffixes are refused unless they equal the derived name.

The engine block currently reads:

```bash
BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT:-build_forest}"
[ -n "${FOREST_REFERENCE_SUFFIX:-}" ] && BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT}-${FOREST_REFERENCE_SUFFIX}"
```

- [ ] **Step 1: Write the failing test**

Create `bin/tests/test_forest_name.py`. It shells out to the engine's `list` command (cheap, no build) and reads the forest it resolved. Add a `--print-forest` command to the engine in Step 3 so the test has a stable probe.

```python
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENG = os.path.join(ROOT, "bin", "setup-itk-downstream-testbed.sh")


def _forest(env_extra):
    env = dict(os.environ)
    env.pop("FOREST", None)
    env.pop("FOREST_REFERENCE_SUFFIX", None)
    env.pop("ITK_REF", None)
    env.update(env_extra)
    p = subprocess.run(["bash", ENG, "--print-forest"], env=env,
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def test_derives_from_itk_ref():
    rc, out, _ = _forest({"ITK_REF": "origin/release-5.4"})
    assert rc == 0, out
    assert os.path.basename(out) == "build_forest-itk-release-5.4", out


def test_derives_pr():
    rc, out, _ = _forest({"ITK_REF": "pr/6250"})
    assert rc == 0, out
    assert os.path.basename(out) == "build_forest-itk-pr6250", out


def test_bare_build_forest_retired():
    # No ITK_REF: the configured default (origin/main) derives itk-main.
    rc, out, _ = _forest({})
    assert rc == 0, out
    assert os.path.basename(out) == "build_forest-itk-main", out


def test_freeform_suffix_passthrough():
    rc, out, _ = _forest({"FOREST_REFERENCE_SUFFIX": "svdc"})
    assert rc == 0, out
    assert os.path.basename(out) == "build_forest-svdc", out


def test_reserved_prefix_refused():
    rc, out, err = _forest({"FOREST_REFERENCE_SUFFIX": "itk-foo",
                            "ITK_REF": "origin/main"})
    assert rc != 0, f"expected refusal, got rc=0 out={out}"
    assert "reserved" in (out + err).lower(), (out, err)


def test_reserved_prefix_allowed_when_it_matches_derivation():
    rc, out, _ = _forest({"FOREST_REFERENCE_SUFFIX": "itk-main",
                          "ITK_REF": "origin/main"})
    assert rc == 0, out
    assert os.path.basename(out) == "build_forest-itk-main", out


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_forest_name.py`
Expected: FAIL — `--print-forest` is an unknown command (engine `die`s with the usage list).

- [ ] **Step 3: Write minimal implementation**

In `bin/setup-itk-downstream-testbed.sh`, replace lines 64-74 (from `BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT:-build_forest}"` through the closing `esac`) with:

```bash
# build_forest root: config BUILD_FOREST_ROOT (default 'build_forest'); a
# relative value resolves against the repo root, an absolute value is used as-is.
BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT:-build_forest}"
# The forest name is DERIVED from the ITK ref: build_forest-itk-<refslug>. A
# name that is merely a promise drifts from its contents (build_forest-itkv5
# held release-5.4). FOREST_REFERENCE_SUFFIX remains for free-form experiment
# forests; the 'itk-' prefix is reserved for derivation.
_derived_suffix(){
  local ref="${ITK_REF:-$(cfg get components.ITK.ref)}" slug
  slug="$(cfg refslug "${ref}" "${REPOS}/ITK" 2>/dev/null)" || return 1
  [ -n "${slug}" ] || return 1
  printf 'itk-%s' "${slug}"
}
if [ -n "${FOREST_REFERENCE_SUFFIX:-}" ]; then
  case "${FOREST_REFERENCE_SUFFIX}" in
    itk-*)
      _want="$(_derived_suffix)" || die "cannot derive a forest name from ITK_REF='${ITK_REF:-}'"
      [ "${FOREST_REFERENCE_SUFFIX}" = "${_want}" ] || die \
        "'itk-' is reserved for derived ref forests (got: ${FOREST_REFERENCE_SUFFIX},
      ITK_REF='${ITK_REF:-$(cfg get components.ITK.ref)}' derives ${_want}).
      Set ITK_REF, or choose a suffix that does not start with 'itk-'."
      unset _want ;;
  esac
  BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT}-${FOREST_REFERENCE_SUFFIX}"
else
  FOREST_REFERENCE_SUFFIX="$(_derived_suffix)" \
    || die "cannot derive a forest name from ITK_REF='${ITK_REF:-}'; set a free-form FOREST_REFERENCE_SUFFIX"
  export FOREST_REFERENCE_SUFFIX
  BUILD_FOREST_ROOT="${BUILD_FOREST_ROOT}-${FOREST_REFERENCE_SUFFIX}"
fi
case "${BUILD_FOREST_ROOT}" in
  /*) FOREST="${FOREST:-${BUILD_FOREST_ROOT}}" ;;
  *)  FOREST="${FOREST:-${TESTBED}/${BUILD_FOREST_ROOT}}" ;;
esac
```

**Ordering constraint:** this block uses `cfg` and `die`, and `_derived_suffix` reads `REPOS`. `cfg()` is defined at line 49, `REPOS` at line ~62, but `die()` is at line 373 — *after* this block. Since `_derived_suffix` is only *called* here, move the `warn()`/`die()` definitions (lines 372-373) to just above this block so `die` is defined when it runs. Verify with `bash -n bin/setup-itk-downstream-testbed.sh` and by running the tests.

Add the `--print-forest` probe to the dispatcher (`case "${1:-checkout}" in`, ~line 1143), as the first branch:

```bash
  --print-forest) printf '%s\n' "${FOREST}" ;;
```

Also add it to the `die` usage list at the bottom of the same `case` so the message stays accurate.

Then add the spec's derived-name/manifest agreement check, immediately after the
`case "${BUILD_FOREST_ROOT}" in … esac` that sets `FOREST`. An existing forest
whose recorded identity disagrees with derivation means the name drifted from
its contents — the exact failure this work removes:

```bash
# A derived forest whose manifest records a different identity has drifted:
# refuse rather than build into a mislabelled tree.
if [ -f "${FOREST}/manifest.toml" ]; then
  _rec_from="$(grep -E '^derived_from' "${FOREST}/manifest.toml" 2>/dev/null | head -1 | cut -d'"' -f2 || true)"
  _rec_name="$(grep -E '^name' "${FOREST}/manifest.toml" 2>/dev/null | head -1 | cut -d'"' -f2 || true)"
  if [ -n "${_rec_from}" ] && [ -n "${_rec_name}" ] \
     && [ "${_rec_name}" != "$(basename "${FOREST}")" ]; then
    die "forest identity mismatch: ${FOREST} records name='${_rec_name}'
      (derived_from='${_rec_from}') but resolved to '$(basename "${FOREST}")'.
      Use the matching ITK_REF, or a free-form FOREST_REFERENCE_SUFFIX."
  fi
  unset _rec_from _rec_name
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_forest_name.py`
Expected:
```
ok test_bare_build_forest_retired
ok test_derives_from_itk_ref
ok test_derives_pr
ok test_freeform_suffix_passthrough
ok test_reserved_prefix_allowed_when_it_matches_derivation
ok test_reserved_prefix_refused
PASS
```

Also confirm the engine still parses and its other commands work:
```bash
bash -n bin/setup-itk-downstream-testbed.sh && echo "syntax OK"
ITK_REF=origin/release-5.4 bash bin/setup-itk-downstream-testbed.sh --print-forest
```
Expected: `syntax OK`, then a path ending `build_forest-itk-release-5.4`.

- [ ] **Step 5: Commit**

```bash
git add bin/setup-itk-downstream-testbed.sh bin/tests/test_forest_name.py
git commit -m "ENH: Derive the forest name from ITK_REF; reserve the itk- prefix

FOREST_REFERENCE_SUFFIX was a free-form promise with nothing tying it to the
ref checked out, so build_forest-itkv5 drifted onto release-5.4 unnoticed.
The engine now derives build_forest-itk-<refslug> from ITK_REF, refuses a
hand-passed itk-* suffix that disagrees with derivation, and retires the bare
build_forest (no ITK_REF derives itk-main from the configured default).
Free-form suffixes still work for experiment forests."
```

---

### Task 4: Migrate + validate suffix-keyed config

**Files:**
- Modify: `versions.toml` (`subbuild.ANTs.skip_suffix`, line ~268 `[scenarios.itkv6_main.elastix]`)
- Modify: `bin/config.py` (add `validate_suffix_keys`; call from `check_only`)
- Test: `bin/tests/test_suffix_keys.py` (create)

**Interfaces:**
- Consumes: `config.refslug` (Task 1).
- Produces: `config.validate_suffix_keys(vers: dict) -> list[str]` — returns a list of error strings (empty = valid). A key starting with `itk-` whose remainder is not a valid slug is an error.

**Why:** two tracked values are keyed by the suffix string. Renaming a forest without updating them changes build behaviour with **no error**: `subbuild.ANTs.skip_suffix = "itkv5"` (engine L478/L495) silently stops skipping the ANTs fork, and `[scenarios.itkv6_main.elastix]` silently stops applying the PR #1452 MatrixExponential fork.

- [ ] **Step 1: Write the failing test**

Create `bin/tests/test_suffix_keys.py`:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


def test_valid_keys_pass():
    vers = {"scenarios": {"itk-main": {"elastix": {}}, "svdc": {"x": {}}},
            "subbuild": {"ANTs": {"skip_suffix": "itk-release-5.4"}}}
    assert config.validate_suffix_keys(vers) == []


def test_malformed_itk_scenario_key_is_error():
    vers = {"scenarios": {"itk-": {"elastix": {}}}}
    errs = config.validate_suffix_keys(vers)
    assert len(errs) == 1, errs
    assert "itk-" in errs[0]


def test_itk_key_with_invalid_slug_is_error():
    vers = {"scenarios": {"itk-bad..slug": {"elastix": {}}}}
    errs = config.validate_suffix_keys(vers)
    assert len(errs) == 1, errs


def test_malformed_skip_suffix_is_error():
    vers = {"subbuild": {"ANTs": {"skip_suffix": "itk-"}}}
    errs = config.validate_suffix_keys(vers)
    assert len(errs) == 1, errs


def test_freeform_keys_are_not_validated():
    vers = {"scenarios": {"svdc": {}, "base": {}, "linpackref": {}},
            "subbuild": {"ANTs": {"skip_suffix": "svdc"}}}
    assert config.validate_suffix_keys(vers) == []


def test_unmatched_scenario_warns_but_is_not_an_error():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        vers = {"scenarios": {"itk-main": {"elastix": {}}}}
        assert config.validate_suffix_keys(vers) == []          # not an error
        w = config.warn_unmatched_scenarios(vers, d)            # but warns
        assert len(w) == 1 and "itk-main" in w[0], w
        os.makedirs(os.path.join(d, "build_forest-itk-main"))
        assert config.warn_unmatched_scenarios(vers, d) == []   # silent once present
    finally:
        shutil.rmtree(d)


def test_live_versions_toml_is_valid():
    # The real file must be migrated (itkv6_main -> itk-main, itkv5 ->
    # itk-release-5.4) and must validate.
    vers = config.load_versions()
    assert config.validate_suffix_keys(vers) == []
    assert "itkv6_main" not in vers.get("scenarios", {}), \
        "scenarios.itkv6_main not migrated to itk-main"
    assert vers["subbuild"]["ANTs"]["skip_suffix"] == "itk-release-5.4", \
        vers["subbuild"]["ANTs"]["skip_suffix"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_suffix_keys.py`
Expected: FAIL — `validate_suffix_keys` not defined.

- [ ] **Step 3: Write minimal implementation**

In `bin/config.py`, add near `refslug`:

```python
def validate_suffix_keys(vers):
    """Config keyed by the forest suffix must stay consistent with derivation.

    A rename that misses these changes the build with no error:
    subbuild.ANTs.skip_suffix gates the ANTs fork, and [scenarios.<suffix>]
    selects consumer overrides. Only 'itk-' keys are checked; free-form
    experiment suffixes are unconstrained by design.
    """
    errs = []

    def _check(where, value):
        if not isinstance(value, str) or not value.startswith("itk-"):
            return
        try:
            _validate_slug(value[len("itk-"):])
        except ValueError as e:
            errs.append(f"{where}: {value!r} is a reserved 'itk-' key but not a "
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
    for key in sorted((vers.get("scenarios") or {})):
        if not os.path.isdir(os.path.join(testbed_root, f"build_forest-{key}")):
            out.append(f"scenarios.{key}: no build_forest-{key} on disk "
                       "(harmless if the forest has not been created yet)")
    return out
```

Wire the warning into `check_only` alongside the errors — it must not affect the
return code:

```python
    for w in warn_unmatched_scenarios(load_versions(), ROOT):
        if warn:
            print(f"  [i] {w}", file=sys.stderr)
```

Call it from `check_only` so `config.py --check` fails on a malformed key.
`check_only` is at `bin/config.py:244` and already accumulates into `rc`.
Replace it in full:

```python
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
```

- [ ] **Step 4: Migrate `versions.toml`**

Edit `versions.toml`:

```toml
[scenarios.itk-main.elastix]
url    = "https://github.com/hjmjohnson/elastix.git"
branch = "demo-itkv6_main"        # PR #1452 MatrixExponential fix on latest main
```

The **key** becomes `itk-main`; the `branch` **value** stays `demo-itkv6_main` — it names a real branch on `hjmjohnson/elastix` that this change does not rename.

And the ANTs skip suffix (find `skip_suffix` under `[subbuild.ANTs]`):

```toml
skip_suffix = "itk-release-5.4"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 bin/tests/test_suffix_keys.py`
Expected: all `ok test_*`, then `PASS`.

Then: `python3 bin/config.py --check; echo "exit=$?"`
Expected: `exit=0`.

Then confirm the scenario still resolves under its new key:
```bash
python3 bin/config.py scenario itk-main elastix
```
Expected: `https://github.com/hjmjohnson/elastix.git|demo-itkv6_main`

- [ ] **Step 6: Commit**

```bash
git add bin/config.py bin/tests/test_suffix_keys.py versions.toml
git commit -m "BUG: Migrate and validate suffix-keyed config

subbuild.ANTs.skip_suffix and [scenarios.<suffix>] are keyed by the forest
suffix string, so renaming a forest without updating them changes the build
with no error: the ANTs fork stops being skipped and elastix silently drops
the PR #1452 MatrixExponential fork. Migrate both to derived names and reject
a reserved itk-* key that is not a valid itk-<refslug>."
```

---

### Task 5: `compare` surfaces the ref/slug delta

**Files:**
- Modify: `bin/config.py` — `cmd_compare` (~line 340)
- Test: `bin/tests/test_compare.py` (extend)

**Interfaces:**
- Consumes: `_parse_manifest` 3-tuple (Task 2).
- Produces: `cmd_compare` output gains a `## forest` section and per-component `ref`/`slug` deltas.

**Why:** comparing `release-5.4` against a PR is the common task, and today `cmd_compare` prints only SHA and `[config.*]` deltas. With every manifest reporting `ref="origin/main"`, a ref delta was structurally invisible.

- [ ] **Step 1: Write the failing test**

Add to `bin/tests/test_compare.py` (above its `__main__` block):

```python
def test_compare_reports_ref_and_slug_delta(capsys=None):
    import tempfile, shutil, io, contextlib
    a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        config._emit_manifest(a, {"ITK": {"ref": "origin/release-5.4",
                                          "slug": "release-5.4",
                                          "sha": "c8721a5c93"}}, {},
                              {"name": "build_forest-itk-release-5.4"})
        config._emit_manifest(b, {"ITK": {"ref": "pr/6250", "slug": "pr6250",
                                          "sha": "deadbeef01"}}, {},
                              {"name": "build_forest-itk-pr6250"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            config.cmd_compare(a, b)
        out = buf.getvalue()
        assert "release-5.4" in out and "pr6250" in out, out
        assert "c8721a5c93"[:12] in out, out
    finally:
        shutil.rmtree(a); shutil.rmtree(b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 bin/tests/test_compare.py`
Expected: FAIL — slugs absent from output.

- [ ] **Step 3: Write minimal implementation**

Replace `cmd_compare`'s body in `bin/config.py`:

```python
def cmd_compare(forest_a, forest_b):
    """Diff two forests' manifest.toml: forest identity, ref/slug/SHA deltas,
    and [config.*] -D deltas."""
    ca, cfa, fma = _parse_manifest(os.path.join(os.path.abspath(forest_a), "manifest.toml"))
    cb, cfb, fmb = _parse_manifest(os.path.join(os.path.abspath(forest_b), "manifest.toml"))
    print(f"# compare A={forest_a}  B={forest_b}")
    print("## forest")
    for k in ("name", "derived_from", "itk_version"):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 bin/tests/test_compare.py`
Expected: all `ok test_*`, then `PASS`.

- [ ] **Step 5: Commit**

```bash
git add bin/config.py bin/tests/test_compare.py
git commit -m "ENH: Surface forest identity and ref/slug deltas in compare

Comparing release-5.4 against a PR is the common task, but compare printed
only SHA and config deltas -- and with every manifest reporting
ref=\"origin/main\", a ref delta was structurally invisible."
```

---

### Task 6: Documentation + migration runbook

**Files:**
- Modify: `CLAUDE.md` (the ⚠ "which forest" section)
- Modify: `docs/config.md` (forest selection / `BUILD_FOREST_ROOT`)
- Modify: `docs/workflow.md` (`FOREST_REFERENCE_SUFFIX` usage, ~lines 75-90)
- Create: `docs/superpowers/plans/2026-07-16-forest-wipe-runbook.md`

**Interfaces:**
- Consumes: everything above. Produces: no code.

- [ ] **Step 1: Update `docs/workflow.md`**

Replace the `FOREST_REFERENCE_SUFFIX` example block with:

````markdown
Forest names are **derived** from the ITK ref — `build_forest-itk-<refslug>`:

```bash
ITK_REF=origin/release-5.4 pixi run checkout   # -> build_forest-itk-release-5.4
ITK_REF=pr/6250 pixi run repoint-itk           # -> build_forest-itk-pr6250
pixi run bash bin/config.py compare build_forest-itk-release-5.4 build_forest-itk-pr6250
```

`itk-` is reserved for derived names; a hand-passed `FOREST_REFERENCE_SUFFIX`
starting with `itk-` that disagrees with derivation is refused. Free-form
suffixes remain for experiment forests (`FOREST_REFERENCE_SUFFIX=svdc`). There
is no bare `build_forest`: with no `ITK_REF`, the configured default
(`origin/main`) derives `build_forest-itk-main`.

One forest per ref: two forests on the same ITK ref need a free-form suffix.
````

- [ ] **Step 2: Update `CLAUDE.md`**

In the ⚠ section, replace the forest list sentence with:

```markdown
**2. Which forest (sub-environment)?** Ref forests are **derived**:
`build_forest-itk-<refslug>` (`build_forest-itk-release-5.4`,
`build_forest-itk-pr6250`, `build_forest-itk-main`). The `itk-` prefix is
reserved for derivation, so a ref forest's name cannot drift from its
contents; `manifest.toml` records the resolved ref, slug, SHA and ITK version.
Experiment forests are free-form (`build_forest-svdc`). **The same source repo
exists in each forest as a separate worktree on a separate per-forest branch
(`itk-downstream-<suffix>`) at a possibly different SHA.** "I built ITK" is
meaningless; "I built ITK `pr/6250` in `build_forest-itk-pr6250`" is actionable.
```

- [ ] **Step 3: Update `docs/config.md`**

Add under the forest-selection heading:

````markdown
### Forest naming (derived)

`FOREST_REFERENCE_SUFFIX` is no longer the primary input — `ITK_REF` is:

| `ITK_REF` | forest |
|---|---|
| `origin/release-5.4` | `build_forest-itk-release-5.4` |
| `v5.4.6` | `build_forest-itk-v5.4.6` |
| `origin/main` (default) | `build_forest-itk-main` |
| `pr/6250` | `build_forest-itk-pr6250` |
| `origin/v6-integration` | `build_forest-itk-v6-integration` |

Slugs come from `python3 bin/config.py refslug <ref> [itk_clone]`.

**Suffix-keyed config.** `subbuild.ANTs.skip_suffix` and `[scenarios.<suffix>]`
in `versions.toml` are keyed by the forest suffix. Renaming a forest without
updating them changes the build with no error, so `config.py --check` rejects a
reserved `itk-*` key that is not a valid `itk-<refslug>`.
````

- [ ] **Step 4: Write the wipe runbook**

Create `docs/superpowers/plans/2026-07-16-forest-wipe-runbook.md`:

````markdown
# Forest wipe + remake runbook (phase 1 migration)

Uncommitted work was preserved on 2026-07-16 to `.devlocal/preserved-20260716/`
(9 patches, 52 K). `build_forest-svdc_Slicer.patch` holds the SUV work
(`ADDITIONAL_SRCS itkDCMTKFileReader.cxx`; BRAINSTools repointed to
`hjmjohnson/BRAINSTools` @ `bfbd9bce`). `.devlocal/` is gitignored and
machine-local, and the patches cover tracked-file edits only.

```bash
cd ~/src/itk_forest_build_testbed

# 1. Confirm the preserved patches are still there BEFORE deleting anything.
ls -la .devlocal/preserved-20260716/*.patch | wc -l    # expect 9

# 2. Delete the forests (~94 G).
rm -rf build_forest build_forest-base build_forest-itkv5 \
       build_forest-itkv6_main build_forest-linpackref build_forest-svdc \
       build_forest-pr-to-merge-into-release5.4

# 3. MANDATORY: prune stale worktree registrations. Without this the central
#    clones still believe those worktrees exist and re-adding the same branch
#    fails with "already checked out".
for r in forest_git_repos/*/; do git -C "$r" worktree prune; done

# 4. Verify no stale registrations remain.
for r in forest_git_repos/*/; do
  git -C "$r" worktree list | grep -q "build_forest" && echo "STALE: $r"
done
echo "prune check done"

# 5. Remake on demand, correctly named.
ITK_REF=origin/release-5.4 pixi run checkout
ITK_REF=origin/release-5.4 pixi run build-ITK
```

**Leave the per-forest branches** (`itk-downstream-itkv5`, …) in the central
clones. They cost nothing and are the only remaining record of what those
forests held — the fallback if a preserved patch proves incomplete. Prune them
in a separate, deliberate cleanup, never as a side effect of this migration.

**Known loss:** `build_forest-svdc` held a Slicer/VTK SuperBuild that 43
manifest entries in other forests pointed at (`VTK_DIR` →
`build_forest-svdc/Slicer/build/VTK-build`). Until phase 3
(`shared_resources/`) lands, a forest needing VTK builds its own.
````

- [ ] **Step 5: Run the full suite once more**

Run: `for t in bin/tests/test_*.py; do echo "-- $t"; python3 "$t" || exit 1; done`
Expected: `PASS` from every file.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md docs/config.md docs/workflow.md \
        docs/superpowers/plans/2026-07-16-forest-wipe-runbook.md
git commit -m "DOC: Document derived forest naming and the wipe runbook"
```

---

## Execution notes

- Tasks 1→5 are strictly ordered: Task 2 consumes `refslug` from Task 1; Task 3 consumes the CLI from Task 1; Task 5 consumes the 3-tuple `_parse_manifest` from Task 2.
- Task 6 is documentation and can be done last.
- **The wipe (runbook, Task 6 Step 4) is written but NOT executed by this plan.** It destroys ~94 G and is gated on explicit human go-ahead.
- After Task 3, existing forests will resolve to new names. That is expected — the old directories are wiped by the runbook, not silently reused.
