from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from detection.categories_map import get_all_frequency_categories


class ObjectsPanel:
    """Manages the objects panel for displaying detections"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.section_filter_dropdown = None
        self.category_filter_dropdown = None
        self.objects_table = None
        self.progress_bar = None
        
    def create_panel(self):
        """Create the objects panel with filters and table"""
        objects_panel = QWidget()
        objects_layout = QVBoxLayout()
        objects_panel.setLayout(objects_layout)

        # Filter by section and category
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter by Section:")
        filter_layout.addWidget(filter_label)
        
        self.section_filter_dropdown = QComboBox()
        self.section_filter_dropdown.addItem("All")
        self.section_filter_dropdown.currentIndexChanged.connect(
            self.main_window.apply_section_filter
        )
        filter_layout.addWidget(self.section_filter_dropdown)

        # Category filter
        category_filter_label = QLabel("Filter by Category:")
        filter_layout.addWidget(category_filter_label)
        
        self.category_filter_dropdown = QComboBox()
        self.category_filter_dropdown.addItem("All")
        for cat in get_all_frequency_categories():
            self.category_filter_dropdown.addItem(cat)
        self.category_filter_dropdown.currentIndexChanged.connect(
            self.main_window.apply_section_filter
        )
        filter_layout.addWidget(self.category_filter_dropdown)

        objects_layout.addLayout(filter_layout)

        # Objects table
        self.objects_table = QTableWidget()
        self.objects_table.setColumnCount(8)
        self.objects_table.setHorizontalHeaderLabels(
            [
                "Object",
                "Page",
                "Section",
                "X1,Y1",
                "X2,Y2",
                "Line Size [mm]",
                "Count",
                "Confidence",
            ]
        )
        objects_layout.addWidget(self.objects_table)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        objects_layout.addWidget(self.progress_bar)

        return objects_panel

    def update_objects_table(self):
        """Update the objects table with filtered detections"""
        if not self.objects_table:
            return
            
        filtered = self.main_window.get_filtered_detections()
        self.objects_table.setRowCount(len(filtered))
        
        for i, detection in enumerate(filtered):
            self.objects_table.setItem(i, 0, QTableWidgetItem(detection.name))
            self.objects_table.setItem(i, 1, QTableWidgetItem(str(detection.page_num)))
            
            section_str = getattr(detection, "section", "Unassigned")
            self.objects_table.setItem(i, 2, QTableWidgetItem(section_str))
            
            bbox = detection.bbox
            coord1 = f"{bbox[0]},{bbox[1]}"
            coord2 = f"{bbox[2]},{bbox[3]}"
            self.objects_table.setItem(i, 3, QTableWidgetItem(coord1))
            self.objects_table.setItem(i, 4, QTableWidgetItem(coord2))
            
            # Line size (show override if present, else section's)
            line_size = (
                detection.line_size
                if getattr(detection, "line_size", None) is not None
                else None
            )
            if line_size is None:
                # Try to get from section
                for section in self.main_window.sections_list:
                    if section.name == section_str:
                        line_size = section.line_size
                        break
            line_size_str = f"{line_size:.2f}" if line_size is not None else ""
            self.objects_table.setItem(i, 5, QTableWidgetItem(line_size_str))
            
            # Count
            count_str = str(getattr(detection, "count", 1))
            self.objects_table.setItem(i, 6, QTableWidgetItem(count_str))
            
            # Confidence
            conf_str = f"{detection.confidence:.3f}"
            self.objects_table.setItem(i, 7, QTableWidgetItem(conf_str))
            
        self.objects_table.resizeColumnsToContents()

    def update_section_filter_dropdown(self):
        """Update the section filter dropdown with current sections"""
        if not self.section_filter_dropdown:
            return
            
        current = self.section_filter_dropdown.currentText()
        self.section_filter_dropdown.blockSignals(True)
        self.section_filter_dropdown.clear()
        self.section_filter_dropdown.addItem("All")
        
        # Add section names, not Section objects
        section_names = [section.name for section in self.main_window.sections_list]
        for section_name in section_names:
            self.section_filter_dropdown.addItem(section_name)
            
        self.section_filter_dropdown.setCurrentText(
            current if current in ["All"] + section_names else "All"
        )
        self.section_filter_dropdown.blockSignals(False) 