from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from sections.sections import (
    handle_section_edit,
    import_sections_csv,
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
        sections_panel = QWidget()
        sections_layout = QVBoxLayout()
        sections_panel.setLayout(sections_layout)

        # Create sections table
        self.sections_table = QTableWidget()
        self.sections_table.setColumnCount(3)
        self.sections_table.setHorizontalHeaderLabels(
            ["Section Name", "Line Size [mm]", "Color"]
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

        # Buttons to move sections up/down
        move_layout = QHBoxLayout()
        up_button = QPushButton("Move Up")
        up_button.clicked.connect(lambda: move_section_up(self.main_window))
        move_layout.addWidget(up_button)
        down_button = QPushButton("Move Down")
        down_button.clicked.connect(lambda: move_section_down(self.main_window))
        move_layout.addWidget(down_button)
        sections_layout.addLayout(move_layout)
        
        sections_layout.addStretch()

        # Initial update
        update_sections_table(self.main_window)

        return sections_panel 