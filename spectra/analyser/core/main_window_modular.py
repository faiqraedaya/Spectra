import os
import re
import csv
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QTabWidget
)
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
    MAIN_SPLITTER_SIZES
)
from detection.types import Detection
from sections.sections import Section
from utils.frequency import FrequencyTable

# Import modular components
from ui.menus import MenuManager
from ui.panels.viewer_panel import ViewerPanel
from ui.panels.sections_panel import SectionsPanel
from ui.panels.objects_panel import ObjectsPanel
from ui.panels.results_panel import ResultsPanel
from core.project_manager import ProjectManager
from core.detection_manager import DetectionManager
from core.analysis_manager import AnalysisManager


class SpectraModular(QMainWindow):
    """Modular main application window using separated components"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setGeometry(DEFAULT_WINDOW_X, DEFAULT_WINDOW_Y, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.version = "0.1.0"

        # Initialize variables
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
        self.sections_list: List[Section] = []

        # Initialize managers
        self.menu_manager = MenuManager(self)
        self.project_manager = ProjectManager(self)
        self.detection_manager = DetectionManager(self)
        self.analysis_manager = AnalysisManager(self)

        # Initialize panels
        self.viewer_panel = ViewerPanel(self)
        self.sections_panel = SectionsPanel(self)
        self.objects_panel = ObjectsPanel(self)
        self.results_panel = ResultsPanel(self)

        # Store frequency table instance
        self.frequency_table = FrequencyTable(str(FREQUENCY_CSV_PATH))

        self.init_ui()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def closeEvent(self, event):
        """Clean up on application close"""
        # TODO: Add any cleanup code here
        event.accept()

    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout = central_widget.layout()
        if layout is None:
            layout = QVBoxLayout()
            central_widget.setLayout(layout)
        layout.addWidget(main_splitter)

        # Create menus
        self.menu_manager.create_menus()

        # Create panels
        sections_widget = self.sections_panel.create_panel()
        main_splitter.addWidget(sections_widget)

        viewer_widget = self.viewer_panel.create_panel()
        main_splitter.addWidget(viewer_widget)

        # Create results widget as a tab widget
        tab_widget = QTabWidget()
        objects_widget = self.objects_panel.create_panel()
        results_widget = self.results_panel.create_panel()
        tab_widget.addTab(objects_widget, "Objects")
        tab_widget.addTab(results_widget, "Results")
        main_splitter.addWidget(tab_widget)

        # Initialize widget sizes
        main_splitter.setSizes(MAIN_SPLITTER_SIZES)

        # Connect signals
        self._connect_signals()

        # Initial updates
        self.update_navigation_controls()
        self.update_results_table()

    def _connect_signals(self):
        """Connect all signal handlers"""
        # PDF viewer signals
        self.viewer_panel.pdf_viewer.manual_box_drawn.connect(self.detection_manager.add_manual_detection)
        self.viewer_panel.pdf_viewer.bbox_changed.connect(self.detection_manager.on_bbox_changed)
        self.viewer_panel.pdf_viewer.bbox_edit_finished.connect(self.update_results_table)
        self.viewer_panel.pdf_viewer.bbox_right_clicked.connect(self.detection_manager.on_bbox_right_clicked)
        self.viewer_panel.pdf_viewer.background_right_clicked.connect(self.detection_manager.on_background_right_clicked)

        # Zoom label update
        self.viewer_panel.pdf_viewer.zoom_changed.connect(self.viewer_panel.update_zoom_label)

    # Navigation methods (delegated to viewer panel)
    def first_page(self):
        if self.viewer_panel.pdf_viewer and self.viewer_panel.pdf_viewer.pdf_document:
            self.viewer_panel.pdf_viewer.set_page(0)
            self.update_navigation_controls()

    def prev_page(self):
        if self.viewer_panel.pdf_viewer and self.viewer_panel.pdf_viewer.pdf_document:
            self.viewer_panel.pdf_viewer.set_page(self.viewer_panel.pdf_viewer.current_page - 1)
            self.update_navigation_controls()

    def next_page(self):
        if self.viewer_panel.pdf_viewer and self.viewer_panel.pdf_viewer.pdf_document:
            self.viewer_panel.pdf_viewer.set_page(self.viewer_panel.pdf_viewer.current_page + 1)
            self.update_navigation_controls()

    def last_page(self):
        if self.viewer_panel.pdf_viewer and self.viewer_panel.pdf_viewer.pdf_document:
            self.viewer_panel.pdf_viewer.set_page(self.viewer_panel.pdf_viewer.total_pages - 1)
            self.update_navigation_controls()

    def zoom_out(self):
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.zoom_out()

    def zoom_in(self):
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.zoom_in()

    def reset_zoom(self):
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.reset_zoom()

    def fit_to_window(self):
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.fit_to_window()

    def enter_add_object_mode(self):
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.set_add_object_mode(True)

    def exit_add_object_mode(self):
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.set_add_object_mode(False)

    # Project management methods (delegated to project manager)
    def new_project(self):
        self.project_manager.new_project()

    def open_project(self):
        self.project_manager.open_project()

    def save_project(self):
        self.project_manager.save_project()

    def open_pdf(self):
        self.project_manager.open_pdf()

    def save_pdf(self):
        self.project_manager.save_pdf()

    # Detection management methods (delegated to detection manager)
    def undo(self):
        self.detection_manager.undo()

    def redo(self):
        self.detection_manager.redo()

    def menu_cut(self):
        idx = self.viewer_panel.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.detection_manager.cut_detection(idx)
        self.menu_manager.update_edit_menu_actions()

    def menu_copy(self):
        idx = self.viewer_panel.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.detection_manager.copy_detection(idx)
        self.menu_manager.update_edit_menu_actions()

    def menu_paste(self):
        idx = self.viewer_panel.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.detection_manager.paste_detection(idx)
        else:
            # Paste at center of viewer
            from PySide6.QtCore import QPoint
            w = self.viewer_panel.pdf_viewer.width() // 2
            h = self.viewer_panel.pdf_viewer.height() // 2
            self.detection_manager.paste_detection(None, QPoint(w, h))
        self.menu_manager.update_edit_menu_actions()

    def get_filtered_detections(self):
        return self.detection_manager.get_filtered_detections()

    def apply_section_filter(self):
        self.objects_panel.update_objects_table()
        self.viewer_panel.pdf_viewer.set_detections(self.get_filtered_detections())

    # Analysis methods (delegated to analysis manager)
    def run_analysis(self):
        self.analysis_manager.run_analysis()

    def set_confidence(self):
        self.analysis_manager.set_confidence()

    def set_overlap(self):
        self.analysis_manager.set_overlap()

    def set_api_key(self):
        self.analysis_manager.set_api_key()

    # UI update methods
    def update_navigation_controls(self):
        self.viewer_panel.update_navigation_controls()

    def update_objects_table(self):
        self.objects_panel.update_objects_table()

    def update_sections_table(self):
        from sections.sections import update_sections_table
        update_sections_table(self)

    def update_section_filter_dropdown(self):
        self.objects_panel.update_section_filter_dropdown()
        self.results_panel.update_results_section_filter_dropdown()

    def update_results_table(self):
        self.results_panel.update_results_table()

    def update_zoom_label(self, zoom_factor: float):
        self.viewer_panel.update_zoom_label(zoom_factor)

    def on_page_input_changed(self):
        """Handle page input change"""
        if not self.viewer_panel.pdf_viewer or not self.viewer_panel.pdf_viewer.pdf_document:
            return
        page_text = self.viewer_panel.page_input.text().strip()
        if not page_text:
            return
        try:
            # Handle different input formats: "5", "5/10", "page 5", etc.
            if "/" in page_text:
                # Format: "5/10" - extract just the page number
                page_number = int(page_text.split("/")[0])
            else:
                # Format: "5" or "page 5" - extract number
                numbers = re.findall(r"\d+", page_text)
                if numbers:
                    page_number = int(numbers[0])
                else:
                    return
            # Validate page number is within range (1-indexed for user, 0-indexed for internal)
            total_pages = self.viewer_panel.pdf_viewer.total_pages
            if 1 <= page_number <= total_pages:
                self.viewer_panel.pdf_viewer.set_page(page_number - 1)  # Convert to 0-indexed
                self.update_navigation_controls()
            else:
                # Invalid page number, restore current page display
                current_page = self.viewer_panel.pdf_viewer.current_page
                self.viewer_panel.page_input.setText(f"{current_page + 1}/{total_pages}")
        except (ValueError, IndexError):
            # Invalid input, restore current page display
            if self.viewer_panel.pdf_viewer and self.viewer_panel.pdf_viewer.pdf_document:
                current_page = self.viewer_panel.pdf_viewer.current_page
                total_pages = self.viewer_panel.pdf_viewer.total_pages
                self.viewer_panel.page_input.setText(f"{current_page + 1}/{total_pages}")

    def on_bbox_edit_finished(self, idx):
        self.update_results_table()

    # About/Help methods
    def show_about(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "About",
            "Spectra\n"
            "Object Detection and Isolatable-section Navigator\n"
            f"Version {self.version}\n"
            "© Faiq Raedaya 2025",
        )

    def show_help(self):
        from PySide6.QtWidgets import QMessageBox
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
        from PySide6.QtWidgets import QMessageBox
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

    def export_results_to_csv(self):
        """Export the results table to a CSV file."""
        from PySide6.QtWidgets import QFileDialog
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
            for row in range(self.results_panel.results_table.rowCount()):
                writer.writerow(
                    [
                        (
                            self.results_panel.results_table.item(row, col).text()
                            if self.results_panel.results_table.item(row, col)
                            else ""
                        )
                        for col in range(self.results_panel.results_table.columnCount())
                    ]
                )

    # Property accessors for managers
    @property
    def pdf_viewer(self):
        return self.viewer_panel.pdf_viewer

    @property
    def progress_bar(self):
        return self.objects_panel.progress_bar

    @property
    def section_filter_dropdown(self):
        return self.objects_panel.section_filter_dropdown

    @property
    def category_filter_dropdown(self):
        return self.objects_panel.category_filter_dropdown

    @property
    def clipboard_detection(self):
        return self.detection_manager.clipboard_detection 