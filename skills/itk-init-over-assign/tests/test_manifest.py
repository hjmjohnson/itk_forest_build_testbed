from pathlib import Path

from ioa.manifest import Manifest, Site
from ioa.skip import Reason


def test_manifest_roundtrip(tmp_path):
    m = Manifest("local-init", [Site(Path("a.cxx"), 10, 12, "local-init", "assign")])
    m.write(tmp_path / "m.json")
    assert Manifest.read(tmp_path / "m.json").covers(Path("a.cxx"), 11)


def test_roundtrip_preserves_skip_reason_and_note(tmp_path):
    s = Site(Path("a.cxx"), 1, 2, "k", "c", skipped=Reason.PREPROCESSOR, note="n")
    Manifest("k", [s]).write(tmp_path / "m.json")
    got = Manifest.read(tmp_path / "m.json")
    assert got.sites == [s]
    assert got.sites[0].skipped is Reason.PREPROCESSOR


def test_skipped_sites_are_not_covered():
    s = Site(Path("a.cxx"), 1, 2, "k", "c", skipped=Reason.LOOP_CARRIED)
    assert not Manifest("k", [s]).covers(Path("a.cxx"), 1)


def test_covers_bounds_and_file():
    m = Manifest("k", [Site(Path("a.cxx"), 5, 7, "k", "c")])
    assert m.covers(Path("a.cxx"), 5) and m.covers(Path("a.cxx"), 7)
    assert not m.covers(Path("a.cxx"), 8)
    assert not m.covers(Path("b.cxx"), 6)


def test_applied_and_skipped_partition():
    a = Site(Path("a"), 1, 1, "k", "c")
    b = Site(Path("a"), 2, 2, "k", "c", skipped=Reason.NARROWING)
    m = Manifest("k", [a, b])
    assert m.applied() == [a] and m.skipped() == [b]


def test_reason_vocabulary_is_exact():
    assert [r.value for r in Reason] == [
        "loop-carried", "costly-construct", "try-read-after", "preprocessor",
        "goto-or-case", "narrowing", "init-list-ctor", "static-local",
        "order-violation", "no-including-tu", "comment-stranded",
        "gate-failed", "itk-version",
    ]
