from typing import Optional, List, Tuple
import colorsys
import math
import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem
from PySide6.QtGui import QColor

RAINBOW_COLORS = 12  # Number of distinct colors before looping

def get_next_rainbow_color(index: int) -> QColor:
    """Return a QColor from a rainbow palette, cycling by index."""
    hue = (index % RAINBOW_COLORS) / RAINBOW_COLORS
    rgb = colorsys.hsv_to_rgb(hue, 0.85, 0.95)
    return QColor(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))

class Section:
    """Represents a section with name, line size, polyline points, and color properties"""
    def __init__(self, name: str, line_size: Optional[float] = None, points: Optional[List[Tuple[float, float]]] = None, color: Optional[QColor] = None, color_index: Optional[int] = None):
        self.name = name
        self.line_size = line_size
        self.points = points or []
        # Use rainbow color cycling if no color provided
        if color is not None:
            self.color = color
        elif color_index is not None:
            self.color = get_next_rainbow_color(color_index)
        else:
            self.color = get_next_rainbow_color(0)
    
    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            'name': self.name,
            'line_size': self.line_size,
            'points': self.points,
            'color': self.color.name() if self.color else None
        }

    @staticmethod
    def from_dict(data):
        color = None
        if data.get('color'):
            color = QColor(data['color'])
        
        return Section(
            name=data.get('name', ''),
            line_size=data.get('line_size', None),
            points=data.get('points', []),
            color=color
        )

def move_section_up(self):
    """Move the selected section up in the list"""
    if not self.sections_panel.sections_table:
        return
    selected = self.sections_panel.sections_table.currentRow()
    if selected > 0:
        self.sections_list[selected-1], self.sections_list[selected] = self.sections_list[selected], self.sections_list[selected-1]
        update_sections_table(self)
        self.sections_panel.sections_table.selectRow(selected-1)
        update_section_filter_dropdown(self)

def move_section_down(self):
    """Move the selected section down in the list"""
    if not self.sections_panel.sections_table:
        return
    selected = self.sections_panel.sections_table.currentRow()
    if 0 <= selected < len(self.sections_list)-1:
        self.sections_list[selected+1], self.sections_list[selected] = self.sections_list[selected], self.sections_list[selected+1]
        update_sections_table(self)
        self.sections_panel.sections_table.selectRow(selected+1)
        update_section_filter_dropdown(self)

def import_sections_csv(self):
    """Import sections from a CSV file"""
    import csv
    
    file_path, _ = QFileDialog.getOpenFileName(self, "Import Sections from CSV", "", "CSV Files (*.csv)")
    if file_path:
        try:
            with open(file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                existing_names = set(section.name for section in self.sections_list)
                
                for row in reader:
                    if row and row[0].strip():
                        section_name = row[0].strip()
                        
                        # Skip if section name already exists
                        if section_name in existing_names:
                            continue
                        
                        # Create new section
                        new_section = Section(section_name)
                        
                        # Try to parse line size data if available
                        if len(row) > 1 and row[1].strip():
                            try:
                                new_section.line_size = float(row[1].strip())
                            except ValueError:
                                pass  # Invalid number, keep as None
                        
                        self.sections_list.append(new_section)
                        existing_names.add(section_name)
            
            update_sections_table(self)
            update_section_filter_dropdown(self)
            
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import CSV file: {str(e)}")

def update_sections_table(self):
    if not self.sections_panel.sections_table:
        return
    self.sections_panel.sections_table.blockSignals(True)
    self.sections_panel.sections_table.setRowCount(len(self.sections_list))
    for i, section in enumerate(self.sections_list):
        # Section name
        name_item = QTableWidgetItem(section.name)
        name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.sections_panel.sections_table.setItem(i, 0, name_item)
        
        # Line size
        mm_text = f"{section.line_size:.2f}" if section.line_size is not None else ""
        mm_item = QTableWidgetItem(mm_text)
        mm_item.setFlags(mm_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.sections_panel.sections_table.setItem(i, 1, mm_item)
        
        # Color
        color_item = QTableWidgetItem()
        if section.color:
            color_item.setBackground(section.color)
            color_item.setText(section.color.name())
        else:
            color_item.setText("Auto")
        color_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.sections_panel.sections_table.setItem(i, 2, color_item)
    self.sections_panel.sections_table.blockSignals(False)

def handle_section_edit(self, item):
    """Handle editing of section table items"""
    if not self.sections_panel.sections_table:
        return
    row = item.row()
    col = item.column()
    text = item.text().strip()
    
    if row >= len(self.sections_list):
        return
        
    section = self.sections_list[row]
    
    if col == 0:  # Section name
        if not text:
            # Prevent empty names
            update_sections_table(self)
            return
        section.name = text
    elif col == 1:  # Line size
        if text:
            try:
                value = float(text)
                if value > 2000:
                    reply = QMessageBox.question(
                        self,
                        "Large Line Size",
                        "You have entered a line size greater than 2000 mm. Are you sure?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        update_sections_table(self)
                        return
                section.line_size = value
            except ValueError:
                # Invalid number, revert
                QMessageBox.warning(
                    self,
                    "Invalid Input",
                    "Please enter a valid number for line size."
                )
                update_sections_table(self)
                return
        else:
            section.line_size = None
    
    # Update the table to reflect the calculated values
    update_sections_table(self)
    assign_objects_to_sections(self)

def update_section_filter_dropdown(self):
    """Update the section filter dropdown with current section names"""
    if hasattr(self, 'section_filter_dropdown'):
        self.section_filter_dropdown.clear()
        self.section_filter_dropdown.addItem("All")
        for section in self.sections_list:
            self.section_filter_dropdown.addItem(section.name)

def add_section_with_points(self, points):
    from ui.dialogs.section_dialog import SectionDialog
    base_name = "New Section"
    existing_names = set(section.name for section in self.sections_list)
    i = 1
    while f"{base_name} {i}" in existing_names:
        i += 1
    new_name = f"{base_name} {i}"
    color_index = len(self.sections_list)
    default_color = get_next_rainbow_color(color_index)
    dialog = SectionDialog(self, new_name, None, default_color)
    if not dialog.exec():
        return  # User cancelled
    name = dialog.get_name()
    line_size = dialog.get_line_size()
    color = dialog.get_color()
    new_section = Section(name, line_size=line_size, points=points, color=color)
    self.sections_list.append(new_section)
    update_sections_table(self)
    update_section_filter_dropdown(self)
    if hasattr(self, 'viewer_panel') and self.viewer_panel.pdf_viewer:
        self.viewer_panel.pdf_viewer.set_sections(self.sections_list)
    if self.sections_panel.sections_table:
        self.sections_panel.sections_table.selectRow(len(self.sections_list) - 1)
    assign_objects_to_sections(self)

def show_section_context_menu(self, section_index: int, global_pos=None):
    """Show context menu for section operations"""
    from PySide6.QtWidgets import QMenu, QColorDialog
    from PySide6.QtCore import QPoint
    
    if section_index < 0 or section_index >= len(self.sections_list):
        return
    
    section = self.sections_list[section_index]
    
    if hasattr(self, '_section_clipboard'):
        clipboard = self._section_clipboard
    else:
        clipboard = None
    
    menu = QMenu(self)
    
    # Edit Section action
    edit_action = menu.addAction("Edit Section")
    edit_action.triggered.connect(lambda: edit_section_points(self, section_index))
    
    menu.addSeparator()
    
    # Cut/Copy/Paste actions
    cut_action = menu.addAction("Cut Section")
    cut_action.triggered.connect(lambda: cut_section(self, section_index))
    
    copy_action = menu.addAction("Copy Section")
    copy_action.triggered.connect(lambda: copy_section(self, section_index))
    
    paste_action = menu.addAction("Paste Section")
    paste_action.triggered.connect(lambda: paste_section(self))
    paste_action.setEnabled(hasattr(self, '_section_clipboard') and self._section_clipboard is not None)
    
    menu.addSeparator()
    
    # Change Color action
    color_action = menu.addAction("Change Color")
    color_action.triggered.connect(lambda: change_section_color(self, section_index))
    
    menu.addSeparator()
    
    # Delete action
    delete_action = menu.addAction("Delete Section")
    delete_action.triggered.connect(lambda: delete_section_from_context(self, section_index))
    
    if global_pos is not None:
        menu.exec(global_pos)
    else:
        if hasattr(self, 'viewer_panel') and self.viewer_panel.pdf_viewer:
            cursor_pos = self.viewer_panel.pdf_viewer.mapToGlobal(QPoint(0, 0))
        else:
            cursor_pos = QPoint(0, 0)
        menu.exec(cursor_pos)

def edit_section_points(self, section_index: int):
    """Edit the points of a section"""
    if section_index < 0 or section_index >= len(self.sections_list):
        return
    
    section = self.sections_list[section_index]
    
    # For now, we'll just show a message. In a full implementation,
    # this would open a dialog to edit the points
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information(
        self,
        "Edit Section",
        f"Editing points for section '{section.name}'.\n"
        "This feature will be implemented in a future update."
    )

def cut_section(self, section_index: int):
    """Cut a section (copy and delete)"""
    if section_index < 0 or section_index >= len(self.sections_list):
        return
    
    copy_section(self, section_index)
    delete_section_from_context(self, section_index)

def copy_section(self, section_index: int):
    """Copy a section to clipboard"""
    if section_index < 0 or section_index >= len(self.sections_list):
        return
    
    section = self.sections_list[section_index]
    self._section_clipboard = copy.deepcopy(section)

def paste_section(self):
    """Paste a section from clipboard"""
    if not hasattr(self, '_section_clipboard') or self._section_clipboard is None:
        return
    
    copied_section = copy.deepcopy(self._section_clipboard)
    
    # Generate unique name
    base_name = copied_section.name.split()[0]
    existing_names = set(section.name for section in self.sections_list)
    i = 1
    while f"{base_name} {i}" in existing_names:
        i += 1
    new_name = f"{base_name} {i}"
    color_index = len(self.sections_list)
    copied_section.name = new_name
    copied_section.color = get_next_rainbow_color(color_index)
    self.sections_list.append(copied_section)
    update_sections_table(self)
    update_section_filter_dropdown(self)
    
    # Update the PDF viewer
    if hasattr(self, 'viewer_panel') and self.viewer_panel.pdf_viewer:
        self.viewer_panel.pdf_viewer.set_sections(self.sections_list)

def change_section_color(self, section_index: int):
    """Change the color of a section"""
    if section_index < 0 or section_index >= len(self.sections_list):
        return
    
    section = self.sections_list[section_index]
    
    from PySide6.QtWidgets import QColorDialog
    from PySide6.QtGui import QColor
    
    current_color = section.color if section.color else QColor(Qt.GlobalColor.blue)
    new_color = QColorDialog.getColor(current_color, self, "Choose Section Color")
    
    if new_color.isValid():
        section.color = new_color
        update_sections_table(self)
        
        # Update the PDF viewer
        if hasattr(self, 'viewer_panel') and self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.set_sections(self.sections_list)

def delete_section_from_context(self, section_index: int):
    """Delete a section from context menu"""
    if section_index < 0 or section_index >= len(self.sections_list):
        return
    
    section = self.sections_list[section_index]
    
    from PySide6.QtWidgets import QMessageBox
    reply = QMessageBox.question(
        self,
        "Delete Section",
        f"Are you sure you want to delete section '{section.name}'?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    
    if reply == QMessageBox.StandardButton.Yes:
        del self.sections_list[section_index]
        update_sections_table(self)
        update_section_filter_dropdown(self)
        
        # Update the PDF viewer
        if hasattr(self, 'viewer_panel') and self.viewer_panel.pdf_viewer:
            self.viewer_panel.pdf_viewer.set_sections(self.sections_list)

def get_section_for_bbox(bbox, sections_list):
    """Return the name of the most recently added section whose polyline crosses the bbox, or 'Unassigned'."""
    for section in reversed(sections_list):
        if polyline_intersects_bbox(section.points, bbox):
            return section.name
    return "Unassigned"

def assign_objects_to_sections(self):
    """Assign each detection to the most recently added section whose polyline crosses its bbox."""
    if not hasattr(self, 'detections') or not hasattr(self, 'sections_list'):
        return
    for det in self.detections:
        det.section = get_section_for_bbox(det.bbox, self.sections_list)

def polyline_intersects_bbox(points, bbox):
    """Return True if any segment of the polyline intersects the bbox."""
    if not points or len(points) < 2:
        return False
    x1, y1, x2, y2 = bbox
    for i in range(len(points) - 1):
        if segment_intersects_rect(points[i], points[i+1], x1, y1, x2, y2):
            return True
    return False

def segment_intersects_rect(p1, p2, x1, y1, x2, y2):
    """Check if a line segment (p1, p2) intersects a rectangle (x1, y1, x2, y2)."""
    from PySide6.QtCore import QLineF
    edges = [
        QLineF(x1, y1, x2, y1),  # top
        QLineF(x2, y1, x2, y2),  # right
        QLineF(x2, y2, x1, y2),  # bottom
        QLineF(x1, y2, x1, y1),  # left
    ]
    seg = QLineF(p1[0], p1[1], p2[0], p2[1])
    for edge in edges:
        intersect_type, _ = seg.intersects(edge)
        # Compare by name to avoid enum/int issues
        if hasattr(intersect_type, 'name') and intersect_type.name == 'BoundedIntersection':
            return True
    if (x1 <= p1[0] <= x2 and y1 <= p1[1] <= y2) or (x1 <= p2[0] <= x2 and y1 <= p2[1] <= y2):
        return True
    return False

def point_in_polygon(point, poly):
    """Ray casting algorithm for point-in-polygon test."""
    x, y = point
    n = len(poly)
    inside = False
    if n < 3:
        return False
    px1, py1 = poly[0]
    for i in range(n+1):
        px2, py2 = poly[i % n]
        if min(py1, py2) < y <= max(py1, py2) and x <= max(px1, px2):
            if py1 != py2:
                xinters = (y - py1) * (px2 - px1) / (py2 - py1) + px1
            if px1 == px2 or x <= xinters:
                inside = not inside
        px1, py1 = px2, py2
    return inside