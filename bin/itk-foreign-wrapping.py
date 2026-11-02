#!/usr/bin/env python3
"""Print the wrapped modules in an ITK build's Python package that ITK did not build.

Usage: itk-foreign-wrapping.py <ITK source dir> <ITK build dir>

Consumers built against an ITK build tree (RTK, Cleaver, VkFFTBackend, ...) install
their wrapping into ITK's package, and ITK's whole-package Python tests then fail on
classes that are not ITK's. A module is ITK's when ITK's source declares it in an
itk-module.cmake or ITK's cache enables it as Module_<Name>; every other
Configuration/<Name>Config.py is foreign. One name per line.
"""
import os
import re
import sys

src, build = sys.argv[1], sys.argv[2]
owned = {"ITKPyBase"}
for top in ("Modules", "Wrapping"):
    for root, dirs, files in os.walk(os.path.join(src, top)):
        dirs[:] = [d for d in dirs if d != "build"]
        if "itk-module.cmake" in files:
            with open(os.path.join(root, "itk-module.cmake"), errors="ignore") as fh:
                m = re.search(r"itk_module\(\s*([A-Za-z0-9_]+)", fh.read())
            if m:
                owned.add(m.group(1))
with open(os.path.join(build, "CMakeCache.txt"), errors="ignore") as fh:
    for line in fh:
        m = re.match(r"Module_([A-Za-z0-9_]+):BOOL=ON", line)
        if m:
            owned.add(m.group(1))

config = os.path.join(build, "Wrapping", "Generators", "Python", "itk", "Configuration")
wrapped = sorted(f[: -len("Config.py")] for f in os.listdir(config) if f.endswith("Config.py"))
for name in wrapped:
    if name not in owned:
        print(name)
