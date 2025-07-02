from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

class Section:
    """Represents a section with name and line size properties"""
    def __init__(self, name: str, line_size: Optional[float] = None):
        self.name = name
        self.line_size = line_size
    
    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            'name': self.name,
            'line_size': self.line_size
        }

    @staticmethod
    def from_dict(data):
        return Section(
            name=data.get('name', ''),
            line_size=data.get('line_size', None)
        )

def add_section(self):
    """Add a new section with an incrementing name"""
    base_name = "New Section"
    existing_names = set(section.name for section in self.sections_list)
    i = 1
    # Increment to first non-existing number
    while f"{base_name} {i}" in existing_names:
        i += 1
    new_name = f"{base_name} {i}"
    new_section = Section(new_name)
    self.sections_list.append(new_section)
    update_sections_table(self)
    update_section_filter_dropdown(self)
    if self.sections_panel.sections_table:
        self.sections_panel.sections_table.selectRow(len(self.sections_list) - 1)

def delete_section(self):
    if not self.sections_panel.sections_table:
        return
    selected = self.sections_panel.sections_table.currentRow()
    if selected < 0:
        return
    section = self.sections_list[selected]

    # Count assigned objects
    # Reset assignments
    del self.sections_list[selected]
    update_sections_table(self)
    update_section_filter_dropdown(self)

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
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply != QMessageBox.Yes:
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

def update_section_filter_dropdown(self):
    """Update the section filter dropdown with current section names"""
    if hasattr(self, 'section_filter_dropdown'):
        self.section_filter_dropdown.clear()
        self.section_filter_dropdown.addItem("All")
        for section in self.sections_list:
            self.section_filter_dropdown.addItem(section.name)