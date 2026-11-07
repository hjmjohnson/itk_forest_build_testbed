import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import const_iterators  # noqa: E402


def scan_source(text, name="sample.cxx"):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / name).write_text(text)
        return const_iterators.scan(root)


class ScanTest(unittest.TestCase):
    def test_read_only_iterator_is_reported(self):
        candidates, counts = scan_source(
            "void f(Image * img) {\n"
            "  itk::ImageRegionIterator<Image> it(img, img->GetLargestPossibleRegion());\n"
            "  for (; !it.IsAtEnd(); ++it) { sum += it.Get(); }\n"
            "}\n"
        )
        self.assertEqual([c["variable"] for c in candidates], ["it"])
        self.assertEqual(counts["never_written"], 1)

    def test_written_iterator_is_not_reported(self):
        candidates, _ = scan_source(
            "itk::ImageRegionIterator<Image> out(img, region);\nout.Set(1);\n"
        )
        self.assertEqual(candidates, [])

    def test_const_iterator_is_counted_not_reported(self):
        candidates, counts = scan_source("itk::ImageRegionConstIterator<Image> it(img, region);\n")
        self.assertEqual(candidates, [])
        self.assertEqual(counts["const"], 1)

    def test_shared_alias_is_marked_for_splitting(self):
        candidates, _ = scan_source(
            "using IteratorType = itk::ImageRegionIterator<Image>;\n"
            "IteratorType in(a, region);\n"
            "IteratorType out(b, region);\n"
            "out.Set(in.Get());\n"
        )
        self.assertEqual([c["variable"] for c in candidates], ["in"])
        self.assertTrue(any("split it" in n for n in candidates[0]["notes"]))

    def test_iterator_passed_to_function_is_marked(self):
        candidates, _ = scan_source("itk::ImageRegionIterator<Image> it(img, region);\nhelper(it);\n")
        self.assertEqual([c["variable"] for c in candidates], ["it"])
        self.assertIn("passed to a function", candidates[0]["notes"])

    def test_qualified_container_iterator_is_ignored(self):
        candidates, _ = scan_source(
            "using Iterator = itk::ImageRegionIterator<Image>;\n"
            "HistogramType::Iterator histoIter;\n"
            "Iterator real(img, region);\n"
            "real.Set(1);\n"
        )
        self.assertEqual(candidates, [])

    def test_dot_directories_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidden = root / ".claude" / "worktrees"
            hidden.mkdir(parents=True)
            (hidden / "a.cxx").write_text("itk::ImageRegionIterator<Image> it(img, region);\n")
            candidates, _ = const_iterators.scan(root)
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
