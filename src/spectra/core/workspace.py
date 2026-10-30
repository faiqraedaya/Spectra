"""A project with its open drawings: the operations both the GUI and CLI use.

Keeps PDFs open and caches per-page vectors and words, so repeated actions
(find similar, snap, re-run detection) stay fast.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .bluebeam import ImportReport, import_markups, import_regions, items_by_page
from .detectors import OnnxDetector, detect_page as model_detect_page
from .frequency import FrequencyTable
from .geometry import Box, ios
from .library import SymbolLibrary, build_from_items, detect_page as library_detect_page, template_for_item
from .linesize import LineNumber, find_line_numbers, infer_size
from .matching import Template, find_matches
from .pdfdoc import PdfDoc, Word
from .project import Document, Item, Project, new_id
from .vectors import PageVectors, snap_box, snap_point


class Workspace:
    def __init__(self, project: Project | None = None):
        self.project = project or Project()
        self._pdfs: dict[str, PdfDoc] = {}
        self._vectors: dict[tuple[str, int], PageVectors] = {}
        self._numbers: dict[tuple[str, int], list[LineNumber]] = {}
        self._table: FrequencyTable | None = None

    # --- Drawings -------------------------------------------------------------

    def pdf(self, doc_id: str) -> PdfDoc:
        if doc_id not in self._pdfs:
            doc = self.project.document(doc_id)
            if doc is None:
                raise KeyError(doc_id)
            self._pdfs[doc_id] = PdfDoc(doc.path)
        return self._pdfs[doc_id]

    def add_document(self, path: str | Path) -> Document:
        path = str(Path(path).resolve())
        for d in self.project.documents:
            if Path(d.path) == Path(path):
                return d
        pdf = PdfDoc(path)
        sha = pdf.sha256
        for d in self.project.documents:
            if d.sha256 == sha:
                pdf.close()
                return d
        doc = Document(new_id(), path, sha, Path(path).name, pdf.n_pages)
        self.project.documents.append(doc)
        self._pdfs[doc.id] = pdf
        return doc

    def remove_document(self, doc_id: str) -> None:
        self.project.documents = [d for d in self.project.documents if d.id != doc_id]
        self.project.items = [i for i in self.project.items if i.doc != doc_id]
        for s in self.project.sections:
            s.regions = [r for r in s.regions if r.doc != doc_id]
        pdf = self._pdfs.pop(doc_id, None)
        if pdf:
            pdf.close()

    def vectors(self, doc_id: str, page: int) -> PageVectors:
        key = (doc_id, page)
        if key not in self._vectors:
            self._vectors[key] = PageVectors(self.pdf(doc_id).vectors(page))
        return self._vectors[key]

    def words(self, doc_id: str, page: int) -> list[Word]:
        return self.pdf(doc_id).words(page)

    def line_numbers(self, doc_id: str, page: int) -> list[LineNumber]:
        key = (doc_id, page)
        if key not in self._numbers:
            self._numbers[key] = find_line_numbers(self.words(doc_id, page), self.project.settings.line_number_pattern)
        return self._numbers[key]

    def close(self) -> None:
        for p in self._pdfs.values():
            p.close()
        self._pdfs.clear()
        self._vectors.clear()

    @property
    def table(self) -> FrequencyTable:
        if self._table is None:
            self._table = FrequencyTable.builtin(self.project.settings.frequency_table)
        return self._table

    # --- Symbol geometry -----------------------------------------------------------

    def snap_point(self, doc_id: str, page: int, x: float, y: float) -> Box | None:
        r = snap_point(self.vectors(doc_id, page), x, y)
        return r[0] if r else None

    def snap_box(self, doc_id: str, page: int, box: Box) -> Box:
        r = snap_box(self.vectors(doc_id, page), box)
        return r[0] if r else box

    def find_similar(self, item: Item, scope: str = "document") -> list[Item]:
        """Items for every copy of item's symbol; scope is 'page', 'document' or 'project'."""
        tpl = template_for_item(self.vectors(item.doc, item.page), item)
        if tpl is None:
            return []
        pages = self._pages(scope, item.doc, item.page)
        return self._matches_to_items([tpl], pages, source="similar", meta={"example": item.id})

    def _pages(self, scope: str, doc_id: str, page: int) -> list[tuple[str, int]]:
        if scope == "page":
            return [(doc_id, page)]
        if scope == "document":
            return [(doc_id, p) for p in range(self.pdf(doc_id).n_pages)]
        return [(d.id, p) for d in self.project.documents for p in range(d.n_pages)]

    def _matches_to_items(self, templates: list[Template], pages, source: str, meta: dict | None = None, progress=None) -> list[Item]:
        s = self.project.settings
        out: list[Item] = []
        for n, (doc_id, page) in enumerate(pages):
            pv = self.vectors(doc_id, page)
            existing = self.project.page_items(doc_id, page)
            for tpl in templates:
                for m in find_matches(tpl, pv, s.match_min_score, s.match_min_precision):
                    if any(ios(m.box, e.box) > 0.5 for e in existing + out if e.page == page and e.doc == doc_id):
                        continue
                    out.append(Item(doc_id, page, m.box, tpl.label, source=source,
                                    status="accepted" if m.score >= s.auto_accept else "proposed",
                                    score=m.score, meta=dict(meta or {})))
            if progress:
                progress(n + 1, len(pages))
        return out

    # --- Detection ------------------------------------------------------------

    def detect_with_library(self, lib: SymbolLibrary, pages: list[tuple[str, int]], progress=None) -> list[Item]:
        out: list[Item] = []
        for n, (doc_id, page) in enumerate(pages):
            out += library_detect_page(self.project, doc_id, page, self.vectors(doc_id, page), lib.templates)
            if progress:
                progress(n + 1, len(pages))
        return out

    def detect_with_model(self, det: OnnxDetector, pages: list[tuple[str, int]], progress=None) -> list[Item]:
        s = self.project.settings
        known = set(self.project.taxonomy.keys)
        out: list[Item] = []
        for n, (doc_id, page) in enumerate(pages):
            existing = self.project.page_items(doc_id, page)
            for c in model_detect_page(self.pdf(doc_id), page, det, s.model_confidence):
                if any(ios(c.box, e.box) > 0.5 for e in existing):
                    continue
                box = self.snap_box(doc_id, page, (c.box[0] - 2, c.box[1] - 2, c.box[2] + 2, c.box[3] + 2))
                out.append(Item(doc_id, page, box, c.label if c.label in known else "other", source="model",
                                status="accepted" if c.score >= s.auto_accept else "proposed", score=c.score,
                                meta={"model": det.card.name, "alternatives": c.alternatives}))
            if progress:
                progress(n + 1, len(pages))
        return out

    def fill_sizes(self, items: list[Item]) -> int:
        """Set missing item sizes from line numbers. Returns the number filled."""
        if not self.project.settings.auto_size:
            return 0
        n = 0
        tax = self.project.taxonomy
        for it in items:
            if it.size_mm is not None or tax.get(it.cls).default_size_mm is not None or tax.get(it.cls).category is None:
                continue
            ln = infer_size(it.box, self.vectors(it.doc, it.page), self.line_numbers(it.doc, it.page))
            if ln is not None:
                it.size_mm = ln.size_mm
                it.meta["size_from"] = ln.text
                n += 1
        return n

    # --- Bluebeam -------------------------------------------------------------------

    def import_bluebeam(self, doc_id: str, field_name: str | None = None, mapping: dict[str, str] | None = None,
                        with_regions: bool = False) -> tuple[list[Item], ImportReport, list]:
        items, report = import_markups(self.project, doc_id, self.pdf(doc_id), field_name, mapping)
        regions = import_regions(self.project, doc_id, self.pdf(doc_id)) if with_regions else []
        return items, report, regions

    def build_library(self, lib: SymbolLibrary, items: list[Item] | None = None) -> dict[str, int]:
        items = [i for i in (items if items is not None else self.project.items) if i.status == "accepted"]
        return build_from_items(lib, items_by_page(items), self.vectors)

    def all_pages(self) -> list[tuple[str, int]]:
        return [(d.id, p) for d in self.project.documents for p in range(d.n_pages)]

    def page_counts(self) -> dict[tuple[str, int], int]:
        out: dict[tuple[str, int], int] = defaultdict(int)
        for i in self.project.items:
            out[(i.doc, i.page)] += 1
        return out
