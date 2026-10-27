import difflib
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


@pytest.mark.parametrize("name", ["doxygen", "trailing", "todo"])
def test_moved_comment_passes(name):
    assert check_hunks(diff(name, "after_ok")) == []


@pytest.mark.parametrize("name", ["doxygen", "trailing", "todo"])
def test_stranded_comment_fails(name):
    s = check_hunks(diff(name, "after_bad"))
    assert s and s[0].text.strip().startswith(("//", "/*", "*"))


def test_todo_after_removed_fill_must_follow_new_decl():
    s = check_hunks(diff("todo", "after_bad"))
    assert s[0].text.strip() == "// TODO: use spacing from input"
    assert s[0].file == Path("todo.cxx")
    assert s[0].line == 6


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
