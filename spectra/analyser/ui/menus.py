from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

class MenuManager:
    """Manages all menu creation and actions for the main window"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.cut_action = None
        self.copy_action = None
        self.paste_action = None
        
    def create_menus(self):
        """Create menu bar and menus"""
        menu_bar = self.main_window.menuBar()

        # File menu
        file_menu: QMenu = menu_bar.addMenu("File")
        self._create_file_menu(file_menu)

        # Edit menu
        edit_menu: QMenu = menu_bar.addMenu("Edit")
        self._create_edit_menu(edit_menu)

        # Objects menu
        objects_menu: QMenu = menu_bar.addMenu("Objects")
        self._create_objects_menu(objects_menu)

        # Sections menu
        sections_menu: QMenu = menu_bar.addMenu("Sections")
        self._create_sections_menu(sections_menu)

        # Analysis menu
        analysis_menu: QMenu = menu_bar.addMenu("Analysis")
        self._create_analysis_menu(analysis_menu)

        # About menu
        about_menu_obj: QMenu = menu_bar.addMenu("About")
        self._create_about_menu(about_menu_obj)

        self.main_window.setMenuBar(menu_bar)

    def _create_file_menu(self, file_menu):
        """Create File menu items"""
        new_action = QAction("New Project", self.main_window)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.main_window.new_project)
        file_menu.addAction(new_action)

        open_project_action = QAction("Open Project", self.main_window)
        open_project_action.setShortcut("Ctrl+O")
        open_project_action.triggered.connect(self.main_window.open_project)
        file_menu.addAction(open_project_action)

        save_project_action = QAction("Save Project", self.main_window)
        save_project_action.setShortcut("Ctrl+S")
        save_project_action.triggered.connect(self.main_window.save_project)
        file_menu.addAction(save_project_action)

        file_menu.addSeparator()

        open_pdf_action = QAction("Open PDF", self.main_window)
        open_pdf_action.setShortcut("Ctrl+Shift+O")
        open_pdf_action.triggered.connect(self.main_window.open_pdf)
        file_menu.addAction(open_pdf_action)

        save_pdf_action = QAction("Save PDF", self.main_window)
        save_pdf_action.setShortcut("Ctrl+Shift+S")
        save_pdf_action.triggered.connect(self.main_window.save_pdf)
        file_menu.addAction(save_pdf_action)

    def _create_edit_menu(self, edit_menu):
        """Create Edit menu items"""
        undo_action = QAction("Undo", self.main_window)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.main_window.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self.main_window)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self.main_window.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        self.cut_action = QAction("Cut", self.main_window)
        self.cut_action.setShortcut("Ctrl+X")
        self.cut_action.triggered.connect(self.main_window.menu_cut)
        edit_menu.addAction(self.cut_action)

        self.copy_action = QAction("Copy", self.main_window)
        self.copy_action.setShortcut("Ctrl+C")
        self.copy_action.triggered.connect(self.main_window.menu_copy)
        edit_menu.addAction(self.copy_action)

        self.paste_action = QAction("Paste", self.main_window)
        self.paste_action.setShortcut("Ctrl+V")
        self.paste_action.triggered.connect(self.main_window.menu_paste)
        edit_menu.addAction(self.paste_action)

        edit_menu.addSeparator()

    def _create_sections_menu(self, sections_menu):
        """Create Sections menu items"""
        draw_section_action = QAction("Draw Section", self.main_window)
        draw_section_action.setShortcut("Ctrl+Shift+Space")
        draw_section_action.triggered.connect(self.main_window.enter_add_section_mode)
        sections_menu.addAction(draw_section_action)

    def _create_objects_menu(self, objects_menu):
        """Create Objects menu items"""
        add_object_action = QAction("Add Object", self.main_window)
        add_object_action.setShortcut("Ctrl+Space")
        add_object_action.triggered.connect(self.main_window.enter_add_object_mode)
        objects_menu.addAction(add_object_action)

        objects_menu.addSeparator()

        import_csv_action = QAction("Import CSV", self.main_window)
        import_csv_action.triggered.connect(self.main_window.import_sections_csv)
        objects_menu.addAction(import_csv_action)

    def _create_analysis_menu(self, analysis_menu):
        """Create Analysis menu items"""
        run_analysis_action = QAction("Run Analysis", self.main_window)
        run_analysis_action.setShortcut("Ctrl+Enter")
        run_analysis_action.triggered.connect(self.main_window.run_analysis)
        analysis_menu.addAction(run_analysis_action)

        analysis_menu.addSeparator()

        set_conf_action = QAction("Set Confidence", self.main_window)
        set_conf_action.triggered.connect(self.main_window.set_confidence)
        analysis_menu.addAction(set_conf_action)

        set_overlap_action = QAction("Set Overlap", self.main_window)
        set_overlap_action.triggered.connect(self.main_window.set_overlap)
        analysis_menu.addAction(set_overlap_action)

        analysis_menu.addSeparator()

        set_api_action = QAction("Set API Key", self.main_window)
        set_api_action.triggered.connect(self.main_window.set_api_key)
        analysis_menu.addAction(set_api_action)

    def _create_about_menu(self, about_menu_obj):
        """Create About menu items"""
        about_action = QAction("About", self.main_window)
        about_action.triggered.connect(self.main_window.show_about)
        about_menu_obj.addAction(about_action)

        help_action = QAction("Help", self.main_window)
        help_action.triggered.connect(self.main_window.show_help)
        about_menu_obj.addAction(help_action)

    def update_edit_menu_actions(self):
        """Update the enabled state of edit menu actions"""
        selected = self.main_window.pdf_viewer.selected_bbox_index is not None
        if self.cut_action:
            self.cut_action.setEnabled(selected)
        if self.copy_action:
            self.copy_action.setEnabled(selected)
        if self.paste_action:
            self.paste_action.setEnabled(self.main_window.clipboard_detection is not None) 