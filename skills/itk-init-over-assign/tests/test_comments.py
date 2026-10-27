import difflib
import re
import subprocess
from pathlib import Path

import pytest

from ioa.comments import check_hunks

FIXTURES = Path(__file__).parent / "fixtures" / "comments"


def diff(name, variant):
    old = (FIXTURES / name / "before.cxx").read_text().splitlines(keepends=True)
    new = (FIXTURES / name / f"{variant}.cxx").read_text().splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old, new, f"a/{name}.cxx", f"b/{name}.cxx", n=0)
    )


ALL = ["doxygen", "trailing", "todo", "block_prose", "trailing_block", "deref"]
BAD = {
    "doxygen": (3, "/**\n* Number of bins.\n*/"),
    "trailing": (5, "// isotropic"),
    "todo": (6, "// TODO: use spacing from input"),
    "block_prose": (4, "/* Histogram of the\ninput values. */"),
    "trailing_block": (5, "/* start at zero */"),
}


@pytest.mark.parametrize("name", ALL)
def test_moved_comment_passes(name):
    assert check_hunks(diff(name, "after_ok")) == []


@pytest.mark.parametrize("name", sorted(BAD))
def test_stranded_comment_fails(name):
    s = check_hunks(diff(name, "after_bad"))
    assert [(x.line, x.text) for x in s] == [BAD[name]]
    assert s[0].file == Path(f"{name}.cxx")


def test_rewritten_pointer_dereference_is_not_a_comment():
    assert check_hunks(diff("deref", "after_ok")) == []


CROSS_HUNK = """\
--- a/x.cxx
+++ b/x.cxx
@@ -4,2 +3,0 @@
-  Vec v;
-  // note about v
@@ -20,0 +19,2 @@
+  // note about v
+  const auto v = Vec::Filled(0);
"""


def test_comment_re_added_in_other_hunk_next_to_its_identifier_passes():
    assert check_hunks(CROSS_HUNK) == []


def test_comment_in_other_hunk_without_the_identifier_fails():
    text = CROSS_HUNK.replace("const auto v", "const auto w")
    assert [s.text.strip() for s in check_hunks(text)] == ["// note about v"]


CROSS_FILE = """\
--- a/a.cxx
+++ b/a.cxx
@@ -7 +6,0 @@
-  m_Foo = 1; // why
--- a/a.h
+++ b/a.h
@@ -12,0 +13 @@
+  int m_Foo{ 1 }; // why
"""


def test_comment_moving_to_another_file_next_to_its_identifier_passes():
    assert check_hunks(CROSS_FILE) == []


def test_cross_file_move_without_the_identifier_fails():
    s = check_hunks(CROSS_FILE.replace("m_Foo{", "m_Bar{"))
    assert [(x.file, x.line, x.text) for x in s] == [(Path("a.cxx"), 7, "// why")]


def test_duplicate_removed_comments_need_duplicate_added_ones():
    text = """\
--- a/d.cxx
+++ b/d.cxx
@@ -3,2 +3 @@
-  a = 1; // same
-  b = 2; // same
+  int a{ 1 }; // same
"""
    assert [x.line for x in check_hunks(text)] == [4]


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def git_diff_after(tmp_path, variant, extra_before=None, extra_after=None):
    repo = tmp_path / variant
    repo.mkdir()
    git(repo, "init", "-q")
    names = ("todo", "trailing")
    for n in names:
        (repo / f"{n}.cxx").write_text((FIXTURES / n / "before.cxx").read_text())
    (repo / "gone.cxx").write_text("int x; // removed with the file\n")
    (repo / "nonl.cxx").write_bytes(b"int x = 1; // keep")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "before")
    for n in names:
        (repo / f"{n}.cxx").write_text((FIXTURES / n / f"{variant}.cxx").read_text())
    (repo / "gone.cxx").unlink()
    (repo / "nonl.cxx").write_bytes(b"int y = 1; // keep")
    git(repo, "add", "-A")
    return subprocess.run(
        ["git", "diff", "-U0", "--cached"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_real_git_diff_with_two_files_deletion_and_no_newline(tmp_path):
    text = git_diff_after(tmp_path, "after_ok")
    assert "diff --git" in text and "/dev/null" in text and "No newline" in text
    assert re.search(r"^@@ -\d+ \+", text, re.M)
    assert check_hunks(text) == []


def test_real_git_diff_reports_both_stranded_comments(tmp_path):
    s = check_hunks(git_diff_after(tmp_path, "after_bad"))
    assert sorted((str(x.file), x.line, x.text) for x in s) == [
        ("todo.cxx", 6, "// TODO: use spacing from input"),
        ("trailing.cxx", 5, "// isotropic"),
    ]
