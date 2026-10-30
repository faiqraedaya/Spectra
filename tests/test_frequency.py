import pytest

from spectra.core.frequency import FrequencyTable, calculate
from spectra.core.project import Document, Item, Project, Region, Section


@pytest.fixture(scope="module")
def table():
    return FrequencyTable.builtin()


def test_lookup_uses_continuous_size_bands(table):
    assert table.lookup("Flanged Joints", 50).max_mm == 50
    assert table.lookup("Flanged Joints", 50.5).max_mm == 100  # was the 601-9999 row in 1.x
    assert table.lookup("Flanged Joints", 5000).max_mm == 9999
    assert table.lookup("Filters", 25).min_mm == 50  # below the first band: first row, not the largest


def test_section_total_with_implied_flanges_and_pipe(table):
    p = Project()
    p.documents.append(Document("d", "x.pdf"))
    s = Section("S1", size_mm=150, pipe_length_m=10.0, regions=[Region("d", 0, [(0, 0), (1000, 0), (1000, 1000), (0, 1000)], True)])
    p.sections.append(s)
    p.items += [
        Item("d", 0, (10, 10, 20, 20), "manual_valve"),
        Item("d", 0, (30, 10, 40, 20), "manual_valve", size_mm=50),
        Item("d", 0, (50, 10, 60, 20), "instrument"),
    ]
    res = calculate(p, table)
    s1 = res.sections[0]
    parts = {(l.category, l.size_mm): (l.explicit, l.implied) for l in s1.parts}
    assert parts[("Manual Valves", 150)] == (1, 0)
    assert parts[("Flanged Joints", 150)] == (0, 2)
    assert parts[("Flanged Joints", 50)] == (0, 2)
    assert parts[("Instrument Connection", 25.0)] == (1, 0)
    assert parts[("Steel Pipes", 150)] == (10.0, 0)

    def f(cat, size):
        return table.lookup(cat, size).values

    expected = [
        f("Manual Valves", 150)[b] + 2 * f("Flanged Joints", 150)[b] + f("Manual Valves", 50)[b]
        + 2 * f("Flanged Joints", 50)[b] + f("Instrument Connection", 25)[b] + 10 * f("Steel Pipes", 150)[b]
        for b in range(5)
    ]
    assert s1.by_band == pytest.approx(expected)
    assert res.issues == []


def test_missing_sizes_and_unassigned_items_are_reported_not_dropped(table):
    p = Project()
    p.items.append(Item("d", 0, (10, 10, 20, 20), "actuated_valve"))
    p.items.append(Item("d", 0, (10, 10, 20, 20), "spectacle_blind"))
    p.items.append(Item("d", 0, (10, 10, 20, 20), "manual_valve", status="proposed"))
    res = calculate(p, table)
    assert res.sections[0].section == "Unassigned"
    assert len(res.issues) == 1 and "no size" in res.issues[0].message
    assert res.not_counted == {"Spectacle blind": 1}
