from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget
)

from ui.pdf_viewer import PDFViewer


class ViewerPanel:
    """Manages the PDF viewer panel and navigation controls"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.pdf_viewer = None
        self.first_page_button = None
        self.prev_page_button = None
        self.next_page_button = None
        self.last_page_button = None
        self.page_input = None
        self.zoom_out_button = None
        self.zoom_in_button = None
        self.reset_zoom_button = None
        self.fit_to_window_button = None
        self.zoom_label = None
        
    def create_panel(self):
        """Create the viewer panel with PDF viewer and navigation controls"""
        # Create viewer panel
        viewer_panel = QWidget()
        viewer_layout = QVBoxLayout()
        viewer_panel.setLayout(viewer_layout)

        # Create scroll area for PDF viewer and set it to resizable
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # Create PDF viewer and connect signals
        self.pdf_viewer = PDFViewer()
        self.pdf_viewer.zoom_changed.connect(self.main_window.update_zoom_label)
        self.pdf_viewer.bbox_right_clicked.connect(self.main_window.on_bbox_right_clicked)
        self.pdf_viewer.background_right_clicked.connect(
            self.main_window.on_background_right_clicked
        )
        self.pdf_viewer.bbox_edit_finished.connect(self.main_window.on_bbox_edit_finished)
        # Set PDF viewer as widget in scroll area
        scroll_area.setWidget(self.pdf_viewer)
        # Add scroll area to viewer layout
        viewer_layout.addWidget(scroll_area)

        # Create navigation bar with page and zoom controls
        nav_bar = self._create_navigation_bar()
        viewer_layout.addLayout(nav_bar)

        return viewer_panel

    def _create_navigation_bar(self):
        """Create the navigation bar with page and zoom controls"""
        # Create navigation bar
        nav_bar = QHBoxLayout()
        
        # Left: Page controls
        nav_left = QHBoxLayout()
        # Create first page button and connect it to first page
        self.first_page_button = QPushButton("◀◀ First")
        self.first_page_button.clicked.connect(self.main_window.first_page)
        nav_left.addWidget(self.first_page_button)
        
        # Create previous page button and connect it to previous page
        self.prev_page_button = QPushButton("◀ Prev")
        self.prev_page_button.clicked.connect(self.main_window.prev_page)
        nav_left.addWidget(self.prev_page_button)

        # Create page label
        page_label = QLabel("Page:")
        nav_left.addWidget(page_label)
        
        # Create page input and connect it to page input changed
        self.page_input = QLineEdit("0/0")
        self.page_input.setFixedWidth(80)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.main_window.on_page_input_changed)
        nav_left.addWidget(self.page_input)

        # Create next page button and connect it to next page
        self.next_page_button = QPushButton("Next ▶")
        self.next_page_button.clicked.connect(self.main_window.next_page)
        nav_left.addWidget(self.next_page_button)
        
        # Create last page button and connect it to last page
        self.last_page_button = QPushButton("Last ▶▶")
        self.last_page_button.clicked.connect(self.main_window.last_page)
        nav_left.addWidget(self.last_page_button)

        # Add stretch to left layout
        nav_left.addStretch()
        # Add left layout to navigation bar
        nav_bar.addLayout(nav_left, 1)
        
        # Right: Zoom controls
        nav_right = QHBoxLayout()
        # Add stretch to right layout
        nav_right.addStretch()
        
        # Create zoom out button and connect it to zoom out
        self.zoom_out_button = QPushButton("Zoom -")
        self.zoom_out_button.clicked.connect(self.main_window.zoom_out)
        nav_right.addWidget(self.zoom_out_button)
        
        # Create zoom label
        self.zoom_label = QLabel("100%")
        nav_right.addWidget(self.zoom_label)
        
        # Create zoom in button and connect it to zoom in
        self.zoom_in_button = QPushButton("Zoom +")
        self.zoom_in_button.clicked.connect(self.main_window.zoom_in)
        nav_right.addWidget(self.zoom_in_button)
        
        # Create reset zoom button and connect it to reset zoom
        self.reset_zoom_button = QPushButton("Reset Zoom")
        self.reset_zoom_button.clicked.connect(self.main_window.reset_zoom)
        nav_right.addWidget(self.reset_zoom_button)
        
        # Create fit to window button and connect it to fit to window
        self.fit_to_window_button = QPushButton("Fit to Window")
        self.fit_to_window_button.clicked.connect(self.main_window.fit_to_window)
        nav_right.addWidget(self.fit_to_window_button)
        
        # Add right layout to navigation bar
        nav_bar.addLayout(nav_right, 1)

        return nav_bar

    def update_navigation_controls(self):
        """Update UI states for navigation controls"""
        # Get variables
        has_pdf = bool(self.pdf_viewer and self.pdf_viewer.pdf_document is not None) # Check if there is a pdf
        current_page = self.pdf_viewer.current_page if self.pdf_viewer else 0 # Get current page
        total_pages = self.pdf_viewer.total_pages if self.pdf_viewer else 0 # Get total pages

        # Reset UI states
        if self.prev_page_button:
            self.prev_page_button.setEnabled(has_pdf and current_page > 0) # Enable previous page button if there is a pdf and current page is greater than 0
        if self.next_page_button:
            self.next_page_button.setEnabled(has_pdf and current_page < total_pages - 1) # Enable next page button if there is a pdf and current page is less than total pages - 1
        if self.zoom_in_button:
            self.zoom_in_button.setEnabled(has_pdf) # Enable zoom in button if there is a pdf
        if self.zoom_out_button:
            self.zoom_out_button.setEnabled(has_pdf) # Enable zoom out button if there is a pdf
        if self.reset_zoom_button:
            self.reset_zoom_button.setEnabled(has_pdf) # Enable reset zoom button if there is a pdf
        if self.fit_to_window_button:
            self.fit_to_window_button.setEnabled(has_pdf) # Enable fit to window button if there is a pdf
        if self.page_input:
            if has_pdf:
                self.page_input.setText(f"{current_page + 1}/{total_pages}") # Set page input to current page + 1 and total pages
            else:
                self.page_input.setText("0/0") # Set page input to 0/0 if there is no pdf

    def update_zoom_label(self, zoom_factor: float):
        """Update the zoom label with current zoom percentage"""
        if self.zoom_label:
            self.zoom_label.setText(f"{int(zoom_factor * 100)}%") 