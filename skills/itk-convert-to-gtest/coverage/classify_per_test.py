#!/usr/bin/env python3
"""Classify per-test coverage residuals into explained categories.

Residual = lines the original CTest covered (minus the legacy driver's startup
overhead and TestKernel) that its GoogleTest did not. Each residual line is
assigned to one category; anything left is "unexplained" and must be checked
with repeat_pairs.py (run-to-run variation) or fixed.

Categories (see README.md for the evidence behind each):
  factory-environment  ObjectFactoryBase loops over registered factories; the
                       legacy driver registers IO/FFT factories, GoogleTest
                       drivers register none.
  exception-printing   ExceptionObject::Print and operator<< chain; originals
                       printed caught exceptions, EXPECT_THROW does not.
  check-helper         itk::Math / SmartPointer / Index comparison helpers
                       the original used for its checks, replaced by the
                       equivalent EXPECT_* macro.
  known-variable       lines that repeated runs of the same unchanged test
                       cover in some runs and not others (thread-pool and
                       progress-reporting paths, BinaryGenerator exception
                       branches). Reported, not counted as lost.

Usage: classify_per_test.py <per_test_coverage.json> [out.json]
"""

import json
import sys
from collections import Counter
from pathlib import Path

RULES = [
    ("factory-environment", "Modules/Core/Common/src/itkObjectFactoryBase.cxx", set(range(198, 206)) | set(range(713, 726))),
    ("exception-printing", "Modules/Core/Common/src/itkExceptionObject.cxx", set(range(200, 250))),
    ("exception-printing", "Modules/Core/Common/include/itkExceptionObject.h", set(range(150, 160))),
    ("exception-printing", "Modules/Core/Common/src/itkIndent.cxx", None),
    ("exception-printing", "Modules/Core/Common/include/itkIndent.h", None),
    ("exception-printing", "Modules/Core/Common/include/itkMacro.h", set(range(430, 440))),
    ("check-helper", "Modules/Core/Common/include/itkMath.h", None),
    ("check-helper", "Modules/Core/Common/include/itkSmartPointer.h", set(range(115, 125)) | set(range(265, 275))),
    ("check-helper", "Modules/Core/Common/include/itkIndex.h", set(range(550, 560))),
    ("known-variable", "Modules/Core/Common/include/itkTotalProgressReporter.h", set(range(115, 125))),
    ("known-variable", "Modules/Core/Common/src/itkPoolMultiThreader.cxx", set(range(290, 300))),
    ("known-variable", "Modules/Filtering/ImageFilterBase/include/itkBinaryGeneratorImageFilter.hxx", set(range(205, 255))),
    ("known-variable", "Modules/Core/Common/include/itkMacro.h", set(range(565, 635))),
    ("known-variable", "Modules/Core/Common/include/itkConstNeighborhoodIterator.hxx", {257, 258, 260, 261, 475, 476, 477, 478}),
    ("known-variable", "Modules/Core/Common/include/itkImageAlgorithm.hxx", {166, 167, 179, 180, 188}),
    ("check-helper", "Modules/Core/Common/include/itkMacro.h", set(range(856, 864))),
]


def classify(path, line):
    for category, rule_path, lines in RULES:
        if path == rule_path and (lines is None or line in lines):
            return category
    return "unexplained"


def main():
    results = json.loads(Path(sys.argv[1]).read_text())
    out = []
    totals = Counter()
    for r in results:
        cats = Counter()
        unexplained = {}
        for path, lines in r["lost"].items():
            for line in lines:
                c = classify(path, line)
                cats[c] += 1
                if c == "unexplained":
                    unexplained.setdefault(path, []).append(line)
        totals.update(cats)
        healthy = r["before"]["failed"] == 0 and r["after"]["failed"] == 0 and r["after"]["ran"] > 0
        out.append({"legacy_test": r["legacy_test"], "categories": dict(cats), "unexplained": unexplained,
                    "tests_healthy": healthy})
    print("residual lines by category:", dict(totals))
    flagged = [o for o in out if o["unexplained"] or not o["tests_healthy"]]
    print(f"{len(out)} conversions; {len(flagged)} with unexplained residuals or test problems")
    for o in flagged:
        print(f"  {o['legacy_test']}: healthy={o['tests_healthy']} unexplained=" +
              "; ".join(f"{p.split('/')[-1]}:{v}" for p, v in o["unexplained"].items())[:200])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
