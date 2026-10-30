"""Tags from drawing text, and isolatable sections traced from pipe strokes."""

import pytest

from spectra.core.geometry import centre
from spectra.core.network import is_boundary, propose_sections
from spectra.core.project import Document, Item, Project
from spectra.core.synthetic import MM
from spectra.core.tags import assign_tags
from spectra.core.vectors import PageVectors


def _items(drawing, page):
    return [Item("d", t.page, t.box, t.cls, meta={"symbol": t.symbol, "truth_tag": t.tag}) for t in drawing.truth if t.page == page]


@pytest.mark.parametrize("page", [0, 1])
def test_tags_are_read_from_bubbles_and_nearby_text(synthetic, page):
    drawing, pdf = synthetic
    items = _items(drawing, page)
    assign_tags(items, pdf.words(page))
    drawn = [i for i in items if i.meta["truth_tag"] and i.meta["symbol"] != "relief_valve"]  # relief tags are not drawn
    assert drawn and all(i.tag == i.meta["truth_tag"] for i in drawn)
    assert all(not i.tag or i.tag == i.meta["truth_tag"] for i in items)


@pytest.mark.parametrize("page", [0, 1])
def test_sections_split_every_pipe_run_at_isolation_valves(synthetic, page):
    drawing, pdf = synthetic
    items = _items(drawing, page)
    assign_tags(items, pdf.words(page))
    sections = propose_sections(PageVectors(pdf.vectors(page)), items)
    section_of = {iid: k for k, s in enumerate(sections) for iid in s.items}
    assert not any(section_of.get(i.id) is not None for i in items if is_boundary(i))

    # Runs are horizontal lines at known positions in authoring space; page 1 is rotated 90 degrees.
    height_mm = 841 if page == 1 else 594
    run_y = [(40 + r * (height_mm - 80) / 8) * MM for r in range(9)]
    checked = 0
    for y in run_y:
        if page == 0:
            line = [i for i in items if i.box[1] - 1 <= y <= i.box[3] + 1]
            line.sort(key=lambda i: centre(i.box)[0])
        else:
            x = 841 * MM - y
            line = [i for i in items if i.box[0] - 1 <= x <= i.box[2] + 1]
            line.sort(key=lambda i: centre(i.box)[1])
        groups, current = [], []
        for i in line:
            if i.meta["symbol"] in ("instrument", "relief_valve"):
                continue
            if is_boundary(i):
                groups.append(current)
                current = []
            else:
                current.append(section_of.get(i.id))
        groups.append(current)
        groups = [g for g in groups if g]
        assert all(len(set(g)) == 1 and g[0] is not None for g in groups)  # one section between valves
        assert len({g[0] for g in groups}) == len(groups)  # a different section across each valve
        checked += len(groups)
    assert checked >= 9


def test_workspace_proposes_sections_and_assigns_items(synthetic):
    from spectra.core.workspace import Workspace

    drawing, pdf = synthetic
    ws = Workspace(Project())
    doc = ws.add_document(pdf.path)
    ws.project.items = [Item(doc.id, t.page, t.box, t.cls) for t in drawing.truth]
    ws.fill_details(ws.project.items)
    sections, before, after, n_bounds = ws.propose_sections([(doc.id, 0), (doc.id, 1)])
    assert n_bounds == sum(1 for t in drawing.truth if t.symbol == "actuated_valve")
    assert len(sections) >= 18 and len(after) == len(before) > 100
    assert all(a.section in {s.id for s in sections} for a in after)
    ws.close()
