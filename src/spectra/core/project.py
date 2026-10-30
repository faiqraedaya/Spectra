"""Project data: drawings, counted items, sections and settings.

Geometry is stored in display-space PDF points (see pdfdoc.py), so a project
is independent of zoom and render resolution. Items have stable IDs; nothing
refers to an item by its position in a list.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .geometry import Box, centre, point_in_polygon, polyline_intersects_box
from .taxonomy import Taxonomy

SCHEMA = 2


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Document:
    id: str
    path: str  # absolute in memory; stored relative to the project file when possible
    sha256: str = ""
    name: str = ""
    n_pages: int = 0
    reviewed_pages: list[int] = field(default_factory=list)


@dataclass
class Item:
    """One counted object on a drawing."""

    doc: str
    page: int  # 0-based
    box: Box  # display points
    cls: str
    id: str = field(default_factory=new_id)
    size_mm: float | None = None  # None: inherit from the section
    tag: str = ""
    count: int = 1
    section: str | None = None  # explicit section id; None: from section regions
    source: str = "manual"  # manual | snap | library | model | bluebeam
    status: str = "accepted"  # proposed | accepted
    score: float = 1.0
    edited: bool = False  # a proposal the reviewer changed (class, box or size)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["box"] = [round(v, 2) for v in self.box]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Item:
        d = dict(d)
        d["box"] = tuple(float(v) for v in d["box"])
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Region:
    """A polyline (along pipework) or polygon (around an area) on one page."""

    doc: str
    page: int
    points: list[tuple[float, float]]
    closed: bool = False

    def covers(self, box: Box) -> bool:
        if self.closed and len(self.points) >= 3:
            return point_in_polygon(*centre(box), self.points)
        return polyline_intersects_box(self.points, box)


@dataclass
class Section:
    name: str
    id: str = field(default_factory=new_id)
    colour: str = "#2563eb"
    size_mm: float | None = None
    pipe_length_m: float = 0.0
    regions: list[Region] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Section:
        d = dict(d)
        d["regions"] = [Region(r["doc"], r["page"], [tuple(p) for p in r["points"]], r.get("closed", False)) for r in d.get("regions", [])]
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Settings:
    frequency_table: str = "iogp_434-01_2019.csv"
    bare_numbers: str = "auto"  # how to read unitless sizes in labels
    line_number_pattern: str = ""  # empty: built-in pattern
    auto_size: bool = True  # fill missing sizes from nearby line numbers
    tag_pattern: str = ""  # empty: built-in pattern, e.g. ESDV-2001, PT1006
    boundary_pattern: str = ""  # tags of isolation valves; empty: ESDV, SDV, XV, BDV, ...
    match_min_score: float = 0.9
    match_min_precision: float = 0.9
    model_confidence: float = 0.35
    auto_accept: float = 0.95  # proposals at or above this score are accepted
    libraries: list[str] = field(default_factory=list)


@dataclass
class Project:
    name: str = "Untitled"
    documents: list[Document] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    taxonomy: Taxonomy = field(default_factory=Taxonomy)
    settings: Settings = field(default_factory=Settings)
    stats: dict = field(default_factory=dict)  # review statistics, e.g. auto detections rejected
    path: Path | None = None

    # --- Look-ups ---------------------------------------------------------

    def document(self, doc_id: str) -> Document | None:
        return next((d for d in self.documents if d.id == doc_id), None)

    def section(self, section_id: str | None) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)

    def item(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def page_items(self, doc_id: str, page: int) -> list[Item]:
        return [i for i in self.items if i.doc == doc_id and i.page == page]

    def section_of(self, item: Item) -> Section | None:
        """Explicit section first, else the first section whose regions cover the item."""
        if item.section:
            s = self.section(item.section)
            if s is not None:
                return s
        for s in self.sections:
            for r in s.regions:
                if r.doc == item.doc and r.page == item.page and r.covers(item.box):
                    return s
        return None

    def effective_size(self, item: Item) -> float | None:
        """Item size, else the class default (e.g. instrument tapping), else the section line size."""
        if item.size_mm is not None:
            return item.size_mm
        default = self.taxonomy.get(item.cls).default_size_mm
        if default is not None:
            return default
        s = self.section_of(item)
        return s.size_mm if s else None

    # --- Persistence ------------------------------------------------------

    def to_dict(self, base: Path | None = None) -> dict:
        def rel(p: str) -> str:
            if base is None:
                return p
            try:
                return os.path.relpath(p, base)
            except ValueError:  # different drive on Windows
                return p

        return {
            "schema": SCHEMA,
            "app": "Spectra",
            "name": self.name,
            "documents": [{**asdict(d), "path": rel(d.path)} for d in self.documents],
            "items": [i.to_dict() for i in self.items],
            "sections": [s.to_dict() for s in self.sections],
            "taxonomy": self.taxonomy.to_list(),
            "settings": asdict(self.settings),
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, data: dict, base: Path | None = None) -> Project:
        if data.get("schema", 1) < 2:
            raise ValueError("This is a Spectra 1.x project. Use File > Import 1.x project.")
        docs = []
        for d in data.get("documents", []):
            p = d["path"]
            if base is not None and not os.path.isabs(p):
                p = str((base / p).resolve())
            docs.append(Document(**{**d, "path": p}))
        settings = Settings(**{k: v for k, v in data.get("settings", {}).items() if k in Settings.__dataclass_fields__})
        return cls(
            name=data.get("name", "Untitled"),
            documents=docs,
            items=[Item.from_dict(i) for i in data.get("items", [])],
            sections=[Section.from_dict(s) for s in data.get("sections", [])],
            taxonomy=Taxonomy.from_list(data["taxonomy"]) if data.get("taxonomy") else Taxonomy(),
            settings=settings,
            stats=data.get("stats", {}),
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(path.parent), indent=1), encoding="utf-8")
        tmp.replace(path)  # atomic on the same volume: a crash never leaves half a file
        self.path = path
        if self.name == "Untitled":
            self.name = path.name.removesuffix(".spectra.json").removesuffix(".json")

    @classmethod
    def load(cls, path: str | Path) -> Project:
        path = Path(path)
        p = cls.from_dict(json.loads(path.read_text(encoding="utf-8")), path.parent)
        p.path = path
        return p


def import_v1(data: dict, doc: Document, taxonomy: Taxonomy, scale: float = 1.0) -> tuple[list[Item], list[Section]]:
    """Convert a Spectra 1.x project for one drawing.

    1.x stored boxes in pixels of a render whose scale depended on the zoom at
    the time; scale is that factor (1.0 for the default render). Labels are
    mapped to classes by name.
    """
    k = 1.0 / scale
    sections = []
    by_name: dict[str, Section] = {}
    for s in data.get("sections", []):
        sec = Section(s.get("name", "Section"), colour=s.get("color") or "#2563eb", size_mm=s.get("line_size"))
        for pl in s.get("polylines", []):
            pts = [(x * k, y * k) for x, y in pl.get("points", [])]
            sec.regions.append(Region(doc.id, int(pl.get("page", 1)) - 1, pts))
        sections.append(sec)
        by_name[sec.name] = sec
    items = []
    for d in data.get("detections", []):
        x0, y0, x1, y1 = (v * k for v in d.get("bbox", (0, 0, 0, 0)))
        cls_key = taxonomy.match_label(str(d.get("name", ""))) or "other"
        sec = by_name.get(d.get("section", ""))
        items.append(
            Item(
                doc.id,
                int(d.get("page_num", 1)) - 1,
                (x0, y0, x1, y1),
                cls_key,
                size_mm=d.get("line_size"),
                count=int(d.get("count", 1)),
                section=sec.id if sec else None,
                source=d.get("source", "manual"),
                score=float(d.get("confidence", 1.0)),
                meta={"v1_name": d.get("name", "")},
            )
        )
    return items, sections
