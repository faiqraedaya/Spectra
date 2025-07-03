from typing import List

from PySide6.QtWidgets import QInputDialog, QMessageBox

from detection.categories_map import get_category
from detection.roboflow import RoboflowAnalysisThread
from sections.sections import assign_objects_to_sections


class AnalysisManager:
    """Manages analysis operations and settings"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.analysis_thread = None
        
    def run_analysis(self):
        """Analyze all pages of the PDF"""
        # Get all page images
        image_paths = self.main_window.pdf_viewer.get_page_image_paths()
        if not image_paths:
            QMessageBox.warning(self.main_window, "Warning", "No pages to analyze")
            return

        # Setup UI for analysis
        self.main_window.progress_bar.setVisible(True)
        self.main_window.progress_bar.setMaximum(len(image_paths))
        self.main_window.progress_bar.setValue(0)

        # Start analysis thread (Roboflow)
        self.analysis_thread = RoboflowAnalysisThread(
            self.main_window.api_key, 
            image_paths, 
            self.main_window.confidence, 
            int(self.main_window.overlap * 100)  # Convert to percentage
        )

        self.analysis_thread.analysis_complete.connect(self.on_analysis_complete)
        self.analysis_thread.error_occurred.connect(self.on_analysis_error)
        self.analysis_thread.progress_updated.connect(self.on_progress_updated)
        self.analysis_thread.start()

    def on_progress_updated(self, current: int, total: int):
        """Handle progress update"""
        self.main_window.progress_bar.setValue(current)

    def on_analysis_complete(self, detections: List):
        """Handle analysis completion"""
        # Preserve manual detections
        manual_detections = [
            d for d in self.main_window.detections if getattr(d, "source", "model") == "manual"
        ]

        # Map model detections to categories
        for d in detections:
            d.name = get_category(d.name)
            
        self.main_window.detections = manual_detections + detections
        from sections.sections import assign_objects_to_sections
        assign_objects_to_sections(self.main_window)
        self.main_window.undo_stack.clear()
        self.main_window.redo_stack.clear()
        self.main_window.pdf_viewer.set_detections(self.main_window.detections)
        self.main_window.update_objects_table()

        # Update UI
        self.main_window.progress_bar.setVisible(False)
        QMessageBox.information(
            self.main_window,
            "Analysis Complete",
            f"Found {len(detections)} objects across {self.main_window.pdf_viewer.total_pages} pages",
        )

    def on_analysis_error(self, error_message: str):
        """Handle analysis error"""
        QMessageBox.critical(
            self.main_window, "Analysis Error", f"Error during analysis:\n{error_message}"
        )
        self.main_window.progress_bar.setVisible(False)

    def set_confidence(self):
        """Set the confidence threshold for analysis"""
        value, ok = QInputDialog.getDouble(
            self.main_window,
            "Set Confidence",
            "Confidence (0.0 - 1.0):",
            self.main_window.confidence,
            0.0,
            1.0,
            2,
        )
        if ok:
            self.main_window.confidence = value

    def set_overlap(self):
        """Set the overlap threshold for analysis"""
        value, ok = QInputDialog.getDouble(
            self.main_window, 
            "Set Overlap", 
            "Overlap (0.0 - 1.0):", 
            self.main_window.overlap, 
            0.0, 
            1.0, 
            2
        )
        if ok:
            self.main_window.overlap = value

    def set_api_key(self):
        """Set the Roboflow API key"""
        api_key, ok = QInputDialog.getText(
            self.main_window, 
            "Set API Key", 
            "Enter your Roboflow API key:", 
            text=self.main_window.api_key or ""
        )
        if ok:
            self.main_window.api_key = api_key 