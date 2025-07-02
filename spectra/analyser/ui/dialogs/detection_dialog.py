from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, 
    QLineEdit, QDialogButtonBox, QMessageBox
)
from detection.categories_map import get_all_frequency_categories
from detection.types import Detection


class DetectionDialog(QDialog):
    """Dialog for editing or creating detections"""
    
    def __init__(self, main_window, detection: Optional[Detection] = None):
        super().__init__(main_window)
        self.main_window = main_window
        self.detection = detection
        self.is_edit_mode = detection is not None
        
        self.class_combo = None
        self.section_combo = None
        self.line_size_edit = None
        self.count_edit = None
        self.ok_button = None
        
        self.setWindowTitle("Edit Object" if self.is_edit_mode else "Add Object")
        self.setup_ui()
        self.setup_connections()
        self.load_detection_data()
        
    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Class dropdown
        class_label = QLabel("Object Category:")
        layout.addWidget(class_label)
        self.class_combo = QComboBox()
        self.class_combo.addItems(get_all_frequency_categories())
        self.class_combo.setEditable(True)
        layout.addWidget(self.class_combo)
        
        # Section dropdown
        section_label = QLabel("Section:")
        layout.addWidget(section_label)
        self.section_combo = QComboBox()
        section_names = [section.name for section in self.main_window.sections_list]
        self.section_combo.addItems(section_names)
        self.section_combo.setEditable(True)
        layout.addWidget(self.section_combo)
        
        # Line size input
        line_size_label = QLabel("Line Size [mm]:")
        layout.addWidget(line_size_label)
        self.line_size_edit = QLineEdit()
        layout.addWidget(self.line_size_edit)
        
        # Count input
        count_label = QLabel("Count (number of objects in box):")
        layout.addWidget(count_label)
        self.count_edit = QLineEdit()
        self.count_edit.setText("1")
        layout.addWidget(self.count_edit)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
    def setup_connections(self):
        """Setup signal connections"""
        if self.section_combo:
            self.section_combo.currentTextChanged.connect(self.update_line_size_edit)
        if self.line_size_edit:
            self.line_size_edit.textChanged.connect(self.validate_line_size)
        
    def load_detection_data(self):
        """Load existing detection data if editing"""
        if self.is_edit_mode and self.detection:
            if self.class_combo:
                self.class_combo.setCurrentText(self.detection.name)
            if self.section_combo:
                self.section_combo.setCurrentText(getattr(self.detection, "section", "Unassigned"))
            line_size = getattr(self.detection, "line_size", "")
            if self.line_size_edit:
                self.line_size_edit.setText(str(line_size) if line_size is not None else "")
            if self.count_edit:
                self.count_edit.setText(str(getattr(self.detection, "count", 1)))
        else:
            # Set default values for new detection
            if self.class_combo:
                self.class_combo.setCurrentText("")
            if self.section_combo:
                self.section_combo.setCurrentText("Unassigned")
            if self.line_size_edit:
                self.line_size_edit.setText("")
            if self.count_edit:
                self.count_edit.setText("1")
            
        # Initial validation
        self.update_line_size_edit()
        
    def update_line_size_edit(self):
        """Update line size edit based on selected section"""
        if not self.section_combo or not self.line_size_edit or not self.ok_button:
            return
            
        section_name = self.section_combo.currentText().strip()
        section = next(
            (s for s in self.main_window.sections_list if s.name == section_name), None
        )
        if section and section.line_size is not None:
            self.line_size_edit.setText(f"{section.line_size:.2f}")
            self.ok_button.setEnabled(True)
        else:
            self.ok_button.setEnabled(True)
            
    def validate_line_size(self):
        """Validate line size input"""
        if not self.section_combo or not self.line_size_edit or not self.ok_button:
            return
            
        section_name = self.section_combo.currentText().strip()
        section = next(
            (s for s in self.main_window.sections_list if s.name == section_name), None
        )
        if section and section.line_size is not None:
            self.ok_button.setEnabled(True)
            return
            
        text = self.line_size_edit.text().strip()
        try:
            if text:  # Allow empty text
                float(text)
            self.ok_button.setEnabled(True)
        except ValueError:
            self.ok_button.setEnabled(False)
            
    def get_class_name(self) -> str:
        """Get the selected class name"""
        if not self.class_combo:
            return "Manual"
        return self.class_combo.currentText().strip() or "Manual"
        
    def get_section_name(self) -> str:
        """Get the selected section name"""
        if not self.section_combo:
            return "Unassigned"
        return self.section_combo.currentText().strip() or "Unassigned"
        
    def get_line_size(self) -> Optional[float]:
        """Get the line size value"""
        if not self.line_size_edit:
            return None
        text = self.line_size_edit.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
            
    def get_count(self) -> int:
        """Get the count value"""
        if not self.count_edit:
            return 1
        text = self.count_edit.text().strip()
        if not text:
            return 1
        try:
            return int(text)
        except ValueError:
            return 1
            
    def accept(self):
        """Validate and accept the dialog"""
        # Validate line size
        line_size = self.get_line_size()
        if line_size is not None and line_size <= 0:
            QMessageBox.warning(
                self.main_window,
                "Invalid Input",
                "Line size must be a positive number or empty."
            )
            return
            
        # Validate count
        count = self.get_count()
        if count <= 0:
            QMessageBox.warning(
                self.main_window,
                "Invalid Input",
                "Count must be a positive integer."
            )
            return
            
        super().accept() 