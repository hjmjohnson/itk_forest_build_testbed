"""Replace unconditional progress output in GoogleTest files with SCOPED_TRACE.

A GoogleTest prints nothing useful on success: the framework reports each
TEST. Progress lines ("Creating an image", "Testing const iterators") belong
in SCOPED_TRACE, which prints them only when a check inside their scope fails
(N-Dekker, ITK PR #7063). Status lines ("[PASSED]", "Test finished") say what
GoogleTest already says and are removed.

Only one-line prints of a single string literal are touched:

    std::cout << "text" << std::endl;      (also '\\n', "\\n", or "text\\n")
    println("text");  std::puts("text");  printf("text\\n");

Each is classified:

  trace     a heading followed by more code in its block -> SCOPED_TRACE("text");
  status    "[PASSED]", "OK", "Done", "Test finished", a "=====" rule, or a
            heading with nothing after it in its block -> line removed
  keep      inside if/else/catch/switch or an unbraced body (conditional
            output, usually a failure report); failure wording (error, fail,
            exception, ...); a "Label:" or "Label =" header for a value
            printed by the next statement; the only statement in its block

Prints that stream values (`<< x`, `<< *filter`) are never touched: they may
exercise PrintSelf or operator<<, which the coverage parity check counts.

Usage: scoped_trace_progress.py [--fix] [-v] FILE...
  without --fix: list sites, exit 1 if any trace/status site exists
  with --fix:    rewrite the files in place
"""

import argparse
import re
import sys
from pathlib import Path

LIT = r'"(?:[^"\\]|\\.)*"'
END = r"""(?:std::endl|'\\n'|"\\n")"""
PRINT_FORMS = [
    re.compile(rf"^(?P<indent>\s*)std::cout\s*<<\s*(?P<lit>{LIT})\s*<<\s*{END}\s*;\s*$"),
    re.compile(rf"^(?P<indent>\s*)std::cout\s*<<\s*(?P<lit>{LIT})\s*;\s*$"),
    re.compile(rf"^(?P<indent>\s*)(?:println|std::puts|puts)\s*\(\s*(?P<lit>{LIT})\s*\)\s*;\s*$"),
    re.compile(rf"^(?P<indent>\s*)(?:std::)?printf\s*\(\s*(?P<lit>{LIT})\s*\)\s*;\s*$"),
]
CONDITIONAL = re.compile(r"^\s*(?:}\s*)?(?:if|else|catch|switch|case|default)\b")
UNBRACED = re.compile(r"^\s*(?:}\s*)?(?:(?:if|for|while|else\s+if)\s*\(.*\)|else|do)\s*$")
STATUS = re.compile(
    r"^\W*(?:\[\s*)?(?:passed|pass|ok|okay|done|success|succeeded|finished|test (?:finished|passed|succeeded|ok))"
    r"(?:\s*[.!]*\s*\]?)?\W*$"
    r"|^\W*ok\b|^\W*\[\s*(?:passed|ok|done)\s*\]|\bok\s*!*\W*$"
    r"|\b(?:passed|succeeded|test finished|done)\s*[.!]*\s*\]?\W*$"
    r"|^[\s=*#~_-]*$",
    re.I,
)
FAILURE = re.compile(r"\b(?:error|fail\w*|exception|wrong|incorrect|mismatch|differ\w*|bad|invalid|not)\b", re.I)


def code_only(line):
    """The line with string/char literals and comments blanked."""
    line = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
    line = re.sub(r"'(?:[^'\\]|\\.)*'", "''", line)
    return re.sub(r"//.*", "", line)


def significant(lines, i, step):
    """Index of the nearest non-blank, non-comment line from i in direction step."""
    in_block = False
    j = i + step
    while 0 <= j < len(lines):
        s = lines[j].strip()
        if step < 0 and s.endswith("*/"):
            in_block = "/*" not in s
        elif in_block:
            in_block = "/*" not in s
        elif s and not s.startswith("//") and not (s.startswith("/*") and s.endswith("*/")):
            return j
        j += step
    return None


def opener_headers(lines):
    """For each line, the code text that opened its innermost enclosing block."""
    stack, stmt, result = [], "", []
    in_comment = False
    for line in lines:
        result.append(stack[-1] if stack else "")
        text = code_only(line)
        if in_comment:
            end = text.find("*/")
            if end < 0:
                continue
            text, in_comment = text[end + 2 :], False
        while "/*" in text:
            a = text.find("/*")
            b = text.find("*/", a + 2)
            if b < 0:
                text, in_comment = text[:a], True
                break
            text = text[:a] + text[b + 2 :]
        for ch in text:
            if ch == "{":
                stack.append(stmt.strip())
                stmt = ""
            elif ch == "}":
                if stack:
                    stack.pop()
                stmt = "}"
            elif ch == ";":
                stmt = ""
            else:
                stmt += ch
        stmt += " "
    return result


def trimmed(lit):
    body = lit[1:-1]
    body = re.sub(r"^(?:\s|\\n|\\t)+", "", body)
    body = re.sub(r"(?:\s|\\n|\\t)+$", "", body)
    return body


def decoded(lit):
    return trimmed(lit).encode().decode("unicode_escape", errors="replace")


def classify(lines, headers, i, lit, continued):
    text = decoded(lit)
    header = headers[i]
    prev = significant(lines, i, -1)
    nxt = significant(lines, i, +1)
    prev_s = lines[prev].strip() if prev is not None else ""
    next_s = lines[nxt].strip() if nxt is not None else ""
    if CONDITIONAL.match(header) or re.search(r"\belse\b", header):
        return "keep", "conditional block"
    if UNBRACED.match(code_only(prev_s)):
        return "keep", "unbraced body"
    if prev_s.endswith("{") and next_s.startswith("}"):
        return "keep", "only statement in block"
    if STATUS.search(text) and not FAILURE.search(text.replace("not ", "")):
        return "status", "success marker"
    if FAILURE.search(text):
        return "keep", "failure wording"
    if re.search(r"[:=]\s*$", text) and re.match(r"(?:std::)?(?:cout|printf|puts|println)\b", next_s):
        return "keep", "header for a printed value"
    if continued and re.match(r"(?:std::)?(?:cout|printf|puts|println)\b", next_s):
        return "keep", "line completed by the next print"
    if next_s.startswith("}"):
        return "status", "nothing follows in block"
    return "trace", ""


def process(path, fix, verbose):
    lines = path.read_text().split("\n")
    headers = opener_headers(lines)
    edits, hits = {}, 0
    for i, line in enumerate(lines):
        for form in PRINT_FORMS:
            m = form.match(line)
            if m:
                break
        else:
            continue
        lit = m.group("lit")
        if form is PRINT_FORMS[3] and "%" in lit:
            continue
        continued = form is PRINT_FORMS[1] and not lit.endswith('\\n"')
        kind, why = classify(lines, headers, i, lit, continued)
        if kind == "keep":
            if verbose:
                print(f"{path}:{i + 1}: keep ({why}): {line.strip()}")
            continue
        hits += 1
        print(f"{path}:{i + 1}: {kind}{' (' + why + ')' if why else ''}: {line.strip()}")
        edits[i] = None if kind == "status" else f'{m.group("indent")}SCOPED_TRACE("{trimmed(lit)}");'
    if fix and edits:
        out = []
        for i, line in enumerate(lines):
            if i not in edits:
                out.append(line)
            elif edits[i] is not None:
                out.append(edits[i])
            elif out and not out[-1].strip() and i + 1 < len(lines) and not lines[i + 1].strip():
                out.pop()
        path.write_text("\n".join(out))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="also list kept prints and why")
    args = ap.parse_args()
    total = sum(process(f, args.fix, args.verbose) for f in args.files)
    return 1 if total and not args.fix else 0


if __name__ == "__main__":
    sys.exit(main())
