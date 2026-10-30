"""Side panels: drawings, items with inspector, sections and results."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QTableView, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.frequency import HOLE_BANDS
from ..core.project import Item, Section
from ..core.sizes import NPS_TO_DN, format_size, parse_size
from . import theme
from .theme import Tokens as T

STATUS_TEXT = {"proposed": "To review", "accepted": "Accepted"}
SOURCE_TEXT = {"manual": "Manual", "snap": "Manual", "library": "Library", "model": "Model", "similar": "Find similar",
               "bluebeam": "Bluebeam"}


def _caption(text: str, tone: str | None = None) -> QLabel:
    lab = QLabel(text)
    theme.set_role(lab, "caption", **({"tone": tone} if tone else {}))
    lab.setWordWrap(True)
    return lab


def _section_label(text: str) -> QLabel:
    lab = QLabel(text)
    theme.set_role(lab, "section")
    return lab


# --- Drawings ----------------------------------------------------------------------


class DrawingsPanel(QWidget):
    add_requested = Signal()
    remove_requested = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = theme.apply_layout(QVBoxLayout(self), T.GROUP_MARGIN, T.ROW_SPACING)
        lay.addWidget(_section_label("Drawings"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tree.itemClicked.connect(self._clicked)
        lay.addWidget(self.tree, 1)
        self.empty = _caption("Add P&ID PDFs to start. Each page appears here with its item count.")
        lay.addWidget(self.empty)
        row = QHBoxLayout()
        row.setSpacing(T.ROW_SPACING)
        add = QPushButton("Add drawings…")
        add.clicked.connect(self.add_requested)
        self.reviewed = QPushButton("Mark page reviewed")
        self.reviewed.setToolTip("Reviewed pages are complete: every symbol on them is correct. Only reviewed pages "
                                 "should be used as training data.")
        self.reviewed.clicked.connect(self._toggle_reviewed)
        row.addWidget(add)
        row.addWidget(self.reviewed)
        lay.addLayout(row)
        for sig in (state.project_changed, state.items_changed, state.page_changed):
            sig.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        st = self.state
        counts: dict[tuple[str, int], tuple[int, int]] = {}
        for i in st.project.items:
            n, r = counts.get((i.doc, i.page), (0, 0))
            counts[(i.doc, i.page)] = (n + i.count, r + (i.status != "accepted"))
        self.tree.blockSignals(True)
        self.tree.clear()
        current = None
        for d in st.project.documents:
            top = QTreeWidgetItem([d.name])
            top.setToolTip(0, d.path)
            top.setData(0, Qt.ItemDataRole.UserRole, (d.id, -1))
            for p in range(d.n_pages):
                n, r = counts.get((d.id, p), (0, 0))
                bits = [f"Page {p + 1}", f"{n} items"]
                if r:
                    bits.append(f"{r} to review")
                if p in d.reviewed_pages:
                    bits.append("reviewed")
                child = QTreeWidgetItem([" · ".join(bits)])
                child.setData(0, Qt.ItemDataRole.UserRole, (d.id, p))
                top.addChild(child)
                if d.id == st.doc_id and p == st.page:
                    current = child
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)
        if current is not None:
            self.tree.setCurrentItem(current)
        self.tree.blockSignals(False)
        self.empty.setVisible(not st.project.documents)
        doc = st.project.document(st.doc_id) if st.doc_id else None
        self.reviewed.setEnabled(doc is not None)
        self.reviewed.setText("Mark page not reviewed" if doc and st.page in doc.reviewed_pages else "Mark page reviewed")

    def _clicked(self, item: QTreeWidgetItem) -> None:
        doc_id, page = item.data(0, Qt.ItemDataRole.UserRole)
        self.state.go_to(doc_id, max(page, 0))

    def _toggle_reviewed(self) -> None:
        st = self.state
        doc = st.project.document(st.doc_id)
        if doc is None:
            return
        if st.page in doc.reviewed_pages:
            doc.reviewed_pages.remove(st.page)
        else:
            doc.reviewed_pages.append(st.page)
            doc.reviewed_pages.sort()
        st.dirty = True
        self.refresh()


# --- Items --------------------------------------------------------------------------------


class ItemsModel(QAbstractTableModel):
    HEADERS = ["Class", "Size", "Tag", "Section", "Status", "Page"]

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.rows: list[Item] = []

    def set_rows(self, rows: list[Item]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        it = self.rows[index.row()]
        p = self.state.project
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return it.id
        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            return QColor(p.taxonomy.get(it.cls).colour)
        if role == Qt.ItemDataRole.ForegroundRole and col == 1:
            if p.effective_size(it) is None and p.taxonomy.get(it.cls).category:
                return QColor(T.WARNING)
            if it.size_mm is None:
                return QColor(theme.solid(T.INK_TERTIARY))
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (1, 5):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            src = SOURCE_TEXT.get(it.source, it.source)
            score = f", score {it.score:.2f}" if it.source in ("library", "model", "similar") else ""
            size_note = "" if it.size_mm is not None else "\nSize inherited from the section or class default"
            label = f"\nBluebeam label: {it.meta['label']}" if it.meta.get("label") else ""
            return f"{p.taxonomy.name(it.cls)} from {src}{score}{size_note}{label}"
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if col == 0:
            return p.taxonomy.name(it.cls)
        if col == 1:
            size = p.effective_size(it)
            if size is None:
                return "No size" if p.taxonomy.get(it.cls).category else ""
            return f"{size:g}"
        if col == 2:
            return it.tag
        if col == 3:
            s = p.section_of(it)
            return s.name if s else "Unassigned"
        if col == 4:
            return STATUS_TEXT.get(it.status, it.status)
        if col == 5:
            return it.page + 1
        return None


class ItemsPanel(QWidget):
    navigate = Signal(str)  # item id
    find_similar = Signal()
    accept_requested = Signal()
    delete_requested = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = theme.apply_layout(QVBoxLayout(self), T.GROUP_MARGIN, T.ROW_SPACING)

        filters = QHBoxLayout()
        filters.setSpacing(T.ROW_SPACING)
        self.scope = QComboBox()
        self.scope.addItems(["This page", "All pages"])
        self.status = QComboBox()
        self.status.addItems(["Any status", "To review", "Accepted"])
        self.cls = QComboBox()
        self.cls.addItem("All classes", "")
        for c in state.project.taxonomy:
            self.cls.addItem(c.name, c.key)
        for w in (self.scope, self.status, self.cls):
            w.currentIndexChanged.connect(self.refresh)
            filters.addWidget(w)
        lay.addLayout(filters)

        self.model = ItemsModel(state)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        theme.style_table(self.table)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(3, 110)
        self.table.selectionModel().selectionChanged.connect(self._table_selected)
        self.table.doubleClicked.connect(lambda idx: self.navigate.emit(self.proxy.data(idx, Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.table, 1)
        self.count = _caption("")
        lay.addWidget(self.count)

        lay.addSpacing(T.ROW_SPACING)
        lay.addWidget(_section_label("Selected"))
        self.selection_note = _caption("Select items on the drawing or in the table to edit them.")
        lay.addWidget(self.selection_note)
        form = QFormLayout()
        form.setSpacing(T.ROW_SPACING)
        self.f_cls = QComboBox()
        for c in state.project.taxonomy:
            self.f_cls.addItem(f"{c.name}" + (f"  ({c.hotkey})" if c.hotkey else ""), c.key)
        self.f_cls.activated.connect(lambda _: self._apply("cls", self.f_cls.currentData()))
        self.f_size = QComboBox()
        self.f_size.setEditable(True)
        self.f_size.addItem("")
        for nps, dn in NPS_TO_DN.items():
            if nps >= 0.5:
                self.f_size.addItem(format_size(dn), dn)
        self.f_size.lineEdit().setPlaceholderText('e.g. 6" or DN150; blank = from section')
        self.f_size.lineEdit().editingFinished.connect(self._size_edited)
        self.f_size.activated.connect(lambda _: self._size_edited())
        self.f_tag = QLineEdit()
        self.f_tag.editingFinished.connect(lambda: self._apply("tag", self.f_tag.text().strip()))
        self.f_count = QSpinBox()
        self.f_count.setRange(1, 999)
        self.f_count.editingFinished.connect(lambda: self._apply("count", self.f_count.value()))
        self.f_section = QComboBox()
        self.f_section.activated.connect(lambda _: self._apply("section", self.f_section.currentData()))
        form.addRow("Class", self.f_cls)
        form.addRow("Size (mm)", self.f_size)
        form.addRow("Tag", self.f_tag)
        form.addRow("Count", self.f_count)
        form.addRow("Section", self.f_section)
        lay.addLayout(form)
        self.size_from = _caption("")
        lay.addWidget(self.size_from)

        row = QHBoxLayout()
        row.setSpacing(T.ROW_SPACING)
        self.b_accept = QPushButton("Accept")
        theme.set_variant(self.b_accept, "primary")
        self.b_accept.setToolTip("Accept the selected proposals (Enter)")
        self.b_accept.clicked.connect(self.accept_requested)
        self.b_similar = QPushButton("Find similar")
        self.b_similar.setToolTip("Find every copy of this symbol in the drawing set (F)")
        self.b_similar.clicked.connect(self.find_similar)
        self.b_delete = QPushButton("Delete")
        theme.set_variant(self.b_delete, "quiet")
        self.b_delete.setToolTip("Delete the selected items (Del)")
        self.b_delete.clicked.connect(self.delete_requested)
        row.addWidget(self.b_accept)
        row.addWidget(self.b_similar)
        row.addStretch()
        row.addWidget(self.b_delete)
        lay.addLayout(row)

        self._syncing = False
        state.items_changed.connect(self.refresh)
        state.sections_changed.connect(self.refresh)
        state.page_changed.connect(self.refresh)
        state.project_changed.connect(self.refresh)
        state.selection_changed.connect(self._sync_from_state)
        self.refresh()

    def refresh(self) -> None:
        st = self.state
        items = st.page_items() if self.scope.currentIndex() == 0 else list(st.project.items)
        status = self.status.currentIndex()
        if status == 1:
            items = [i for i in items if i.status != "accepted"]
        elif status == 2:
            items = [i for i in items if i.status == "accepted"]
        if self.cls.currentData():
            items = [i for i in items if i.cls == self.cls.currentData()]
        items.sort(key=lambda i: (i.doc, i.page, i.status == "accepted", i.box[1], i.box[0]))
        self.model.set_rows(items)
        self.table.setColumnHidden(5, self.scope.currentIndex() == 0)
        n_review = sum(i.status != "accepted" for i in items)
        self.count.setText(f"{len(items)} items" + (f", {n_review} to review" if n_review else ""))
        self.f_section.clear()
        self.f_section.addItem("Auto (from drawn regions)", None)
        for s in st.project.sections:
            self.f_section.addItem(s.name, s.id)
        self._sync_from_state()

    def _table_selected(self) -> None:
        if self._syncing:
            return
        ids = [self.proxy.data(i, Qt.ItemDataRole.UserRole) for i in self.table.selectionModel().selectedRows()]
        self.state.select(ids)

    def _sync_from_state(self) -> None:
        st = self.state
        sel = st.selected_items()
        self._syncing = True
        try:
            sm = self.table.selectionModel()
            sm.clearSelection()
            want = set(st.selected)
            first = None
            for r in range(self.proxy.rowCount()):
                idx = self.proxy.index(r, 0)
                if self.proxy.data(idx, Qt.ItemDataRole.UserRole) in want:
                    sm.select(idx, sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
                    first = first or idx
            if first is not None:
                self.table.scrollTo(first)
        finally:
            self._syncing = False
        enabled = bool(sel)
        for w in (self.f_cls, self.f_size, self.f_tag, self.f_count, self.f_section, self.b_accept, self.b_similar, self.b_delete):
            w.setEnabled(enabled)
        self.b_similar.setEnabled(len(sel) == 1)
        self.b_accept.setEnabled(any(i.status != "accepted" for i in sel))
        if not sel:
            self.selection_note.setText("Select items on the drawing or in the table to edit them.")
            self.size_from.setText("")
            return
        self.selection_note.setText(f"{len(sel)} item selected" if len(sel) == 1 else f"{len(sel)} items selected; edits apply to all")

        def common(attr):
            vals = {getattr(i, attr) for i in sel}
            return vals.pop() if len(vals) == 1 else None

        cls = common("cls")
        self.f_cls.setCurrentIndex(self.f_cls.findData(cls) if cls else -1)
        size = common("size_mm")
        self.f_size.setEditText(format_size(size) if size else "")
        self.f_tag.setText(common("tag") or "")
        self.f_count.setValue(common("count") or 1)
        sec = common("section")
        self.f_section.setCurrentIndex(max(0, self.f_section.findData(sec)) if sec else 0)
        if len(sel) == 1:
            it = sel[0]
            src = it.meta.get("size_from")
            eff = st.project.effective_size(it)
            if it.size_mm is not None and src:
                self.size_from.setText(f"Size read from line number {src}")
            elif it.size_mm is None and eff is not None:
                self.size_from.setText(f"Size {eff:g} mm inherited from the section or class default")
            elif eff is None and st.project.taxonomy.get(it.cls).category:
                self.size_from.setText("No size: set one here, or give the section a line size")
            else:
                self.size_from.setText(f"From Bluebeam label: {it.meta['label']}" if it.meta.get("label") else "")
        else:
            self.size_from.setText("")

    def _size_edited(self) -> None:
        text = self.f_size.currentText().strip()
        data = self.f_size.currentData()
        if data and format_size(data) == text:
            size = float(data)
        elif text:
            size, _ = parse_size(text.replace("DN", "DN "), "auto")
            if size is None:
                theme.set_state(self.f_size, "error")
                return
        else:
            size = None
        theme.set_state(self.f_size, None)
        self._apply("size_mm", size)

    def _apply(self, attr: str, value) -> None:
        if self._syncing:
            return
        sel = [i for i in self.state.selected_items() if getattr(i, attr) != value]
        if sel:
            self.state.change_items(sel, f"Set {attr.replace('_mm', '')}", **{attr: value})


# --- Sections ------------------------------------------------------------------------------


class SectionsPanel(QWidget):
    draw_requested = Signal(str)  # section id

    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = theme.apply_layout(QVBoxLayout(self), T.GROUP_MARGIN, T.ROW_SPACING)
        lay.addWidget(_caption("Isolatable sections. Draw regions along pipework or around areas; items they touch "
                               "belong to the section. Line size applies to items without their own size."))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Section", "Line size (mm)", "Pipe length (m)", "Items", "Total (/yr)"])
        theme.style_table(self.table)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._edited)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        lay.addWidget(self.table, 1)
        self.empty = _caption("No sections yet. Add one, then draw its regions on the drawing (S).")
        lay.addWidget(self.empty)
        row = QHBoxLayout()
        row.setSpacing(T.ROW_SPACING)
        add = QPushButton("Add section")
        add.clicked.connect(self._add)
        self.draw = QPushButton("Draw region")
        self.draw.setToolTip("Click points along the pipework; double-click or Enter to finish (S)")
        self.draw.clicked.connect(self._draw)
        self.colour = QPushButton("Colour…")
        self.colour.clicked.connect(self._recolour)
        self.delete = QPushButton("Delete")
        theme.set_variant(self.delete, "quiet")
        self.delete.clicked.connect(self._delete)
        for b in (add, self.draw, self.colour):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.delete)
        lay.addLayout(row)
        self._loading = False
        for sig in (state.sections_changed, state.items_changed, state.project_changed):
            sig.connect(self.refresh)
        self.refresh()

    def current(self) -> Section | None:
        r = self.table.currentRow()
        secs = self.state.project.sections
        return secs[r] if 0 <= r < len(secs) else None

    def refresh(self) -> None:
        st = self.state
        res = {r.section: r for r in st.results().sections}
        counts: dict[str, int] = {}
        for it in st.project.items:
            s = st.project.section_of(it)
            if s:
                counts[s.id] = counts.get(s.id, 0) + it.count
        self._loading = True
        row = self.table.currentRow()
        self.table.setRowCount(len(st.project.sections))
        for k, s in enumerate(st.project.sections):
            cells = [s.name, f"{s.size_mm:g}" if s.size_mm else "", f"{s.pipe_length_m:g}" if s.pipe_length_m else "",
                     str(counts.get(s.id, 0)), f"{res[s.name].total:.2e}" if s.name in res else ""]
            for c, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if c >= 3:
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c >= 1:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 0:
                    cell.setData(Qt.ItemDataRole.DecorationRole, QColor(s.colour))
                self.table.setItem(k, c, cell)
        if 0 <= row < self.table.rowCount():
            self.table.setCurrentCell(row, 0)
        self._loading = False
        has = bool(st.project.sections)
        self.empty.setVisible(not has)
        for b in (self.draw, self.colour, self.delete):
            b.setEnabled(has)

    def _edited(self, cell: QTableWidgetItem) -> None:
        if self._loading:
            return
        import copy

        secs = copy.deepcopy(self.state.project.sections)
        s = secs[cell.row()]
        text = cell.text().strip()
        try:
            if cell.column() == 0 and text:
                s.name = text
            elif cell.column() == 1:
                s.size_mm = parse_size(text, "auto")[0] if text else None
            elif cell.column() == 2:
                s.pipe_length_m = float(text) if text else 0.0
        except ValueError:
            self.refresh()
            return
        self.state.set_sections(secs, "Edit section")

    def _double_clicked(self, row: int, col: int) -> None:
        pass  # editing is inline

    def _add(self) -> None:
        import copy

        palette = T.SERIES
        secs = copy.deepcopy(self.state.project.sections)
        n = len(secs) + 1
        names = {s.name for s in secs}
        while f"Section {n}" in names:
            n += 1
        secs.append(Section(f"Section {n}", colour=palette[len(secs) % len(palette)]))
        self.state.set_sections(secs, "Add section")
        self.table.setCurrentCell(len(secs) - 1, 0)
        self.table.editItem(self.table.item(len(secs) - 1, 0))

    def _draw(self) -> None:
        s = self.current() or (self.state.project.sections[-1] if self.state.project.sections else None)
        if s:
            self.draw_requested.emit(s.id)

    def _recolour(self) -> None:
        import copy

        s = self.current()
        if not s:
            return
        c = QColorDialog.getColor(QColor(s.colour), self, "Section colour")
        if c.isValid():
            secs = copy.deepcopy(self.state.project.sections)
            secs[self.table.currentRow()].colour = c.name()
            self.state.set_sections(secs, "Section colour")

    def _delete(self) -> None:
        s = self.current()
        if not s:
            return
        before = [i for i in self.state.project.items if i.section == s.id]
        after = []
        for i in before:
            j = Item.from_dict(i.to_dict())
            j.section = None
            after.append(j)
        self.state.set_sections([x for x in self.state.project.sections if x.id != s.id], f"Delete {s.name}", before, after)


# --- Results -------------------------------------------------------------------------------------


class ResultsPanel(QWidget):
    export_xlsx = Signal()
    export_csv = Signal()
    navigate = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = theme.apply_layout(QVBoxLayout(self), T.GROUP_MARGIN, T.ROW_SPACING)
        top = QHBoxLayout()
        top.setSpacing(T.GROUP_SPACING)
        self.m_total = QLabel("–")
        theme.set_role(self.m_total, "metric")
        box = QVBoxLayout()
        box.setSpacing(0)
        box.addWidget(self.m_total)
        cap = _caption("Total release frequency (/yr)")
        cap.setWordWrap(False)
        box.addWidget(cap)
        top.addLayout(box)
        self.m_items = QLabel("–")
        theme.set_role(self.m_items, "metric")
        box2 = QVBoxLayout()
        box2.setSpacing(0)
        box2.addWidget(self.m_items)
        self.items_caption = _caption("Accepted items")
        self.items_caption.setWordWrap(False)
        box2.addWidget(self.items_caption)
        top.addLayout(box2)
        top.addStretch()
        lay.addLayout(top)

        self.include = QCheckBox("Include proposals awaiting review")
        self.include.toggled.connect(self.refresh)
        lay.addWidget(self.include)
        lay.addWidget(_caption("Release frequency per year, by hole size (mm)"))
        self.table = QTableWidget(0, len(HOLE_BANDS) + 2)
        self.table.setHorizontalHeaderLabels(["Section"] + [b.replace(" mm", "") for b in HOLE_BANDS] + ["Total"])
        theme.style_table(self.table)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 2)
        self.basis = _caption("")
        lay.addWidget(self.basis)

        lay.addWidget(_section_label("Issues"))
        self.issues = QListWidget()
        self.issues.itemDoubleClicked.connect(lambda it: it.data(Qt.ItemDataRole.UserRole) and self.navigate.emit(it.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.issues, 1)
        buttons = QDialogButtonBox()
        b_csv = buttons.addButton("Export CSV", QDialogButtonBox.ButtonRole.ActionRole)
        b_x = buttons.addButton("Export Excel report", QDialogButtonBox.ButtonRole.AcceptRole)
        theme.set_variant(b_x, "primary")
        b_csv.clicked.connect(self.export_csv)
        b_x.clicked.connect(self.export_xlsx)
        lay.addWidget(buttons)
        for sig in (state.items_changed, state.sections_changed, state.project_changed):
            sig.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        st = self.state
        res = st.results(self.include.isChecked())
        self.table.setRowCount(len(res.sections))
        for r, sec in enumerate(res.sections):
            vals = [sec.section] + [f"{v:.2e}" for v in sec.by_band] + [f"{sec.total:.2e}"]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if c:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, cell)
        total = sum(s.total for s in res.sections)
        self.m_total.setText(f"{total:.2e}" if total else "–")
        accepted = sum(i.count for i in st.project.items if i.status == "accepted")
        review = sum(1 for i in st.project.items if i.status != "accepted")
        self.m_items.setText(str(accepted))
        self.items_caption.setText("Accepted items" + (f", {review} awaiting review" if review else ""))
        t = st.ws.table
        self.basis.setText(f"{t.meta.get('name', 'Frequency data')}, {t.meta.get('edition', '')}. "
                           "Implied components and class default sizes are set under Settings > Classes and conventions.")
        self.issues.clear()
        for iss in res.issues:
            it = QListWidgetItem(iss.message)
            it.setData(Qt.ItemDataRole.UserRole, iss.item_id)
            it.setForeground(QColor(T.WARNING))
            self.issues.addItem(it)
        for k, v in res.not_counted.items():
            self.issues.addItem(QListWidgetItem(f"Not counted (no frequency category): {k} x{v}"))
        if not self.issues.count():
            self.issues.addItem(QListWidgetItem("No issues: every accepted item has a category and a size."))
