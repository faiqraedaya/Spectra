import json
import os
from typing import List

from PySide6.QtCore import Qt, QPoint
from config.settings import (
    APP_TITLE,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_X,
    DEFAULT_WINDOW_Y,
    DEFAULT_CONFIDENCE,
    DEFAULT_OVERLAP,
    FREQUENCY_CSV_PATH,
    ROBOFLOW_API_KEY_ENV,
    RESULTS_TABLE_COLUMNS,
    MAIN_SPLITTER_SIZES
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QAction

from detection.categories_map import (
    get_all_categories,
    get_all_frequency_categories,
    get_category,
)
from detection.roboflow import RoboflowAnalysisThread
from detection.types import Detection
from sections.sections import (
    Section,
    add_section,
    delete_section,
    handle_section_edit,
    import_sections_csv,
    move_section_down,
    move_section_up,
    update_section_filter_dropdown,
    update_sections_table,
)
from ui.pdf_viewer import PDFViewer
from utils.frequency import FrequencyTable, calculate_section_frequencies


class Spectra(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setGeometry(DEFAULT_WINDOW_X, DEFAULT_WINDOW_Y, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.version = "0.1.0"

        # Initialise variables
        if os.getenv(ROBOFLOW_API_KEY_ENV):
            self.api_key = os.getenv(ROBOFLOW_API_KEY_ENV)
        else:
            self.api_key = None
        self.current_pdf_path = None
        self.detections: List[Detection] = []
        self.undo_stack: List[List[Detection]] = []
        self.redo_stack: List[List[Detection]] = []
        self.confidence = DEFAULT_CONFIDENCE
        self.overlap = DEFAULT_OVERLAP

        # Initialize sections list as empty list of Section objects
        self.sections_list: List[Section] = []

        self.clipboard_detection = None  # For cut/copy/paste
        self.clipboard_cut = False

        self.init_ui()

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def closeEvent(self, event):
        """Clean up on application close"""
        # TODO: Add any cleanup code here
        event.accept()

    def init_ui(self):
        """Initialise the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout = central_widget.layout()
        if layout is None:
            layout = QVBoxLayout()
            central_widget.setLayout(layout)
        layout.addWidget(main_splitter)

        # Create menus
        self.create_menus()

        # Create isolatable sections sidebar widget (left)
        sections_widget = self.create_sections_panel()
        main_splitter.addWidget(sections_widget)

        # Create viewer widget (centre)
        viewer_widget = self.create_viewer_panel()
        main_splitter.addWidget(viewer_widget)

        # Create results widget (right) as a tab widget
        tab_widget = QTabWidget()
        objects_widget = self.create_objects_panel()
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
            self.update_results_table
        )
        results_filter_layout.addWidget(self.results_section_filter_dropdown)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(len(RESULTS_TABLE_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(RESULTS_TABLE_COLUMNS)
        results_layout.addLayout(results_filter_layout)
        results_layout.addWidget(self.results_table)
        self.export_results_button = QPushButton("Export to CSV")
        results_layout.addWidget(self.export_results_button)
        tab_widget.addTab(objects_widget, "Objects")
        tab_widget.addTab(results_widget, "Results")
        main_splitter.addWidget(tab_widget)

        # Initialise widget sizes
        main_splitter.setSizes(MAIN_SPLITTER_SIZES)

        self.update_navigation_controls()
        self.pdf_viewer.manual_box_drawn.connect(self.on_manual_box_drawn)
        self.pdf_viewer.bbox_changed.connect(self.on_bbox_changed)
        self.pdf_viewer.bbox_edit_finished.connect(self.on_bbox_edit_finished)

        # Store frequency table instance
        self.frequency_table = FrequencyTable(str(FREQUENCY_CSV_PATH))
        # Connect export button
        self.export_results_button.clicked.connect(self.export_results_to_csv)
        # Initial update
        self.update_results_table()

        self.update_results_section_filter_dropdown()

    def create_menus(self):
        """Create menu bar and menus"""
        menu_bar = self.menuBar()

        # File menu
        file_menu: QMenu = menu_bar.addMenu("File")

        new_action = QAction("New Project", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        open_project_action = QAction("Open Project", self)
        open_project_action.setShortcut("Ctrl+O")
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)

        save_project_action = QAction("Save Project", self)
        save_project_action.setShortcut("Ctrl+S")
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)

        file_menu.addSeparator()

        open_pdf_action = QAction("Open PDF", self)
        open_pdf_action.triggered.connect(self.open_pdf)
        file_menu.addAction(open_pdf_action)

        save_pdf_action = QAction("Save PDF", self)
        save_pdf_action.triggered.connect(self.save_pdf)
        file_menu.addAction(save_pdf_action)

        # Edit menu
        edit_menu: QMenu = menu_bar.addMenu("Edit")

        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        self.cut_action = QAction("Cut", self)
        self.cut_action.setShortcut("Ctrl+X")
        self.cut_action.triggered.connect(self.menu_cut)
        edit_menu.addAction(self.cut_action)

        self.copy_action = QAction("Copy", self)
        self.copy_action.setShortcut("Ctrl+C")
        self.copy_action.triggered.connect(self.menu_copy)
        edit_menu.addAction(self.copy_action)

        self.paste_action = QAction("Paste", self)
        self.paste_action.setShortcut("Ctrl+V")
        self.paste_action.triggered.connect(self.menu_paste)
        edit_menu.addAction(self.paste_action)

        edit_menu.addSeparator()

        add_object_action = QAction("Add Object", self)
        add_object_action.setShortcut("Ctrl+Space")
        add_object_action.triggered.connect(self.enter_add_object_mode)
        edit_menu.addAction(add_object_action)

        # Analysis menu
        analysis_menu: QMenu = menu_bar.addMenu("Analysis")

        run_analysis_action = QAction("Run Analysis", self)
        run_analysis_action.setShortcut("Ctrl+Enter")
        run_analysis_action.triggered.connect(self.run_analysis)
        analysis_menu.addAction(run_analysis_action)

        analysis_menu.addSeparator()

        set_conf_action = QAction("Set Confidence", self)
        set_conf_action.triggered.connect(self.set_confidence)
        analysis_menu.addAction(set_conf_action)

        set_overlap_action = QAction("Set Overlap", self)
        set_overlap_action.triggered.connect(self.set_overlap)
        analysis_menu.addAction(set_overlap_action)

        # API menu
        api_menu_obj: QMenu = menu_bar.addMenu("API")

        set_api_action = QAction("Set API Key", self)
        set_api_action.triggered.connect(self.set_api_key)
        api_menu_obj.addAction(set_api_action)

        # About menu
        about_menu_obj: QMenu = menu_bar.addMenu("About")

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        about_menu_obj.addAction(about_action)

        changelog_action = QAction("Changelog", self)
        changelog_action.triggered.connect(self.show_changelog)
        about_menu_obj.addAction(changelog_action)

        help_action = QAction("Help", self)
        help_action.triggered.connect(self.show_help)
        about_menu_obj.addAction(help_action)

        self.setMenuBar(menu_bar)

    def create_viewer_panel(self):
        viewer_panel = QGroupBox("Viewer")
        viewer_layout = QVBoxLayout()
        viewer_panel.setLayout(viewer_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.zoom_changed.connect(self.update_zoom_label)
        self.pdf_viewer.bbox_right_clicked.connect(self.on_bbox_right_clicked)
        self.pdf_viewer.background_right_clicked.connect(
            self.on_background_right_clicked
        )
        self.pdf_viewer.bbox_edit_finished.connect(self.on_bbox_edit_finished)
        scroll_area.setWidget(self.pdf_viewer)
        viewer_layout.addWidget(scroll_area)

        # Navigation bar at the bottom
        nav_bar = QHBoxLayout()
        # Left: Page controls
        nav_left = QHBoxLayout()
        self.first_page_button = QPushButton("◀◀ First")
        self.first_page_button.clicked.connect(self.first_page)
        nav_left.addWidget(self.first_page_button)
        self.prev_page_button = QPushButton("◀ Prev")
        self.prev_page_button.clicked.connect(self.prev_page)
        nav_left.addWidget(self.prev_page_button)

        page_label = QLabel("Page:")
        nav_left.addWidget(page_label)
        self.page_input = QLineEdit("0/0")
        self.page_input.setFixedWidth(80)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.on_page_input_changed)
        nav_left.addWidget(self.page_input)

        self.next_page_button = QPushButton("Next ▶")
        self.next_page_button.clicked.connect(self.next_page)
        nav_left.addWidget(self.next_page_button)
        self.last_page_button = QPushButton("Last ▶▶")
        self.last_page_button.clicked.connect(self.last_page)
        nav_left.addWidget(self.last_page_button)
        nav_left.addStretch()
        nav_bar.addLayout(nav_left, 1)
        # Right: Zoom controls
        nav_right = QHBoxLayout()
        nav_right.addStretch()
        self.zoom_out_button = QPushButton("Zoom -")
        self.zoom_out_button.clicked.connect(self.zoom_out)
        nav_right.addWidget(self.zoom_out_button)
        self.zoom_label = QLabel("100%")
        nav_right.addWidget(self.zoom_label)
        self.zoom_in_button = QPushButton("Zoom +")
        self.zoom_in_button.clicked.connect(self.zoom_in)
        nav_right.addWidget(self.zoom_in_button)
        self.reset_zoom_button = QPushButton("Reset Zoom")
        self.reset_zoom_button.clicked.connect(self.reset_zoom)
        nav_right.addWidget(self.reset_zoom_button)
        self.fit_to_window_button = QPushButton("Fit to Window")
        self.fit_to_window_button.clicked.connect(self.fit_to_window)
        nav_right.addWidget(self.fit_to_window_button)
        nav_bar.addLayout(nav_right, 1)

        viewer_layout.addLayout(nav_bar)

        return viewer_panel

    def create_objects_panel(self):
        """Create objects pane"""
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
            self.apply_section_filter
        )
        filter_layout.addWidget(self.section_filter_dropdown)

        # Category filter
        category_filter_label = QLabel("Filter by Category:")
        filter_layout.addWidget(category_filter_label)
        self.category_filter_dropdown = QComboBox()
        from detection.categories_map import get_all_frequency_categories

        self.category_filter_dropdown.addItem("All")
        for cat in get_all_frequency_categories():
            self.category_filter_dropdown.addItem(cat)
        self.category_filter_dropdown.currentIndexChanged.connect(
            self.apply_section_filter
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

    def create_sections_panel(self):
        sections_panel = QGroupBox("Sections")
        sections_layout = QVBoxLayout()
        sections_panel.setLayout(sections_layout)

        self.sections_table = QTableWidget()
        self.sections_table.setColumnCount(2)
        self.sections_table.setHorizontalHeaderLabels(
            ["Section Name", "Line Size [mm]"]
        )
        self.sections_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.sections_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sections_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )

        header = self.sections_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)

        vheader = self.sections_table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        self.sections_table.itemChanged.connect(
            lambda item: handle_section_edit(self, item)
        )

        sections_layout.addWidget(self.sections_table, 1)

        # Buttons to add/delete sections
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add")
        add_button.clicked.connect(lambda: add_section(self))
        button_layout.addWidget(add_button)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda: delete_section(self))
        button_layout.addWidget(delete_button)
        sections_layout.addLayout(button_layout)

        # Buttons to move sections up/down
        move_layout = QHBoxLayout()
        up_button = QPushButton("Move Up")
        up_button.clicked.connect(lambda: move_section_up(self))
        move_layout.addWidget(up_button)
        down_button = QPushButton("Move Down")
        down_button.clicked.connect(lambda: move_section_down(self))
        move_layout.addWidget(down_button)
        sections_layout.addLayout(move_layout)

        # Import CSV button
        import_button = QPushButton("Import CSV")
        import_button.clicked.connect(lambda: import_sections_csv(self))
        sections_layout.addWidget(import_button)

        sections_layout.addStretch()

        update_sections_table(self)

        return sections_panel

    def apply_section_filter(self):
        self.update_objects_table()
        self.pdf_viewer.set_detections(self.get_filtered_detections())

    def get_filtered_detections(self):
        if not hasattr(self, "section_filter_dropdown") or not hasattr(
            self, "category_filter_dropdown"
        ):
            return self.detections
        section = self.section_filter_dropdown.currentText()
        category = self.category_filter_dropdown.currentText()
        filtered = self.detections
        if section != "All":
            filtered = [
                d for d in filtered if getattr(d, "section", "Unassigned") == section
            ]
        if category != "All":
            filtered = [d for d in filtered if getattr(d, "name", None) == category]
        return filtered

    def new_project(self):
        """Creates a new project, resets all ongoing progress"""
        # Check if there is anything to clear
        has_pdf = self.current_pdf_path is not None
        has_detections = bool(self.detections)
        has_sections = bool(self.sections_list)
        if has_pdf or has_detections or has_sections:
            msg = []
            if has_pdf:
                msg.append("a PDF is loaded")
            if has_detections:
                msg.append("detections exist")
            if has_sections:
                msg.append("sections exist")
            msg_str = ", ".join(msg)
            reply = QMessageBox.question(
                self,
                "New Project",
                f"This will clear the current project because {msg_str}.\nAre you sure you want to start a new project?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # Reset everything
        self.current_pdf_path = None
        self.detections.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.sections_list.clear()
        self.update_sections_table()
        self.update_section_filter_dropdown()
        self.pdf_viewer.cleanup()
        self.pdf_viewer.setText("No PDF loaded")
        self.pdf_viewer.pdf_document = None
        self.pdf_viewer.current_page = 0
        self.pdf_viewer.total_pages = 0
        self.pdf_viewer.original_pixmap = None
        self.pdf_viewer.scaled_pixmap = None
        self.pdf_viewer.detections = []
        self.update_objects_table()

    def open_project(self):
        """Open a project file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "Spectra Project Files (*.spectra.json);;JSON Files (*.json)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Clear current state
            self.current_pdf_path = data.get("current_pdf_path", None)
            self.sections_list = [
                Section.from_dict(s) for s in data.get("sections", [])
            ]
            self.detections = [
                Detection.from_dict(d) for d in data.get("detections", [])
            ]
            self.confidence = data.get("confidence", 0.5)
            self.overlap = data.get("overlap", 0.3)
            self.api_key = data.get("api_key", None)
            # Update UI
            self.update_sections_table()
            self.update_section_filter_dropdown()
            self.update_objects_table()
            if self.current_pdf_path:
                self.pdf_viewer.load_pdf(self.current_pdf_path)
                self.update_navigation_controls()
            else:
                self.pdf_viewer.cleanup()
                self.pdf_viewer.setText("No PDF loaded")
            self.pdf_viewer.set_detections(self.detections)
            QMessageBox.information(
                self, "Open Project", "Project loaded successfully."
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Open Error", f"Failed to open project: {str(e)}"
            )

    def save_project(self):
        """Save the current project"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            "",
            "Spectra Project Files (*.spectra.json);;JSON Files (*.json)",
        )
        if not file_path:
            return
        data = {
            "current_pdf_path": self.current_pdf_path,
            "sections": [section.to_dict() for section in self.sections_list],
            "detections": [detection.to_dict() for detection in self.detections],
            "confidence": self.confidence,
            "overlap": self.overlap,
            "api_key": self.api_key,
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Save Project", "Project saved successfully.")
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error", f"Failed to save project: {str(e)}"
            )

    def open_pdf(self):
        """Open a PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load PDF", "", "PDF Files (*.pdf)"
        )

        if file_path:
            if self.pdf_viewer.load_pdf(file_path):
                self.current_pdf_path = file_path
                self.update_navigation_controls()
                self.detections.clear()
                self.update_objects_table()

    def update_navigation_controls(self):
        """Update UI states"""
        # Get variables
        has_pdf = self.pdf_viewer.pdf_document is not None
        current_page = self.pdf_viewer.current_page
        total_pages = self.pdf_viewer.total_pages

        # Reset UI states
        self.prev_page_button.setEnabled(has_pdf and current_page > 0)
        self.next_page_button.setEnabled(has_pdf and current_page < total_pages - 1)
        self.zoom_in_button.setEnabled(has_pdf)
        self.zoom_out_button.setEnabled(has_pdf)
        self.reset_zoom_button.setEnabled(has_pdf)
        self.fit_to_window_button.setEnabled(has_pdf)
        if has_pdf:
            self.page_input.setText(f"{current_page + 1}/{total_pages}")
        else:
            self.page_input.setText("0/0")

    def save_pdf(self):
        """Saves the current PDF with annotations"""
        # TODO: Implement PDF saving with annotations
        QMessageBox.information(
            self, "Save PDF", "PDF saving with annotations is not yet implemented."
        )

    def first_page(self):
        """Go to first page of PDF"""
        if self.pdf_viewer and self.pdf_viewer.pdf_document:
            self.pdf_viewer.set_page(0)
            self.update_navigation_controls()

    def prev_page(self):
        """Go to previous page"""
        if self.pdf_viewer and self.pdf_viewer.pdf_document:
            self.pdf_viewer.set_page(self.pdf_viewer.current_page - 1)
            self.update_navigation_controls()

    def next_page(self):
        """Go to next page"""
        if self.pdf_viewer and self.pdf_viewer.pdf_document:
            self.pdf_viewer.set_page(self.pdf_viewer.current_page + 1)
            self.update_navigation_controls()

    def last_page(self):
        """Go to last page"""
        if self.pdf_viewer and self.pdf_viewer.pdf_document:
            self.pdf_viewer.set_page(self.pdf_viewer.total_pages - 1)
            self.update_navigation_controls()

    def zoom_out(self):
        """Zoom out"""
        if self.pdf_viewer:
            self.pdf_viewer.zoom_out()

    def zoom_in(self):
        """Zoom in"""
        if self.pdf_viewer:
            self.pdf_viewer.zoom_in()

    def reset_zoom(self):
        """Reset zoom to 100%"""
        if self.pdf_viewer:
            self.pdf_viewer.reset_zoom()

    def fit_to_window(self):
        """Fit PDF to window size"""
        if self.pdf_viewer:
            self.pdf_viewer.fit_to_window()

    def enter_add_object_mode(self):
        """Enter add object mode for manual bounding box drawing"""
        if self.pdf_viewer:
            self.pdf_viewer.set_add_object_mode(True)

    def exit_add_object_mode(self):
        """Exit add object mode for manual bounding box drawing"""
        if self.pdf_viewer:
            self.pdf_viewer.set_add_object_mode(False)

    def undo(self):
        """Undo the last annotation change"""
        if not self.undo_stack:
            return
        self.redo_stack.append(self.detections.copy())
        self.detections = self.undo_stack.pop()
        self.pdf_viewer.set_detections(self.detections)
        self.update_objects_table()

    def redo(self):
        """Redo the last undone annotation change"""
        if not self.redo_stack:
            return
        self.undo_stack.append(self.detections.copy())
        self.detections = self.redo_stack.pop()
        self.pdf_viewer.set_detections(self.detections)
        self.update_objects_table()

    def menu_cut(self):
        idx = self.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.cut_detection(idx)
        self.update_edit_menu_actions()

    def menu_copy(self):
        idx = self.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.copy_detection(idx)
        self.update_edit_menu_actions()

    def menu_paste(self):
        # Paste at the same position as the selected bbox, or center if none
        idx = self.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.paste_detection(idx)
        else:
            # Paste at center of viewer
            w = self.pdf_viewer.width() // 2
            h = self.pdf_viewer.height() // 2
            self.paste_detection(None, QPoint(w, h))
        self.update_edit_menu_actions()

    def update_edit_menu_actions(self):
        # Enable/disable cut/copy based on selection, paste based on clipboard
        selected = self.pdf_viewer.selected_bbox_index is not None
        self.cut_action.setEnabled(selected)
        self.copy_action.setEnabled(selected)
        self.paste_action.setEnabled(self.clipboard_detection is not None)

    def run_analysis(self):
        """Analyze all pages of the PDF"""
        
        # Get all page images
        image_paths = self.pdf_viewer.get_page_image_paths()
        if not image_paths:
            QMessageBox.warning(self, "Warning", "No pages to analyze")
            return

        # Setup UI for analysis
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(image_paths))
        self.progress_bar.setValue(0)

        # Start analysis thread (Roboflow)
        self.analysis_thread = RoboflowAnalysisThread(
            self.api_key, image_paths, self.confidence, self.overlap
        )

        self.analysis_thread.analysis_complete.connect(self.on_analysis_complete)
        self.analysis_thread.error_occurred.connect(self.on_analysis_error)
        self.analysis_thread.progress_updated.connect(self.on_progress_updated)
        self.analysis_thread.start()

    def on_progress_updated(self, current: int, total: int):
        """Handle progress update"""
        self.progress_bar.setValue(current)

    def on_analysis_complete(self, detections: List[Detection]):
        """Handle analysis completion"""
        # Preserve manual detections
        manual_detections = [
            d for d in self.detections if getattr(d, "source", "model") == "manual"
        ]

        # Map model detections to categories
        for d in detections:
            d.name = get_category(d.name)
        self.detections = manual_detections + detections
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.pdf_viewer.set_detections(self.detections)
        self.update_objects_table()

        # Update UI
        self.progress_bar.setVisible(False)
        QMessageBox.information(
            self,
            "Analysis Complete",
            f"Found {len(detections)} objects across {self.pdf_viewer.total_pages} pages",
        )

    def update_objects_table(self):
        """Update the results table"""
        filtered = self.get_filtered_detections()
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
                for section in self.sections_list:
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
        self.update_section_filter_dropdown()

    def update_section_filter_dropdown(self):
        current = (
            self.section_filter_dropdown.currentText()
            if hasattr(self, "section_filter_dropdown")
            else "All"
        )
        self.section_filter_dropdown.blockSignals(True)
        self.section_filter_dropdown.clear()
        self.section_filter_dropdown.addItem("All")
        # Add section names, not Section objects
        section_names = [section.name for section in self.sections_list]
        for section_name in section_names:
            self.section_filter_dropdown.addItem(section_name)
        self.section_filter_dropdown.setCurrentText(
            current if current in ["All"] + section_names else "All"
        )
        self.section_filter_dropdown.blockSignals(False)
        # Also update results section filter dropdown
        self.update_results_section_filter_dropdown()

    def update_results_section_filter_dropdown(self):
        if not hasattr(self, "results_section_filter_dropdown"):
            return
        current = self.results_section_filter_dropdown.currentText()
        self.results_section_filter_dropdown.blockSignals(True)
        self.results_section_filter_dropdown.clear()
        self.results_section_filter_dropdown.addItem("All")
        section_names = [section.name for section in self.sections_list]
        for section_name in section_names:
            self.results_section_filter_dropdown.addItem(section_name)
        self.results_section_filter_dropdown.setCurrentText(
            current if current in ["All"] + section_names else "All"
        )
        self.results_section_filter_dropdown.blockSignals(False)

    def on_analysis_error(self, error_message: str):
        """Handle analysis error"""
        QMessageBox.critical(
            self, "Analysis Error", f"Error during analysis:\n{error_message}"
        )
        self.progress_bar.setVisible(False)

    def set_confidence(self):
        value, ok = QInputDialog.getDouble(
            self,
            "Set Confidence",
            "Confidence (0.0 - 1.0):",
            self.confidence,
            0.0,
            1.0,
            2,
        )
        if ok:
            self.confidence = value

    def set_overlap(self):
        value, ok = QInputDialog.getDouble(
            self, "Set Overlap", "Overlap (0.0 - 1.0):", self.overlap, 0.0, 1.0, 2
        )
        if ok:
            self.overlap = value

    def set_api_key(self):
        """Set the Roboflow API key"""
        api_key, ok = QInputDialog.getText(
            self, "Set API Key", "Enter your Roboflow API key:", text=self.api_key or ""
        )
        if ok:
            self.api_key = api_key

    def show_about(self):
        QMessageBox.information(
            self,
            "About",
            "Spectra\n"
            "Object Detection and Isolatable-section Navigator\n"
            f"Version {self.version}\n"
            "© Faiq Raedaya 2025",
        )

    def show_help(self):
        QMessageBox.information(
            self,
            "Help",
            "Usage:\n"
            "1. Open a PDF with Ctrl+O or File>Open.\n"
            "2. Select a Detection Method (Recommended to use Roboflow API).\n"
            "3. Click Analyse to start object detection.\n"
            "4. Add Sections from the left tab manually or Import from CSV.\n"
            "5. Right-click bounding boxes to edit and delete detections.\n"
            "6. Add objects manually using Ctrl+Space or Edit>Add Object.\n"
            "7. Export CSV and JSON once all objects are assigned to a Section.\n\n"
            "Controls:\n"
            "- Middle Mouse Button: Pan around\n"
            "- Ctrl+Scroll: Zoom in/out (centered on mouse cursor)\n"
            "- Shift+Scroll: Pan left/right horizontally\n"
            "- Scroll: Pan up/down vertically",
        )

    def show_changelog(self):
        """Show the changelog"""
        QMessageBox.information(
            self,
            "Changelog",
            "Version 0.1.0:\n"
            "- Initial release\n"
            "- PDF viewing and navigation\n"
            "- Object detection with Roboflow API\n"
            "- Manual object annotation\n"
            "- Section management\n"
            "- Export functionality",
        )

    def update_zoom_label(self, zoom_factor: float):
        """Update the zoom label with current zoom percentage"""
        self.zoom_label.setText(f"{int(zoom_factor * 100)}%")

    def on_bbox_right_clicked(self, bbox_index: int):
        """Handle right-click on bounding box"""
        menu = QMenu(self)
        cut_action = QAction("Cut", self)
        copy_action = QAction("Copy", self)
        paste_action = QAction("Paste", self)
        edit_action = QAction("Edit Object", self)
        delete_action = QAction("Delete Object", self)
        menu.addAction(cut_action)
        menu.addAction(copy_action)
        menu.addAction(paste_action)
        menu.addSeparator()
        menu.addAction(edit_action)
        menu.addAction(delete_action)
        # Enable/disable paste
        paste_action.setEnabled(self.clipboard_detection is not None)
        # Connect actions
        cut_action.triggered.connect(lambda: self.cut_detection(bbox_index))
        copy_action.triggered.connect(lambda: self.copy_detection(bbox_index))
        paste_action.triggered.connect(lambda: self.paste_detection(bbox_index))
        edit_action.triggered.connect(lambda: self.edit_detection(bbox_index))
        delete_action.triggered.connect(lambda: self.delete_detection(bbox_index))
        menu.exec(self.cursor().pos())

    def on_background_right_clicked(self, pos):
        menu = QMenu(self)
        paste_action = QAction("Paste", self)
        menu.addAction(paste_action)
        paste_action.setEnabled(self.clipboard_detection is not None)
        paste_action.triggered.connect(lambda: self.paste_detection(None, pos))
        menu.exec(self.cursor().pos())

    def cut_detection(self, idx):
        if idx is not None and 0 <= idx < len(self.detections):
            self.clipboard_detection = self.detections[idx]
            self.clipboard_cut = True
            self.detections.pop(idx)
            self.update_objects_table()
            self.pdf_viewer.set_detections(self.get_filtered_detections())

    def copy_detection(self, idx):
        if idx is not None and 0 <= idx < len(self.detections):
            import copy

            self.clipboard_detection = copy.deepcopy(self.detections[idx])
            self.clipboard_cut = False

    def paste_detection(self, idx=None, pos=None):
        if self.clipboard_detection is not None:
            import copy

            new_det = copy.deepcopy(self.clipboard_detection)
            if pos is not None:
                # Convert widget pos to image coords
                img_x, img_y = self.pdf_viewer.widget_to_image_coords(pos.x(), pos.y())
                w = new_det.bbox[2] - new_det.bbox[0]
                h = new_det.bbox[3] - new_det.bbox[1]
                new_det.bbox = (int(img_x), int(img_y), int(img_x + w), int(img_y + h))
                new_det.page_num = self.pdf_viewer.current_page + 1
            self.detections.append(new_det)
            self.update_objects_table()
            self.pdf_viewer.set_detections(self.get_filtered_detections())
            if self.clipboard_cut:
                self.clipboard_detection = None
                self.clipboard_cut = False
            self.update_results_table()

    def edit_detection(self, idx):
        if idx is not None and 0 <= idx < len(self.detections):
            detection = self.detections[idx]
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Object")
            layout = QVBoxLayout()
            dialog.setLayout(layout)
            class_label = QLabel("Object Category:")
            layout.addWidget(class_label)
            class_combo = QComboBox()
            class_combo.addItems(get_all_frequency_categories())
            class_combo.setEditable(True)
            class_combo.setCurrentText(detection.name)
            layout.addWidget(class_combo)
            section_label = QLabel("Section:")
            layout.addWidget(section_label)
            section_combo = QComboBox()
            section_names = [section.name for section in self.sections_list]
            section_combo.addItems(section_names)
            section_combo.setEditable(True)
            section_combo.setCurrentText(getattr(detection, "section", "Unassigned"))
            layout.addWidget(section_combo)
            line_size_label = QLabel("Line Size [mm]:")
            layout.addWidget(line_size_label)
            line_size_edit = QLineEdit()
            line_size_edit.setText(str(getattr(detection, "line_size", "")))
            layout.addWidget(line_size_edit)
            count_label = QLabel("Count (number of objects in box):")
            layout.addWidget(count_label)
            count_edit = QLineEdit()
            count_edit.setText(str(getattr(detection, "count", 1)))
            layout.addWidget(count_edit)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            layout.addWidget(buttons)
            ok_button = buttons.button(QDialogButtonBox.Ok)

            def update_line_size_edit():
                section_name = section_combo.currentText().strip()
                section = next(
                    (s for s in self.sections_list if s.name == section_name), None
                )
                if section and section.line_size is not None:
                    line_size_edit.setText(f"{section.line_size:.2f}")
                    ok_button.setEnabled(True)
                else:
                    ok_button.setEnabled(True)

            def validate_line_size():
                section_name = section_combo.currentText().strip()
                section = next(
                    (s for s in self.sections_list if s.name == section_name), None
                )
                if section and section.line_size is not None:
                    ok_button.setEnabled(True)
                    return
                text = line_size_edit.text().strip()
                try:
                    float(text)
                    ok_button.setEnabled(True)
                except ValueError:
                    ok_button.setEnabled(False)

            section_combo.currentTextChanged.connect(update_line_size_edit)
            line_size_edit.textChanged.connect(validate_line_size)
            update_line_size_edit()
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            if dialog.exec() == QDialog.Accepted:
                detection.name = class_combo.currentText().strip() or "Manual"
                detection.section = section_combo.currentText().strip() or "Unassigned"
                line_size_text = line_size_edit.text().strip()
                line_size_value = None
                if line_size_text:
                    try:
                        line_size_value = float(line_size_text)
                    except ValueError:
                        QMessageBox.warning(
                            self,
                            "Invalid Input",
                            "Please enter a valid number for line size.",
                        )
                        return
                detection.line_size = line_size_value
                count_text = count_edit.text().strip()
                count_value = 1
                if count_text:
                    try:
                        count_value = int(count_text)
                    except ValueError:
                        QMessageBox.warning(
                            self,
                            "Invalid Input",
                            "Please enter a valid integer for count or leave blank.",
                        )
                        return
                detection.count = count_value
                # If section is new, add it
                if detection.section != "Unassigned" and detection.section not in [
                    section.name for section in self.sections_list
                ]:
                    new_section = Section(detection.section)
                    self.sections_list.append(new_section)
                    update_sections_table(self)
                    self.update_section_filter_dropdown()
                # If section has no line size, set it now
                if detection.section != "Unassigned":
                    section = next(
                        (s for s in self.sections_list if s.name == detection.section),
                        None,
                    )
                    if (
                        section
                        and section.line_size is None
                        and line_size_value is not None
                    ):
                        section.line_size = line_size_value
                        update_sections_table(self)
                self.update_objects_table()
                self.pdf_viewer.set_detections(self.get_filtered_detections())
                self.update_results_table()

    def delete_detection(self, idx):
        if idx is not None and 0 <= idx < len(self.detections):
            self.detections.pop(idx)
            self.update_objects_table()
            self.pdf_viewer.set_detections(self.get_filtered_detections())
            self.update_results_table()

    def on_manual_box_drawn(self, bbox):
        """Handle manual bounding box drawing"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Object")
        layout = QVBoxLayout()
        dialog.setLayout(layout)

        # Class dropdown
        class_label = QLabel("Object Category:")
        layout.addWidget(class_label)
        class_combo = QComboBox()
        class_combo.addItems(get_all_frequency_categories())
        class_combo.setEditable(True)
        layout.addWidget(class_combo)

        # Section
        section_label = QLabel("Section:")
        layout.addWidget(section_label)
        section_combo = QComboBox()
        section_names = [section.name for section in self.sections_list]
        section_combo.addItems(section_names)
        section_combo.setEditable(True)
        layout.addWidget(section_combo)

        # Line size override
        line_size_label = QLabel("Line Size [mm]:")
        layout.addWidget(line_size_label)
        line_size_edit = QLineEdit()
        layout.addWidget(line_size_edit)

        # Count
        count_label = QLabel("Count (number of objects in box):")
        layout.addWidget(count_label)
        count_edit = QLineEdit()
        count_edit.setText("1")
        layout.addWidget(count_edit)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        ok_button = buttons.button(QDialogButtonBox.Ok)

        def update_line_size_edit():
            section_name = section_combo.currentText().strip()
            section = next(
                (s for s in self.sections_list if s.name == section_name), None
            )
            if section and section.line_size is not None:
                line_size_edit.setText(f"{section.line_size:.2f}")
                ok_button.setEnabled(True)
            else:
                line_size_edit.clear()
                ok_button.setEnabled(False)

        def validate_line_size():
            section_name = section_combo.currentText().strip()
            section = next(
                (s for s in self.sections_list if s.name == section_name), None
            )
            if section and section.line_size is not None:
                ok_button.setEnabled(True)
                return
            text = line_size_edit.text().strip()
            try:
                float(text)
                ok_button.setEnabled(True)
            except ValueError:
                ok_button.setEnabled(False)

        section_combo.currentTextChanged.connect(update_line_size_edit)
        line_size_edit.textChanged.connect(validate_line_size)
        # Initial state
        update_line_size_edit()

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            class_name = class_combo.currentText().strip() or "Manual"
            section_name = section_combo.currentText().strip() or "Unassigned"
            line_size_text = line_size_edit.text().strip()
            line_size_value = None
            if line_size_text:
                try:
                    line_size_value = float(line_size_text)
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid Input",
                        "Please enter a valid number for line size.",
                    )
                    return
            count_text = count_edit.text().strip()
            count_value = 1
            if count_text:
                try:
                    count_value = int(count_text)
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid Input",
                        "Please enter a valid integer for count or leave blank.",
                    )
                    return
            # If section is new, add it
            if section_name != "Unassigned" and section_name not in [
                section.name for section in self.sections_list
            ]:
                new_section = Section(section_name)
                self.sections_list.append(new_section)
                update_sections_table(self)
                self.update_section_filter_dropdown()
            # If section has no line size, set it now
            if section_name != "Unassigned":
                section = next(
                    (s for s in self.sections_list if s.name == section_name), None
                )
                if (
                    section
                    and section.line_size is None
                    and line_size_value is not None
                ):
                    section.line_size = line_size_value
                    update_sections_table(self)
            self.undo_stack.append(self.detections.copy())
            self.redo_stack.clear()
            new_detection = Detection(
                name=class_name,
                confidence=1.0,  # Default, not user input
                bbox=bbox,
                page_num=self.pdf_viewer.current_page + 1,
                section=section_name,
                source="manual",
                line_size=line_size_value,
                count=count_value,
            )
            self.detections.append(new_detection)
            self.update_objects_table()
            self.pdf_viewer.set_detections(self.get_filtered_detections())
            self.update_results_table()

    def on_bbox_changed(self, idx, bbox):
        """Handle bounding box changes from drag/resize"""
        # Only update the detection, do not recalculate frequency yet
        if 0 <= idx < len(self.detections):
            self.detections[idx].bbox = bbox
        self.update_objects_table()

    def update_results_table(self):
        """Update the Results tab with frequency calculations for all sections."""
        section_filter = (
            self.results_section_filter_dropdown.currentText()
            if hasattr(self, "results_section_filter_dropdown")
            else "All"
        )
        results = calculate_section_frequencies(
            self.sections_list, self.detections, self.frequency_table
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

    def export_results_to_csv(self):
        """Export the results table to a CSV file."""
        import csv

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Results to CSV", "", "CSV Files (*.csv)"
        )
        if not file_path:
            return
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            headers = [
                "Section",
                "Tiny (1-3 mm)",
                "Small (3-10 mm)",
                "Medium (10-50 mm)",
                "Large (50-150 mm)",
                "FBR (>150 mm)",
                "Total",
            ]
            writer.writerow(headers)
            for row in range(self.results_table.rowCount()):
                writer.writerow(
                    [
                        (
                            self.results_table.item(row, col).text()
                            if self.results_table.item(row, col)
                            else ""
                        )
                        for col in range(self.results_table.columnCount())
                    ]
                )

    def on_page_input_changed(self):
        """Handle page input change"""
        if not self.pdf_viewer or not self.pdf_viewer.pdf_document:
            return
        page_text = self.page_input.text().strip()
        if not page_text:
            return
        try:
            # Handle different input formats: "5", "5/10", "page 5", etc.
            if "/" in page_text:
                # Format: "5/10" - extract just the page number
                page_number = int(page_text.split("/")[0])
            else:
                # Format: "5" or "page 5" - extract number
                import re

                numbers = re.findall(r"\d+", page_text)
                if numbers:
                    page_number = int(numbers[0])
                else:
                    return
            # Validate page number is within range (1-indexed for user, 0-indexed for internal)
            total_pages = self.pdf_viewer.total_pages
            if 1 <= page_number <= total_pages:
                self.pdf_viewer.set_page(page_number - 1)  # Convert to 0-indexed
                self.update_navigation_controls()
            else:
                # Invalid page number, restore current page display
                current_page = self.pdf_viewer.current_page
                self.page_input.setText(f"{current_page + 1}/{total_pages}")
        except (ValueError, IndexError):
            # Invalid input, restore current page display
            if self.pdf_viewer and self.pdf_viewer.pdf_document:
                current_page = self.pdf_viewer.current_page
                total_pages = self.pdf_viewer.total_pages
                self.page_input.setText(f"{current_page + 1}/{total_pages}")

    def on_bbox_edit_finished(self, idx):
        self.update_results_table()
