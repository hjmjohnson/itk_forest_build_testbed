#!/usr/bin/env python3
"""Print a ctest -E regex of SphinxExamples tests that open an interactive window.

Usage: sphinx-gui-tests.py <ctest --show-only=json-v1 output file>

Each test's add_test backtrace names the example directory; a test is GUI when
the sources it runs (Code.py for Python tests, *.cxx otherwise) call a display
API that blocks until a person closes the window. Prints nothing when none match.
"""
import json
import os
import re
import sys

GUI = re.compile(
    r"QuickView|vtkImageViewer|vtkRenderWindowInteractor|->Start\(\)"
    r"|plt\.show\(|itkwidgets|itk\.view\("
)


def sources(src_dir, python):
    want = (".py",) if python else (".cxx", ".h", ".hxx")
    try:
        names = os.listdir(src_dir)
    except OSError:
        return ""
    text = []
    for f in names:
        if f.endswith(want):
            with open(os.path.join(src_dir, f), errors="ignore") as fh:
                text.append(fh.read())
    return "".join(text)


def main(path):
    with open(path) as fh:
        data = json.load(fh)
    graph = data.get("backtraceGraph", {})
    files, nodes = graph.get("files", []), graph.get("nodes", [])
    gui = []
    for t in data.get("tests", []):
        bt = t.get("backtrace")
        if bt is None:
            continue
        src_dir = os.path.dirname(files[nodes[bt]["file"]])
        cmd = " ".join(t.get("command") or [])
        python = ".py" in cmd or t["name"].endswith("Python")
        if GUI.search(sources(src_dir, python)):
            gui.append(t["name"])
    if gui:
        print("|".join("^%s$" % re.escape(n) for n in sorted(gui)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
