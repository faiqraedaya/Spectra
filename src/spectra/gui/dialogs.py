"""Dialogs: Bluebeam import, detection, classes and conventions, dataset export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..core.bluebeam import MarkupPoint, choose_field, label_summary
from ..core.library import SymbolLibrary, library_dir
from ..core.sizes import parse_size
from . import theme
from .theme import Tokens as T


def _caption(text: str) -> QLabel:
    lab = QLabel(text)
    theme.set_role(lab, "caption")
    lab.setWordWrap(True)
    return lab


def _buttons(dialog: QDialog, ok_text: str) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
    theme.set_variant(ok, "primary")
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class BluebeamDialog(QDialog):
    """Map markup labels to classes before importing."""

    def __init__(self, parent, taxonomy, points: list[MarkupPoint], n_docs: int):
        super().__init__(parent)
        self.setWindowTitle("Spectra — Import Bluebeam markups")
        self.setMinimumSize(560, 520)
        self.taxonomy = taxonomy
        self.points = points
        lay = theme.apply_layout(QVBoxLayout(self), T.WINDOW_MARGIN, T.ROW_SPACING)
        intro = QLabel(f"Found {len(points)} counted points in {n_docs} drawing(s).")
        theme.set_role(intro, "heading")
        lay.addWidget(intro)
        lay.addWidget(_caption("Each point becomes an item snapped to the symbol under it. Type and size are read from "
                               "the field below; check the class for each label type. Unmapped types are skipped."))
        form = QFormLayout()
        form.setSpacing(T.ROW_SPACING)
        self.field = QComboBox()
        fields = sorted({k for p in points for k in p.fields})
        self.field.addItems(fields)
        if fields:
            self.field.setCurrentText(choose_field(points, taxonomy))
        self.field.currentTextChanged.connect(self._fill)
        form.addRow("Type is in field", self.field)
        lay.addLayout(form)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Label type", "Points", "Class"])
        theme.style_table(self.table)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(2, 220)
        lay.addWidget(self.table, 1)

        self.regions = QCheckBox("Import polyline and polygon markups as section regions")
        self.complete = QCheckBox("Learn the symbols and find the ones left unmarked (as proposals to review)")
        self.complete.setChecked(True)
        self.sizes = QCheckBox("Fill missing sizes from line numbers")
        self.sizes.setChecked(True)
        for c in (self.regions, self.complete, self.sizes):
            lay.addWidget(c)
        lay.addWidget(_buttons(self, "Import"))
        self._fill()

    def _fill(self) -> None:
        rows = label_summary(self.points, self.field.currentText(), self.taxonomy)
        self.table.setRowCount(len(rows))
        self.combos: list[tuple[str, QComboBox]] = []
        for r, (text, n, cls) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(text or "(empty)"))
            cell = QTableWidgetItem(str(n))
            cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 1, cell)
            combo = QComboBox()
            combo.addItem("Skip", "")
            for c in self.taxonomy:
                combo.addItem(c.name, c.key)
            combo.setCurrentIndex(max(0, combo.findData(cls or "")))
            self.table.setCellWidget(r, 2, combo)
            self.combos.append((text, combo))

    def mapping(self) -> dict[str, str]:
        return {text: combo.currentData() or "__skip__" for text, combo in self.combos}


class DetectDialog(QDialog):
    def __init__(self, parent, has_page: bool):
        super().__init__(parent)
        self.setWindowTitle("Spectra — Detect symbols")
        self.setMinimumWidth(T.MIN_DIALOG_WIDTH + 120)
        s = QSettings()
        lay = theme.apply_layout(QVBoxLayout(self), T.WINDOW_MARGIN, T.GROUP_SPACING)
        form = QFormLayout()
        form.setSpacing(T.ROW_SPACING)

        self.use_lib = QCheckBox("Symbol library")
        self.use_lib.setChecked(True)
        self.lib = QComboBox()
        for p in sorted(library_dir().glob("*.json")):
            try:
                lib = SymbolLibrary.load(p)
            except (OSError, ValueError, KeyError):
                continue
            self.lib.addItem(f"{lib.name} ({len(lib.templates)} symbols)", str(p))
        if not self.lib.count():
            self.lib.addItem("No libraries yet: build one from accepted items", "")
            self.use_lib.setChecked(False)
        last = s.value("detect/library", "")
        if last and self.lib.findData(last) >= 0:
            self.lib.setCurrentIndex(self.lib.findData(last))
        form.addRow(self.use_lib, self.lib)

        self.use_model = QCheckBox("Trained model")
        self.model = QLineEdit(s.value("detect/model", ""))
        self.model.setPlaceholderText("Folder with model.onnx and model_card.json")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.setSpacing(T.ROW_SPACING)
        row.addWidget(self.model, 1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.use_model.setChecked(bool(self.model.text()) and Path(self.model.text(), "model.onnx").exists())
        form.addRow(self.use_model, holder)

        self.scope = QComboBox()
        self.scope.addItems(["This page", "This drawing", "All drawings"])
        self.scope.setCurrentIndex(int(s.value("detect/scope", 1)))
        form.addRow("Pages", self.scope)
        lay.addLayout(form)
        lay.addWidget(_caption("The library finds exact copies of known symbols in CAD drawings within seconds "
                               "per sheet. A trained model also finds symbols in styles the library has not seen; its "
                               "results arrive as proposals to review. Existing items are never duplicated."))
        lay.addWidget(_buttons(self, "Detect"))

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Model folder", self.model.text())
        if d:
            self.model.setText(d)
            self.use_model.setChecked(Path(d, "model.onnx").exists())

    def accept(self) -> None:
        s = QSettings()
        s.setValue("detect/library", self.lib.currentData() or "")
        s.setValue("detect/model", self.model.text())
        s.setValue("detect/scope", self.scope.currentIndex())
        super().accept()


class SettingsDialog(QDialog):
    """Classes, frequency categories, counting conventions and detection thresholds."""

    def __init__(self, parent, project, categories: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Spectra — Classes and conventions")
        self.setMinimumSize(880, 560)
        self.project = project
        lay = theme.apply_layout(QVBoxLayout(self), T.WINDOW_MARGIN, T.ROW_SPACING)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        page = QWidget()
        pl = theme.apply_layout(QVBoxLayout(page), T.GROUP_MARGIN, T.ROW_SPACING)
        pl.addWidget(_caption("Each class maps to one IOGP 434-01 category. Implied flanged joints are added per item "
                              "(your usual convention is two per valve). A default size overrides the section's line "
                              "size, for example the tapping size of instrument connections."))
        self.table = QTableWidget(len(project.taxonomy), 5)
        self.table.setHorizontalHeaderLabels(["Class", "IOGP 434-01 category", "Flanges per item", "Default size (mm)", "Key"])
        theme.style_table(self.table)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col, width in ((0, 210), (2, 130), (3, 140), (4, 64)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(col, width)
        self.rows = []
        for r, c in enumerate(project.taxonomy):
            self.table.setItem(r, 0, QTableWidgetItem(c.name))
            cat = QComboBox()
            cat.addItem("Not counted", None)
            for k in categories:
                cat.addItem(k, k)
            cat.setCurrentIndex(max(0, cat.findData(c.category)))
            self.table.setCellWidget(r, 1, cat)
            fl = QDoubleSpinBox()
            fl.setRange(0, 20)
            fl.setDecimals(1)
            fl.setValue(c.implied.get("Flanged Joints", 0.0))
            self.table.setCellWidget(r, 2, fl)
            ds = QLineEdit(f"{c.default_size_mm:g}" if c.default_size_mm else "")
            self.table.setCellWidget(r, 3, ds)
            key = QLineEdit(c.hotkey)
            key.setMaxLength(1)
            self.table.setCellWidget(r, 4, key)
            self.rows.append((c, cat, fl, ds, key))
        pl.addWidget(self.table, 1)
        tabs.addTab(page, "Classes")

        page2 = QWidget()
        form = theme.apply_layout(QFormLayout(page2), T.GROUP_MARGIN, T.ROW_SPACING)
        st = project.settings
        self.min_score = self._spin(st.match_min_score)
        self.min_precision = self._spin(st.match_min_precision)
        self.auto_accept = self._spin(st.auto_accept)
        self.model_conf = self._spin(st.model_confidence)
        self.auto_size = QCheckBox("Fill missing sizes from line numbers")
        self.auto_size.setChecked(st.auto_size)
        self.pattern = QLineEdit(st.line_number_pattern)
        self.pattern.setPlaceholderText("Built-in: matches 6\"-P-1001-A1A, 150-HC-12345-B1A, …")
        self.bare = QComboBox()
        for text, key in (("Auto (up to 48 = inch, else mm)", "auto"), ("Inches", "in"), ("Millimetres", "mm"), ("Ignore", "ignore")):
            self.bare.addItem(text, key)
        self.bare.setCurrentIndex(max(0, self.bare.findData(st.bare_numbers)))
        form.addRow("Library match: minimum stroke match", self.min_score)
        form.addRow("Library match: minimum precision", self.min_precision)
        form.addRow("Accept automatically at score", self.auto_accept)
        form.addRow("Model confidence threshold", self.model_conf)
        form.addRow("", self.auto_size)
        form.addRow("Line number pattern (regex)", self.pattern)
        self.tag_pattern = QLineEdit(st.tag_pattern)
        self.tag_pattern.setPlaceholderText("Built-in: ESDV-2001, PT1006, FV-100A, …")
        self.boundary = QLineEdit(st.boundary_pattern)
        self.boundary.setPlaceholderText("Built-in: ESDV, SDV, ESV, SSV, XV, EIV, BDV, HIPPS, ZV")
        form.addRow("Tag pattern (regex)", self.tag_pattern)
        form.addRow("Isolation valve tags (regex)", self.boundary)
        form.addRow("Sizes without units in labels", self.bare)
        tabs.addTab(page2, "Detection")
        lay.addWidget(_buttons(self, "Apply"))

    @staticmethod
    def _spin(v: float) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(0.0, 1.0)
        s.setSingleStep(0.05)
        s.setDecimals(2)
        s.setValue(v)
        return s

    def apply(self) -> None:
        for c, cat, fl, ds, key in self.rows:
            c.category = cat.currentData()
            if fl.value() > 0:
                c.implied["Flanged Joints"] = fl.value()
            else:
                c.implied.pop("Flanged Joints", None)
            size, _ = parse_size(ds.text(), "mm") if ds.text().strip() else (None, "")
            c.default_size_mm = size
            c.hotkey = key.text().strip()
        st = self.project.settings
        st.match_min_score = self.min_score.value()
        st.match_min_precision = self.min_precision.value()
        st.auto_accept = self.auto_accept.value()
        st.model_confidence = self.model_conf.value()
        st.auto_size = self.auto_size.isChecked()
        st.line_number_pattern = self.pattern.text().strip()
        st.bare_numbers = self.bare.currentData()
        st.tag_pattern = self.tag_pattern.text().strip()
        st.boundary_pattern = self.boundary.text().strip()


class DatasetDialog(QDialog):
    def __init__(self, parent, n_reviewed: int, n_pages_with_items: int):
        super().__init__(parent)
        self.setWindowTitle("Spectra — Export training dataset")
        self.setMinimumWidth(T.MIN_DIALOG_WIDTH + 120)
        lay = theme.apply_layout(QVBoxLayout(self), T.WINDOW_MARGIN, T.GROUP_SPACING)
        lay.addWidget(_caption(f"{n_reviewed} page(s) marked reviewed; {n_pages_with_items} page(s) have items. Train only "
                               "on reviewed pages: an unmarked symbol on an exported page teaches the model it is background."))
        form = QFormLayout()
        form.setSpacing(T.ROW_SPACING)
        self.out = QLineEdit(QSettings().value("dataset/out", ""))
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self.out.setText(QFileDialog.getExistingDirectory(self, "Output folder") or self.out.text()))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.ROW_SPACING)
        row.addWidget(self.out, 1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Output folder", holder)
        self.reviewed = QCheckBox("Reviewed pages only")
        self.reviewed.setChecked(n_reviewed > 0)
        form.addRow("", self.reviewed)
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 400)
        self.dpi.setValue(200)
        self.tile = QComboBox()
        for t_ in (512, 576, 640):
            self.tile.addItem(f"{t_} px", t_)
        self.overlap = QSpinBox()
        self.overlap.setRange(32, 320)
        self.overlap.setValue(128)
        form.addRow("Render resolution (dpi)", self.dpi)
        form.addRow("Tile size", self.tile)
        form.addRow("Tile overlap (px)", self.overlap)
        lay.addLayout(form)
        lay.addWidget(_caption("512 px tiles suit RF-DETR Small on an 8 GB GPU; use 576 px for RF-DETR Medium. "
                               "Train with training/train_rfdetr.py (see docs/training.md)."))
        lay.addWidget(_buttons(self, "Export"))

    def accept(self) -> None:
        if not self.out.text().strip():
            theme.set_state(self.out, "error")
            return
        QSettings().setValue("dataset/out", self.out.text())
        super().accept()
