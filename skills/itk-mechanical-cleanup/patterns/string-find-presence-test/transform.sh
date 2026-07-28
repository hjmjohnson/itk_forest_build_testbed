#!/usr/bin/env bash
# Rewrite  RECV.find(ARG) < RECV.(length|size)()  ->  RECV.find(ARG) != std::string::npos
# ONLY when both receivers are the same identifier. Receiver-mismatch sites are
# reported SKIPPED and left untouched. Dry-run by default; --apply writes. Never commits.
set -uo pipefail

REPO="."
APPLY=0
for a in "$@"; do
    case "$a" in
        --apply) APPLY=1 ;;
        *)       REPO="$a" ;;
    esac
done

if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "error: '$REPO' is not a git work tree" >&2
    exit 2
fi

PY_REPO="$REPO" PY_APPLY="$APPLY" python3 - <<'PY'
import os, re, subprocess, sys

repo  = os.environ["PY_REPO"]
apply = os.environ["PY_APPLY"] == "1"

pat = re.compile(
    r'(?P<r1>[A-Za-z_][A-Za-z0-9_]*)\.find\((?P<arg>[^()]*)\)'
    r'\s*<\s*'
    r'(?P<r2>[A-Za-z_][A-Za-z0-9_]*)\.(?:length|size)\(\)'
)

files = subprocess.run(
    ["git", "-C", repo, "grep", "-lE",
     r'\.find\([^)]*\)[[:space:]]*<[[:space:]]*[A-Za-z_][A-Za-z0-9_.]*\.(length|size)\(\)',
     "--", "*.cxx", "*.hxx", "*.h", "*.cpp", "*.cc", ":(exclude)*ThirdParty*"],
    capture_output=True, text=True
).stdout.split()

counts = {"rewritten": 0, "skipped": 0}
changed_files = 0

for rel in files:
    path = os.path.join(repo, rel)
    try:
        with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
            lines = fh.readlines()
    except OSError:
        continue

    file_changed = False
    for i, line in enumerate(lines):
        def repl(m, rel=rel, i=i):
            if m.group("r1") == m.group("r2"):
                counts["rewritten"] += 1
                return f'{m.group("r1")}.find({m.group("arg")}) != std::string::npos'
            counts["skipped"] += 1
            print(f'SKIPPED (receiver mismatch) {rel}:{i+1}: '
                  f'{m.group("r1")} vs {m.group("r2")}')
            return m.group(0)

        new = pat.sub(repl, line)
        if new != line:
            file_changed = True
            print(f'{"APPLY " if apply else "DRYRUN"} {rel}:{i+1}')
            print(f'  - {line.rstrip()}')
            print(f'  + {new.rstrip()}')
            lines[i] = new

    if file_changed and apply:
        with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.writelines(lines)
        changed_files += 1

print("----")
print(f"rewritten: {counts['rewritten']}  skipped(mismatch): {counts['skipped']}  "
      f"files_{'written' if apply else 'would_change'}: {changed_files}")
if not apply:
    print("(dry-run; re-run with --apply to write)")
PY
