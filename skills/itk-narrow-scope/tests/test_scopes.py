import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ioa.skip import Reason  # noqa: E402
from scopes import Decl, Source, accept, apply_text, mentions, parse_block, plan  # noqa: E402


def move(code: str, name: str, trivial: bool = True, static: bool = False):
    """Plan the declaration marked by '@' in code, naming the variable `name`."""
    start = code.index("@")
    src = Source(code.replace("@", "", 1))
    return src, plan(src, Decl(start, name, trivial, static))


def moved(code: str, name: str, **kw) -> str:
    src, mv = move(code, name, **kw)
    assert mv is not None and mv.skipped is None, mv
    return apply_text(src, [mv])


def test_parse_block_splits_control_statements():
    code = "{ int a = 0; if (a) { a = 1; } else a = 2; for (;;) {} try {} catch (...) {} lbl: ; }"
    kinds = [s.kind for s in parse_block(Source(code).masked, 0)]
    assert kinds == ["simple", "if", "for", "try", "label", "empty"]


def test_parse_block_marks_range_for_and_directives():
    code = "{\n#if X\n  f();\n#endif\n  for (auto v : w) {}\n  do { } while (x);\n}"
    kinds = [s.kind for s in parse_block(Source(code).masked, 0)]
    assert kinds == ["directive", "simple", "directive", "range_for", "do"]


def test_mentions_ignore_members_comments_and_strings():
    code = 'x = s.x + p->x + n::x; // x\n f("x"); g(x);'
    src = Source(code)
    assert mentions(src.masked, "x", 0, len(code)) == [0, code.index("g(x)") + 2]


def test_block_move():
    code = "void f(int c)\n{\n  @int t = 0;\n  if (c)\n  {\n    t = c;\n    c = t;\n  }\n}\n"
    assert moved(code, "t").startswith("void f(int c)\n{\n  if (c)\n  {\n    int t = 0;\n    t = c;\n")


def test_use_after_block_is_not_a_site():
    _, mv = move("void f(int c)\n{\n  @int t = 0;\n  if (c)\n  {\n    t = c;\n  }\n  g(t);\n}\n", "t")
    assert mv is None


def test_unbraced_branch_is_not_entered():
    _, mv = move("void f(int c)\n{\n  @int t = 0;\n  if (c)\n    g(t);\n}\n", "t")
    assert mv is None


def test_both_branches_of_if_are_siblings():
    _, mv = move("void f(int c)\n{\n  @int t = 0;\n  if (c)\n  {\n    g(t);\n  }\n  else\n  {\n    h(t);\n  }\n}\n",
                 "t")
    assert mv is None


def test_init_statement_of_for_needs_empty_slot():
    _, mv = move("void f(int m)\n{\n  @int i;\n  for (i = 0; i < m; ++i)\n  {\n  }\n}\n", "i")
    assert mv is None


def test_call_initializer_may_not_cross_code():
    _, mv = move("void f(int c)\n{\n  @auto p = make();\n  c += 1;\n  if (c)\n  {\n    use(p);\n  }\n}\n", "p")
    assert (mv.skipped, mv.note) == (Reason.COSTLY_CONSTRUCT, "side-effect")


def test_call_initializer_enters_immediately_following_bare_block():
    code = "void f(int & n)\n{\n  @auto p = make();\n  {\n    n = p;\n  }\n}\n"
    assert moved(code, "p") == "void f(int & n)\n{\n  {\n    auto p = make();\n    n = p;\n  }\n}\n"


def test_dead_initial_value_may_read_state():
    code = "void f(int c, int a)\n{\n  @int t = a;\n  c += 1;\n  if (c)\n  {\n    t = c;\n    a = t;\n  }\n}\n"
    assert "  {\n    int t = a;\n    t = c;\n" in moved(code, "t")


def test_loop_body_requires_trivial_type():
    _, mv = move("void f(int m)\n{\n  @T v;\n  while (m--)\n  {\n    v = m;\n    use(v);\n  }\n}\n", "v",
                 trivial=False)
    assert (mv.skipped, mv.note) == (Reason.COSTLY_CONSTRUCT, "non-trivial")


def test_compound_assignment_first_is_loop_carried():
    _, mv = move("void f(int m)\n{\n  @int v = 0;\n  while (m--)\n  {\n    v += m;\n  }\n}\n", "v")
    assert (mv.skipped, mv.note) == (Reason.LOOP_CARRIED, "")


def test_deepest_failing_candidate_falls_back_to_outer_block():
    code = ("void f(int m, int c)\n{\n  @int v = 0;\n  if (c)\n  {\n    for (;;)\n    {\n      v += m;\n    }\n  }\n}\n")
    assert "  if (c)\n  {\n    int v = 0;\n    for (;;)\n" in moved(code, "v")


def test_implicit_reference_capture_is_address_taken():
    code = "void f(int c)\n{\n  @int v = 0;\n  if (c)\n  {\n    auto l = [&] { v = 1; };\n    l();\n  }\n}\n"
    _, mv = move(code, "v")
    assert (mv.skipped, mv.note) == (Reason.LOOP_CARRIED, "address-taken")


def test_reference_binding_is_address_taken():
    code = "void f(int c)\n{\n  @int v = 0;\n  if (c)\n  {\n    int & r = v;\n    r = 2;\n  }\n}\n"
    _, mv = move(code, "v")
    assert (mv.skipped, mv.note) == (Reason.LOOP_CARRIED, "address-taken")


def test_bitwise_and_is_not_address_taken():
    code = "void f(int c)\n{\n  @int v = 3;\n  if (c)\n  {\n    use(c & v);\n  }\n}\n"
    assert "  {\n    int v = 3;\n    use(c & v);\n" in moved(code, "v")


def test_declaration_sharing_its_line_is_not_a_site():
    _, mv = move("void f(int c)\n{\n  @int t = 0; int u = 1;\n  if (c)\n  {\n    c = t + u;\n  }\n}\n", "t")
    assert mv is None


def test_shadowing_declaration_in_target_is_not_a_site():
    code = "void f(int c)\n{\n  @int t = 0;\n  if (c)\n  {\n    int t = 2;\n    g(t);\n  }\n}\n"
    _, mv = move(code, "t")
    assert mv is None


def test_two_moves_into_one_block_keep_their_order():
    code = "void f(int c)\n{\n  int a = 0;\n  int b = 1;\n  if (c)\n  {\n    c = a + b;\n  }\n}\n"
    src = Source(code)
    mvs = [plan(src, Decl(code.index("int a"), "a", True, False)),
           plan(src, Decl(code.index("int b"), "b", True, False))]
    assert apply_text(src, mvs) == "void f(int c)\n{\n  if (c)\n  {\n    int a = 0;\n    int b = 1;\n    c = a + b;\n  }\n}\n"


def test_only_one_declaration_takes_an_init_statement():
    code = "void f()\n{\n  double lo = 0.5;\n  double hi = 2.0;\n  if (lo < hi)\n  {\n  }\n}\n"
    src = Source(code)
    mvs = [plan(src, Decl(code.index("double lo"), "lo", True, False)),
           plan(src, Decl(code.index("double hi"), "hi", True, False))]
    assert [mv.target.form for mv in mvs] == ["init-statement", "init-statement"]
    assert accept(src, mvs) == mvs[:1]
    assert "  double hi = 2.0;\n  if (double lo = 0.5; lo < hi)\n" in apply_text(src, mvs)


def test_removal_leaves_no_doubled_blank_line():
    code = "void f(int c)\n{\n  int a = 1;\n\n  int t = 0;\n  int u = 0;\n\n  g(a);\n  if (c)\n  {\n    c = t + u;\n  }\n}\n"
    src = Source(code)
    mvs = [plan(src, Decl(code.index("int t"), "t", True, False)),
           plan(src, Decl(code.index("int u"), "u", True, False))]
    assert apply_text(src, mvs) == ("void f(int c)\n{\n  int a = 1;\n\n  g(a);\n  if (c)\n  {\n"
                                    "    int t = 0;\n    int u = 0;\n    c = t + u;\n  }\n}\n")


def test_handler_block_is_still_a_target():
    code = "void f()\n{\n  @int t = 0;\n  try\n  {\n    g();\n  }\n  catch (...)\n  {\n    t = 1;\n    ++t;\n  }\n}\n"
    assert "  catch (...)\n  {\n    int t = 0;\n    t = 1;\n" in moved(code, "t")


def test_escape_through_member_assignment():
    code = "void f(int c, S & out)\n{\n  @std::string s;\n  if (c)\n  {\n    s = g();\n    out.p = s.data();\n  }\n}\n"
    _, mv = move(code, "s", trivial=False)
    assert (mv.skipped, mv.note) == (Reason.LOOP_CARRIED, "escapes")


def test_assignment_to_a_local_of_the_target_does_not_escape():
    code = "void f(int c)\n{\n  @std::string s;\n  if (c)\n  {\n    s = g();\n    auto n = s.size();\n    h(n);\n  }\n}\n"
    assert "  {\n    std::string s;\n    s = g();\n" in moved(code, "s", trivial=False)


def test_array_declarator_equals_is_not_a_side_effect():
    code = "void f(int c, int a)\n{\n  @int v[2] = {0, 0};\n  g(a);\n  if (c)\n  {\n    v[0] = a;\n    g(v[1]);\n  }\n}\n"
    assert "  if (c)\n  {\n    int v[2] = {0, 0};\n    v[0] = a;\n" in moved(code, "v")


def test_shift_assignment_in_initializer_is_a_side_effect():
    code = "void f(int c, int n)\n{\n  @int x = (n <<= 1);\n  g(n);\n  if (c)\n  {\n    x = 1;\n    g(x);\n  }\n}\n"
    _, mv = move(code, "x")
    assert (mv.skipped, mv.note) == (Reason.COSTLY_CONSTRUCT, "side-effect")


def test_accumulating_a_trivial_value_does_not_escape():
    code = "void f(int m)\n{\n  double s = 0;\n  @double v;\n  for (int i = 0; i < m; ++i)\n  {\n    v = i;\n    s += v;\n  }\n  g(s);\n}\n"
    assert "  {\n    double v;\n    v = i;\n" in moved(code, "v")


def test_variable_or_member_call_result_passed_to_a_call_escapes():
    for use in ("g(t);", "g(1, t.Data());", "h->Set(t);"):
        code = "void f(int c)\n{\n  @int t = 0;\n  if (c)\n  {\n    t = c;\n    " + use + "\n  }\n}\n"
        _, mv = move(code, "t")
        assert (mv.skipped, mv.note) == (Reason.LOOP_CARRIED, "escapes"), use
    code = "void f(int c)\n{\n  @int t = 0;\n  if (c)\n  {\n    t = c;\n    g(t + 1);\n  }\n}\n"
    assert move(code, "t")[1].skipped is None


def test_type_without_trivial_destructor_is_a_costly_construct():
    code = "int f(int c)\n{\n  @S s;\n  if (c)\n  {\n    return s.n;\n  }\n  return 0;\n}\n"
    src = Source(code.replace("@", "", 1))
    mv = plan(src, Decl(code.index("@"), "s", False, False, trivial_dtor=False))
    assert (mv.skipped, mv.note) == (Reason.COSTLY_CONSTRUCT, "nontrivial-dtor")
