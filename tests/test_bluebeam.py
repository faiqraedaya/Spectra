from spectra.core.bluebeam import choose_field, import_markups, items_by_page, markup_points, reconcile_with_csv
from spectra.core.geometry import iou
from spectra.core.library import SymbolLibrary, build_from_items, detect_page
from spectra.core.project import Document, Project
from spectra.core.sizes import inch_to_dn
from spectra.core.vectors import PageVectors


def _project(pdf):
    p = Project()
    p.documents.append(Document("d1", str(pdf.path), n_pages=pdf.n_pages))
    return p


def test_count_markups_become_snapped_items_with_class_and_size(synthetic):
    drawing, pdf = synthetic
    project = _project(pdf)
    points = markup_points(pdf)
    assert len(points) == len(drawing.marked)
    assert choose_field(points, project.taxonomy) == "Label"
    items, report = import_markups(project, "d1", pdf)
    assert report.added == len(drawing.marked) and not report.unmapped
    for t in drawing.marked:
        match = [i for i in items if i.page == t.page and iou(i.box, t.box) > 0.9]
        assert len(match) == 1, t.symbol
        assert match[0].cls == t.cls
        assert match[0].size_mm == inch_to_dn(t.size_in)


def test_reimport_skips_existing_items(synthetic):
    _, pdf = synthetic
    project = _project(pdf)
    items, _ = import_markups(project, "d1", pdf)
    project.items += items
    again, report = import_markups(project, "d1", pdf)
    assert again == [] and report.skipped_duplicates == len(items)


def test_library_built_from_markups_completes_unmarked_items(synthetic):
    drawing, pdf = synthetic
    project = _project(pdf)
    items, _ = import_markups(project, "d1", pdf)
    project.items += items
    vectors = {p: PageVectors(pdf.vectors(p)) for p in range(pdf.n_pages)}
    lib = SymbolLibrary("test")
    build_from_items(lib, items_by_page(items), lambda d, p: vectors[p])
    for page in range(pdf.n_pages):
        project.items += detect_page(project, "d1", page, vectors[page], lib.templates)
    counted = {"manual_valve", "check_valve", "actuated_valve", "relief_valve", "flange", "instrument"}
    truth = [t for t in drawing.truth if t.cls in counted]
    for t in truth:
        assert any(i.page == t.page and i.cls == t.cls and iou(i.box, t.box) > 0.9 for i in project.items), t.symbol
    wrong = [i for i in project.items if not any(t.page == i.page and t.cls == i.cls and iou(i.box, t.box) > 0.9 for t in truth)]
    assert wrong == []


def test_reconcile_counts_against_markups_csv(synthetic):
    _, pdf = synthetic
    project = _project(pdf)
    items, _ = import_markups(project, "d1", pdf)
    labels = {}
    for i in items:
        labels[i.meta["label"]] = labels.get(i.meta["label"], 0) + 1
    rows = [{"Subject": "Count", "Label": k, "Count": str(v)} for k, v in labels.items()]
    assert all(exp == got for _, exp, got in reconcile_with_csv(rows, items))
