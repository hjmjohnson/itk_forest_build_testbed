import subprocess
from pathlib import Path

from ioa import gate


def record_subprocess(monkeypatch, rc=0, stderr=""):
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, rc, "", stderr)

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    return calls


def test_header_expands_to_capped_tus(fake_graph, repo_root, monkeypatch):
    calls = record_subprocess(monkeypatch)
    r = gate.run(fake_graph, [Path("Common/foo.h")], repo_root)
    assert len(calls) == 8 and r.ok


def test_dead_header_fails_with_reason(fake_graph, repo_root):
    r = gate.run(fake_graph, [Path("Dead/dead.hxx")], repo_root)
    assert not r.ok
    assert r.failed[Path("Dead/dead.hxx")] == "no-including-tu"


def test_command_is_syntax_only_with_fatal_warnings(fake_graph, repo_root, monkeypatch):
    calls = record_subprocess(monkeypatch)
    gate.run(fake_graph, [Path("IO/tu0.cxx")], repo_root)
    argv, kw = calls[0]
    assert "-fsyntax-only" in argv and "-Werror=unused-variable" in argv
    assert "-c" not in argv and "-o" not in argv and "IO/tu0.cxx.o" not in argv
    for flag in ("-MF", "-MT", "-MD", "-MMD"):
        assert flag not in argv
    assert str(repo_root / "IO/tu0.cxx") in argv
    assert kw["env"]["CCACHE_DISABLE"] == "1"


def test_compile_failure_is_reported(fake_graph, repo_root, monkeypatch):
    record_subprocess(monkeypatch, rc=1, stderr="x.cxx:1: error: boom\nnote\n")
    r = gate.run(fake_graph, [Path("IO/tu0.cxx")], repo_root)
    assert not r.ok and "boom" in r.failed[Path("IO/tu0.cxx")]


def test_expand_cli_prints_tus_and_exit_3_for_dead(fake_graph, repo_root, capsys):
    rc = gate.main(
        ["--expand", "--graph", str(fake_graph), "--repo-root", str(repo_root),
         "Common/one.h", "Dead/dead.hxx", "IO/tu1.cxx"]
    )
    out = capsys.readouterr()
    assert rc == 3
    assert out.out.split() == ["Common/tu0.cxx", "IO/tu1.cxx"]
    assert out.err == "no-including-tu\tDead/dead.hxx\n"


def test_warning_flags_follow_compiler_family():
    assert "-Wunused-local-typedef" in gate.warning_flags(["/x/clang++", "a.cxx"])
    assert "-Wunused-local-typedefs" in gate.warning_flags(["g++", "a.cxx"])


def test_strip_output_flags_handles_joined_and_mixed_forms():
    argv = "cc -MMD -MT a.o -MF a.d -MD -o a.o -c x.cxx -MM -ofoo.o -MFfile.d -MQq".split()
    assert gate.strip_output_flags(argv) == ["cc", "x.cxx"]


def test_missing_compiler_is_a_failure_not_a_raise(fake_graph, repo_root, monkeypatch):
    def boom(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(gate.subprocess, "run", boom)
    r = gate.run(fake_graph, [Path("IO/tu0.cxx")], repo_root)
    assert not r.ok and "cannot run" in r.failed[Path("IO/tu0.cxx")]
