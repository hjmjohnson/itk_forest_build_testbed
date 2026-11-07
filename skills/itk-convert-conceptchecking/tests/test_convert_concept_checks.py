import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import convert_concept_checks as ccc  # noqa: E402


def sa(text: str) -> str:
    return ccc.to_static_assert(text, add_includes=False)[0]


@pytest.mark.parametrize(
    "macro, expected",
    [
        (
            "itkConceptMacro(SameDimensionCheck, (Concept::SameDimension<InputImageDimension, OutputImageDimension>));",
            "static_assert(InputImageDimension == OutputImageDimension);",
        ),
        (
            "itkConceptMacro(D, (Concept::SameDimension<VDimension, 3u>));",
            "static_assert(VDimension == 3u);",
        ),
        (
            "itkConceptMacro(D, (Concept::SameDimension<Self::InputImageDimension, Self::OutputImageDimension>));",
            "static_assert(InputImageDimension == OutputImageDimension);",
        ),
        (
            "itkConceptMacro(D, (Concept::SameDimension<Self::InputImageType::ImageDimension, 3>));",
            "static_assert(InputImageType::ImageDimension == 3);",
        ),
        (
            "itkConceptMacro(D, (Concept::SameDimensionOrMinusOne<Self::InputImageDimension, Self::OutputImageDimension>));",
            "static_assert(OutputImageDimension == InputImageDimension || OutputImageDimension == InputImageDimension - 1);",
        ),
        (
            "itkConceptMacro(D, (Concept::SameDimensionOrMinusOneOrTwo<A, B>));",
            "static_assert(B == A || B == A - 1 || B == A - 2);",
        ),
        (
            "itkConceptMacro(D, (Concept::SameDimensionOrMinusOneOrTwo<3, Self::InputImageDimension>));",
            "static_assert(InputImageDimension > 0 && InputImageDimension <= 3);",
        ),
        (
            "itkConceptMacro(D, (Concept::SameDimensionOrMinusOne<3, N>));",
            "static_assert(N >= 2 && N <= 3);",
        ),
        (
            "itkConceptMacro(T, (Concept::SameType<PixelType, typename TOutputImage::PixelType>));",
            "static_assert(std::is_same_v<PixelType, typename TOutputImage::PixelType>);",
        ),
        (
            "itkConceptMacro(T, (Concept::SameType<typename Self::PixelType, typename Self::ImageType::PixelType>));",
            "static_assert(std::is_same_v<PixelType, typename ImageType::PixelType>);",
        ),
        (
            "itkConceptMacro(I, (itk::Concept::IsInteger<TReturn>));",
            "static_assert(std::is_integral_v<TReturn>);",
        ),
        (
            "itkConceptMacro(U, (Concept::IsUnsignedInteger<InputPixelType>));",
            "static_assert(!NumericTraits<InputPixelType>::is_signed);",
        ),
        (
            "itkConceptMacro(S, (itk::Concept::Signed<OutputPixelType>));",
            "static_assert(itk::NumericTraits<OutputPixelType>::is_signed);",
        ),
        (
            "itkConceptMacro(Z, (Concept::HasZero<typename TInputImage::PixelType>));",
            "static_assert(std::is_default_constructible_v<typename TInputImage::PixelType>);",
        ),
    ],
)
def test_converts_like_itk_7108(macro, expected):
    assert sa(macro) == expected


def test_multiline_macro_is_converted():
    text = "  itkConceptMacro(ImageDimensionCheck,\n                  (Concept::SameDimension<A, B>));\n"
    assert sa(text) == "  static_assert(A == B);\n"


def test_other_concepts_are_left_alone():
    text = "itkConceptMacro(C, (Concept::Convertible<InputPixelType, OutputPixelType>));\n"
    assert sa(text) == text


def test_type_traits_include_goes_after_the_first_include_block():
    text = (
        '#include "itkImageToImageFilter.h"\n'
        '#include "itkNeighborhoodIterator.h"\n'
        "\nnamespace itk\n{\n"
        "itkConceptMacro(T, (Concept::SameType<A, B>));\n"
        "}\n"
        "#ifndef ITK_MANUAL_INSTANTIATION\n"
        '#  include "itkFoo.hxx"\n'
        "#endif\n"
    )
    out = ccc.to_static_assert(text)[0]
    lines = out.splitlines()
    assert lines[2] == "#include <type_traits>"
    assert out.count("<type_traits>") == 1


def test_enable_removes_guard_and_matching_endif():
    text = (
        "#ifdef ITK_USE_CONCEPT_CHECKING\n"
        "#  if defined(FOO)\n"
        "  itkConceptMacro(X, (Concept::Convertible<A, B>));\n"
        "#  endif\n"
        "#endif\n"
        "#endif // include guard\n"
    )
    out, n, notes = ccc.enable_guards(text)
    assert n == 1 and not notes
    assert out == (
        "#  if defined(FOO)\n"
        "  itkConceptMacro(X, (Concept::Convertible<A, B>));\n"
        "#  endif\n"
        "#endif // include guard\n"
    )


def test_enable_leaves_guard_with_else_for_hand_conversion():
    text = "#ifdef ITK_USE_CONCEPT_CHECKING\nA\n#else\nB\n#endif\n"
    out, n, notes = ccc.enable_guards(text)
    assert out == text and n == 0 and "#else" in notes[0]


def test_comments_removes_markers_and_collapses_blank_lines():
    text = "  int a;\n\n  // Begin concept checking\n\n  int b;\n  /** End concept checking */\n"
    out, n = ccc.remove_marker_comments(text)
    assert n == 2
    assert out == "  int a;\n\n  int b;\n"


def test_comments_removes_module_template_placeholder():
    text = (
        "  // Add concept checking such as\n"
        "  // itkConceptMacro( FloatingPointPixel, ( itk::Concept::IsFloatingPoint< T > ) );\n"
        "protected:\n"
    )
    out, n = ccc.remove_marker_comments(text)
    assert n == 1 and out == "protected:\n"


def test_audit_reports_removed_api(tmp_path, capsys):
    (tmp_path / "a.h").write_text(
        "#define ITK_CONCEPT_NO_CHECKING\n"
        "#ifdef ITK_USE_CONCEPT_CHECKING\n"
        "itkConceptMacro(D, (Concept::SameDimension<A, B>));\n"
        "itkConceptMacro(C, (Concept::Convertible<A, B>));\n"
        "#endif\n"
    )
    assert ccc.main(["audit", "--root", str(tmp_path)]) == 0
    report = capsys.readouterr().out
    assert "a.h:1: ITK_CONCEPT_NO_CHECKING" in report
    assert "a.h:2" in report
    assert "1 SameDimension" in report
    assert "Other itkConceptMacro checks (kept): 1" in report


def test_dry_run_writes_nothing(tmp_path):
    f = tmp_path / "a.h"
    original = "itkConceptMacro(D, (Concept::SameDimension<A, B>));\n"
    f.write_text(original)
    ccc.main(["static-assert", "--root", str(tmp_path)])
    assert f.read_text() == original
    ccc.main(["static-assert", "--root", str(tmp_path), "--apply"])
    assert f.read_text().startswith("static_assert(A == B")


def test_markers_go_when_the_block_holds_only_static_asserts():
    text = (
        "  // Begin concept checking\n"
        "  itkConceptMacro(D, (Concept::SameDimension<A, B>));\n"
        "  itkConceptMacro(T,\n"
        "                  (Concept::SameType<A, B>));\n"
        "  // End concept checking\n"
        "protected:\n"
    )
    assert sa(text) == "  static_assert(A == B);\n  static_assert(std::is_same_v<A, B>);\nprotected:\n"


def test_markers_stay_when_the_block_keeps_a_concept_macro():
    text = (
        "  // Begin concept checking\n"
        "  itkConceptMacro(D, (Concept::SameDimension<A, B>));\n"
        "  itkConceptMacro(C, (Concept::Convertible<A, B>));\n"
        "  // End concept checking\n"
    )
    out = sa(text)
    assert out.startswith("  // Begin concept checking\n  static_assert(A == B);\n")
    assert out.endswith("  // End concept checking\n")


def test_unpaired_opening_marker_goes():
    text = "  /** Start concept checking */\n  itkConceptMacro(D, (Concept::SameDimension<A, B>));\n\nprotected:\n"
    assert sa(text) == "  static_assert(A == B);\n\nprotected:\n"
