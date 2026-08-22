from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ...sections.sections import (
    handle_section_edit,
    move_section_down,
    move_section_up,
    update_sections_table,
)


class SectionsPanel:
    """Manages the sections panel for isolatable sections"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.sections_table = None
        
    def create_panel(self):
        """Create the sections panel with table and controls"""
        # Create sections panel
        sections_panel = QWidget()
        sections_layout = QVBoxLayout()
        sections_panel.setLayout(sections_layout)

        # Create sections table with 3 columns: Section Name, Line Size [mm], Color
        self.sections_table = QTableWidget()
        self.sections_table.setColumnCount(3)
        self.sections_table.setHorizontalHeaderLabels(
            ["Section Name", "Line Size [mm]", "Color"]
        )
        # Set selection behavior to select rows
        self.sections_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Set selection mode to single selection
        self.sections_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Set edit triggers to double click, selected click, and edit key pressed
        self.sections_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )

        # Set stretch last section to true
        header = self.sections_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)

        # Set vertical header to invisible
        vheader = self.sections_table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        # Connect item changed signal to handle section edit
        self.sections_table.itemChanged.connect(
            lambda item: handle_section_edit(self.main_window, item)
        )

        # Add sections table to layout
        sections_layout.addWidget(self.sections_table, 1)

        # Create buttons to move sections up/down
        move_layout = QHBoxLayout()
        up_button = QPushButton("Move Up")
        up_button.clicked.connect(lambda: move_section_up(self.main_window))
        move_layout.addWidget(up_button)
        down_button = QPushButton("Move Down")
        down_button.clicked.connect(lambda: move_section_down(self.main_window))
        move_layout.addWidget(down_button)
        sections_layout.addLayout(move_layout)
        
        # Add stretch to layout
        sections_layout.addStretch()

        # Initial update of sections table
        update_sections_table(self.main_window)

        # Return sections panel
        return sections_panel 