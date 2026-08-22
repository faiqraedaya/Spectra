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

from ...detection.categories_map import get_all_frequency_categories


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
        # Create objects panel
        objects_panel = QWidget()
        objects_layout = QVBoxLayout()
        objects_panel.setLayout(objects_layout)

        # Create filter layout
        filter_layout = QHBoxLayout()
        # Create filter label
        filter_label = QLabel("Filter by Section:")
        filter_layout.addWidget(filter_label)
        
        # Create section filter dropdown and connect it to apply section filter
        self.section_filter_dropdown = QComboBox()
        self.section_filter_dropdown.addItem("All")
        self.section_filter_dropdown.currentIndexChanged.connect(
            self.main_window.apply_section_filter
        )
        filter_layout.addWidget(self.section_filter_dropdown)

        # Create category filter label
        category_filter_label = QLabel("Filter by Category:")
        filter_layout.addWidget(category_filter_label)
        
        # Create category filter dropdown and connect it to apply section filter
        self.category_filter_dropdown = QComboBox()
        self.category_filter_dropdown.addItem("All")
        # Add all categories to category filter dropdown
        for cat in get_all_frequency_categories():
            self.category_filter_dropdown.addItem(cat)
        self.category_filter_dropdown.currentIndexChanged.connect(
            self.main_window.apply_section_filter
        )
        filter_layout.addWidget(self.category_filter_dropdown)

        objects_layout.addLayout(filter_layout)

        # Create objects table with 8 columns: Object, Page, Section, X1,Y1, X2,Y2, Line Size [mm], Count, Confidence
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

        # Create progress bar and set it to invisible
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        objects_layout.addWidget(self.progress_bar)

        # Return objects panel
        return objects_panel

    def update_objects_table(self):
        """Update the objects table with filtered detections"""
        if not self.objects_table: # Check if objects table exists
            return
        
        # Get filtered detections from main window
        filtered = self.main_window.get_filtered_detections()
        self.objects_table.setRowCount(len(filtered)) # Set row count to number of filtered detections
        
        # Iterate through filtered detections
        for i, detection in enumerate(filtered):
            # Set object name
            self.objects_table.setItem(i, 0, QTableWidgetItem(detection.name))
            # Set page number
            self.objects_table.setItem(i, 1, QTableWidgetItem(str(detection.page_num)))
            
            # Set section name
            section_str = getattr(detection, "section", "Unassigned") # Get section name from detection, default to "Unassigned" if not present
            self.objects_table.setItem(i, 2, QTableWidgetItem(section_str))
            
            # Set bbox coordinates
            bbox = detection.bbox # Get bbox coordinates
            coord1 = f"{bbox[0]},{bbox[1]}" # Get top left coordinate
            coord2 = f"{bbox[2]},{bbox[3]}" # Get bottom right coordinate
            self.objects_table.setItem(i, 3, QTableWidgetItem(coord1)) # Set top left coordinate
            self.objects_table.setItem(i, 4, QTableWidgetItem(coord2)) # Set bottom right coordinate
            
            # Line size (show override if present, else section's)
            line_size = (
                detection.line_size # Get line size from detection
                if getattr(detection, "line_size", None) is not None # Check if line size is not None
                else None # If line size is None, set to None
            )
            if line_size is None: # Check if line size is None
                # Try to get from section
                for section in self.main_window.sections_list: # Iterate through sections
                    if section.name == section_str: # Check if section name is equal to section name
                        line_size = section.line_size # Get line size from section
                        break # Break if section name is found
            line_size_str = f"{line_size:.2f}" if line_size is not None else "" # Format line size to 2 decimal places
            self.objects_table.setItem(i, 5, QTableWidgetItem(line_size_str)) # Set line size
            
            # Set count
            count_str = str(getattr(detection, "count", 1))
            self.objects_table.setItem(i, 6, QTableWidgetItem(count_str))
            
            # Set confidence
            conf_str = f"{detection.confidence:.3f}"
            self.objects_table.setItem(i, 7, QTableWidgetItem(conf_str))
    
        self.objects_table.resizeColumnsToContents()

    def update_section_filter_dropdown(self):
        """Update the section filter dropdown with current sections"""
        if not self.section_filter_dropdown: # Check if section filter dropdown exists
            return
        
        # Get current section filter
        current = self.section_filter_dropdown.currentText()
        
        # Block signals and clear section filter dropdown
        self.section_filter_dropdown.blockSignals(True)
        self.section_filter_dropdown.clear()
        self.section_filter_dropdown.addItem("All")
        
        # Add section names, not Section objects
        section_names = [section.name for section in self.main_window.sections_list]
        for section_name in section_names:
            self.section_filter_dropdown.addItem(section_name)
            
        # Set current section filter
        self.section_filter_dropdown.setCurrentText(
            current if current in ["All"] + section_names else "All"
        )
        self.section_filter_dropdown.blockSignals(False)