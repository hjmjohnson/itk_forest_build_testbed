import subprocess, sys, tempfile, os, textwrap
DB = os.path.join(os.environ.get("TOOLKIT", os.path.dirname(__file__)+"/.."), "lib", "drop_blocks.py")

def run(src, *args):
    d = tempfile.mkdtemp(); p = os.path.join(d, "f.cxx")
    open(p, "w").write(textwrap.dedent(src))
    r = subprocess.run([sys.executable, DB, *args, p], capture_output=True, text=True)
    return open(p).read(), r.returncode, r.stdout

def test_drop_v6_floor_keeps_ge6():
    src = """\
    #if ITK_VERSION_MAJOR >= 6
    new_api();
    #else
    old_api();
    #endif
    """
    out, rc, _ = run(src, "--floor-major", "6", "--apply")
    assert "new_api();" in out
    assert "old_api();" not in out
    assert "#if" not in out and "#endif" not in out
    assert rc == 0

def test_ambiguous_left_intact():
    src = "#if SOME_UNKNOWN_MACRO\nx();\n#else\ny();\n#endif\n"
    out, rc, _ = run(src, "--floor-major", "6", "--apply")
    assert "#if SOME_UNKNOWN_MACRO" in out      # untouched
    assert rc == 2

def test_has_include_at_floor():
    src = '#if __has_include(<itkMatrixExponential.h>)\nhave();\n#else\nlack();\n#endif\n'
    out, rc, _ = run(src, "--floor-major", "6", "--apply",
                     "--map", os.path.join(os.path.dirname(DB), "header_version_map.tsv"))
    assert "have();" in out and "lack();" not in out

def test_has_include_quoted_at_floor():
    # elastix uses a quoted include: __has_include("itkMatrixExponential.h").
    # At floor 6 the header exists, so the itk::Math branch is kept.
    src = '#if __has_include("itkMatrixExponential.h")\nhave();\n#else\nlack();\n#endif\n'
    out, rc, _ = run(src, "--floor-major", "6", "--apply",
                     "--map", os.path.join(os.path.dirname(DB), "header_version_map.tsv"))
    assert "have();" in out and "lack();" not in out, f"got:\n{out}"
    assert rc == 0

def test_has_include_quoted_below_header_floor():
    # itkMatrixExponential.h is new in ITK 6; at floor 5.0 it does not exist,
    # so the quoted guard resolves FALSE and the vnl fallback is kept.
    src = '#if __has_include("itkMatrixExponential.h")\nhave();\n#else\nlack();\n#endif\n'
    out, rc, _ = run(src, "--floor-major", "5", "--floor-minor", "0", "--apply",
                     "--map", os.path.join(os.path.dirname(DB), "header_version_map.tsv"))
    assert "lack();" in out and "have();" not in out, f"got:\n{out}"
    assert rc == 0

def test_drop_all_below_floor():
    src = """\
    #if ITK_VERSION_MAJOR < 6
    old_only();
    #endif
    keep_me();
    """
    out, rc, _ = run(src, "--floor-major", "6", "--apply")
    assert "old_only();" not in out, f"old_only() should be removed, got:\n{out}"
    assert "#if" not in out and "#endif" not in out, f"directives should be removed, got:\n{out}"
    assert "keep_me();" in out, f"keep_me() should remain, got:\n{out}"
    assert rc == 0, f"exit code should be 0, got {rc}"

def test_else_kept_when_all_false():
    src = """\
    #if ITK_VERSION_MAJOR < 6
    old();
    #else
    modern();
    #endif
    """
    out, rc, _ = run(src, "--floor-major", "6", "--apply")
    assert "modern();" in out, f"modern() should be kept, got:\n{out}"
    assert "old();" not in out, f"old() should be removed, got:\n{out}"
    assert "#if" not in out and "#endif" not in out, f"directives should be removed, got:\n{out}"
    assert rc == 0, f"exit code should be 0, got {rc}"

def test_mixed_ambiguous_intact():
    # A file with one resolvable region AND one ambiguous region must be left byte-for-byte intact
    src = """\
    #if ITK_VERSION_MAJOR < 6
    old_only();
    #endif
    #if SOME_UNKNOWN
    maybe();
    #endif
    keep_me();
    """
    import textwrap
    original = textwrap.dedent(src)
    out, rc, _ = run(src, "--floor-major", "6", "--apply")
    assert out == original, f"file should be byte-for-byte unchanged, got:\n{out!r}"
    assert rc == 2, f"exit code should be 2, got {rc}"

if __name__ == "__main__":
    test_drop_v6_floor_keeps_ge6(); test_ambiguous_left_intact(); test_has_include_at_floor()
    test_has_include_quoted_at_floor(); test_has_include_quoted_below_header_floor()
    test_drop_all_below_floor(); test_else_kept_when_all_false(); test_mixed_ambiguous_intact()
    print("PASS test_drop_blocks")
