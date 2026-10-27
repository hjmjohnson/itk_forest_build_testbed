import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import member_init  # noqa: E402
import postfix  # noqa: E402
from ioa.manifest import Manifest  # noqa: E402
from ioa.skip import Reason  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
TOOLS = ["clang-tidy", "run-clang-tidy", "clang-apply-replacements", "clang-format", "cmake", "ninja"]


def _tool(name: str) -> str | None:
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix and (Path(prefix) / "bin" / name).exists():
        return str(Path(prefix) / "bin" / name)
    return shutil.which(name)


pytestmark = pytest.mark.skipif(
    any(_tool(t) is None for t in TOOLS), reason="clang tools, cmake, or ninja not available"
)


@dataclass
class Graph:
    repo: Path
    build: Path


@dataclass
class Result:
    repo: Path
    manifest: Manifest | None
    stdout: str

    def read(self, name: str) -> str:
        return (self.repo / name).read_text()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def fixture_graph(tmp_path):
    def make(name: str) -> Graph:
        repo = tmp_path / name
        shutil.copytree(FIXTURES / name, repo)
        shutil.copy(FIXTURES / ".clang-format", repo / ".clang-format")
        _git(repo, "init", "-q")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "fixture")
        build = tmp_path / "build"
        subprocess.run(
            [_tool("cmake"), "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={_tool('ninja')}",
             "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", "-S", str(repo), "-B", str(build)],
            check=True, capture_output=True, text=True,
        )
        return Graph(repo, build)

    return make


def run_member_init(g: Graph, apply: bool, capsys=None) -> Result:
    manifest = g.repo.parent / "manifest.json"
    argv = ["--graph", str(g.build), "--repo", str(g.repo), "--manifest", str(manifest)]
    member_init.main(argv + (["--apply"] if apply else []))
    out = capsys.readouterr().out if capsys else ""
    return Result(g.repo, Manifest.read(manifest) if manifest.exists() else None, out)


def test_assignment_moves_to_initializer_list(fixture_graph):
    out = run_member_init(fixture_graph("basic"), apply=True)
    text = out.read("foo.cxx")
    assert ": m_A(1)\n  , m_B(2)" in text
    assert "m_A = 1;" not in text


def test_out_of_order_assignments_are_reordered_to_declaration_order(fixture_graph):
    text = run_member_init(fixture_graph("basic"), apply=True).read("foo.cxx")
    assert "Foo::Foo()\n  : m_A(0)\n  , m_B(0)\n  , m_C(0.5)\n{}" in text


def test_trailing_comment_travels_with_the_moved_assignment(fixture_graph):
    text = run_member_init(fixture_graph("basic"), apply=True).read("foo.cxx")
    assert "  , m_B(2) // the B\n" in text
    assert text.count("// the B") == 1


def test_applied_sites_are_recorded_with_post_edit_lines(fixture_graph):
    out = run_member_init(fixture_graph("basic"), apply=True)
    m = out.manifest
    assert m.kind == "member-init"
    assert m.skipped() == []
    assert {s.cls for s in m.sites} == {"prefer-member-initializer"}
    assert [(s.file, s.start, s.end) for s in m.sites] == [
        (Path("foo.cxx"), 4, 7), (Path("foo.cxx"), 10, 13)]


def test_dependent_out_of_order_initializer_is_skipped(fixture_graph):
    g = fixture_graph("order_violation")
    before = (g.repo / "foo.cxx").read_text()
    out = run_member_init(g, apply=True)
    assert [s.skipped for s in out.manifest.sites] == [Reason.ORDER_VIOLATION]
    assert out.read("foo.cxx") == before


def test_smart_pointer_member_gets_no_brace_init(fixture_graph):
    out = run_member_init(fixture_graph("smart_ptr"), apply=True)
    header = out.read("foo.h")
    assert "m_Reader{}" not in header
    assert "m_Reader{ }" not in header
    assert "m_Owned{" not in header
    assert "m_Smart{" not in header
    assert "m_Count{ 0 };" in header
    assert ": m_Reader()\n  , m_Owned()\n  , m_Smart()\n{}" in out.read("foo.cxx")


def test_constant_initializers_become_default_member_initializers(fixture_graph):
    out = run_member_init(fixture_graph("comments"), apply=True)
    assert "int    m_Count{ 0 }; // reset on construction" in out.read("foo.h")
    assert "double m_Scale{ 1.5 };" in out.read("foo.h")
    assert "Foo::Foo(int a)\n  : m_Size(a) // from the caller\n{}" in out.read("foo.cxx")
    assert "reset on construction" not in out.read("foo.cxx")
    assert {s.cls for s in out.manifest.applied()} == {
        "prefer-member-initializer", "use-default-member-init"}


def test_doxygen_block_stays_above_member_that_gains_initializer(fixture_graph):
    header = run_member_init(fixture_graph("comments"), apply=True).read("foo.h")
    assert "  /** Number of reads since construction. */\n  int    m_Count{ 0 };" in header


def test_no_stranded_comments_after_apply(fixture_graph):
    from ioa.comments import check_hunks

    g = fixture_graph("comments")
    run_member_init(g, apply=True)
    assert check_hunks(_git(g.repo, "diff", "-U0")) == []


def test_without_apply_prints_plan_and_writes_nothing(fixture_graph, capsys):
    g = fixture_graph("basic")
    out = run_member_init(g, apply=False, capsys=capsys)
    assert out.manifest is None
    assert _git(g.repo, "status", "--porcelain") == ""
    assert "prefer-member-initializer foo.cxx 6" in out.stdout


def _originals(g: Graph) -> dict[str, str]:
    return {p.name: p.read_text() for p in g.repo.iterdir() if p.suffix in {".h", ".hxx", ".cxx"}}


def test_template_ctor_in_hxx_finds_class_in_sibling_header(fixture_graph):
    out = run_member_init(fixture_graph("template_hxx"), apply=True)
    assert out.manifest.skipped() == []
    hxx = out.read("foo.hxx")
    assert "m_X = T();" not in hxx
    assert "Tpl<T>::Tpl()\n  : m_X(T())\n" in hxx


def test_preprocessor_line_in_initializer_list_skips_the_ctor(fixture_graph):
    g = fixture_graph("preprocessor")
    before = _originals(g)
    out = run_member_init(g, apply=True)
    assert out.read("foo.cxx") == before["foo.cxx"]
    assert Reason.PREPROCESSOR in {s.skipped for s in out.manifest.sites}
    assert all(s.skipped == Reason.PREPROCESSOR for s in out.manifest.sites if s.skipped)


def test_backstop_revert_restores_every_partner_transitively(fixture_graph, monkeypatch):
    from ioa.comments import Stranded

    g = fixture_graph("shared_header")
    before = _originals(g)
    monkeypatch.setattr(
        member_init, "check_hunks", lambda diff: [Stranded(Path("a.cxx"), 5, "// forced")])
    plan_dmi = member_init.Planner.plan_dmi

    def b_pair_first(self, diags):
        plan_dmi(self, diags)
        self.partners = sorted(self.partners, key=lambda pair: "b.cxx" not in {p.name for p in pair})
        assert [sorted(p.name for p in pair) for pair in self.partners] == [["b.cxx", "foo.h"], ["a.cxx", "foo.h"]]

    monkeypatch.setattr(member_init.Planner, "plan_dmi", b_pair_first)
    out = run_member_init(g, apply=True)
    assert _originals(g) == before
    assert [(s.file, s.skipped) for s in out.manifest.sites] == [(Path("a.cxx"), Reason.COMMENT_STRANDED)]


def test_shared_initializer_is_kept_when_one_ctor_cannot_drop_it(fixture_graph):
    out = run_member_init(fixture_graph("shared_init"), apply=True)
    header, source = out.read("foo.h"), out.read("foo.cxx")
    assert "m_A{" not in header
    assert source.count("m_A(0)") == 2
    assert "int m_B{ 1 };" in header
    assert "m_B(other.m_B)" in source
    assert Reason.COMMENT_STRANDED in {s.skipped for s in out.manifest.sites}


def test_broken_translation_unit_is_dropped_and_reported(fixture_graph, capsys):
    g = fixture_graph("basic")
    before = _originals(g)
    db = g.build / "compile_commands.json"
    entries = json.loads(db.read_text())
    for e in entries:
        e["command"] += " -include /nonexistent/missing.h"
    db.write_text(json.dumps(entries))
    out = run_member_init(g, apply=True, capsys=capsys)
    assert "dropped 1 TU(s) that failed to compile: foo.cxx" in out.stdout
    assert _originals(g) == before


def test_unreadable_compile_database_is_an_error(fixture_graph):
    g = fixture_graph("basic")
    (g.build / "compile_commands.json").write_text("[ not json")
    with pytest.raises(RuntimeError, match="run-clang-tidy failed"):
        run_member_init(g, apply=True)


def test_find_class_skips_a_derived_class_naming_the_base():
    text = (
        "template <typename T> class Foo;\n"
        "template <typename T>\nclass ITK_TEMPLATE_EXPORT Bar : public Foo<T>\n{\n  int m_Z;\n};\n"
        "template <typename T>\nclass ITK_TEMPLATE_EXPORT Foo final : public Base\n{\n  int m_A;\n  int m_B;\n};\n"
    )
    m, _ = postfix.mask(text)
    assert postfix.data_members(m, *postfix.find_class(m, "Foo")) == ["m_A", "m_B"]


def test_in_class_ctor_after_access_specifier_parses():
    text = "class Foo\n{\npublic:\n  Foo()\n  {\n    m_A = 1;\n  }\n  int m_A;\n};\n"
    m, comments = postfix.mask(text)
    ctor = postfix.parse_ctor(text, m, comments, text.index("{\n    m_A"))
    assert ctor is not None and ctor.in_class and ctor.entries == []


def test_base_initializer_does_not_block_reordering():
    entries = [postfix.Entry("Superclass", "Superclass()"),
               postfix.Entry("m_B", "m_B(1)"), postfix.Entry("m_A", "m_A(0)")]
    ordered, _ = postfix.plan_order(entries, ["m_A", "m_B"])
    assert [e.name for e in ordered] == ["Superclass", "m_A", "m_B"]


def test_directive_around_body_assignment_skips_that_fix(fixture_graph):
    out = run_member_init(fixture_graph("preprocessor_body"), apply=True)
    source = out.read("foo.cxx")
    assert "#ifndef X\n  m_A = 1;\n#endif\n  m_C = 3;\n}" in source
    assert "Foo::Foo()\n  : m_B(2)\n{" in source
    assert sorted(s.skipped for s in out.manifest.skipped()) == [Reason.PREPROCESSOR] * 2


def test_unparsable_ctor_sharing_an_initializer_refuses_the_group(fixture_graph):
    g = fixture_graph("shared_unparsed")
    before = _originals(g)
    out = run_member_init(g, apply=True)
    assert _originals(g) == before
    assert {(s.skipped, s.note) for s in out.manifest.sites} == {(Reason.GATE_FAILED, "ctor-unparsed")}


def test_crashed_tus_are_parsed_from_run_clang_tidy_output():
    text = (
        "[1/2][0.0s] clang-tidy ...\nError while processing /r/a.cxx.\n"
        "/r/b.cxx: terminated by signal 11\n"
    )
    assert member_init.crashed_tus(text) == ["/r/a.cxx", "/r/b.cxx"]


def test_each_default_member_move_pairs_its_header_and_source_sites(fixture_graph):
    out = run_member_init(fixture_graph("shared_header"), apply=True)
    dmi = [(s.file.name, s.start, s.group) for s in out.manifest.applied()
           if s.cls == "use-default-member-init"]
    by_file = {}
    for name, _, group in dmi:
        by_file.setdefault(name, set()).add(group)
    assert all(g for _, _, g in dmi), dmi
    assert by_file["a.cxx"] <= by_file["foo.h"] and by_file["b.cxx"] <= by_file["foo.h"]
    assert by_file["a.cxx"].isdisjoint(by_file["b.cxx"])
def test_comment_dropped_by_an_earlier_stage_is_not_charged_here(fixture_graph):
    g = fixture_graph("basic")
    src = g.repo / "foo.cxx"
    text = src.read_text()
    src.write_text(text.replace("Foo::Foo(int a)", "// earlier note\nFoo::Foo(int a)"))
    _git(g.repo, "commit", "-qam", "note")
    src.write_text(text)
    out = run_member_init(g, apply=True)
    assert ": m_A(1)\n  , m_B(2)" in out.read("foo.cxx")
    assert Reason.COMMENT_STRANDED not in {s.skipped for s in out.manifest.sites}


def test_initializer_list_removed_whole_keeps_its_source_site_in_the_header_group(fixture_graph):
    out = run_member_init(fixture_graph("list_removed"), apply=True)
    assert ": m_A" not in out.read("foo.cxx")
    dmi = [s for s in out.manifest.applied() if s.cls == "use-default-member-init"]
    groups = {s.file.name: s.group for s in dmi}
    assert set(groups) == {"foo.h", "foo.cxx"}
    assert groups["foo.cxx"] and groups["foo.cxx"] == groups["foo.h"]
    assert groups["foo.h"].startswith("member-init:")


@pytest.mark.parametrize("sig,cls", [
    ("TensorToAnisotropyImageFilter ::TensorToAnisotropyImageFilter()", "TensorToAnisotropyImageFilter"),
    ("Foo:: Foo()", "Foo"),
    ("ns::Foo<T> ::Foo()", "Foo"),
])
def test_qualified_constructor_with_spaces_around_the_scope_operator_parses(sig, cls):
    text = f"{sig}\n{{\n  m_A = 1;\n}}\n"
    m, comments = postfix.mask(text)
    ctor = postfix.parse_ctor(text, m, comments, text.index("{"))
    assert ctor is not None and ctor.cls == cls and not ctor.in_class


@pytest.mark.parametrize("sig", ["::Foo()", "Foo())", ":: ()"])
def test_unparsable_constructor_shapes_return_none(sig):
    text = f"{sig}\n{{\n}}\n"
    m, comments = postfix.mask(text)
    assert postfix.parse_ctor(text, m, comments, text.index("{")) is None


def test_internal_error_skips_one_constructor_and_the_rest_apply(fixture_graph, monkeypatch, capsys):
    real = postfix.parse_ctor
    blown = []

    def flaky(text, m, comments, body):
        ctor = real(text, m, comments, body)
        if ctor is not None and "Foo(int a)" in text[ctor.sig_end - 12:ctor.sig_end] and not blown:
            blown.append(body)
            raise RuntimeError("boom")
        return ctor

    monkeypatch.setattr(postfix, "parse_ctor", flaky)
    out = run_member_init(fixture_graph("basic"), apply=True)
    errors = [s for s in out.manifest.sites if s.note == "internal-error:RuntimeError"]
    assert blown and len(errors) == 1 and errors[0].skipped == Reason.GATE_FAILED
    assert "m_A = 1;" in out.read("foo.cxx")
    assert out.manifest.applied()
    assert "internal error at" in capsys.readouterr().err


def test_stage_fails_only_when_every_site_hit_an_internal_error(fixture_graph, monkeypatch):
    def boom(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(postfix, "parse_ctor", boom)
    g = fixture_graph("basic")
    manifest = g.repo.parent / "manifest.json"
    rc = member_init.main(["--graph", str(g.build), "--repo", str(g.repo),
                           "--manifest", str(manifest), "--apply"])
    sites = Manifest.read(manifest).sites
    assert rc == 1 and sites and all(s.note == "internal-error:RuntimeError" for s in sites)
    assert _git(g.repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("sig", ["Foo::bar()", "Foo ::Bar()"])
def test_qualified_non_constructor_is_not_a_constructor(sig):
    text = f"{sig}\n{{\n  m_A = 1;\n}}\n"
    m, comments = postfix.mask(text)
    assert postfix.parse_ctor(text, m, comments, text.index("{")) is None


def test_failed_constructor_render_drops_its_whole_default_member_group(fixture_graph, monkeypatch):
    real = postfix.render

    def flaky(ctor, entries):
        if ctor.cls == "A" and len(entries) < len(ctor.entries):
            raise RuntimeError("render")
        return real(ctor, entries)

    monkeypatch.setattr(postfix, "render", flaky)
    out = run_member_init(fixture_graph("shared_header"), apply=True)
    header = out.read("foo.h")
    assert "m_X{" not in header and "m_Y{" not in header and "m_P{ 3 }" in header
    assert "m_X(1)" in out.read("a.cxx") and "m_P(3)" not in out.read("b.cxx")
    dmi = [s for s in out.manifest.sites if s.cls == "use-default-member-init"]
    assert {s.file.name for s in dmi if s.note == "internal-error:RuntimeError"} == {"foo.h"}
    assert not [s for s in dmi if s.file == Path("a.cxx") and s.skipped is None]


def test_failed_apply_restores_crlf_bytes(tmp_path, monkeypatch):
    path = tmp_path / "w.cxx"
    data = b"int a;\r\nint b;\r\n"
    path.write_bytes(data)
    planner = member_init.Planner(tmp_path)
    doc = planner.doc(path)
    planner.edits[doc.path] = [(0, 0, "x")]

    def boom(*args, **kw):
        raise RuntimeError("apply")

    monkeypatch.setattr(member_init, "apply_edits", boom)
    member_init._apply(planner, member_init.PMI, {doc.path: doc.text.replace("\r\n", "\n")})
    assert path.read_bytes() == data and planner.errors == 1 and not planner.edits


def test_error_location_never_raises(tmp_path, monkeypatch):
    path = tmp_path / "v.cxx"
    path.write_bytes(b"a\nb\nc\n")
    planner = member_init.Planner(tmp_path)
    assert planner.where(tmp_path / "missing.cxx", 4) == (tmp_path / "missing.cxx", 0)

    def broken(self, p):
        raise OSError("doc")

    monkeypatch.setattr(member_init.Planner, "doc", broken)
    assert planner.where(path, 4) == (path.resolve(), 2)


def test_grouping_error_skips_one_diagnostic_and_the_rest_apply(fixture_graph, monkeypatch, capsys):
    real = postfix.body_after
    calls = []

    def flaky(m, at):
        calls.append(at)
        if len(calls) == 1:
            raise RuntimeError("group")
        return real(m, at)

    monkeypatch.setattr(postfix, "body_after", flaky)
    out = run_member_init(fixture_graph("basic"), apply=True)
    assert [s.note for s in out.manifest.sites].count("internal-error:RuntimeError") == 1
    assert out.manifest.applied()


def test_constructor_list_insertion_and_removed_assignments_share_a_group(fixture_graph):
    out = run_member_init(fixture_graph("split_ctor"), apply=True)
    assert ": m_A(Get())" in out.read("foo.cxx") and "  Use(m_A);" in out.read("foo.cxx")
    pmi = [s for s in out.manifest.applied() if s.cls == "prefer-member-initializer"]
    assert len(pmi) == 2, pmi
    assert pmi[0].group == pmi[1].group and ":pmi-" in pmi[0].group
