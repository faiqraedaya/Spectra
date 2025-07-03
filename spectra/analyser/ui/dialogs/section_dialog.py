from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QComboBox,
)

class SectionDialog(QDialog):
    def __init__(self, parent, name, line_size, color, polylines=None, existing_section_names=None, existing_sections=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Section Properties")
        self.existing_section_names = existing_section_names or []
        self.existing_sections = existing_sections or []  # List of Section objects
        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.addItems(self.existing_section_names)
        if name:
            idx = self.name_combo.findText(name)
            if idx >= 0:
                self.name_combo.setCurrentIndex(idx)
            else:
                self.name_combo.setEditText(name)
        self.line_size_edit = QLineEdit(str(line_size) if line_size is not None else "")
        self.color = color
        self.color_button = QPushButton()
        self.update_color_button()
        self.ok_button = None
        self.polylines = polylines or []
        self.polyline_list = QListWidget()
        self.remove_polyline_button = QPushButton("Remove Polyline")
        self.setup_ui()
        self.setup_connections()
        self.populate_polyline_list()
        self.update_fields_enabled()
        self.validate()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(QLabel("Section Name:"))
        layout.addWidget(self.name_combo)
        layout.addWidget(QLabel("Line Size [mm]:"))
        layout.addWidget(self.line_size_edit)
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        color_layout.addWidget(self.color_button)
        layout.addLayout(color_layout)
        # Polyline management
        layout.addWidget(QLabel("Polylines (Page, # Points):"))
        layout.addWidget(self.polyline_list)
        layout.addWidget(self.remove_polyline_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def setup_connections(self):
        self.line_size_edit.textChanged.connect(self.validate)
        self.color_button.clicked.connect(self.choose_color)
        self.remove_polyline_button.clicked.connect(self.remove_selected_polyline)
        self.polyline_list.itemSelectionChanged.connect(self.update_remove_button_state)
        self.name_combo.currentTextChanged.connect(self.update_fields_enabled)

    def update_color_button(self):
        if self.color:
            self.color_button.setStyleSheet(f"background-color: {self.color.name()};")
        else:
            self.color_button.setStyleSheet("")

    def choose_color(self):
        color = QColorDialog.getColor(self.color, self, "Choose Section Color")
        if color.isValid():
            self.color = color
            self.update_color_button()

    def validate(self):
        text = self.line_size_edit.text().strip()
        if text:
            try:
                float(text)
                if self.ok_button is not None:
                    self.ok_button.setEnabled(True)
                return
            except ValueError:
                pass
        if self.ok_button is not None:
            self.ok_button.setEnabled(False)

    def populate_polyline_list(self):
        self.polyline_list.clear()
        for poly in self.polylines:
            desc = f"Page {getattr(poly, 'page', '?')}, {len(getattr(poly, 'points', []))} points"
            item = QListWidgetItem(desc)
            self.polyline_list.addItem(item)
        self.update_remove_button_state()

    def remove_selected_polyline(self):
        row = self.polyline_list.currentRow()
        if row >= 0 and row < len(self.polylines):
            del self.polylines[row]
            self.populate_polyline_list()

    def update_remove_button_state(self):
        if self.remove_polyline_button is not None:
            self.remove_polyline_button.setEnabled(self.polyline_list.currentRow() >= 0)

    def update_fields_enabled(self):
        name = self.name_combo.currentText().strip()
        is_existing = name in self.existing_section_names
        if is_existing:
            # Find the section and update line size and color
            section = next((s for s in self.existing_sections if s.name == name), None)
            if section:
                self.line_size_edit.setText(str(section.line_size) if section.line_size is not None else "")
                self.color = section.color
                self.update_color_button()
        self.line_size_edit.setEnabled(not is_existing)
        self.color_button.setEnabled(not is_existing)
        self.validate()

    def get_name(self):
        return self.name_combo.currentText().strip()

    def get_line_size(self):
        text = self.line_size_edit.text().strip()
        try:
            return float(text)
        except ValueError:
            return None

    def get_color(self):
        return self.color

    def get_polylines(self):
        return self.polylines

    def is_existing_section(self):
        return self.get_name() in self.existing_section_names 