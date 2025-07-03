from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QColorDialog, QPushButton, QHBoxLayout
from PySide6.QtGui import QColor

class SectionDialog(QDialog):
    def __init__(self, parent, name, line_size, color):
        super().__init__(parent)
        self.setWindowTitle("Edit Section Properties")
        self.name_edit = QLineEdit(name)
        self.line_size_edit = QLineEdit(str(line_size) if line_size is not None else "")
        self.color = color
        self.color_button = QPushButton()
        self.update_color_button()
        self.ok_button = None
        self.setup_ui()
        self.setup_connections()
        self.validate()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(QLabel("Section Name:"))
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Line Size [mm]:"))
        layout.addWidget(self.line_size_edit)
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        color_layout.addWidget(self.color_button)
        layout.addLayout(color_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def setup_connections(self):
        self.line_size_edit.textChanged.connect(self.validate)
        self.color_button.clicked.connect(self.choose_color)

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
                self.ok_button.setEnabled(True)
                return
            except ValueError:
                pass
        self.ok_button.setEnabled(False)

    def get_name(self):
        return self.name_edit.text().strip()

    def get_line_size(self):
        text = self.line_size_edit.text().strip()
        try:
            return float(text)
        except ValueError:
            return None

    def get_color(self):
        return self.color 