"""cmd_manifest must never record a requested ref its own sha contradicts.

The forest that motivated this recorded ref="origin/release-5.4" next to a sha
that was origin/main: the request was never honored and nothing checked.
"""
import io, os, sys, subprocess, tempfile, contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _git(d, *a):
    subprocess.run(["git", "-C", d, *a], check=True,
                   capture_output=True, text=True)


def _sha(d, rev="HEAD"):
    return subprocess.run(["git", "-C", d, "rev-parse", rev], check=True,
                          capture_output=True, text=True).stdout.strip()


def _forest_with_itk(tmp):
    """A forest whose ITK repo has branch 'feat' (c1) and 'main' (c2 = HEAD)."""
    d = os.path.join(tmp, "ITK")
    os.makedirs(d)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    _git(d, "remote", "add", "origin", "https://example.invalid/ITK.git")
    open(os.path.join(d, "f"), "w").write("1")
    _git(d, "add", "f"); _git(d, "commit", "-qm", "c1")
    _git(d, "branch", "feat")            # feat stays at c1
    open(os.path.join(d, "f"), "w").write("2")
    _git(d, "add", "f"); _git(d, "commit", "-qm", "c2")
    return d


def _manifest(tmp, requested):
    """Run cmd_manifest with ITK_REF_EXPLICIT=requested; return (rec, stderr)."""
    old = os.environ.get("ITK_REF_EXPLICIT")
    os.environ["ITK_REF_EXPLICIT"] = requested
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            config.cmd_manifest(tmp)
    finally:
        if old is None:
            os.environ.pop("ITK_REF_EXPLICIT", None)
        else:
            os.environ["ITK_REF_EXPLICIT"] = old
    comps, _, _ = config._parse_manifest(os.path.join(tmp, "manifest.toml"))
    return comps["ITK"], err.getvalue()


def test_unhonored_request_is_not_recorded():
    """The defect: worktree on main, 'feat' requested -> must record main."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _forest_with_itk(tmp)
        rec, err = _manifest(tmp, "feat")
        assert rec["sha"] == _sha(d, "main"), rec
        assert rec["ref"] != "feat", f"recorded a ref its own sha contradicts: {rec}"
        assert rec["ref"] == "main", rec
        assert rec.get("slug") != "feat", rec
        assert "requested ref" in err and "feat" in err, err


def test_unhonored_request_warns_naming_both_shas():
    with tempfile.TemporaryDirectory() as tmp:
        d = _forest_with_itk(tmp)
        _, err = _manifest(tmp, "feat")
        assert _sha(d, "feat")[:8] in err, err
        assert _sha(d, "main")[:8] in err, err


def test_unresolvable_request_is_not_recorded():
    with tempfile.TemporaryDirectory() as tmp:
        _forest_with_itk(tmp)
        rec, err = _manifest(tmp, "origin/no-such-branch")
        assert rec["ref"] == "main", rec
        assert "<unresolvable>" in err, err


def test_honored_request_is_recorded():
    """Verification must not block the truthful case."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _forest_with_itk(tmp)
        _git(d, "checkout", "-q", "feat")
        rec, err = _manifest(tmp, "feat")
        assert rec["ref"] == "feat", rec
        assert rec["sha"] == _sha(d, "feat"), rec
        assert rec.get("slug") == "feat", rec
        assert "requested ref" not in err, err  # only the ref check speaks here


def test_verification_never_raises():
    """A manifest write rides on nearly every command; it must not brick one."""
    with tempfile.TemporaryDirectory() as tmp:
        _forest_with_itk(tmp)
        for ref in ("feat", "pr/6250", "origin/nope", "deadbeef", "@@bogus@@"):
            rec, _ = _manifest(tmp, ref)
            assert rec["ref"] == "main", (ref, rec)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"ok {name}")
    print("PASS")
