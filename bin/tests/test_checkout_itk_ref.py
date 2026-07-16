"""_checkout_itk_ref lands on the requested ref, and dies when it cannot.

`ITK_REF=<ref> checkout` was a silent no-op on the ref: cmd_checkout resolved
ITK from its versions.toml default and only repoint-itk ever read ITK_REF. Both
now call this one helper, so testing it covers both entry points.

The engine cannot be sourced (its dispatch defaults to `checkout`), so the
helper's real source text is extracted and evaluated against stub log/warn/die.
"""
import os, re, sys, subprocess, tempfile

BIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(BIN, "setup-itk-downstream-testbed.sh")


def _extract(func):
    """The function's real text from the engine, from `name(){` to a bare `}`."""
    src = open(ENGINE).read()
    m = re.search(rf"^{re.escape(func)}\(\)\{{$.*?^\}}$", src, re.M | re.S)
    assert m, f"{func} not found in {ENGINE}"
    return m.group(0)


STUBS = """
log(){ :; }
warn(){ printf 'warn: %s\\n' "$*" >&2; }
die(){ printf 'err: %s\\n' "$*" >&2; exit 1; }
"""


def _run(itk, ref, wt="itk-downstream"):
    script = STUBS + _extract("_checkout_itk_ref") + \
        f'\n_checkout_itk_ref "{itk}" "{ref}" "{wt}"\n'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def _git(d, *a):
    subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, text=True)


def _sha(d, rev="HEAD"):
    return subprocess.run(["git", "-C", d, "rev-parse", rev], check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(tmp, name="ITK"):
    """A repo on 'main' (c2) with 'feat' left behind at c1."""
    d = os.path.join(tmp, name)
    os.makedirs(d)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t"); _git(d, "config", "user.name", "t")
    open(os.path.join(d, "f"), "w").write("1")
    _git(d, "add", "f"); _git(d, "commit", "-qm", "c1")
    _git(d, "branch", "feat")
    open(os.path.join(d, "f"), "w").write("2")
    _git(d, "add", "f"); _git(d, "commit", "-qm", "c2")
    return d


def test_lands_on_requested_local_branch():
    with tempfile.TemporaryDirectory() as tmp:
        d = _repo(tmp)
        want = _sha(d, "feat")
        r = _run(d, "feat")
        assert r.returncode == 0, r.stderr
        assert _sha(d) == want, "did not land on the requested ref"


def test_lands_on_requested_remote_ref():
    """The shape that failed for real: ITK_REF=origin/release-5.4."""
    with tempfile.TemporaryDirectory() as tmp:
        up = _repo(tmp, "upstream")
        d = _repo(tmp, "ITK")
        _git(d, "remote", "add", "origin", up)
        _git(d, "fetch", "-q", "origin")
        want = _sha(up, "feat")
        r = _run(d, "origin/feat")
        assert r.returncode == 0, r.stderr
        assert _sha(d) == want, "did not land on the requested remote ref"


def test_checkout_is_on_the_forest_branch():
    with tempfile.TemporaryDirectory() as tmp:
        d = _repo(tmp)
        r = _run(d, "feat", wt="itk-downstream-suffix")
        assert r.returncode == 0, r.stderr
        cur = subprocess.run(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        assert cur == "itk-downstream-suffix", cur


def test_bogus_ref_dies_nonzero():
    """A ref that was asked for and not honored must never reach success."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _repo(tmp)
        before = _sha(d)
        r = _run(d, "no-such-ref")
        assert r.returncode != 0, "bogus ref fell through to success"
        assert _sha(d) == before


def test_bogus_remote_ref_dies_nonzero():
    with tempfile.TemporaryDirectory() as tmp:
        d = _repo(tmp)
        r = _run(d, "origin/no-such-ref")
        assert r.returncode != 0, "bogus remote ref fell through to success"


def test_cmd_checkout_applies_itk_ref():
    """cmd_checkout must consult ITK_REF for ITK -- the root cause."""
    src = open(ENGINE).read()
    m = re.search(r"^cmd_checkout\(\)\{.*?^\s*cfg manifest", src, re.M | re.S)
    assert m, "cmd_checkout not found"
    body = m.group(0)
    assert "_checkout_itk_ref" in body, \
        "cmd_checkout never applies ITK_REF: ITK_REF=<ref> checkout is a no-op"
    assert "ITK_REF_EXPLICIT" in body, \
        "cmd_checkout must act only on an explicitly requested ref"


def test_ref_resolution_is_not_duplicated():
    """One fact, one implementation: only the helper resolves ITK refs."""
    src = open(ENGINE).read()
    assert len(re.findall(r"^_checkout_itk_ref\(\)\{$", src, re.M)) == 1
    # The PR-shorthand fetch is the fingerprint of the resolution logic.
    assert src.count("pull/${num}/head") == 1, \
        "ITK ref resolution appears to be implemented twice"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
