"""Symbol libraries: reusable vector templates per client drawing style.

A library is a JSON file of templates, each tagged with an object class.
Libraries are built from reviewed items (including imported Bluebeam
markups) and then detect the same symbols on new drawings in a fraction of
a second per page, with no training.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import ios
from .matching import Match, Template, match_library
from .project import Item, Project
from .vectors import PageVectors, snap_box

MIN_TEMPLATE_STROKES = 2


def library_dir() -> Path:
    base = os.environ.get("SPECTRA_DATA") or os.environ.get("APPDATA")
    root = Path(base) / "Spectra" / "libraries" if base else Path.home() / ".local" / "share" / "spectra" / "libraries"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class SymbolLibrary:
    name: str
    templates: list[Template] = field(default_factory=list)
    path: Path | None = None

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path else (self.path or library_dir() / f"{self.name}.json")
        data = {"name": self.name, "version": 1, "templates": [t.to_dict() for t in self.templates]}
        path.write_text(json.dumps(data), encoding="utf-8")
        self.path = path
        return path

    @classmethod
    def load(cls, path: str | Path) -> SymbolLibrary:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data.get("name", path.stem), [Template.from_dict(t) for t in data.get("templates", [])], path)

    def classes(self) -> Counter:
        return Counter(t.label for t in self.templates)

    def add(self, tpl: Template) -> bool:
        """Add a template unless an identical one exists. Returns True if added."""
        sig = tpl.signature()
        for t in self.templates:
            if t.signature() == sig:
                if t.label != tpl.label:
                    t.label = tpl.label  # latest reviewed class wins
                return False
        self.templates.append(tpl)
        return True


def template_for_item(pv: PageVectors, item: Item, source: str = "") -> Template | None:
    snapped = snap_box(pv, item.box)
    if snapped is None:
        return None
    box, idx = snapped
    if len(idx) < MIN_TEMPLATE_STROKES:
        return None
    return Template.from_page(pv, idx, box, item.cls, source)


def build_from_items(lib: SymbolLibrary, items_by_page: dict[tuple[str, int], list[Item]], vectors) -> dict[str, int]:
    """Add one template per distinct symbol geometry found among the items.

    vectors(doc_id, page) must return PageVectors. Geometries seen only once
    are still added; frequency information is kept in the template source.
    Returns the number of templates added per class.
    """
    added: dict[str, int] = defaultdict(int)
    seen: dict[frozenset, tuple[Template, int]] = {}
    for (doc_id, page), items in items_by_page.items():
        pv = vectors(doc_id, page)
        for it in items:
            tpl = template_for_item(pv, it, f"{doc_id}:{page + 1}")
            if tpl is None:
                continue
            sig = tpl.signature()
            if sig in seen:
                seen[sig] = (seen[sig][0], seen[sig][1] + 1)
            else:
                seen[sig] = (tpl, 1)
    for tpl, n in seen.values():
        tpl.source = f"{tpl.source} ({n} examples)"
        if lib.add(tpl):
            added[tpl.label] += 1
    return dict(added)


def detect_page(
    project: Project,
    doc_id: str,
    page: int,
    pv: PageVectors,
    templates: list[Template],
    status_threshold: float | None = None,
) -> list[Item]:
    """New items for template matches that do not overlap existing items."""
    s = project.settings
    matches: list[Match] = match_library(templates, pv, s.match_min_score, s.match_min_precision)
    existing = project.page_items(doc_id, page)
    threshold = s.auto_accept if status_threshold is None else status_threshold
    new = []
    for m in matches:
        if any(ios(m.box, e.box) > 0.5 for e in existing):
            continue
        new.append(
            Item(
                doc_id,
                page,
                m.box,
                m.label,
                source="library",
                status="accepted" if m.score >= threshold else "proposed",
                score=m.score,
                meta={"template": m.template_id},
            )
        )
    return new
