from pathlib import Path

from ioa.query import parse_dump
from ioa.source import mask

DUMP = """Match #1:

Binding for "push_back_run":
VarDecl 0x1 </src/a.cxx:9:3, col:23> col:23 used v 'std::vector<size_t>':'std::vector<unsigned long>' callinit destroyed
`-CXXConstructExpr 0x2 <col:23> 'std::vector<size_t>':'std::vector<unsigned long>' 'void () noexcept'


Match #2:

Binding for "index_assign_run":
VarDecl 0x3 </src/h.h:4:5, col:28> col:28 a 'std::array<double, 2>' callinit


Match #3:

Binding for "push_back_run":
VarDecl 0x4 </src/a.cxx:12:3 <Spelling=/src/m.h:1:1>, col:9> col:9 used m 'std::vector<int>' callinit

3 matches.
"""


def test_parse_dump_reads_location_name_and_types():
    found = parse_dump(DUMP, Path("/src/a.cxx"))
    assert [(m.binding, m.node.kind, m.node.file, m.node.line, m.node.col, m.node.name, m.node.type,
             m.node.canonical) for m in found] == [
        ("push_back_run", "VarDecl", Path("/src/a.cxx"), 9, 3, "v", "std::vector<size_t>",
         "std::vector<unsigned long>"),
        ("index_assign_run", "VarDecl", Path("/src/h.h"), 4, 5, "a", "std::array<double, 2>",
         "std::array<double, 2>"),
    ]


def test_mask_blanks_comments_and_keeps_offsets():
    text = 'int a; // c\nchar s[] = "x/*y";\n'
    masked = mask(text, literals=True)
    assert len(masked) == len(text) and "// c" not in masked and "/*" not in masked
    assert '"x/*y"' in mask(text)
