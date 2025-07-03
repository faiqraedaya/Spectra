import csv
import os
import re
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import (
    APP_TITLE,
    DEFAULT_CONFIDENCE,
    DEFAULT_OVERLAP,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_X,
    DEFAULT_WINDOW_Y,
    FREQUENCY_CSV_PATH,
    MAIN_SPLITTER_SIZES,
    ROBOFLOW_API_KEY_ENV,
)
from core.analysis_manager import AnalysisManager
from core.detection_manager import DetectionManager
from core.project_manager import ProjectManager
from detection.types import Detection
from sections.sections import Section, import_sections_csv
from ui.menus import MenuManager
from ui.panels.objects_panel import ObjectsPanel
from ui.panels.results_panel import ResultsPanel
from ui.panels.sections_panel import SectionsPanel
from ui.panels.viewer_panel import ViewerPanel
from utils.frequency import FrequencyTable

class Spectra(QMainWindow):
    """Modular main application window using separated components"""

    def __init__(self):
        super().__init__()
        self.project_name = "New Project"  # Track current project name
        self.setWindowTitle(f"{APP_TITLE} - {self.project_name}")
        self.setGeometry(DEFAULT_WINDOW_X, DEFAULT_WINDOW_Y, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.version = "1.1.0"

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
        self.mode_label = None  # QLabel for mode indicator

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
        tab_widget = QTabWidget()
        sections_widget = self.sections_panel.create_panel()
        tab_widget.addTab(sections_widget, "Sections")
        main_splitter.addWidget(tab_widget)

        tab_widget = QTabWidget()
        viewer_widget = self.viewer_panel.create_panel()
        tab_widget.addTab(viewer_widget, "Viewer")
        main_splitter.addWidget(tab_widget)

        # Create results widget as a tab widget
        tab_widget = QTabWidget()
        objects_widget = self.objects_panel.create_panel()
        results_widget = self.results_panel.create_panel()
        tab_widget.addTab(objects_widget, "Objects")
        tab_widget.addTab(results_widget, "Results")
        main_splitter.addWidget(tab_widget)

        # Create mode label in status bar
        self.mode_label = QLabel("Mode: Normal")
        self.statusBar().addPermanentWidget(self.mode_label)

        # Initialize widget sizes
        main_splitter.setSizes(MAIN_SPLITTER_SIZES)

        # Connect signals
        self._connect_signals()

        # Initial updates
        self.update_navigation_controls()
        self.update_results_table()

    def _connect_signals(self):
        """Connect all signal handlers"""
        # PDF viewer signals - connect only the ones not handled by viewer panel
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.manual_box_drawn.connect(self.detection_manager.add_manual_detection)
            self.viewer_panel.pdf_viewer.bbox_changed.connect(self.detection_manager.on_bbox_changed)
            self.viewer_panel.pdf_viewer.section_drawn.connect(self.on_section_drawn)
            self.viewer_panel.pdf_viewer.section_right_clicked.connect(self.on_section_right_clicked)

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
        self.set_mode_label("Add Object")

    def exit_add_object_mode(self):
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.set_add_object_mode(False)
        self.set_mode_label("Normal")

    def enter_add_section_mode(self):
        """Enter section drawing mode"""
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.set_add_section_mode(True)
        self.set_mode_label("Draw Section")

    def exit_add_section_mode(self):
        """Exit section drawing mode"""
        if self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.set_add_section_mode(False)
        self.set_mode_label("Normal")

    def on_section_drawn(self, points):
        """Handle when a new section is drawn"""
        from sections.sections import add_section_with_points
        add_section_with_points(self, points)

    def on_section_right_clicked(self, section_index: int, global_pos=None):
        """Handle right-click on a section"""
        from sections.sections import show_section_context_menu
        show_section_context_menu(self, section_index, global_pos=global_pos)

    # Project management methods (delegated to project manager)
    def new_project(self):
        self.project_manager.new_project()
        self.project_name = "New Project"
        self.update_window_title()

    def open_project(self):
        project_file = self.project_manager.open_project()
        if project_file:
            self.project_name = os.path.splitext(os.path.basename(project_file))[0]
        else:
            self.project_name = "New Project"
        self.update_window_title()

    def save_project(self):
        project_file = self.project_manager.save_project()
        if project_file:
            self.project_name = os.path.splitext(os.path.basename(project_file))[0]
            self.update_window_title()

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
        if not self.viewer_panel.pdf_viewer:
            return
        idx = self.viewer_panel.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.detection_manager.cut_detection(idx)
        self.menu_manager.update_edit_menu_actions()

    def menu_copy(self):
        if not self.viewer_panel.pdf_viewer:
            return
        idx = self.viewer_panel.pdf_viewer.selected_bbox_index
        if idx is not None:
            self.detection_manager.copy_detection(idx)
        self.menu_manager.update_edit_menu_actions()

    def menu_paste(self):
        if not self.viewer_panel.pdf_viewer:
            return
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
        if self.viewer_panel.pdf_viewer:
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

    def import_sections_csv(self):
        import_sections_csv(self)

    def update_zoom_label(self, zoom_factor: float):
        self.viewer_panel.update_zoom_label(zoom_factor)

    def on_page_input_changed(self):
        """Handle page input change"""
        if not self.viewer_panel.pdf_viewer or not self.viewer_panel.pdf_viewer.pdf_document:
            return
        if not self.viewer_panel.page_input:
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

    def on_bbox_right_clicked(self, bbox_index: int):
        """Delegate bbox right click to detection manager"""
        self.detection_manager.on_bbox_right_clicked(bbox_index)

    def on_background_right_clicked(self, pos):
        """Delegate background right click to detection manager"""
        self.detection_manager.on_background_right_clicked(pos)

    # About/Help methods
    def show_about(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "About",
            "Spectra\n"
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
            "- Scroll: Pan up/down vertically\n\n"
            "Modes:\n"
            "- Normal: Default mode for viewing and editing objects.\n"
            "- Add Object: Add objects manually by clicking on the PDF.\n"
            "- Draw Section: Draw sections by clicking and dragging on the PDF.\n\n"
            "Keyboard Shortcuts:\n"
            "- Ctrl+Space: Add object manually\n"
            "- Ctrl+N: New project\n"
            "- Ctrl+O: Open project\n"
            "- Ctrl+S: Save project\n"
            "- Ctrl+P: Open PDF\n"
            "- Ctrl+Z: Undo\n"
            "- Ctrl+Y: Redo\n"
            "- Ctrl+X: Cut\n"
            "- Ctrl+C: Copy\n"
            "- Ctrl+V: Paste\n"
            "- Ctrl+D: Delete\n"
        )

    def export_results_to_csv(self):
        """Export the results table to a CSV file."""
        from PySide6.QtWidgets import QFileDialog
        if not self.results_panel.results_table:
            return
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

    def set_mode_label(self, mode: str):
        if self.mode_label:
            self.mode_label.setText(f"Mode: {mode}")

    def update_window_title(self):
        """Update the window title with the current project name."""
        self.setWindowTitle(f"{APP_TITLE} - {self.project_name}") 