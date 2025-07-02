from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QPushButton, QAbstractItemView
)
from sections.sections import (
    add_section, delete_section, handle_section_edit,
    move_section_up, move_section_down, import_sections_csv,
    update_sections_table
)


class SectionsPanel:
    """Manages the sections panel for isolatable sections"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.sections_table = None
        
    def create_panel(self):
        """Create the sections panel with table and controls"""
        sections_panel = QGroupBox("Sections")
        sections_layout = QVBoxLayout()
        sections_panel.setLayout(sections_layout)

        # Create sections table
        self.sections_table = QTableWidget()
        self.sections_table.setColumnCount(2)
        self.sections_table.setHorizontalHeaderLabels(
            ["Section Name", "Line Size [mm]"]
        )
        self.sections_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sections_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sections_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )

        header = self.sections_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)

        vheader = self.sections_table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        self.sections_table.itemChanged.connect(
            lambda item: handle_section_edit(self.main_window, item)
        )

        sections_layout.addWidget(self.sections_table, 1)

        # Buttons to add/delete sections
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add")
        add_button.clicked.connect(lambda: add_section(self.main_window))
        button_layout.addWidget(add_button)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda: delete_section(self.main_window))
        button_layout.addWidget(delete_button)
        sections_layout.addLayout(button_layout)

        # Buttons to move sections up/down
        move_layout = QHBoxLayout()
        up_button = QPushButton("Move Up")
        up_button.clicked.connect(lambda: move_section_up(self.main_window))
        move_layout.addWidget(up_button)
        down_button = QPushButton("Move Down")
        down_button.clicked.connect(lambda: move_section_down(self.main_window))
        move_layout.addWidget(down_button)
        sections_layout.addLayout(move_layout)

        # Import CSV button
        import_button = QPushButton("Import CSV")
        import_button.clicked.connect(lambda: import_sections_csv(self.main_window))
        sections_layout.addWidget(import_button)

        sections_layout.addStretch()

        # Initial update
        update_sections_table(self.main_window)

        return sections_panel 