#!/usr/bin/env python3
"""Add #include "itkABINamespace.h" to files the build reports as missing it."""
import re
import sys
from pathlib import Path

INC = '#include "itkABINamespace.h"\n'
ERR = re.compile(r"^(/\S+\.(?:h|hxx|cxx|txx)):\d+:\d+: error: unknown type name 'ITK_ABI_NAMESPACE", re.M)

log = Path(sys.argv[1]).read_text()
files = sorted({Path(m) for m in ERR.findall(log)})
for path in files:
    text = path.read_text()
    if "itkABINamespace.h" in text:
        continue
    # Place it before the first #include, or before the namespace if none.
    m = re.search(r"^#include ", text, re.M) or re.search(r"^namespace itk", text, re.M)
    if not m:
        print(f"  MANUAL {path}")
        continue
    path.write_text(text[: m.start()] + INC + text[m.start() :])
    print(f"  +include {path.name}")
print(f"patched {len(files)} files")
