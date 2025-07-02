from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QComboBox, QLabel, QPushButton, QTableWidgetItem
)
from utils.frequency import calculate_section_frequencies


class ResultsPanel:
    """Manages the results panel for frequency calculations"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.results_section_filter_dropdown = None
        self.results_table = None
        self.export_results_button = None
        
    def create_panel(self):
        """Create the results panel with filter and table"""
        results_widget = QWidget()
        results_layout = QVBoxLayout()
        results_widget.setLayout(results_layout)
        
        # Add section filter to results
        results_filter_layout = QHBoxLayout()
        results_filter_label = QLabel("Filter by Section:")
        results_filter_layout.addWidget(results_filter_label)
        
        self.results_section_filter_dropdown = QComboBox()
        self.results_section_filter_dropdown.addItem("All")
        self.results_section_filter_dropdown.currentIndexChanged.connect(
            self.main_window.update_results_table
        )
        results_filter_layout.addWidget(self.results_section_filter_dropdown)
        
        self.results_table = QTableWidget()
        from config.settings import RESULTS_TABLE_COLUMNS
        self.results_table.setColumnCount(len(RESULTS_TABLE_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(RESULTS_TABLE_COLUMNS)
        
        results_layout.addLayout(results_filter_layout)
        results_layout.addWidget(self.results_table)
        
        self.export_results_button = QPushButton("Export to CSV")
        self.export_results_button.clicked.connect(self.main_window.export_results_to_csv)
        results_layout.addWidget(self.export_results_button)

        return results_widget

    def update_results_table(self):
        """Update the Results tab with frequency calculations for all sections."""
        if not self.results_table:
            return
            
        section_filter = (
            self.results_section_filter_dropdown.currentText()
            if self.results_section_filter_dropdown
            else "All"
        )
        
        results = calculate_section_frequencies(
            self.main_window.sections_list, 
            self.main_window.detections, 
            self.main_window.frequency_table
        )
        
        # Filter results by section if needed
        if section_filter != "All":
            results = [row for row in results if str(row["section"]) == section_filter]
            
        self.results_table.setRowCount(len(results))
        
        for i, row in enumerate(results):
            self.results_table.setItem(i, 0, QTableWidgetItem(str(row["section"])))
            self.results_table.setItem(i, 1, QTableWidgetItem(f"{row['tiny']:.2e}"))
            self.results_table.setItem(i, 2, QTableWidgetItem(f"{row['small']:.2e}"))
            self.results_table.setItem(i, 3, QTableWidgetItem(f"{row['medium']:.2e}"))
            self.results_table.setItem(i, 4, QTableWidgetItem(f"{row['large']:.2e}"))
            self.results_table.setItem(i, 5, QTableWidgetItem(f"{row['fbr']:.2e}"))
            self.results_table.setItem(i, 6, QTableWidgetItem(f"{row['total']:.2e}"))
            
        self.results_table.resizeColumnsToContents()

    def update_results_section_filter_dropdown(self):
        """Update the results section filter dropdown"""
        if not self.results_section_filter_dropdown:
            return
            
        current = self.results_section_filter_dropdown.currentText()
        self.results_section_filter_dropdown.blockSignals(True)
        self.results_section_filter_dropdown.clear()
        self.results_section_filter_dropdown.addItem("All")
        
        section_names = [section.name for section in self.main_window.sections_list]
        for section_name in section_names:
            self.results_section_filter_dropdown.addItem(section_name)
            
        self.results_section_filter_dropdown.setCurrentText(
            current if current in ["All"] + section_names else "All"
        )
        self.results_section_filter_dropdown.blockSignals(False) 