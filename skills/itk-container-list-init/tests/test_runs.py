import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ioa.skip import Reason  # noqa: E402
from runs import brace_list, container_of, count_elements, element_type, find_run, judge, render  # noqa: E402


def body(*lines: str) -> str:
    return "int f()\n{\n" + "".join(f"  {s}\n" for s in lines) + "  return 0;\n}\n"


def run_of(text: str, name: str = "v", canonical: str = "std::vector<int>"):
    line = next(i for i, s in enumerate(text.splitlines(), 1) if f" {name};" in s)
    run = find_run(text, line, 3, name)
    if run is not None:
        judge(run, [canonical], text[: run.begin])
    return run


def test_push_back_run_collects_elements_in_order():
    run = run_of(body("std::vector<int> v;", "v.push_back(1);", "v.push_back(f(2, 3));", "v.push_back(4);", "g(v);"))
    assert (run.cls, run.args, run.first, run.last) == ("push_back_run", [["1"], ["f(2, 3)"], ["4"]], 3, 6)
    assert run.skipped is None
    assert render(run) == "std::vector<int> v{1, f(2, 3), 4};"


def test_read_of_the_variable_ends_the_run():
    run = run_of(body("std::vector<double> v;", "v.push_back(1.5);", "v.push_back(v[0]);"),
                 canonical="std::vector<double>")
    assert run.args == [["1.5"]]


def test_blank_line_comment_line_and_other_statement_end_the_run():
    for stop in ("", "// note", "h();", "  v.push_back(9);"):
        run = run_of(body("std::vector<double> v;", "v.push_back(1.5);", stop, "v.push_back(2.5);"),
                     canonical="std::vector<double>")
        assert run.args == [["1.5"]], stop


def test_no_element_is_not_a_site():
    assert run_of(body("std::vector<int> v;", "v.reserve(2);", "v.push_back(1);")) is None


def test_declaration_with_initializer_or_two_declarators_is_not_a_site():
    assert find_run(body("std::vector<int> v(3);", "v.push_back(1);"), 3, 3, "v") is None
    text = body("std::vector<int> w, v;", "v.push_back(1);")
    assert find_run(text, 3, 3, "v") is None


def test_index_run_sorted_and_complete():
    run = run_of(body("std::array<int, 2> v;", "v[1] = 2;", "v[0] = 1;"), canonical="std::array<int, 2>")
    assert (run.cls, run.skipped) == ("index_assign_run", None)
    assert brace_list(run) == ["1", "2"]


def test_index_run_with_gap_is_partial_coverage():
    run = run_of(body("std::array<int, 3> v;", "v[0] = 1;", "v[2] = 3;"), canonical="std::array<int, 3>")
    assert (run.skipped, run.note) == (Reason.NARROWING, "partial-coverage")


def test_index_run_shorter_than_std_array_is_partial_coverage():
    run = run_of(body("std::array<int, 3> v;", "v[0] = 1;", "v[1] = 2;"), canonical="std::array<int, 3>")
    assert (run.skipped, run.note) == (Reason.NARROWING, "partial-coverage")


def test_out_of_order_index_run_with_calls_is_order_violation():
    run = run_of(body("std::array<int, 2> v;", "v[1] = g();", "v[0] = h();"), canonical="std::array<int, 2>")
    assert (run.skipped, run.note) == (Reason.ORDER_VIOLATION, "index-order")


def test_non_constant_index_ends_the_run():
    assert run_of(body("std::array<int, 2> v;", "v[i] = 1;"), canonical="std::array<int, 2>") is None


@pytest.mark.parametrize("decl, elem, canonical", [
    ("unsigned int n = 2;", "n", "std::vector<int>"),
    ("size_t n = 2;", "n", "std::vector<long>"),
    ("itk::SizeValueType n = 2;", "n", "std::vector<int>"),
    ("", "2u", "std::vector<int>"),
    ("", "2.5", "std::vector<int>"),
    ("int n = 2;", "n", "std::vector<double>"),
    ("long n = 2;", "n", "std::vector<int>"),
    ("int n = 2;", "n", "std::vector<unsigned int>"),
    ("", "-1", "std::vector<unsigned long>"),
    ("itk::IndexValueType n = 2;", "n", "std::vector<unsigned long>"),
])
def test_narrowing_elements_are_skipped(decl, elem, canonical):
    lines = [decl] if decl else []
    run = run_of(body(*lines, "std::vector<T> v;", f"v.push_back({elem});", "v.push_back(7);"),
                 canonical=canonical)
    assert run.skipped == Reason.NARROWING, (decl, elem, canonical)


def test_unknown_element_types_are_allowed():
    run = run_of(body("std::vector<int> v;", "v.push_back(g());", "v.push_back(k);", "v.push_back(9);"))
    assert run.skipped is None


@pytest.mark.parametrize("elems", [["3"], ["3", "4"], ["n"]])
def test_short_integer_vector_is_init_list_ctor(elems):
    run = run_of(body("size_t n = 1;", "std::vector<size_t> v;", *(f"v.push_back({e});" for e in elems)),
                 canonical="std::vector<unsigned long>")
    assert run.skipped == Reason.INIT_LIST_CTOR


def test_three_integer_elements_are_not_init_list_ctor():
    run = run_of(body("std::vector<size_t> v;", "v.push_back(3);", "v.push_back(4);", "v.push_back(5);"),
                 canonical="std::vector<unsigned long>")
    assert run.skipped is None


def test_vnl_vector_is_never_rewritten():
    run = run_of(body("vnl_vector<double> v;", "v.push_back(1.5);"), canonical="vnl_vector<double>")
    assert (run.skipped, run.note) == (Reason.INIT_LIST_CTOR, "no-init-list")


def test_emplace_with_two_arguments_constructs_the_element_type():
    run = run_of(body("std::vector<std::pair<int, int>> v;", "v.emplace_back(1, 2);"),
                 canonical="std::vector<std::pair<int, int>>")
    assert brace_list(run) == ["std::pair<int, int>(1, 2)"]


def test_emplace_without_spelled_element_type_is_skipped():
    run = run_of(body("PairVec v;", "v.emplace_back(1, 2);"), canonical="std::vector<std::pair<int, int>>")
    assert (run.skipped, run.note) == (Reason.INIT_LIST_CTOR, "element-type-unknown")


def test_preprocessor_inside_run_is_skipped():
    run = run_of(body("std::vector<double> v;", "v.push_back(1.5);", "#if 1", "v.push_back(2.5);", "#endif"),
                 canonical="std::vector<double>")
    assert run.skipped == Reason.PREPROCESSOR


def test_preprocessor_after_run_ends_it():
    run = run_of(body("std::vector<double> v;", "v.push_back(1.5);", "#if 1", "h();", "#endif"),
                 canonical="std::vector<double>")
    assert (run.args, run.skipped) == ([["1.5"]], None)


def test_trailing_comments_are_collected():
    run = run_of(body("std::vector<double> v; // the v", "v.push_back(1.5); // one"),
                 canonical="std::vector<double>")
    assert run.comments == ["// the v", "// one"]
    assert render(run) == "std::vector<double> v{1.5}; // the v"


def test_long_list_breaks_one_element_per_line():
    elems = [f"some_long_function_name({i})" for i in range(6)]
    run = run_of(body("std::vector<double> v;", *(f"v.push_back({e});" for e in elems)),
                 canonical="std::vector<double>")
    assert render(run).splitlines() == ["std::vector<double> v{", *(f"    {e}," for e in elems[:-1]),
                                        f"    {elems[-1]}", "  };"]


def test_multiline_element_is_joined():
    run = run_of(body("std::vector<double> v;", "v.push_back(g(1,", "                 2));"),
                 canonical="std::vector<double>")
    assert run.args == [["g(1, 2)"]]


def test_container_and_element_type_parsing():
    assert container_of("std::vector<std::pair<int, int>>") == ("std::vector", ["std::pair<int, int>"])
    assert container_of("std::__1::array<double, 3>") == ("std::array", ["double", "3"])
    assert container_of("itk::Array<float>") == ("itk::Array", ["float"])
    assert container_of("int") is None
    assert element_type("const std::vector<std::pair<int, int>> v") == "std::pair<int, int>"
    assert element_type("VecType v") is None


def test_comment_inside_element_is_skipped():
    run = run_of(body("std::vector<double> v;", "v.push_back(g(1, // one", "                 2));"),
                 canonical="std::vector<double>")
    assert (run.skipped, run.note) == (Reason.COMMENT_STRANDED, "comment-in-element")


def test_index_value_type_is_signed():
    run = run_of(body("itk::IndexValueType n = 2;", "std::vector<long> v;", "v.push_back(n);", "v.push_back(7);",
                      "v.push_back(8);"), canonical="std::vector<long>")
    assert run.skipped is None


@pytest.mark.parametrize("head", ["static std::vector<double> v;", "thread_local std::vector<double> v;",
                                  "static thread_local std::vector<double> v;"])
def test_static_and_thread_local_are_skipped(head):
    run = run_of(body(head, "v.push_back(1.5);", "v.push_back(2.5);"), canonical="std::vector<double>")
    assert run.skipped == Reason.STATIC_LOCAL


@pytest.mark.parametrize("rhs", ["i++", "x += 1", "-i", "a.b"])
def test_out_of_order_index_run_with_effects_is_order_violation(rhs):
    run = run_of(body("std::array<int, 2> v;", f"v[1] = {rhs};", f"v[0] = {rhs};"), canonical="std::array<int, 2>")
    assert (run.skipped, run.note) == (Reason.ORDER_VIOLATION, "index-order")


def test_out_of_order_index_run_of_identifiers_is_sorted():
    run = run_of(body("std::array<int, 2> v;", "v[1] = q;", "v[0] = 'c';"), canonical="std::array<int, 2>")
    assert (run.skipped, brace_list(run)) == (None, ["'c'", "q"])


@pytest.mark.parametrize("elems", [["n + 1"], ["g()", "h()"], ["n", "k"]])
def test_short_integral_vector_with_unclassified_element_is_init_list_ctor(elems):
    run = run_of(body("std::vector<int> v;", *(f"v.push_back({e});" for e in elems)))
    assert run.skipped == Reason.INIT_LIST_CTOR


def test_count_elements_detects_a_wrong_rendering():
    text = body("std::vector<int> v{ 1, 2 };")
    assert count_elements(text, 0, "v")[0] == 2
    assert count_elements(body("std::vector<int> v{ 1, f(2, 3) };"), 0, "v")[0] == 2
    assert count_elements(body("std::vector<int> v{};"), 0, "v")[0] == 0
    assert count_elements(body("std::vector<int> v;"), 0, "v") is None
