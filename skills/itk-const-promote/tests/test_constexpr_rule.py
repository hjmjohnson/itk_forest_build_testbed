import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from constexpr_rule import initializer, mask, promotable  # noqa: E402


@pytest.mark.parametrize("decl, name, ctype", [
    ("int n = 3;", "n", "int"),
    ("double d = -1.5e3;", "d", "double"),
    ("unsigned long u = 0x10UL;", "u", "unsigned long"),
    ("bool b = true;", "b", "bool"),
    ("char c = '\\n';", "c", "char"),
    ("int n{ 3 };", "n", "int"),
    ("int n(3);", "n", "int"),
    ("const char * s = \"abc\";", "s", "const char *"),
    ("auto size = SizeType::Filled(2);", "size", "Size<2>"),
    ("SizeType size = SizeType::Filled(2);", "size", "itk::Size<2>"),
    ("auto r = itk::MakeFilled<RegionType::SizeType>(3);", "r", "itk::Size<3>"),
    ("double m = std::numeric_limits<double>::max();", "m", "double"),
    ("PixelType z = itk::NumericTraits<PixelType>::ZeroValue();", "z", "float"),
    ("int arr[] = { 1, 2 };", "arr", "int[2]"),
    ("std::array<int, 2> a = { 1, 2 };", "a", "std::array<int, 2>"),
    ("SizeType s = { { 1, 2 } };", "s", "itk::Size<2>"),
    ("int * p = nullptr;", "p", "int *"),
])
def test_promotable(decl, name, ctype):
    assert promotable(decl, name, ctype)


@pytest.mark.parametrize("decl, name, ctype", [
    ("int n = f();", "n", "int"),
    ("int n = 3 + k;", "n", "int"),
    ("std::string s = \"abc\";", "s", "std::string"),
    ("std::vector<int> v = { 1, 2 };", "v", "std::vector<int>"),
    ("std::vector<int> v{ 1, 2 };", "v", "std::vector<int>"),
    ("ImageType::Pointer p = nullptr;", "p", "itk::SmartPointer<Image>"),
    ("auto p = ImageType::Pointer(nullptr);", "p", "itk::SmartPointer<Image>"),
    ("int & r = n;", "r", "int &"),
    ("auto size = SizeType::Filled(k);", "size", "Size<2>"),
    ("double m = std::numeric_limits<double>::max(k);", "m", "double"),
    ("RGBType z = itk::NumericTraits<RGBType>::ZeroValue();", "z", "itk::RGBPixel<unsigned char>"),
    ("Foo x = 3;", "x", "Foo"),
    ("int arr[] = { 1, k };", "arr", "int[2]"),
    ("int n = 3; // three", "x", "int"),
])
def test_not_promotable(decl, name, ctype):
    assert not promotable(decl, name, ctype)


def test_initializer_ignores_comments_and_trailing_semicolon():
    assert initializer("int n = /* lit */ 3; // three", "n") == "3"
    assert initializer("int n{ 3 };", "n") == "{ 3 }"
    assert initializer("int arr[2] = { 1, 2 };", "arr") == "{ 1, 2 }"
    assert initializer("int n;", "n") is None


def test_mask_keeps_digit_separators_out_of_char_literals():
    text = "int x = 0xFF'FF; // c\nchar c = u8'a';"
    masked = mask(text, literals=True)
    assert masked.startswith("int x = 0xFF'FF;")
    assert "// c" not in masked
    assert "u8' '" in masked
