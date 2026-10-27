import json
from dataclasses import dataclass, field
from pathlib import Path

from ioa.skip import Reason


@dataclass
class Site:
    file: Path
    start: int
    end: int
    kind: str
    cls: str
    skipped: Reason | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "file": str(self.file),
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
            "cls": self.cls,
            "skipped": str(self.skipped) if self.skipped else None,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Site":
        return cls(
            Path(d["file"]),
            d["start"],
            d["end"],
            d["kind"],
            d["cls"],
            Reason(d["skipped"]) if d.get("skipped") else None,
            d.get("note", ""),
        )


@dataclass
class Manifest:
    kind: str
    sites: list[Site] = field(default_factory=list)
    partners: list[tuple[Path, Path]] = field(default_factory=list)
    """File pairs whose sites the partitioner keeps together, e.g. a header and its .cxx."""

    def write(self, path: Path) -> None:
        data: dict = {"kind": self.kind, "sites": [s.to_dict() for s in self.sites]}
        if self.partners:
            data["partners"] = [[str(a), str(b)] for a, b in self.partners]
        path.write_text(json.dumps(data, indent=2) + "\n")

    @classmethod
    def read(cls, path: Path) -> "Manifest":
        data = json.loads(path.read_text())
        pairs = [(Path(a), Path(b)) for a, b in data.get("partners", [])]
        return cls(data["kind"], [Site.from_dict(s) for s in data["sites"]], pairs)

    def applied(self) -> list[Site]:
        return [s for s in self.sites if s.skipped is None]

    def skipped(self) -> list[Site]:
        return [s for s in self.sites if s.skipped is not None]

    def covers(self, file: Path, line: int) -> bool:
        return any(s.file == file and s.start <= line <= s.end for s in self.applied())
