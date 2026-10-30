"""Import parts-count markups made in Bluebeam Revu.

Engineers mark each counted item with a markup whose label holds the type
and size ("Manual Valve 6in"). Count markups carry one vertex per item. This
module turns those markups into Spectra items:

1. read every markup point and its text fields from the PDF;
2. pick the field that holds the type (usually Label) and parse type and size;
3. snap each point to the symbol strokes under it to get an exact box.

The result serves two purposes: it brings past studies into Spectra for
review, and it produces training labels and symbol templates at no extra
annotation cost.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .annotations import Annotation
from .geometry import ios, mm_to_pt
from .pdfdoc import PdfDoc
from .project import Item, Project, Region, Section
from .sizes import parse_size
from .taxonomy import Taxonomy
from .vectors import PageVectors, snap_box, snap_point

FIELD_PRIORITY = ["Label", "Subj", "Contents"]
FALLBACK_HALF = mm_to_pt(3.0)
SHAPE_SUBTYPES = ("Circle", "Square", "Stamp")
MAX_SHAPE = mm_to_pt(40.0)  # larger shapes are areas, not single items
SKIP = "__skip__"  # mapping value for label types the user chose not to import


@dataclass
class MarkupPoint:
    page: int
    x: float  # display points
    y: float
    fields: dict[str, str]
    annotation: Annotation
    shape: tuple[float, float, float, float] | None = None  # display box of a shape drawn round the item


@dataclass
class LabelInfo:
    text: str
    cls: str | None
    size_mm: float | None
    type_text: str


@dataclass
class ImportReport:
    added: int = 0
    skipped_duplicates: int = 0
    snapped: int = 0
    unsnapped: int = 0
    unmapped: Counter = field(default_factory=Counter)  # type text -> points
    by_label: Counter = field(default_factory=Counter)
    field: str = ""

    def summary(self) -> str:
        lines = [
            f"Imported {self.added} items from the '{self.field}' field "
            f"({self.snapped} snapped to symbols, {self.unsnapped} kept as markup position).",
        ]
        if self.skipped_duplicates:
            lines.append(f"{self.skipped_duplicates} points already had an item and were skipped.")
        if self.unmapped:
            lines.append("Labels with no class (map them and import again): " + ", ".join(
                f"'{k}' x{v}" for k, v in self.unmapped.most_common()))
        return "\n".join(lines)


def markup_points(pdf: PdfDoc, pages: list[int] | None = None) -> list[MarkupPoint]:
    """Every counted point in the PDF's markups, in display space."""
    out = []
    for page, annots in pdf.annotations.items():
        if pages is not None and page not in pages:
            continue
        geom = pdf.geometry(page)
        for a in annots:
            if a.is_text_like() or a.subtype in ("FreeText", "Text", "Highlight", "Underline", "StrikeOut"):
                continue
            if a.vertices and not a.is_count:
                continue  # polylines and polygons are section regions, not items
            fields = a.candidate_labels()
            if not fields:
                continue
            shape = None
            if not a.is_count and a.subtype in SHAPE_SUBTYPES:
                b = geom.box_to_display(a.rect)
                if max(b[2] - b[0], b[3] - b[1]) <= MAX_SHAPE:
                    shape = b
            for ux, uy in a.points():
                xs, ys = geom.to_display(ux, uy)
                out.append(MarkupPoint(page, float(xs), float(ys), fields, a, shape))
    return out


def normalise_type(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_label(text: str, taxonomy: Taxonomy, mapping: dict[str, str] | None = None, bare_numbers: str = "auto") -> LabelInfo:
    size, rest = parse_size(text, bare_numbers)
    key = normalise_type(rest)
    cls = (mapping or {}).get(key)
    if cls == SKIP:
        cls = None
    elif not cls:
        cls = taxonomy.match_label(rest)
    return LabelInfo(text, cls, size, key)


def choose_field(points: list[MarkupPoint], taxonomy: Taxonomy) -> str:
    """The text field that best describes item types across all points."""
    scores: Counter = Counter()
    present: Counter = Counter()
    for p in points:
        for name, value in p.fields.items():
            present[name] += 1
            if taxonomy.match_label(parse_size(value)[1]):
                scores[name] += 1
    if not present:
        return "Label"

    def rank(name: str) -> tuple[float, int]:
        prio = FIELD_PRIORITY.index(name) if name in FIELD_PRIORITY else len(FIELD_PRIORITY)
        return (scores[name] / max(present[name], 1) * present[name], -prio)

    return max(present, key=rank)


def label_summary(points: list[MarkupPoint], field_name: str, taxonomy: Taxonomy, mapping: dict[str, str] | None = None,
                  bare_numbers: str = "auto") -> list[tuple[str, int, str | None]]:
    """Distinct type texts with their point counts and proposed class, for the mapping dialog."""
    counts: Counter = Counter()
    proposal: dict[str, str | None] = {}
    for p in points:
        info = parse_label(p.fields.get(field_name, ""), taxonomy, mapping, bare_numbers)
        counts[info.type_text] += 1
        proposal[info.type_text] = info.cls
    return [(t, n, proposal[t]) for t, n in counts.most_common()]


def import_markups(
    project: Project,
    doc_id: str,
    pdf: PdfDoc,
    field_name: str | None = None,
    mapping: dict[str, str] | None = None,
    status: str = "accepted",
    pages: list[int] | None = None,
) -> tuple[list[Item], ImportReport]:
    """Create items from markups. Items are returned, not added to the project."""
    tax = project.taxonomy
    points = markup_points(pdf, pages)
    report = ImportReport()
    report.field = field_name or choose_field(points, tax)
    vectors: dict[int, PageVectors] = {}
    new: list[Item] = []
    for p in points:
        text = p.fields.get(report.field, "")
        info = parse_label(text, tax, mapping, project.settings.bare_numbers)
        report.by_label[text] += 1
        if info.cls is None:
            report.unmapped[info.type_text or "(empty)"] += 1
            continue
        if p.page not in vectors:
            vectors[p.page] = PageVectors(pdf.vectors(p.page))
        snapped = None
        if p.shape is not None:  # a circle or box drawn round the symbol
            inside = snap_box(vectors[p.page], p.shape, margin=mm_to_pt(1.0))
            if inside is not None and len(inside[1]) >= 2:
                snapped = inside
        if snapped is None:
            snapped = snap_point(vectors[p.page], p.x, p.y)
        if snapped is not None:
            box = snapped[0]
            report.snapped += 1
        else:
            box = (p.x - FALLBACK_HALF, p.y - FALLBACK_HALF, p.x + FALLBACK_HALF, p.y + FALLBACK_HALF)
            report.unsnapped += 1
        existing = project.page_items(doc_id, p.page) + [i for i in new if i.page == p.page]
        if any(e.cls == info.cls and ios(e.box, box) > 0.6 for e in existing):
            report.skipped_duplicates += 1
            continue
        new.append(
            Item(
                doc_id,
                p.page,
                box,
                info.cls,
                size_mm=info.size_mm,
                source="bluebeam",
                status=status if snapped is not None else "proposed",
                meta={"label": text, "snapped": snapped is not None, "markup": p.annotation.fields.get("NM", "")},
            )
        )
        report.added += 1
    return new, report


def import_regions(project: Project, doc_id: str, pdf: PdfDoc) -> list[Section]:
    """Polyline and polygon markups as section regions, grouped by label or subject."""
    groups: dict[str, Section] = {}
    palette = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#ea580c", "#0891b2", "#be185d", "#65a30d"]
    for page, annots in pdf.annotations.items():
        geom = pdf.geometry(page)
        for a in annots:
            if not a.vertices or a.is_count:
                continue
            name = (a.label or a.subject or "Section").strip()
            sec = groups.get(name)
            if sec is None:
                sec = Section(name, colour=palette[len(groups) % len(palette)])
                groups[name] = sec
            pts = []
            for ux, uy in a.vertices:
                X, Y = geom.to_display(ux, uy)
                pts.append((float(X), float(Y)))
            sec.regions.append(Region(doc_id, page, pts, closed=a.subtype == "Polygon"))
    return list(groups.values())


def read_markup_csv(path: str | Path) -> list[dict[str, str]]:
    """Rows of a Bluebeam Markups List CSV summary (any column layout)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [dict(r) for r in csv.DictReader(f)]


def reconcile_with_csv(rows: list[dict[str, str]], items: list[Item]) -> list[tuple[str, int, int]]:
    """Compare counts per label: (label, count in CSV, count imported).

    Looks for columns named like Label and Count; a row without a Count
    column counts as one.
    """
    if not rows:
        return []
    cols = {c.lower().strip(): c for c in rows[0]}
    label_col = cols.get("label") or cols.get("subject")
    count_col = cols.get("count")
    if label_col is None:
        raise ValueError("CSV has no Label or Subject column")
    expected: Counter = Counter()
    for r in rows:
        try:
            n = int(float(r.get(count_col, "1") or 1)) if count_col else 1
        except ValueError:
            n = 1
        expected[r[label_col].strip()] += n
    got: Counter = Counter()
    for it in items:
        got[str(it.meta.get("label", "")).strip()] += it.count
    labels = sorted(set(expected) | set(got))
    return [(lab, expected[lab], got[lab]) for lab in labels]


def items_by_page(items: list[Item]) -> dict[tuple[str, int], list[Item]]:
    out: dict[tuple[str, int], list[Item]] = defaultdict(list)
    for i in items:
        out[(i.doc, i.page)].append(i)
    return out
