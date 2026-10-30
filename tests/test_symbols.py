"""Snapping and template matching on the synthetic drawing (rotated and mirrored symbols)."""

from collections import Counter

from spectra.core.geometry import centre, iou
from spectra.core.matching import Template, find_matches, match_library
from spectra.core.vectors import PageVectors, snap_point


def test_snap_recovers_every_symbol_box(synthetic):
    drawing, pdf = synthetic
    for page in range(pdf.n_pages):
        pv = PageVectors(pdf.vectors(page))
        for t in (t for t in drawing.truth if t.page == page):
            cx, cy = centre(t.box)
            box, _ = snap_point(pv, cx + 0.5, cy + 0.5)
            assert iou(box, t.box) > 0.98, t.symbol


def test_find_similar_returns_only_the_same_symbol(synthetic):
    drawing, pdf = synthetic
    pv = PageVectors(pdf.vectors(1))  # the rotated page
    truth = [t for t in drawing.truth if t.page == 1]
    for symbol in ("gate_valve", "check_valve", "actuated_valve", "flange", "instrument", "relief_valve"):
        examples = [t for t in truth if t.symbol == symbol]
        box, idx = snap_point(pv, *centre(examples[0].box))
        matches = find_matches(Template.from_page(pv, idx, box, symbol), pv)
        hits = Counter(next((t.symbol for t in truth if iou(m.box, t.box) > 0.9), "none") for m in matches)
        assert hits == Counter({symbol: len(examples)}), symbol


def test_library_from_one_page_detects_all_symbols_on_another(synthetic):
    drawing, pdf = synthetic
    pv0, pv1 = PageVectors(pdf.vectors(0)), PageVectors(pdf.vectors(1))
    templates = []
    for symbol in sorted({t.symbol for t in drawing.truth}):
        ex = next(t for t in drawing.truth if t.symbol == symbol)
        pv = pv0 if ex.page == 0 else pv1
        box, idx = snap_point(pv, *centre(ex.box))
        templates.append(Template.from_page(pv, idx, box, symbol))
    truth = [t for t in drawing.truth if t.page == 1]
    matches = match_library(templates, pv1)
    correct = sum(any(iou(m.box, t.box) > 0.9 and m.label == t.symbol for t in truth) for m in matches)
    assert correct == len(matches) == len(truth)


def test_template_signature_ignores_orientation(synthetic):
    drawing, pdf = synthetic
    pv = PageVectors(pdf.vectors(0))
    sigs = set()
    for t in (t for t in drawing.truth if t.symbol == "check_valve"):
        box, idx = snap_point(pv, *centre(t.box)) if t.page == 0 else (None, None)
        if box is not None:
            sigs.add(Template.from_page(pv, idx, box).signature())
    assert len(sigs) == 1


def test_matching_is_independent_of_chunk_size(synthetic):
    drawing, pdf = synthetic
    pv = PageVectors(pdf.vectors(0))
    ex = next(t for t in drawing.truth if t.page == 0 and t.symbol == "flange")
    box, idx = snap_point(pv, *centre(ex.box))
    tpl = Template.from_page(pv, idx, box)
    big = find_matches(tpl, pv)
    small = find_matches(tpl, pv, chunk=3)
    assert [m.box for m in big] == [m.box for m in small] and len(big) > 5
