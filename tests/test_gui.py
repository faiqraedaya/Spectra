"""The main window drives the core correctly (headless)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    from spectra.gui.theme import apply_theme

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setOrganizationName("SpectraTest")
    apply_theme(app)
    return app


@pytest.fixture
def window(app, synthetic, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spectra.gui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    w = MainWindow()
    w.resize(1400, 900)
    _, pdf = synthetic
    st = w.state
    doc = st.ws.add_document(pdf.path)
    st.doc_id, st.page = doc.id, 0
    st.project_changed.emit()
    st.page_changed.emit()
    yield w
    w.state.dirty = False
    w.view.shutdown()
    w.close()


def _wait_tasks(w):
    """Run a real event loop until the background task ends (QTest.qWait holds the GIL)."""
    from PySide6.QtCore import QEventLoop, QTimer

    if not w.tasks.busy:
        return
    loop = QEventLoop()
    w.tasks.finished.connect(loop.quit)
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    assert not w.tasks.busy, "task did not finish"


def test_click_adds_snapped_item_then_find_similar_accept_and_undo(window, synthetic):
    from spectra.core.geometry import centre, iou

    drawing, _ = synthetic
    st = window.state
    st.project.settings.auto_accept = 1.01  # every match arrives as a proposal to review
    gate = next(t for t in drawing.truth if t.page == 0 and t.symbol == "gate_valve")
    window.add_item((*centre(gate.box), *centre(gate.box)), True)
    assert len(st.project.items) == 1
    added = st.project.items[0]
    assert iou(added.box, gate.box) > 0.98 and added.cls == "manual_valve"
    assert added.size_mm == pytest.approx(25.4 * gate.size_in, rel=0.2)  # read from the line number

    window.find_similar("document")
    _wait_tasks(window)
    gates = [t for t in drawing.truth if t.symbol == "gate_valve"]
    assert len(st.project.items) == len(gates)

    st.select([i.id for i in st.project.items if i.status != "accepted"])
    window.accept_selected()
    assert all(i.status == "accepted" for i in st.project.items)
    st.undo.undo()
    assert any(i.status != "accepted" for i in st.project.items)


def test_deleting_an_automatic_detection_counts_against_the_target(window, synthetic):
    from spectra.core.geometry import centre

    drawing, _ = synthetic
    st = window.state
    flange = next(t for t in drawing.truth if t.page == 0 and t.symbol == "flange")
    window.add_item((*centre(flange.box), *centre(flange.box)), True)
    window.find_similar("page")
    _wait_tasks(window)
    auto = [i for i in st.project.items if i.source == "similar"]
    st.change_items(auto, "accept", status="accepted")
    rate, n = st.auto_kept_rate()
    assert rate == 1.0 and n == len(auto)
    st.select([auto[0].id])
    window.delete_selected()
    rate, n = st.auto_kept_rate()
    assert n == len(auto) and rate == pytest.approx((len(auto) - 1) / len(auto))
    st.undo.undo()
    assert st.auto_kept_rate() == (1.0, len(auto))


def test_section_region_assigns_items_and_feeds_results(window, synthetic, tmp_path):
    from spectra.core.geometry import centre
    from spectra.core.project import Project

    drawing, _ = synthetic
    st = window.state
    t = next(t for t in drawing.truth if t.page == 0 and t.symbol == "ball_valve")
    window.add_item((*centre(t.box), *centre(t.box)), True)
    x0, y0, x1, y1 = t.box
    window._draw_target = None
    from PySide6.QtWidgets import QInputDialog

    QInputDialog.getItem = staticmethod(lambda *a, **k: ("S-01", True))
    window.section_drawn([(x0 - 20, (y0 + y1) / 2), (x1 + 20, (y0 + y1) / 2)], False)
    item = st.project.items[0]
    assert st.project.section_of(item).name == "S-01"
    res = st.results()
    assert res.sections[0].section == "S-01" and res.sections[0].total > 0

    path = tmp_path / "p.spectra.json"
    st.project.save(path)
    again = Project.load(path)
    assert again.section_of(again.items[0]).name == "S-01"
