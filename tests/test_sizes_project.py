import pytest

from spectra.core.linesize import find_line_numbers, infer_size
from spectra.core.project import Document, Item, Project, Section, import_v1
from spectra.core.sizes import inch_to_dn, parse_line_number, parse_size
from spectra.core.taxonomy import Taxonomy
from spectra.core.vectors import PageVectors


@pytest.mark.parametrize(
    "text, size, rest",
    [
        ('Manual Valve 6"', 150, "Manual Valve"),
        ("Manual Valve 6in", 150, "Manual Valve"),
        ("MV 1-1/2\"", 40, "MV"),
        ("ESDV DN200", 200, "ESDV"),
        ("Flange 150mm", 150, "Flange"),
        ("Flange 6", 150, "Flange"),
        ("Vessel 900", 900, "Vessel"),
        ("Check valve", None, "Check valve"),
    ],
)
def test_parse_size(text, size, rest):
    assert parse_size(text) == (size, rest)


@pytest.mark.parametrize(
    "text, size",
    [('6"-P-1001-A1A', 150), ("150-HC-12345-B1A", 150), ('1-1/2"-PG-100-AA1', 40), ("2-P-10-A", 50), ("PT-1001", None), ("HV-1234", None)],
)
def test_parse_line_number(text, size):
    assert parse_line_number(text) == size


@pytest.mark.parametrize(
    "label, cls",
    [("Manual Valve", "manual_valve"), ("Check Valve", "check_valve"), ("ESDV", "actuated_valve"), ("PSV", "relief_valve"),
     ("Flanged Joints", "flange"), ("Instrument Connection", "instrument"), ("Control valve", "actuated_valve"),
     ("Gate valve", "manual_valve"), ("Recip pump", "pump_reciprocating"), ("Separator", "vessel")],
)
def test_label_to_class(label, cls):
    assert Taxonomy().match_label(label) == cls


def test_sizes_from_line_numbers(synthetic):
    from spectra.core.geometry import iou

    drawing, pdf = synthetic
    ok = total = 0
    for page in range(pdf.n_pages):
        pv = PageVectors(pdf.vectors(page))
        numbers = find_line_numbers(pdf.words(page))
        for t in drawing.truth:
            if t.page != page or t.cls not in ("manual_valve", "check_valve", "actuated_valve", "flange"):
                continue
            ln = infer_size(t.box, pv, numbers)
            total += 1
            ok += bool(ln and ln.size_mm == inch_to_dn(t.size_in))
    assert ok == total


def test_project_round_trip_with_relative_paths(tmp_path):
    p = Project()
    pdf = tmp_path / "drawings" / "a.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF")
    p.documents.append(Document("d", str(pdf), "abc", "a.pdf", 2, [0]))
    s = Section("S1", size_mm=100)
    p.sections.append(s)
    p.items.append(Item("d", 1, (1.234, 2, 3, 4), "flange", section=s.id, meta={"label": "Flange 4in"}))
    path = tmp_path / "study.spectra.json"
    p.save(path)
    assert '"drawings' in path.read_text()  # stored relative
    q = Project.load(path)
    assert q.documents[0].path == str(pdf.resolve())
    assert q.items[0].box == (1.23, 2, 3, 4) and q.section_of(q.items[0]).name == "S1"
    assert q.effective_size(q.items[0]) == 100


def test_import_v1_project():
    data = {
        "sections": [{"name": "A", "line_size": 50.0, "polylines": [{"points": [[0, 0], [100, 0]], "page": 2}], "color": "#ff0000"}],
        "detections": [{"name": "Manual Valve", "confidence": 0.8, "bbox": [10, 10, 20, 20], "page_num": 2, "section": "A", "line_size": None, "count": 1}],
    }
    items, sections = import_v1(data, Document("d", "x.pdf"), Taxonomy(), scale=2.0)
    assert sections[0].regions[0].page == 1 and sections[0].regions[0].points[1] == (50.0, 0.0)
    assert items[0].cls == "manual_valve" and items[0].box == (5.0, 5.0, 10.0, 10.0) and items[0].section == sections[0].id
