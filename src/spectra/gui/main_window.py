"""Main window: drawing in the middle, drawings on the left, items, sections and results on the right."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
    QMenu, QMessageBox, QProgressBar, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.bluebeam import SKIP, markup_points
from ..core.geometry import ios, mm_to_pt
from ..core.library import SymbolLibrary, library_dir, template_for_item
from ..core.project import Item, Project, Region, Section, import_v1
from ..core.report import write_csv, write_xlsx
from . import theme
from .dialogs import BluebeamDialog, DatasetDialog, DetectDialog, SettingsDialog
from .page_view import PageView
from .panels import DrawingsPanel, ItemsPanel, ResultsPanel, SectionsPanel
from .state import AppState
from .theme import Tokens as T
from .workers import TaskRunner

FILTER = "Spectra project (*.spectra.json)"


def _not_overlapping(new: list[Item], existing: list[Item]) -> list[Item]:
    """Drop new items that duplicate one already found on the same page."""
    return [n for n in new if not any(e.doc == n.doc and e.page == n.page and ios(e.box, n.box) > 0.5 for e in existing)]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        self.tasks = TaskRunner(self)
        self.setMinimumSize(1024, 640)
        self._draw_target: str | None = None

        self.view = PageView(self.state)
        self.drawings = DrawingsPanel(self.state)
        self.items_panel = ItemsPanel(self.state)
        self.sections_panel = SectionsPanel(self.state)
        self.results_panel = ResultsPanel(self.state)

        right = QTabWidget()
        right.addTab(self.items_panel, "Items")
        right.addTab(self.sections_panel, "Sections")
        right.addTab(self.results_panel, "Results")
        self.right = right

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.drawings)
        split.addWidget(self.view)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([250, 850, 500])
        split.setChildrenCollapsible(False)
        self.drawings.setMinimumWidth(200)
        right.setMinimumWidth(420)

        root = QWidget()
        rl = theme.apply_layout(QVBoxLayout(root), 0, 0)
        rl.addWidget(self._build_toolbar())
        rule = QFrame()
        theme.set_role(rule, "divider")
        rl.addWidget(rule)
        rl.addWidget(split, 1)
        self.setCentralWidget(root)

        self._build_menus()
        self._build_status()
        self._connect()
        self._update_title()
        self._update_status()

    # --- Construction --------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        lay = theme.apply_layout(QHBoxLayout(bar), T.ROW_SPACING, T.ROW_SPACING)
        lay.setContentsMargins(T.GROUP_MARGIN, T.ROW_SPACING, T.GROUP_MARGIN, T.ROW_SPACING)

        seg = QFrame()
        theme.set_role(seg, "segmented")
        sl = theme.apply_layout(QHBoxLayout(seg), 2, 2)
        self.mode_buttons = QButtonGroup(self)
        for key, text, tip in (("select", "Select", "Select, move and resize items (V)"),
                               ("add", "Add", "Click a symbol to add it, or drag a box round it (A)"),
                               ("section", "Section", "Draw a section region along pipework (S)")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setProperty("mode", key)
            self.mode_buttons.addButton(b)
            sl.addWidget(b)
            if key == "select":
                b.setChecked(True)
        self.mode_buttons.buttonClicked.connect(lambda b: self.view.set_mode(b.property("mode")))
        lay.addWidget(seg)

        self.class_combo = QComboBox()
        self.class_combo.setToolTip("Class for new items; number keys change it")
        for c in self.state.project.taxonomy:
            self.class_combo.addItem(c.name + (f"  ({c.hotkey})" if c.hotkey else ""), c.key)
        self.class_combo.currentIndexChanged.connect(lambda _: setattr(self.state, "current_class", self.class_combo.currentData()))
        lay.addWidget(self.class_combo)
        lay.addSpacing(T.GROUP_SPACING)

        detect = QPushButton("Detect…")
        theme.set_variant(detect, "primary")
        detect.setToolTip("Find symbols with a library and/or a trained model (Ctrl+D)")
        detect.clicked.connect(self.detect)
        similar = QPushButton("Find similar")
        similar.setToolTip("Find every copy of the selected symbol (F)")
        similar.clicked.connect(self.find_similar)
        nxt = QPushButton("Next to review")
        nxt.setToolTip("Go to the next proposal awaiting review (N)")
        nxt.clicked.connect(lambda: self.next_review(+1))
        accept_page = QPushButton("Accept page")
        accept_page.setToolTip("Accept every proposal on this page (Ctrl+Enter)")
        accept_page.clicked.connect(self.accept_page)
        for w in (detect, similar, nxt, accept_page):
            lay.addWidget(w)
        for b in self.mode_buttons.buttons() + [detect, similar, nxt, accept_page]:
            b.setMinimumWidth(b.sizeHint().width())
        self.class_combo.setMinimumWidth(self.class_combo.sizeHint().width())
        lay.addStretch()
        self.zoom_label = QLabel("")
        theme.set_role(self.zoom_label, "caption")
        fit = QPushButton("Fit")
        theme.set_variant(fit, "quiet")
        fit.setToolTip("Fit the page (Ctrl+0)")
        fit.clicked.connect(self.view.fit_page)
        lay.addWidget(self.zoom_label)
        lay.addWidget(fit)
        return bar

    def _action(self, menu: QMenu, text: str, slot, shortcut=None, tip: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setStatusTip(tip)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _build_menus(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu("File")
        self._action(f, "New project", self.new_project, QKeySequence.StandardKey.New)
        self._action(f, "Open project…", self.open_project, QKeySequence.StandardKey.Open)
        self._action(f, "Save", self.save, QKeySequence.StandardKey.Save)
        self._action(f, "Save as…", self.save_as, QKeySequence.StandardKey.SaveAs)
        f.addSeparator()
        self._action(f, "Add drawings…", self.add_drawings, "Ctrl+Shift+O")
        self._action(f, "Import Bluebeam markups…", self.import_bluebeam_current)
        self._action(f, "Import Spectra 1.x project…", self.import_v1)
        f.addSeparator()
        self._action(f, "Export Excel report…", self.export_xlsx, "Ctrl+E")
        self._action(f, "Export CSV summary…", self.export_csv)
        f.addSeparator()
        self._action(f, "Quit", self.close, QKeySequence.StandardKey.Quit)

        e = mb.addMenu("Edit")
        undo = self.state.undo.createUndoAction(self, "Undo")
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        redo = self.state.undo.createRedoAction(self, "Redo")
        redo.setShortcut(QKeySequence.StandardKey.Redo)
        e.addAction(undo)
        e.addAction(redo)
        e.addSeparator()
        self._action(e, "Accept selected\tEnter", self.accept_selected)
        self._action(e, "Accept all on page\tCtrl+Enter", self.accept_page)
        self._action(e, "Delete selected\tDel", self.delete_selected)
        self._action(e, "Select all on page\tCtrl+A", self.select_page)

        v = mb.addMenu("View")
        self._action(v, "Fit page", self.view.fit_page, "Ctrl+0")
        self._action(v, "Zoom in", lambda: self.view.set_zoom(self.view.transform().m11() * 1.25), QKeySequence.StandardKey.ZoomIn)
        self._action(v, "Zoom out", lambda: self.view.set_zoom(self.view.transform().m11() / 1.25), QKeySequence.StandardKey.ZoomOut)
        self._action(v, "Next page", lambda: self.step_page(+1), "PgDown")
        self._action(v, "Previous page", lambda: self.step_page(-1), "PgUp")
        v.addSeparator()
        for key, text, sc in (("select", "Select mode", "V"), ("add", "Add mode", "A"), ("section", "Section mode", "S")):
            self._action(v, f"{text}\t{sc}", lambda checked=False, k=key: self.set_mode(k))

        d = mb.addMenu("Detect")
        self._action(d, "Detect symbols…", self.detect, "Ctrl+D")
        self._action(d, "Find similar to selected\tF", self.find_similar)
        self._action(d, "Next to review\tN", lambda: self.next_review(+1))
        self._action(d, "Previous to review\tShift+N", lambda: self.next_review(-1))
        d.addSeparator()
        self._action(d, "Add selected to library…", self.add_to_library)
        self._action(d, "Build library from accepted items…", self.build_library)

        t = mb.addMenu("Training")
        self._action(t, "Export dataset…", self.export_dataset)
        self._action(t, "Evaluate detection on this project…", self.evaluate)

        s = mb.addMenu("Settings")
        self._action(s, "Classes and conventions…", self.settings)

        h = mb.addMenu("Help")
        self._action(h, "Keyboard shortcuts", self.show_shortcuts, "F1")
        self._action(h, "Open demo drawing", self.open_demo)
        self._action(h, "About Spectra", self.about)

        # Single-key shortcuts act only while the drawing or the item table has
        # focus, so typing a tag such as "FV-100" never triggers them.
        keys = [
            ("Return", self.accept_selected), ("Enter", self.accept_selected), ("Ctrl+Return", self.accept_page),
            ("Delete", self.delete_selected), ("Ctrl+A", self.select_page), ("F", self.find_similar),
            ("N", lambda: self.next_review(+1)), ("Shift+N", lambda: self.next_review(-1)),
            ("V", lambda: self.set_mode("select")), ("A", lambda: self.set_mode("add")), ("S", lambda: self.set_mode("section")),
        ]
        keys += [(c.hotkey, lambda k=c.key: self.set_class(k)) for c in self.state.project.taxonomy if c.hotkey]
        for widget in (self.view, self.items_panel.table):
            for seq, slot in keys:
                QShortcut(QKeySequence(seq), widget, activated=slot, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _build_status(self) -> None:
        sb = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.kpi = QLabel("")
        self.kpi.setToolTip("Automatic detections accepted without any change, out of all automatic detections "
                            "accepted or deleted. Target: 90 %.")
        self.counts = QLabel("")
        sb.addPermanentWidget(self.counts)
        sb.addPermanentWidget(self.kpi)
        sb.addPermanentWidget(self.progress)

    def _connect(self) -> None:
        st = self.state
        self.view.add_requested.connect(self.add_item)
        self.view.geometry_edited.connect(self.geometry_edited)
        self.view.section_drawn.connect(self.section_drawn)
        self.view.item_menu_requested.connect(self.item_menu)
        self.view.zoom_changed.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f} %"))
        self.view.mode_changed.connect(self._mode_changed)
        self.drawings.add_requested.connect(self.add_drawings)
        self.items_panel.navigate.connect(self.navigate_to)
        self.items_panel.find_similar.connect(self.find_similar)
        self.items_panel.accept_requested.connect(self.accept_selected)
        self.items_panel.delete_requested.connect(self.delete_selected)
        self.sections_panel.draw_requested.connect(self.draw_section_region)
        self.sections_panel.propose_requested.connect(self.propose_sections)
        self.results_panel.export_xlsx.connect(self.export_xlsx)
        self.results_panel.export_csv.connect(self.export_csv)
        self.results_panel.navigate.connect(self.navigate_to)
        for sig in (st.items_changed, st.page_changed, st.project_changed, st.sections_changed):
            sig.connect(self._update_status)
        st.undo.cleanChanged.connect(self._update_title)
        st.project_changed.connect(self._update_title)
        self.tasks.started.connect(self._busy_start)
        self.tasks.progress.connect(self._busy_progress)
        self.tasks.finished.connect(self._busy_end)
        self.tasks.failed.connect(lambda label, msg: QMessageBox.critical(self, "Spectra", f"{label} failed.\n\n{msg}"))

    # --- Status ------------------------------------------------------------------------

    def _update_title(self, *_) -> None:
        p = self.state.project
        name = p.path.name.removesuffix(".spectra.json") if p.path else p.name
        self.setWindowTitle(f"Spectra — {name}{' *' if self.state.dirty else ''}")

    def _update_status(self) -> None:
        st = self.state
        page = st.page_items()
        review = sum(i.status != "accepted" for i in page)
        self.counts.setText(f"Page: {len(page)} items" + (f", {review} to review" if review else ""))
        rate, n = st.auto_kept_rate()
        self.kpi.setText(f"Kept unchanged: {rate * 100:.0f} % of {n} automatic" if n else "")
        self._update_title()

    def _busy_start(self, label: str) -> None:
        self.statusBar().showMessage(label + "…")
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)

    def _busy_progress(self, i: int, n: int) -> None:
        self.progress.setRange(0, n)
        self.progress.setValue(i)

    def _busy_end(self) -> None:
        self.progress.setVisible(False)
        self.statusBar().clearMessage()

    def _mode_changed(self, mode: str) -> None:
        for b in self.mode_buttons.buttons():
            b.setChecked(b.property("mode") == mode)
        if mode != "section":
            self._draw_target = None

    def set_mode(self, mode: str) -> None:
        self.view.set_mode(mode)
        self.view.setFocus()

    # --- Project --------------------------------------------------------------------------

    def _confirm_discard(self) -> bool:
        if not self.state.dirty:
            return True
        r = QMessageBox.question(self, "Spectra", "Save changes to the current project?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def new_project(self) -> None:
        if self._confirm_discard():
            self.state.set_project(Project())

    def open_project(self, path: str | None = None) -> None:
        if not self._confirm_discard():
            return
        path = path or QFileDialog.getOpenFileName(self, "Open project", QSettings().value("dir", ""), FILTER)[0]
        if not path:
            return
        try:
            project = Project.load(path)
        except (ValueError, OSError, json.JSONDecodeError, KeyError) as e:
            QMessageBox.warning(self, "Spectra", f"Could not open {Path(path).name}:\n{e}")
            return
        missing = [d.name for d in project.documents if not Path(d.path).exists()]
        if missing:
            QMessageBox.warning(self, "Spectra", "These drawings were not found next to the project and will be skipped:\n"
                                + "\n".join(missing))
            project.documents = [d for d in project.documents if Path(d.path).exists()]
        QSettings().setValue("dir", str(Path(path).parent))
        self.state.set_project(project)

    def save(self) -> bool:
        if self.state.project.path is None:
            return self.save_as()
        self.state.project.save(self.state.project.path)
        self.state.undo.setClean()
        self.state.dirty = False
        self._update_title()
        self.statusBar().showMessage("Saved", 2000)
        return True

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save project", QSettings().value("dir", ""), FILTER)
        if not path:
            return False
        if not path.endswith(".spectra.json"):
            path = path.removesuffix(".json") + ".spectra.json"
        self.state.project.path = Path(path)
        return self.save()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._confirm_discard():
            self.view.shutdown()
            self.state.ws.close()
            event.accept()
        else:
            event.ignore()

    def add_drawings(self, paths: list[str] | None = None) -> None:
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(self, "Add drawings", QSettings().value("dir", ""), "PDF drawings (*.pdf)")
        if not paths:
            return
        QSettings().setValue("dir", str(Path(paths[0]).parent))
        added = []
        for p in paths:
            try:
                n_before = len(self.state.project.documents)
                doc = self.state.ws.add_document(p)
                if len(self.state.project.documents) > n_before:
                    added.append(doc)
            except Exception as e:  # a broken PDF should not stop the others
                QMessageBox.warning(self, "Spectra", f"Could not open {Path(p).name}:\n{e}")
        if not added:
            return
        self.state.dirty = True
        if self.state.doc_id is None:
            self.state.doc_id, self.state.page = added[0].id, 0
        self.state.project_changed.emit()
        self.state.page_changed.emit()
        marked = [d for d in added if markup_points(self.state.ws.pdf(d.id))]
        if marked:
            self.import_bluebeam([d.id for d in marked])

    def import_v1(self) -> None:
        if self.state.doc_id is None:
            QMessageBox.information(self, "Spectra", "Open the drawing the 1.x project belongs to first, then import.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Spectra 1.x project", QSettings().value("dir", ""), "Spectra 1.x (*.json)")
        if not path:
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        scale, ok = QInputDialog.getDouble(self, "Spectra", "Render scale used by 1.x when the boxes were made (usually 1.0):", 1.0, 0.5, 2.0, 2)
        if not ok:
            return
        items, sections = import_v1(data, self.state.project.document(self.state.doc_id), self.state.project.taxonomy, scale)
        self.state.set_sections(self.state.project.sections + sections, "Import 1.x project", [], items)

    # --- Bluebeam -------------------------------------------------------------------------------

    def import_bluebeam_current(self) -> None:
        if self.state.doc_id is None:
            self.add_drawings()
            return
        self.import_bluebeam([d.id for d in self.state.project.documents])

    def import_bluebeam(self, doc_ids: list[str]) -> None:
        st = self.state
        points = [p for d in doc_ids for p in markup_points(st.ws.pdf(d))]
        if not points:
            QMessageBox.information(self, "Spectra", "No Bluebeam count markups found in these drawings.")
            return
        dlg = BluebeamDialog(self, st.project.taxonomy, points, len(doc_ids))
        if not dlg.exec():
            return
        field_name, mapping = dlg.field.currentText(), dlg.mapping()
        regions, complete, sizes = dlg.regions.isChecked(), dlg.complete.isChecked(), dlg.sizes.isChecked()

        def work(progress):
            items, reports, secs = [], [], []
            for k, d in enumerate(doc_ids):
                new, report, rs = st.ws.import_bluebeam(d, field_name, mapping, with_regions=regions)
                items += new
                reports.append(report)
                secs += rs
                progress(k + 1, len(doc_ids) * (2 if complete else 1))
            extra = []
            if complete and items:
                lib = SymbolLibrary("imported")
                st.ws.build_library(lib, items)
                pages = [(d, p) for d in doc_ids for p in range(st.project.document(d).n_pages)]
                extra = _not_overlapping(st.ws.detect_with_library(lib, pages), items)
                for it in extra:
                    it.status = "proposed"
                    it.meta["reason"] = "matches a marked symbol but was not marked"
            if sizes:
                st.ws.fill_details(items + extra)
            return items, extra, reports, secs

        def done(result):
            items, extra, reports, secs = result
            if secs:
                st.set_sections(st.project.sections + secs, "Import Bluebeam markups", [], items + extra)
            else:
                st.add_items(items + extra, "Import Bluebeam markups")
            msg = "\n".join(r.summary() for r in reports)
            if extra:
                msg += f"\n\n{len(extra)} further symbols match the marked ones but were not marked. They are proposals: " \
                       "review them with N (next) and Enter (accept) or Delete."
            QMessageBox.information(self, "Bluebeam import", msg)

        self.tasks.run("Importing Bluebeam markups", work, done)

    # --- Items --------------------------------------------------------------------------------

    def add_item(self, box, from_click: bool) -> None:
        st = self.state
        if st.doc_id is None:
            return
        if from_click:
            snapped = st.ws.snap_point(st.doc_id, st.page, box[0], box[1])
            if snapped is None:
                h = mm_to_pt(3)
                snapped = (box[0] - h, box[1] - h, box[0] + h, box[1] + h)
                self.statusBar().showMessage("No symbol under the cursor: added a 6 mm box; drag its edges to fit", 4000)
            box = snapped
        else:
            box = st.ws.snap_box(st.doc_id, st.page, box)
        item = Item(st.doc_id, st.page, box, st.current_class, source="manual")
        st.ws.fill_details([item])
        st.add_items([item], "Add item")
        st.select([item.id])

    def geometry_edited(self, item_id: str, box) -> None:
        it = self.state.project.item(item_id)
        if it:
            self.state.change_items([it], "Move item", box=tuple(box))

    def set_class(self, key: str) -> None:
        sel = self.state.selected_items()
        if sel:
            self.state.change_items([i for i in sel if i.cls != key], "Set class", cls=key)
        idx = self.class_combo.findData(key)
        if idx >= 0:
            self.class_combo.setCurrentIndex(idx)

    def accept_selected(self) -> None:
        if self.view.mode == "section":
            return
        sel = [i for i in self.state.selected_items() if i.status != "accepted"]
        if sel:
            self.state.change_items(sel, "Accept", status="accepted")
            self.next_review(+1)

    def accept_page(self) -> None:
        items = [i for i in self.state.page_items() if i.status != "accepted"]
        self.state.change_items(items, f"Accept {len(items)} item(s)", status="accepted")

    def delete_selected(self) -> None:
        sel = self.state.selected_items()
        was_review = any(i.status != "accepted" for i in sel)
        self.state.delete_items(sel)
        if was_review:
            self.next_review(+1)

    def select_page(self) -> None:
        self.state.select([i.id for i in self.state.page_items()])

    def navigate_to(self, item_id: str) -> None:
        it = self.state.project.item(item_id)
        if it is None:
            return
        self.state.go_to(it.doc, it.page)
        self.state.select([it.id])
        QTimer.singleShot(0, lambda: self.view.centre_on(it))

    def next_review(self, step: int) -> None:
        st = self.state
        order = {d.id: k for k, d in enumerate(st.project.documents)}
        todo = sorted((i for i in st.project.items if i.status != "accepted"),
                      key=lambda i: (order.get(i.doc, 0), i.page, round(i.box[1] / 20), i.box[0]))
        if not todo:
            self.statusBar().showMessage("Nothing left to review", 3000)
            return
        ids = [i.id for i in todo]
        cur = st.selected[0] if st.selected else None
        if cur in ids:
            k = (ids.index(cur) + step) % len(ids)
        else:
            here = [n for n, i in enumerate(todo) if (i.doc, i.page) == (st.doc_id, st.page)]
            k = here[0] if here else 0
        self.navigate_to(todo[k].id)

    def step_page(self, step: int) -> None:
        st = self.state
        pages = st.ws.all_pages()
        if not pages or st.doc_id is None:
            return
        k = pages.index((st.doc_id, st.page)) if (st.doc_id, st.page) in pages else 0
        st.go_to(*pages[max(0, min(len(pages) - 1, k + step))])

    def item_menu(self, screen_pos) -> None:
        m = QMenu(self)
        m.addAction("Accept", self.accept_selected)
        cls_menu = m.addMenu("Class")
        for c in self.state.project.taxonomy:
            cls_menu.addAction(c.name, lambda k=c.key: self.set_class(k))
        m.addSeparator()
        m.addAction("Find similar in this drawing", lambda: self.find_similar("document"))
        m.addAction("Find similar in all drawings", lambda: self.find_similar("project"))
        m.addAction("Add to symbol library…", self.add_to_library)
        m.addSeparator()
        m.addAction("Delete", self.delete_selected)
        m.exec(screen_pos)

    # --- Detection ------------------------------------------------------------------------------

    def _pages_for(self, scope: int) -> list[tuple[str, int]]:
        st = self.state
        if scope == 0:
            return [(st.doc_id, st.page)] if st.doc_id else []
        if scope == 1:
            d = st.project.document(st.doc_id)
            return [(d.id, p) for p in range(d.n_pages)] if d else []
        return st.ws.all_pages()

    def detect(self) -> None:
        st = self.state
        if st.doc_id is None:
            QMessageBox.information(self, "Spectra", "Add a drawing first.")
            return
        dlg = DetectDialog(self, True)
        if not dlg.exec():
            return
        lib_path = dlg.lib.currentData() if dlg.use_lib.isChecked() else ""
        model_dir = dlg.model.text().strip() if dlg.use_model.isChecked() else ""
        pages = self._pages_for(dlg.scope.currentIndex())
        if not lib_path and not model_dir:
            return

        def work(progress):
            found = []
            if lib_path:
                lib = SymbolLibrary.load(lib_path)
                found += st.ws.detect_with_library(lib, pages, progress)
            if model_dir:
                from ..core.detectors import OnnxDetector

                found += _not_overlapping(st.ws.detect_with_model(OnnxDetector(model_dir), pages, progress), found)
            st.ws.fill_details(found)
            return found

        def done(found):
            st.add_items(found, f"Detect {len(found)} item(s)")
            review = sum(i.status != "accepted" for i in found)
            self.statusBar().showMessage(f"Detected {len(found)} new items" + (f", {review} to review (N)" if review else ""), 6000)

        self.tasks.run("Detecting symbols", work, done)

    def find_similar(self, scope: str = "document") -> None:
        st = self.state
        sel = st.selected_items()
        if len(sel) != 1:
            self.statusBar().showMessage("Select one item to find its copies", 3000)
            return
        example = sel[0]

        def work(progress):
            found = st.ws.find_similar(example, scope if isinstance(scope, str) else "document")
            for it in found:
                it.cls = example.cls
                it.size_mm = None
            st.ws.fill_details(found)
            return found

        def done(found):
            st.add_items(found, f"Find similar: {len(found)}")
            self.statusBar().showMessage(f"Found {len(found)} more like this", 5000)

        self.tasks.run("Finding similar symbols", work, done)

    def _choose_library(self, title: str) -> SymbolLibrary | None:
        names = sorted(p.stem for p in library_dir().glob("*.json"))
        name, ok = QInputDialog.getItem(self, title, "Library (type a new name to create one):", names or ["Default"], 0, True)
        if not ok or not name.strip():
            return None
        path = library_dir() / f"{name.strip()}.json"
        return SymbolLibrary.load(path) if path.exists() else SymbolLibrary(name.strip())

    def add_to_library(self) -> None:
        st = self.state
        sel = st.selected_items()
        if not sel:
            return
        lib = self._choose_library("Add to symbol library")
        if lib is None:
            return
        n = 0
        for it in sel:
            tpl = template_for_item(st.ws.vectors(it.doc, it.page), it, f"{st.project.document(it.doc).name} p{it.page + 1}")
            n += bool(tpl and lib.add(tpl))
        lib.save()
        self.statusBar().showMessage(f"Library {lib.name}: {n} symbol(s) added, {len(lib.templates)} in total", 5000)

    def build_library(self) -> None:
        lib = self._choose_library("Build library from accepted items")
        if lib is None:
            return

        def work(progress):
            return self.state.ws.build_library(lib)

        def done(added):
            lib.save()
            QMessageBox.information(self, "Spectra", f"Library {lib.name} has {len(lib.templates)} symbols.\nAdded: "
                                    + (", ".join(f"{self.state.project.taxonomy.name(k)} {v}" for k, v in added.items()) or "none"))

        self.tasks.run("Building library", work, done)

    # --- Sections -------------------------------------------------------------------------------

    def draw_section_region(self, section_id: str) -> None:
        self._draw_target = section_id
        self.view.set_mode("section")
        self._draw_target = section_id
        self.view.setFocus()
        s = self.state.project.section(section_id)
        self.statusBar().showMessage(f"Drawing a region for {s.name}: click points, double-click to finish, Esc to cancel")

    def section_drawn(self, points, closed: bool) -> None:
        st = self.state
        secs = copy.deepcopy(st.project.sections)
        target = next((s for s in secs if s.id == self._draw_target), None)
        if target is None:
            names = [s.name for s in secs]
            name, ok = QInputDialog.getItem(self, "Section", "Add this region to section (or type a new name):",
                                            names or [f"Section {len(secs) + 1}"], 0, True)
            if not ok or not name.strip():
                return
            target = next((s for s in secs if s.name == name.strip()), None)
            if target is None:
                target = Section(name.strip(), colour=T.SERIES[len(secs) % len(T.SERIES)])
                secs.append(target)
        target.regions.append(Region(st.doc_id, st.page, [tuple(p) for p in points], closed))
        st.set_sections(secs, f"Draw region for {target.name}")
        self.statusBar().clearMessage()

    def propose_sections(self) -> None:
        st = self.state
        pages = sorted({(i.doc, i.page) for i in st.project.items})
        if not pages:
            QMessageBox.information(self, "Spectra", "Find the items first; sections are traced between them.")
            return

        def work(progress):
            st.ws.fill_tags([i for i in st.project.items if not i.tag])
            return st.ws.propose_sections(pages, progress)

        def done(result):
            sections, before, after, n_bounds = result
            if not sections:
                QMessageBox.information(self, "Spectra", "No connected pipework with counted items was found.")
                return
            st.set_sections(st.project.sections + sections, f"Propose {len(sections)} section(s)", before, after)
            QMessageBox.information(
                self, "Spectra",
                f"Proposed {len(sections)} sections on {len(pages)} page(s), split at {n_bounds} isolation valve(s).\n\n"
                "Isolation valves themselves are left unassigned: assign each to the section your convention requires. "
                "Sections continuing across off-page connectors appear once per sheet; give them the same name to merge "
                "them in the results, and set line sizes where items have none.")
            self.right.setCurrentWidget(self.sections_panel)

        self.tasks.run("Tracing pipework", work, done)

    # --- Settings, reports, training --------------------------------------------------------------

    def settings(self) -> None:
        dlg = SettingsDialog(self, self.state.project, self.state.ws.table.categories)
        if dlg.exec():
            dlg.apply()
            self.state.dirty = True
            self.state.items_changed.emit()

    def export_xlsx(self) -> None:
        p = self.state.project
        default = str(Path(QSettings().value("dir", "")) / f"{p.path.name.removesuffix('.spectra.json') if p.path else p.name}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel report", default, "Excel workbook (*.xlsx)")
        if path:
            write_xlsx(p, self.state.ws.table, path)
            self.statusBar().showMessage(f"Wrote {Path(path).name}", 4000)

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV summary", QSettings().value("dir", ""), "CSV (*.csv)")
        if path:
            write_csv(self.state.results(), path)

    def export_dataset(self) -> None:
        from ..core.dataset import ExportSettings, PageSource, export_coco

        p = self.state.project
        reviewed = sum(len(d.reviewed_pages) for d in p.documents)
        with_items = len({(i.doc, i.page) for i in p.items})
        dlg = DatasetDialog(self, reviewed, with_items)
        if not dlg.exec():
            return
        sources = []
        for d in p.documents:
            pages = d.reviewed_pages if dlg.reviewed.isChecked() else sorted({i.page for i in p.items if i.doc == d.id})
            for page in pages:
                items = [i for i in p.items if i.doc == d.id and i.page == page and i.status == "accepted"]
                sources.append(PageSource(d.path, d.sha256, page, items))
        settings = ExportSettings(dpi=dlg.dpi.value(), tile=dlg.tile.currentData(), overlap=dlg.overlap.value())
        out = dlg.out.text()
        self.tasks.run("Exporting dataset", lambda progress: export_coco(sources, out, settings, progress),
                       lambda meta: QMessageBox.information(self, "Spectra", f"Dataset written to {out}\n{json.dumps(meta['stats'])}"))

    def evaluate(self) -> None:
        from ..core.evaluation import Det, evaluate

        st = self.state
        dlg = DetectDialog(self, True)
        dlg.setWindowTitle("Spectra — Evaluate detection")
        if not dlg.exec():
            return
        lib_path = dlg.lib.currentData() if dlg.use_lib.isChecked() else ""
        model_dir = dlg.model.text().strip() if dlg.use_model.isChecked() else ""
        pages = [(d.id, pg) for d in st.project.documents for pg in d.reviewed_pages] or self._pages_for(dlg.scope.currentIndex())

        def work(progress):
            from ..core.workspace import Workspace

            trial = copy.deepcopy(st.project)
            trial.items = []
            ws = Workspace(trial)
            preds = []
            if lib_path:
                preds += ws.detect_with_library(SymbolLibrary.load(lib_path), pages, progress)
            if model_dir:
                from ..core.detectors import OnnxDetector

                preds += _not_overlapping(ws.detect_with_model(OnnxDetector(model_dir), pages, progress), preds)
            ws.close()
            key = {d.id: d.sha256 for d in st.project.documents}
            page_set = set(pages)
            truth = [Det(f"{key[i.doc]}:{i.page}", i.box, i.cls) for i in st.project.items if (i.doc, i.page) in page_set and i.status == "accepted"]
            pred = [Det(f"{key[i.doc]}:{i.page}", i.box, i.cls, i.score) for i in preds]
            return evaluate(truth, pred)

        def done(report):
            box = QMessageBox(self)
            box.setWindowTitle("Spectra — Evaluation")
            box.setText(f"Compared with the accepted items on {len(pages)} page(s).\n"
                        f"Kept without edit: {report.no_edit_rate * 100:.0f} % (target 90 %); found {report.found_rate * 100:.0f} % of items.")
            box.setDetailedText(report.table())
            box.exec()

        self.tasks.run("Evaluating", work, done)

    # --- Help -------------------------------------------------------------------------------------

    def show_shortcuts(self) -> None:
        keys = [
            ("V / A / S", "Select, Add and Section modes; Esc returns to Select"),
            ("Click (Add mode)", "Add the symbol under the cursor, snapped to its strokes"),
            ("Drag (Add mode)", "Add an item from a box, tightened to the strokes inside"),
            ("1 to 7", "Set the class of the selection (or of new items)"),
            ("Enter", "Accept the selected proposal and go to the next"),
            ("Ctrl+Enter", "Accept every proposal on the page"),
            ("N / Shift+N", "Next / previous proposal to review"),
            ("F", "Find every copy of the selected symbol"),
            ("Delete", "Delete the selection"),
            ("Ctrl+D", "Detect symbols with a library or model"),
            ("PgUp / PgDn", "Previous / next page"),
            ("Wheel, Space+drag, middle drag", "Zoom; pan"),
            ("Ctrl+0", "Fit page"),
            ("Ctrl+Z / Ctrl+Y", "Undo / redo"),
        ]
        QMessageBox.information(self, "Keyboard shortcuts", "\n".join(f"{k}\t{v}" for k, v in keys))

    def open_demo(self) -> None:
        from ..core.pdfdoc import cache_dir
        from ..core.synthetic import make_drawing

        path = cache_dir().parent / "demo" / "synthetic_pid.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            make_drawing(path, seed=3)
        self.add_drawings([str(path)])

    def about(self) -> None:
        QMessageBox.about(self, "About Spectra", f"Spectra {__version__}\nP&ID parts counting for quantitative risk assessment.\n"
                          "Frequencies: IOGP Report 434-01 (2019).\nRuns fully offline.")
