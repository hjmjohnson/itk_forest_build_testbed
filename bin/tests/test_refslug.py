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
    # 'main.' / 'origin/main.': git rejects a ref component with a trailing
    # dot, so a forest named for it fails later at worktree creation instead.
    for bad in ("", "..", "-lead", ".lead", "a..b", "x.lock", "has space", "a/b",
                "main.", "origin/main."):
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
