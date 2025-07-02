import copy
from typing import List, Optional
from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox
from detection.types import Detection
from detection.categories_map import get_all_frequency_categories, get_category
from sections.sections import Section, update_sections_table


class DetectionManager:
    """Manages detection operations and state"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.clipboard_detection = None
        self.clipboard_cut = False
        
    def get_filtered_detections(self) -> List[Detection]:
        """Get detections filtered by current section and category filters"""
        if not hasattr(self.main_window, "section_filter_dropdown") or not hasattr(
            self.main_window, "category_filter_dropdown"
        ):
            return self.main_window.detections
            
        section = self.main_window.section_filter_dropdown.currentText()
        category = self.main_window.category_filter_dropdown.currentText()
        filtered = self.main_window.detections
        
        if section != "All":
            filtered = [
                d for d in filtered if getattr(d, "section", "Unassigned") == section
            ]
        if category != "All":
            filtered = [d for d in filtered if getattr(d, "name", None) == category]
            
        return filtered

    def cut_detection(self, idx: int):
        """Cut a detection to clipboard"""
        if idx is not None and 0 <= idx < len(self.main_window.detections):
            self.clipboard_detection = self.main_window.detections[idx]
            self.clipboard_cut = True
            self.main_window.detections.pop(idx)
            self.main_window.update_objects_table()
            self.main_window.pdf_viewer.set_detections(self.get_filtered_detections())

    def copy_detection(self, idx: int):
        """Copy a detection to clipboard"""
        if idx is not None and 0 <= idx < len(self.main_window.detections):
            self.clipboard_detection = copy.deepcopy(self.main_window.detections[idx])
            self.clipboard_cut = False

    def paste_detection(self, idx: Optional[int] = None, pos: Optional[QPoint] = None):
        """Paste a detection from clipboard"""
        if self.clipboard_detection is not None:
            new_det = copy.deepcopy(self.clipboard_detection)
            if pos is not None:
                # Convert widget pos to image coords
                img_x, img_y = self.main_window.pdf_viewer.widget_to_image_coords(pos.x(), pos.y())
                w = new_det.bbox[2] - new_det.bbox[0]
                h = new_det.bbox[3] - new_det.bbox[1]
                new_det.bbox = (int(img_x), int(img_y), int(img_x + w), int(img_y + h))
                new_det.page_num = self.main_window.pdf_viewer.current_page + 1
                
            self.main_window.detections.append(new_det)
            self.main_window.update_objects_table()
            self.main_window.pdf_viewer.set_detections(self.get_filtered_detections())
            
            if self.clipboard_cut:
                self.clipboard_detection = None
                self.clipboard_cut = False
                
            self.main_window.update_results_table()

    def delete_detection(self, idx: int):
        """Delete a detection"""
        if idx is not None and 0 <= idx < len(self.main_window.detections):
            self.main_window.detections.pop(idx)
            self.main_window.update_objects_table()
            self.main_window.pdf_viewer.set_detections(self.get_filtered_detections())
            self.main_window.update_results_table()

    def edit_detection(self, idx: int):
        """Edit a detection's properties"""
        if idx is not None and 0 <= idx < len(self.main_window.detections):
            detection = self.main_window.detections[idx]
            from ui.dialogs.detection_dialog import DetectionDialog
            
            dialog = DetectionDialog(self.main_window, detection)
            if dialog.exec():
                # Update detection with dialog values
                detection.name = dialog.get_class_name()
                detection.section = dialog.get_section_name()
                detection.line_size = dialog.get_line_size()
                detection.count = dialog.get_count()
                
                # Handle new section creation
                self._handle_new_section(detection.section, detection.line_size)
                
                self.main_window.update_objects_table()
                self.main_window.pdf_viewer.set_detections(self.get_filtered_detections())
                self.main_window.update_results_table()

    def add_manual_detection(self, bbox):
        """Add a manually drawn detection"""
        from ui.dialogs.detection_dialog import DetectionDialog
        
        dialog = DetectionDialog(self.main_window, None)
        if dialog.exec():
            class_name = dialog.get_class_name()
            section_name = dialog.get_section_name()
            line_size_value = dialog.get_line_size()
            count_value = dialog.get_count()
            
            # Handle new section creation
            self._handle_new_section(section_name, line_size_value)
            
            # Create new detection
            new_detection = Detection(
                name=class_name,
                confidence=1.0,  # Default for manual detections
                bbox=bbox,
                page_num=self.main_window.pdf_viewer.current_page + 1,
                section=section_name,
                source="manual",
                line_size=line_size_value,
                count=count_value,
            )
            
            self.main_window.undo_stack.append(self.main_window.detections.copy())
            self.main_window.redo_stack.clear()
            self.main_window.detections.append(new_detection)
            self.main_window.update_objects_table()
            self.main_window.pdf_viewer.set_detections(self.get_filtered_detections())
            self.main_window.update_results_table()

    def _handle_new_section(self, section_name: str, line_size: Optional[float]):
        """Handle creation of new sections when editing detections"""
        if section_name != "Unassigned" and section_name not in [
            section.name for section in self.main_window.sections_list
        ]:
            new_section = Section(section_name)
            self.main_window.sections_list.append(new_section)
            update_sections_table(self.main_window)
            self.main_window.update_section_filter_dropdown()
            
        # If section has no line size, set it now
        if section_name != "Unassigned":
            section = next(
                (s for s in self.main_window.sections_list if s.name == section_name),
                None,
            )
            if section and section.line_size is None and line_size is not None:
                section.line_size = line_size
                update_sections_table(self.main_window)

    def undo(self):
        """Undo the last annotation change"""
        if not self.main_window.undo_stack:
            return
        self.main_window.redo_stack.append(self.main_window.detections.copy())
        self.main_window.detections = self.main_window.undo_stack.pop()
        self.main_window.pdf_viewer.set_detections(self.main_window.detections)
        self.main_window.update_objects_table()

    def redo(self):
        """Redo the last undone annotation change"""
        if not self.main_window.redo_stack:
            return
        self.main_window.undo_stack.append(self.main_window.detections.copy())
        self.main_window.detections = self.main_window.redo_stack.pop()
        self.main_window.pdf_viewer.set_detections(self.main_window.detections)
        self.main_window.update_objects_table()

    def on_bbox_changed(self, idx: int, bbox):
        """Handle bounding box changes from drag/resize"""
        if 0 <= idx < len(self.main_window.detections):
            self.main_window.detections[idx].bbox = bbox
        self.main_window.update_objects_table()

    def on_bbox_right_clicked(self, bbox_index: int):
        """Handle right-click on bounding box"""
        menu = QMenu(self.main_window)
        
        cut_action = QAction("Cut", self.main_window)
        copy_action = QAction("Copy", self.main_window)
        paste_action = QAction("Paste", self.main_window)
        edit_action = QAction("Edit Object", self.main_window)
        delete_action = QAction("Delete Object", self.main_window)
        
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
        
        menu.exec(self.main_window.cursor().pos())

    def on_background_right_clicked(self, pos: QPoint):
        """Handle right-click on background"""
        menu = QMenu(self.main_window)
        paste_action = QAction("Paste", self.main_window)
        menu.addAction(paste_action)
        paste_action.setEnabled(self.clipboard_detection is not None)
        paste_action.triggered.connect(lambda: self.paste_detection(None, pos))
        menu.exec(self.main_window.cursor().pos()) 