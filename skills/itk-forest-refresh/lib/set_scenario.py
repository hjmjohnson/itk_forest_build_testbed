#!/usr/bin/env python3
"""Add or update a [scenarios.<suffix>.<Name>] block in versions.toml.

Pure stdlib (no tomlkit dependency): versions.toml is hand-maintained TOML
with comments that a round-trip through tomllib+toml-writer would discard, so
this edits only the one block it owns, by text surgery, and leaves everything
else in the file byte-for-byte untouched.

Usage: set_scenario.py <versions.toml> <suffix> <Name> <url> <branch>
"""
import re
import sys


def main():
    path, suffix, name, url, branch = sys.argv[1:6]
    header = f"[scenarios.{suffix}.{name}]"
    with open(path, encoding="utf-8") as f:
        text = f.read()

    block = f"{header}\nurl    = \"{url}\"\nbranch = \"{branch}\"\n\n"

    pattern = re.compile(
        r"^\[scenarios\." + re.escape(suffix) + r"\." + re.escape(name) + r"\]\n"
        r"(?:(?!\[).*\n)*",
        re.MULTILINE,
    )
    if pattern.search(text):
        text = pattern.sub(block, text, count=1)
        print(f"updated {header}")
    else:
        # Insert after the last existing [scenarios.<suffix>.*] block if any,
        # else append a new [scenarios.<suffix>] section at end of file.
        suffix_block = re.compile(
            r"(^\[scenarios\." + re.escape(suffix) + r"\.[^\]]+\]\n(?:(?!\[).*\n)*)",
            re.MULTILINE,
        )
        matches = list(suffix_block.finditer(text))
        if matches:
            last = matches[-1]
            text = text[: last.end()] + block + text[last.end() :]
        else:
            if not text.endswith("\n"):
                text += "\n"
            text += f"\n{block}"
        print(f"added {header}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
