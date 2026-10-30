"""Read PDF annotations, including Bluebeam Revu markups.

Bluebeam stores each markup as a standard PDF annotation. The keys that
matter for parts counting are:

- /Subj         markup subject (tool name or user subject)
- /Label        the markup label (where engineers put type and size)
- /Contents     comments
- /BSIColumnData values of custom Markups List columns
- /Vertices     for Count markups, one (x, y) pair per counted item
- /IT, /NumCounts, /CountStyle  identify Count markups

Reading uses pypdf (BSD-3-Clause) because PDFium cannot list arbitrary keys.
Coordinates returned here are PDF user space; convert them with
PageGeometry before use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

TEXT_KEYS = ("/Label", "/Subj", "/Contents", "/T", "/NM", "/IT", "/RC", "/DA")


def _resolve(obj):
    while isinstance(obj, IndirectObject):
        obj = obj.get_object()
    return obj


def _to_str(v) -> str:
    v = _resolve(v)
    if v is None:
        return ""
    if isinstance(v, NameObject):
        return str(v)[1:]
    return str(v)


@dataclass
class Annotation:
    page: int
    subtype: str
    rect: tuple[float, float, float, float]
    fields: dict[str, str] = field(default_factory=dict)  # text-valued keys without the slash
    column_data: list[str] = field(default_factory=list)  # Bluebeam /BSIColumnData
    vertices: list[tuple[float, float]] = field(default_factory=list)
    color: tuple[float, ...] = ()
    flags: int = 0

    @property
    def subject(self) -> str:
        return self.fields.get("Subj", "")

    @property
    def label(self) -> str:
        return self.fields.get("Label", "")

    @property
    def contents(self) -> str:
        return self.fields.get("Contents", "")

    @property
    def is_count(self) -> bool:
        intent = self.fields.get("IT", "").lower()
        return bool(self.vertices) and (
            "count" in intent or "NumCounts" in self.fields or "CountStyle" in self.fields
        )

    @property
    def hidden(self) -> bool:
        return bool(self.flags & 2)

    def text_hint(self) -> str:
        return (self.label or self.contents or self.subject).strip()

    def is_text_like(self) -> bool:
        """AutoCAD exports SHX text as comments so it stays searchable."""
        probe = " ".join(self.fields.get(k, "") for k in ("Subj", "NM", "T")).lower()
        return "shx" in probe

    def points(self) -> list[tuple[float, float]]:
        """Counted item locations in user space.

        Count markups give one point per vertex; any other markup gives the
        centre of its rectangle.
        """
        if self.is_count:
            return list(self.vertices)
        x0, y0, x1, y1 = self.rect
        return [((x0 + x1) / 2.0, (y0 + y1) / 2.0)]

    def candidate_labels(self) -> dict[str, str]:
        """All text fields that could hold the item type, keyed by field name."""
        out = {k: v for k, v in self.fields.items() if k in ("Label", "Subj", "Contents") and v.strip()}
        for i, v in enumerate(self.column_data):
            if v.strip():
                out[f"Column{i + 1}"] = v
        return out


def _annotation_from_dict(page_index: int, d: DictionaryObject) -> Annotation | None:
    subtype = _to_str(d.get("/Subtype"))
    if subtype in ("Link", "Widget", "Popup"):
        return None
    rect_obj = _resolve(d.get("/Rect"))
    if not isinstance(rect_obj, ArrayObject) or len(rect_obj) != 4:
        return None
    r = [float(_resolve(v)) for v in rect_obj]
    rect = (min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3]))

    fields: dict[str, str] = {}
    for key, value in d.items():
        value = _resolve(value)
        if key in ("/Rect", "/Vertices", "/BSIColumnData", "/P", "/AP", "/Parent", "/Popup"):
            continue
        if isinstance(value, (DictionaryObject, ArrayObject)):
            if key in ("/NumCounts", "/CountStyle"):
                fields[key[1:]] = "1"
            continue
        fields[key[1:]] = _to_str(value)

    column_data: list[str] = []
    cd = _resolve(d.get("/BSIColumnData"))
    if isinstance(cd, ArrayObject):
        column_data = [_to_str(v) for v in cd]

    vertices: list[tuple[float, float]] = []
    vs = _resolve(d.get("/Vertices"))
    if isinstance(vs, ArrayObject):
        nums = [float(_resolve(v)) for v in vs]
        vertices = list(zip(nums[0::2], nums[1::2]))

    color: tuple[float, ...] = ()
    c = _resolve(d.get("/C"))
    if isinstance(c, ArrayObject):
        color = tuple(float(_resolve(v)) for v in c)

    flags = int(_resolve(d.get("/F", 0)) or 0)
    return Annotation(page_index, subtype, rect, fields, column_data, vertices, color, flags)


def read_annotations(path: str | Path, pages: list[int] | None = None) -> dict[int, list[Annotation]]:
    """Annotations per page index (0-based)."""
    reader = PdfReader(str(path))
    out: dict[int, list[Annotation]] = {}
    indices = range(len(reader.pages)) if pages is None else pages
    for i in indices:
        page = reader.pages[i]
        annots = _resolve(page.get("/Annots"))
        if not isinstance(annots, ArrayObject):
            continue
        items = []
        for ref in annots:
            d = _resolve(ref)
            if isinstance(d, DictionaryObject):
                a = _annotation_from_dict(i, d)
                if a is not None:
                    items.append(a)
        if items:
            out[i] = items
    return out
