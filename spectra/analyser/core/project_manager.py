import json

from PySide6.QtWidgets import QFileDialog, QMessageBox

from detection.types import Detection
from sections.sections import Section


class ProjectManager:
    """Manages project file operations and state"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        
    def new_project(self):
        """Creates a new project, resets all ongoing progress"""
        # Check if there is anything to clear
        has_pdf = self.main_window.current_pdf_path is not None
        has_detections = bool(self.main_window.detections)
        has_sections = bool(self.main_window.sections_list)
        
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
                self.main_window,
                "New Project",
                f"This will clear the current project because {msg_str}.\nAre you sure you want to start a new project?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return None

        # Reset everything
        self.main_window.current_pdf_path = None
        self.main_window.detections.clear()
        self.main_window.undo_stack.clear()
        self.main_window.redo_stack.clear()
        self.main_window.sections_list.clear()
        
        # Update UI - these are already debounced in the main window
        self.main_window.update_sections_table()
        self.main_window.update_section_filter_dropdown()
        self.main_window.update_objects_table()
        
        # Reset PDF viewer (cleanup method handles all state reset)
        self.main_window.pdf_viewer.cleanup()
        return None  # No file path for new project

    def open_project(self):
        """Open a project file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Open Project",
            "",
            "Spectra Project Files (*.spectra.json);;JSON Files (*.json)",
        )
        if not file_path:
            return None
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Clear current state
            self.main_window.sections_list = [
                Section.from_dict(s) for s in data.get("sections", [])
            ]
            self.main_window.detections = [
                Detection.from_dict(d) for d in data.get("detections", [])
            ]
            self.main_window.confidence = data.get("confidence", 0.5)
            self.main_window.overlap = data.get("overlap", 0.3)
            self.main_window.api_key = data.get("api_key", None)
            
            # Update UI - these are already debounced in the main window
            self.main_window.update_sections_table()
            self.main_window.update_section_filter_dropdown()
            self.main_window.update_objects_table()
            
            # Do not auto-load PDF, just update viewer state
            self.main_window.pdf_viewer.cleanup()
            
            self.main_window.pdf_viewer.set_detections(self.main_window.detections)
            self.main_window.pdf_viewer.set_sections(self.main_window.sections_list)
            QMessageBox.information(
                self.main_window, "Open Project", "Project loaded successfully."
            )
            return file_path
        except Exception as e:
            QMessageBox.critical(
                self.main_window, "Open Error", f"Failed to open project: {str(e)}"
            )
            return None

    def save_project(self):
        """Save the current project"""
        file_path, _ = QFileDialog.getSaveFileName(
            self.main_window,
            "Save Project",
            "",
            "Spectra Project Files (*.spectra.json);;JSON Files (*.json)",
        )
        if not file_path:
            return None
            
        data = {
            "sections": [section.to_dict() for section in self.main_window.sections_list],
            "detections": [detection.to_dict() for detection in self.main_window.detections],
            "confidence": self.main_window.confidence,
            "overlap": self.main_window.overlap,
            "api_key": self.main_window.api_key,
        }
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self.main_window, "Save Project", "Project saved successfully.")
            return file_path
        except Exception as e:
            QMessageBox.critical(
                self.main_window, "Save Error", f"Failed to save project: {str(e)}"
            )
            return None

    def open_pdf(self):
        """Open a PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window, "Load PDF", "", "PDF Files (*.pdf)"
        )

        if file_path:
            if self.main_window.pdf_viewer.load_pdf(file_path):
                self.main_window.current_pdf_path = file_path
                self.main_window.update_navigation_controls()
                self.main_window.detections.clear()
                self.main_window.update_objects_table()

    def save_pdf(self):
        """Saves the current PDF with annotations"""
        # TODO: Implement PDF saving with annotations
        QMessageBox.information(
            self.main_window, "Save PDF", "PDF saving with annotations is not yet implemented."
        ) 