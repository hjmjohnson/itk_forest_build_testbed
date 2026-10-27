"""Source-text helpers shared by the init-over-assign stages."""


def _digit_separator(text: str, i: int) -> bool:
    j = i - 1
    while j >= 0 and (text[j].isalnum() or text[j] in "'_."):
        j -= 1
    return text[j + 1:i][:1].isdigit()


def mask(text: str, literals: bool = False) -> str:
    """Blank comments (and literal contents when asked), keeping offsets and newlines."""
    out = list(text)
    i, n = 0, len(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif text[i] == '"' or (text[i] == "'" and not _digit_separator(text, i)):
            q, j = text[i], i + 1
            while j < n and text[j] != q and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            if literals:
                blank(i + 1, j - 1)
            i = j
        else:
            i += 1
    return "".join(out)
