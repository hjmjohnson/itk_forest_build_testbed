"""Find (and with --fix, promote) EXPECT_* checks that must be ASSERT_*.

For each GoogleTest source given:
- EXPECT_NO_THROW(...) followed by more statements in the same function
  becomes ASSERT_NO_THROW(...).
- A null check (EXPECT_NE(p, nullptr), EXPECT_NE(nullptr, p), EXPECT_TRUE(p),
  EXPECT_TRUE(p != nullptr), EXPECT_TRUE(p.IsNotNull()) and the -> form)
  followed by a dereference of p becomes the ASSERT_ form.
ASSERT_* compiles only in TEST bodies and void functions; other sites are
reported as LEFTOVER for a manual rewrite.

Usage: check_gtest_asserts.py [--fix] FILE...   (exit 1 if any site remains)
"""

import argparse
import re
from pathlib import Path

NULL_CHECK = re.compile(
    r"EXPECT_(?:NE\((?P<a>[\w.\->]+)\s*,\s*nullptr\)|NE\(nullptr\s*,\s*(?P<b>[\w.\->]+)\)"
    r"|TRUE\((?P<c>[\w.\->]+)\s*(?:!= nullptr)?\)|TRUE\((?P<d>[\w.\->]+)(?:\.|->)IsNotNull\(\)\))"
)


def enclosing(lines, i):
    """Return (signature_text, body_end_index) of the function containing line i."""
    start = i
    while start > 0 and lines[start] != "{":
        start -= 1
    sig = []
    k = start - 1
    while k >= 0 and lines[k].strip() and not lines[k].rstrip().endswith((";", "}")):
        sig.insert(0, lines[k])
        k -= 1
    end = i + 1
    while end < len(lines) and lines[end] != "}":
        end += 1
    return " ".join(sig), end


def is_void_context(sig):
    if re.search(r"(^|\s)(TYPED_)?TEST(_F|_P)?\(", sig):
        return True
    s = sig.strip()
    s = re.sub(r"template\s*<[^>]*>", "", s)
    head = s.split("(", 1)[0]
    return re.search(r"\bvoid\b", head) is not None


def in_void_member(lines, i):
    """True when line i is inside a class member function whose return type line is 'void'."""
    for k in range(i - 1, -1, -1):
        m = re.match(r"^  (\S[^(;{}]*)$", lines[k])
        if m and k + 1 < len(lines) and re.match(r"^  \w+\(", lines[k + 1]):
            return m.group(1).strip() == "void"
        if lines[k].startswith(("class ", "struct ", "TEST")):
            return False
    return False


def has_code_after(lines, i, end):
    for k in range(i + 1, end):
        t = lines[k].strip()
        if t and not t.startswith("//") and t not in ("{", "}"):
            return True
    return False


def derefs_later(lines, i, end, var):
    pat = re.compile(re.escape(var) + r"\s*->|\*\s*" + re.escape(var) + r"\b|\(\*" + re.escape(var))
    return any(pat.search(lines[k]) for k in range(i + 1, end))

def scan(path, apply):
    """Return (promotable, leftover) site lists; rewrite the file when apply."""
    p = Path(path)
    lines = p.read_text().split("\n")
    promotable, leftover = [], []
    for i, line in enumerate(lines):
        target = None
        if line.lstrip().startswith("//"):
            continue
        if "EXPECT_NO_THROW(" in line:
            sig, end = enclosing(lines, i)
            if has_code_after(lines, i, end):
                target = ("EXPECT_NO_THROW(", "ASSERT_NO_THROW(", sig)
        else:
            m = NULL_CHECK.search(line)
            if m:
                var = next(g for g in m.group("a", "b", "c", "d") if g)
                sig, end = enclosing(lines, i)
                if derefs_later(lines, i, end, var):
                    kind = m.group(0)[len("EXPECT_") :].split("(", 1)[0]
                    target = (f"EXPECT_{kind}(", f"ASSERT_{kind}(", sig)
        if target is None:
            continue
        old, new_macro, sig = target
        site = f"{path}:{i + 1}: {line.strip()[:100]}"
        if is_void_context(sig) or in_void_member(lines, i):
            promotable.append(site)
            lines[i] = line.replace(old, new_macro, 1)
        else:
            leftover.append(f"{site}  [in non-void: {sig.strip()[:60]}]")
    if apply and promotable:
        p.write_text("\n".join(lines))
    return promotable, leftover


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", action="store_true", help="rewrite promotable sites in place")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    total_p = total_l = 0
    for f in args.files:
        promotable, leftover = scan(f, args.fix)
        for s in promotable:
            print(("FIXED " if args.fix else "ASSERT ") + s)
        for s in leftover:
            print("LEFTOVER " + s)
        total_p += len(promotable)
        total_l += len(leftover)
    print(f"# {total_p} {'fixed' if args.fix else 'to promote'}, {total_l} leftover (manual)")
    raise SystemExit(1 if (total_l or (total_p and not args.fix)) else 0)
