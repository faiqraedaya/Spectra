import copy as _copy
import io
import os
import shutil
import tempfile
from typing import List, Optional, Tuple, cast

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, Signal, QThread, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
)
from PySide6.QtWidgets import QLabel, QMenu, QMessageBox
import fitz

class PDFViewer(QLabel):
    """PDF Viewer with zoom and pan"""
    # UI Signals
    zoom_changed = Signal(float) # zoom factor
    bbox_right_clicked = Signal(int)  # index of detection in self.detections
    manual_box_drawn = Signal(tuple)  # (x1, y1, x2, y2)
    bbox_changed = Signal(int, tuple)  # index, new bbox
    background_right_clicked = Signal(QPoint)  # position of right click on background
    bbox_edit_finished = Signal(int)  # index of detection finished editing
    section_drawn = Signal(list)  # list of (x, y) points for new section
    section_right_clicked = Signal(int, object)  # index of section, global position

    def __init__(self):
        super().__init__()
        self.setMinimumSize(800, 600)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("No PDF loaded")

        # PDF handling
        self.pdf_document = None
        self.current_page = 0
        self.total_pages = 0
        self.temp_dir = None
        
        # Page caching to prevent unnecessary re-rendering
        self._page_cache = {}  # page_num -> (pixmap, temp_path)
        self._page_cache_rendered = set()  # Set of page numbers that have been rendered
        
        # Display properties
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        self.zoom_step = 0.2
        self.image_offset = [0, 0]
        
        # Pixmaps
        self.original_pixmap = None
        self.scaled_pixmap = None
        
        # Detection data
        self.detections = []
        
        # Section data
        self.sections = []
        self.section_points = []
        
        # Pan properties
        self.pan_start_pos = None
        self.is_panning = False
        
        # Drawing modes
        self.add_object_mode = False
        self.drawing_box = False
        self.box_start = None
        self.box_end = None
        
        # Section drawing mode
        self.add_section_mode = False
        self.drawing_section = False
        
        # Drag/resize bbox state
        self.selected_bbox_index = None
        self.dragging = False
        self.resizing = False
        self.resize_handle = None
        self.drag_offset = None
        self.resize_start_bbox = None
        self.resize_start_pos = None
        self.handle_size = 8
        
        # Polyline selection state
        self.selected_section_index = None
        self.selected_polyline_index = None
        self._polyline_clipboard = None
        self._polyline_dragging = False
        self._polyline_drag_start_pos = None
        self._polyline_drag_start_points = None
        self._polyline_point_drag_idx = None
        self.debug_mode = True  # Set to True to show detection areas

        # Display update batching
        self._display_update_pending = False
        self._display_update_timer = QTimer()
        self._display_update_timer.setSingleShot(True)
        self._display_update_timer.timeout.connect(self._perform_display_update)
        
        # Enable mouse tracking for pan
        self.setMouseTracking(True)

    def __del__(self):
        """Destructor to ensure cleanup is called when object is destroyed"""
        try:
            self.cleanup()
        except:
            # Ignore errors during destruction
            pass

    def load_pdf(self, pdf_path: str) -> bool:
        """Load PDF and convert pages to images"""
        try:
            # Clean up previous temp directory and cache
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            
            # Clear page cache
            self._page_cache.clear()
            self._page_cache_rendered.clear()

            # Create new temp directory
            self.temp_dir = tempfile.mkdtemp()

            # Open PDF with PyMuPDF
            self.pdf_document = fitz.open(pdf_path)
            self.total_pages = len(self.pdf_document)
            self.current_page = 0

            # Convert first page
            self.render_current_page()
            return True
        except Exception as e:
            QMessageBox.critical(None, "PDF Load Error", f"Failed to load PDF: {str(e)}")
            return False
    
    def render_current_page(self):
        """Render current PDF page to image with caching"""
        if not self.pdf_document or self.current_page >= self.total_pages:
            return
        if self.temp_dir is None:
            return
            
        # Check if page is already cached
        if self.current_page in self._page_cache:
            pixmap, temp_path = self._page_cache[self.current_page]
            self.original_pixmap = pixmap
            self.update_display()
            return
            
        # Render page using helper method
        result = self._render_page_to_cache(self.current_page)
        if result:
            pixmap, temp_path = result
            self.original_pixmap = pixmap
            self.update_display()
    
    def _render_page_to_cache(self, page_num: int) -> Optional[Tuple[QPixmap, str]]:
        """Render a specific page and cache it. Returns (pixmap, temp_path) or None on error."""
        if not self.pdf_document or page_num >= self.total_pages or self.temp_dir is None:
            return None
            
        try:
            # Get page
            page = self.pdf_document[page_num]
            
            # Render at high DPI for quality
            mat = fitz.Matrix(2.0, 2.0)  # 2x scaling for better quality
            pix = page.get_pixmap(matrix=mat)  # type: ignore[attr-defined]
            
            # Convert to PIL Image then to QPixmap
            img_data = pix.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # Convert PIL to QPixmap
            temp_path = os.path.join(self.temp_dir, f"page_{page_num}.png")
            pil_image.save(temp_path)
            
            pixmap = QPixmap(temp_path)
            
            # Cache the rendered page
            self._page_cache[page_num] = (pixmap, temp_path)
            self._page_cache_rendered.add(page_num)
            
            return pixmap, temp_path
            
        except Exception as e:
            QMessageBox.critical(None, "Error Rendering Page", f"Error rendering page {page_num}: {e}")
            return None
        
    def set_page(self, page_num: int):
        """Set current page (0-indexed)"""
        if 0 <= page_num < self.total_pages:
            self.current_page = page_num
            self.image_offset = [0, 0]
            self.render_current_page()
            # Force immediate update for page changes
            self.force_display_update()
        
    def zoom_in(self):
        """Zoom in"""
        if self.zoom_factor < self.max_zoom:
            self.zoom_factor = min(self.zoom_factor + self.zoom_step, self.max_zoom)
            self.update_display()
            self.zoom_changed.emit(self.zoom_factor)

    def zoom_out(self):
        """Zoom out"""
        if self.zoom_factor > self.min_zoom:
            self.zoom_factor = max(self.zoom_factor - self.zoom_step, self.min_zoom)
            self.update_display()
            self.zoom_changed.emit(self.zoom_factor)
        
    def reset_zoom(self):
        """Reset zoom to fit"""
        self.zoom_factor = 1.0
        self.image_offset = [0, 0]
        self.update_display()
        self.zoom_changed.emit(self.zoom_factor)

    def _perform_display_update(self):
        """Internal method to perform the actual display update"""
        self._display_update_pending = False
        if not self.original_pixmap:
            return
        
        # Apply zoom - create scaled pixmap only if needed
        zoomed_size = self.original_pixmap.size() * self.zoom_factor
        
        # Reuse existing scaled pixmap if size matches, otherwise create new one
        if (self.scaled_pixmap is None or 
            self.scaled_pixmap.size() != zoomed_size):
            self.scaled_pixmap = self.original_pixmap.scaled(
                zoomed_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        
        # Create a working copy for drawing detections (don't modify the cached scaled pixmap)
        working_pixmap = QPixmap(self.scaled_pixmap)
        
        # Draw detections if any
        if self.detections:
            self.draw_detections(working_pixmap)
        
        # Display the working pixmap with offset
        self.display_with_offset(working_pixmap)
        
        # Ensure cursor is correct after display update
        if self.add_object_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def update_display(self):
        """Update the display with current zoom and pan - batched to prevent excessive redraws"""
        if not self._display_update_pending:
            self._display_update_pending = True
            self._display_update_timer.start(16)  # ~60 FPS, batches rapid calls
    
    def force_display_update(self):
        """Force immediate display update - use sparingly for operations that can't be batched"""
        if self._display_update_pending:
            self._display_update_timer.stop()
            self._display_update_pending = False
        self._perform_display_update()

    def draw_detections(self, target_pixmap: QPixmap):
        """Draw detection bounding boxes on the target pixmap, with selection/handles"""
        if not target_pixmap or not self.detections:
            return
        painter = QPainter(target_pixmap)
        painter.setFont(QFont("Arial", max(8, int(10 * self.zoom_factor))))
        scale_factor = self.zoom_factor
        for idx, detection in enumerate(self.detections):
            bbox = detection.bbox
            x1, y1, x2, y2 = [int(coord * scale_factor) for coord in bbox]
            # Use detection.color if set, else fallback
            box_color = detection.color if getattr(detection, 'color', None) is not None else (Qt.GlobalColor.blue if idx == self.selected_bbox_index else Qt.GlobalColor.red)
            pen = QPen(box_color, max(3, int(3 * scale_factor)) if idx == self.selected_bbox_index else max(2, int(2 * scale_factor)))
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # Transparent fill
            painter.drawRect(x1, y1, x2-x1, y2-y1)
            # Draw label background
            label = f"{detection.name}: {detection.confidence:.2f}"
            label_width = max(150, int(150 * scale_factor))
            label_height = max(20, int(20 * scale_factor))
            painter.fillRect(x1, y1-label_height, label_width, label_height, box_color)
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.drawText(x1+2, y1-5, label)
            painter.setPen(pen)
            # Draw resize handles if selected
            if idx == self.selected_bbox_index:
                for hx, hy in self.get_handle_positions((x1, y1, x2, y2)):
                    painter.setBrush(Qt.GlobalColor.white)
                    painter.setPen(QPen(Qt.GlobalColor.black, 1))
                    painter.drawRect(hx-self.handle_size//2, hy-self.handle_size//2, self.handle_size, self.handle_size)
        painter.end()

    def set_detections(self, detections):
        """Set detections for current page. Detections must have 1-indexed page_num matching the PDF page."""
        # Ensure this method is thread-safe
        if QThread.currentThread() != self.thread():
            # If called from a different thread, schedule the update on the main thread
            QTimer.singleShot(0, lambda: self._set_detections_safe(detections))
        else:
            # Already on main thread, update directly
            self._set_detections_safe(detections)
    
    def _set_detections_safe(self, detections):
        """Thread-safe internal method to set detections"""
        self.detections = [d for d in detections if d.page_num == self.current_page + 1]
        self.update_display()

    def get_handle_positions(self, bbox):
        # Returns list of (x, y) for 8 handles: tl, tr, bl, br, l, r, t, b
        x1, y1, x2, y2 = bbox
        xm = (x1 + x2) // 2
        ym = (y1 + y2) // 2
        return [
            (x1, y1), (x2, y1), (x1, y2), (x2, y2),  # corners: tl, tr, bl, br
            (x1, ym), (x2, ym), (xm, y1), (xm, y2)   # edges: l, r, t, b
        ]

    def handle_at_pos(self, pos, bbox):
        # Returns handle name if pos is on a handle, else None
        handles = self.get_handle_positions(bbox)
        names = ['tl', 'tr', 'bl', 'br', 'l', 'r', 't', 'b']
        for (hx, hy), name in zip(handles, names):
            # Match the drawn handle area (centered square)
            rect = QRect(hx-self.handle_size//2, hy-self.handle_size//2, self.handle_size, self.handle_size)
            if rect.contains(pos):
                return name
        return None

    def mousePressEvent(self, event: QMouseEvent):
        # Handle drawing modes first
        if self.add_object_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                # Start drawing a box
                self.drawing_box = True
                self.box_start = event.pos()
                self.box_end = event.pos()
                self.update()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                # Cancel object drawing and exit mode
                self.drawing_box = False
                self.box_start = None
                self.box_end = None
                self.set_add_object_mode(False)
                main_window = self.get_main_window()
                if main_window is not None:
                    main_window.exit_add_object_mode()
                return
        
        if self.add_section_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                # Convert widget coordinates to image coordinates
                img_x, img_y = self.widget_to_image_coords(event.pos().x(), event.pos().y())
                # Check for double-click to finish section
                if hasattr(self, '_last_click_time') and hasattr(self, '_last_click_pos'):
                    import time
                    current_time = time.time()
                    if (current_time - self._last_click_time < 0.3 and 
                        abs(event.pos().x() - self._last_click_pos.x()) < 5 and 
                        abs(event.pos().y() - self._last_click_pos.y()) < 5):
                        # Double-click detected - finish section
                        if len(self.section_points) >= 2:
                            self.section_drawn.emit(self.section_points.copy())
                            self.section_points = []
                            self.drawing_section = False
                        self.update()
                        return
                # Single click - add point
                self.section_points.append((img_x, img_y))
                self.drawing_section = True
                # Store click info for double-click detection
                import time
                self._last_click_time = time.time()
                self._last_click_pos = event.pos()
                self.update()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                if not self.section_points:
                    # Exit draw mode if not currently drawing
                    self.set_add_section_mode(False)
                    main_window = self.get_main_window()
                    if main_window is not None:
                        main_window.exit_add_section_mode()
                    return
                # Remove last point
                if self.section_points:
                    self.section_points.pop()
                    if not self.section_points:
                        self.drawing_section = False
                self.update()
                return
            elif event.button() == Qt.MouseButton.MiddleButton:
                self.is_panning = True
                self.pan_start_pos = event.pos()
                self.update()
                return

        # 1. Handle object (bbox) selection and resizing on left click
        if event.button() == Qt.MouseButton.LeftButton:
            if self.scaled_pixmap is None:
                self.selected_section_index = None
                self.selected_polyline_index = None
                self.selected_bbox_index = None
                self.update()
                return
            
            # Check for bbox selection first
            bbox_idx = self.get_bbox_at_pos(event.pos())
            if bbox_idx is not None:
                # Check if clicking on a resize handle
                bbox = self.detections[bbox_idx].bbox
                scale = self.zoom_factor
                x1, y1, x2, y2 = [int(c * scale) for c in bbox]
                # Adjust mouse pos for pan/centering offset
                if self.scaled_pixmap is not None:
                    x_offset = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
                    y_offset = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
                    adj_pos = QPoint(event.pos().x() - x_offset, event.pos().y() - y_offset)
                else:
                    adj_pos = event.pos()
                handle = self.handle_at_pos(adj_pos, (x1, y1, x2, y2))
                
                if handle:
                    # Start resizing
                    self.resizing = True
                    self.resize_handle = handle
                    self.selected_bbox_index = bbox_idx
                    self.resize_start_bbox = list(bbox)
                    self.resize_start_pos = event.pos()
                    self.update()
                    return
                else:
                    # Start dragging
                    self.dragging = True
                    self.selected_bbox_index = bbox_idx
                    self.drag_offset = (event.pos().x(), event.pos().y())
                    self.drag_start_bbox = list(bbox)  # Store original bbox position
                    self.update()
                    return
            else:
                # No bbox clicked, clear selection
                self.selected_bbox_index = None
                self.dragging = False
                self.resizing = False
                self.resize_handle = None
                self.resize_start_bbox = None
                self.resize_start_pos = None
                self.drag_offset = None
                self.drag_start_bbox = None
                self.update()  # Add this line to refresh the display
            # Check for polyline selection with proper priority
            nearest_section = None
            nearest_polyline = None
            nearest_dist = float('inf')
            nearest_s_idx = None
            nearest_p_idx = None
            nearest_seg = None
            nearest_point_idx = None
            
            for s_idx, section in enumerate(self.sections):
                for p_idx, polyline in enumerate(getattr(section, 'polylines', [])):
                    if polyline.page != self.current_page + 1:
                        continue
                    if not polyline.points or len(polyline.points) < 2:
                        continue
                    
                    widget_points = self.convert_polyline_points_to_widget(polyline.points)
                    
                    # Check for point hits FIRST (higher priority)
                    handle_size = max(20, int(25 * self.zoom_factor))  # Larger hit area
                    for idx, pt in enumerate(widget_points):
                        dist = (event.pos() - pt).manhattanLength()
                        if dist < handle_size and dist < nearest_dist:
                            nearest_section = section
                            nearest_polyline = polyline
                            nearest_dist = dist
                            nearest_s_idx = s_idx
                            nearest_p_idx = p_idx
                            nearest_seg = ('point', idx)
                            nearest_point_idx = idx
            
            # Only check for segment hits if no point was hit
            if nearest_seg is None or nearest_seg[0] != 'point':
                for s_idx, section in enumerate(self.sections):
                    for p_idx, polyline in enumerate(getattr(section, 'polylines', [])):
                        if polyline.page != self.current_page + 1:
                            continue
                        if not polyline.points or len(polyline.points) < 2:
                            continue
                        
                        widget_points = self.convert_polyline_points_to_widget(polyline.points)
                        
                        # Check for segment hits
                        for i in range(len(widget_points) - 1):
                            a = widget_points[i]
                            b = widget_points[i+1]
                            abx = b.x() - a.x()
                            aby = b.y() - a.y()
                            apx = event.pos().x() - a.x()
                            apy = event.pos().y() - a.y()
                            ab_len_sq = abx * abx + aby * aby
                            t = 0 if ab_len_sq == 0 else max(0, min(1, (apx * abx + apy * aby) / ab_len_sq))
                            closest_x = a.x() + t * abx
                            closest_y = a.y() + t * aby
                            dist_sq = (event.pos().x() - closest_x) ** 2 + (event.pos().y() - closest_y) ** 2
                            if dist_sq < 144 and dist_sq < nearest_dist ** 2:  # 12px threshold
                                nearest_section = section
                                nearest_polyline = polyline
                                nearest_dist = dist_sq ** 0.5
                                nearest_s_idx = s_idx
                                nearest_p_idx = p_idx
                                nearest_seg = ('segment', i)
            
            # Select the nearest polyline if any
            if nearest_section is not None:
                self.selected_section_index = nearest_s_idx
                self.selected_polyline_index = nearest_p_idx
                self.update()
                
                # Handle point drag with higher priority
                if nearest_seg and nearest_seg[0] == 'point':
                    self._polyline_point_drag_idx = nearest_seg[1]
                    return
                # Handle segment drag only if no point was selected
                elif nearest_seg and nearest_seg[0] == 'segment':
                    self._polyline_dragging = True
                    self._polyline_drag_start_pos = event.pos()
                    if self.selected_section_index is not None and self.selected_polyline_index is not None:
                        s_idx = int(self.selected_section_index)
                        p_idx = int(self.selected_polyline_index)
                        section = self.sections[s_idx]
                        polyline = section.polylines[p_idx]
                        self._polyline_drag_start_points = [tuple(pt) for pt in polyline.points]
                    return
            else:
                self.selected_section_index = None
                self.selected_polyline_index = None
                self.update()
                return
        # 4. Right-click logic for context menu
        if event.button() == Qt.MouseButton.RightButton:
            # Check for bbox right-click first
            bbox_idx = self.get_bbox_at_pos(event.pos())
            if bbox_idx is not None:
                self.bbox_right_clicked.emit(bbox_idx)
                return
            
            # Check for section right-click
            if self.selected_section_index is not None and self.selected_polyline_index is not None:
                if self.scaled_pixmap is None:
                    return
                if self.selected_section_index is None or self.selected_polyline_index is None:
                    return
                s_idx = int(self.selected_section_index)
                p_idx = int(self.selected_polyline_index)
                section = self.sections[s_idx]
                polyline = section.polylines[p_idx]
                widget_points = self.convert_polyline_points_to_widget(polyline.points)
                # Check for handle hit
                for idx, pt in enumerate(widget_points):
                    handle_size = max(20, int(25 * self.zoom_factor))
                    if (event.pos() - pt).manhattanLength() < handle_size:
                        self.show_polyline_point_context_menu(idx, event.globalPos())
                        return
                # Check for segment hit
                for i in range(len(widget_points) - 1):
                    a = widget_points[i]
                    b = widget_points[i+1]
                    abx = b.x() - a.x()
                    aby = b.y() - a.y()
                    apx = event.pos().x() - a.x()
                    apy = event.pos().y() - a.y()
                    ab_len_sq = abx * abx + aby * aby
                    t = 0 if ab_len_sq == 0 else max(0, min(1, (apx * abx + apy * aby) / ab_len_sq))
                    closest_x = a.x() + t * abx
                    closest_y = a.y() + t * aby
                    dist_sq = (event.pos().x() - closest_x) ** 2 + (event.pos().y() - closest_y) ** 2
                    if dist_sq < 100:
                        self.show_polyline_add_point_context_menu(i + 1, (closest_x, closest_y), event.globalPos())
                        return
                # Otherwise, show section context menu
                self.show_polyline_context_menu(self.selected_section_index, self.selected_polyline_index, event.globalPos())
                return
            
            # Background right-click - emit signal for context menu
            self.background_right_clicked.emit(event.pos())
            return
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.pan_start_pos = event.pos()
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.add_object_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
            if self.is_panning and self.pan_start_pos is not None:
                delta = event.pos() - self.pan_start_pos
                self.image_offset[0] += delta.x()
                self.image_offset[1] += delta.y()
                self.pan_start_pos = event.pos()
                self.update_display()
                return
            if self.drawing_box:
                self.box_end = event.pos()
                self.update()
                return
            return  # Always use plus cursor in add object mode, skip other cursor logic
        
        if self.add_section_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
            if self.is_panning and self.pan_start_pos is not None:
                delta = event.pos() - self.pan_start_pos
                self.image_offset[0] += delta.x()
                self.image_offset[1] += delta.y()
                self.pan_start_pos = event.pos()
                self.update_display()
                return
            # Update the preview line for section drawing
            if self.drawing_section and self.section_points:
                self.update()
                return
            return  # Always use plus cursor in add section mode, skip other cursor logic
        if self.resizing and self.selected_bbox_index is not None and self.resize_start_bbox is not None and self.resize_start_pos is not None:
            # Resize bbox
            idx = self.selected_bbox_index
            bbox = list(self.detections[idx].bbox)
            scale = self.zoom_factor
            x1, y1, x2, y2 = [int(c * scale) for c in bbox]
            orig_bbox = list(self.resize_start_bbox)
            dx = (int(event.pos().x()) - int(self.resize_start_pos.x())) / scale
            dy = (int(event.pos().y()) - int(self.resize_start_pos.y())) / scale
            # Update bbox based on handle
            if self.resize_handle == 'tl':
                bbox[0] = int(round(orig_bbox[0] + dx))
                bbox[1] = int(round(orig_bbox[1] + dy))
            elif self.resize_handle == 'tr':
                bbox[2] = int(round(orig_bbox[2] + dx))
                bbox[1] = int(round(orig_bbox[1] + dy))
            elif self.resize_handle == 'bl':
                bbox[0] = int(round(orig_bbox[0] + dx))
                bbox[3] = int(round(orig_bbox[3] + dy))
            elif self.resize_handle == 'br':
                bbox[2] = int(round(orig_bbox[2] + dx))
                bbox[3] = int(round(orig_bbox[3] + dy))
            elif self.resize_handle == 'l':
                bbox[0] = int(round(orig_bbox[0] + dx))
            elif self.resize_handle == 'r':
                bbox[2] = int(round(orig_bbox[2] + dx))
            elif self.resize_handle == 't':
                bbox[1] = int(round(orig_bbox[1] + dy))
            elif self.resize_handle == 'b':
                bbox[3] = int(round(orig_bbox[3] + dy))
            # Clamp to image bounds and ensure min size
            min_size = 5
            bbox[0] = max(0, min(bbox[0], bbox[2]-min_size))
            bbox[1] = max(0, min(bbox[1], bbox[3]-min_size))
            bbox[2] = max(bbox[0]+min_size, bbox[2])
            bbox[3] = max(bbox[1]+min_size, bbox[3])
            
            # Use safe bbox validation and casting
            self.detections[idx].bbox = self._validate_and_cast_bbox(bbox, min_size)
            # Only update display, bbox_changed signal will be emitted on mouse release
            self.update_display()
            # Set resize cursor
            handle_cursor_map = {
                'tl': Qt.CursorShape.SizeFDiagCursor,
                'br': Qt.CursorShape.SizeFDiagCursor,
                'tr': Qt.CursorShape.SizeBDiagCursor,
                'bl': Qt.CursorShape.SizeBDiagCursor,
                'l': Qt.CursorShape.SizeHorCursor,
                'r': Qt.CursorShape.SizeHorCursor,
                't': Qt.CursorShape.SizeVerCursor,
                'b': Qt.CursorShape.SizeVerCursor,
            }
            if self.resize_handle in handle_cursor_map:
                self.setCursor(handle_cursor_map[self.resize_handle])
            return
        if self.dragging and self.selected_bbox_index is not None and self.drag_offset is not None and self.drag_start_bbox is not None:
            idx = self.selected_bbox_index
            bbox = list(self.detections[idx].bbox)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            
            # Calculate mouse movement in widget coordinates
            mouse_delta_x = event.pos().x() - self.drag_offset[0]
            mouse_delta_y = event.pos().y() - self.drag_offset[1]
            
            # Convert mouse delta to image coordinates
            delta_img_x = mouse_delta_x / self.zoom_factor
            delta_img_y = mouse_delta_y / self.zoom_factor
            
            # Apply the delta to the original bbox position
            bbox[0] = int(round(self.drag_start_bbox[0] + delta_img_x))
            bbox[1] = int(round(self.drag_start_bbox[1] + delta_img_y))
            bbox[2] = bbox[0] + w
            bbox[3] = bbox[1] + h
            
            # Clamp to image bounds
            bbox[0] = max(0, min(bbox[0], bbox[2]-1))
            bbox[1] = max(0, min(bbox[1], bbox[3]-1))
            bbox[2] = max(bbox[0]+1, bbox[2])
            bbox[3] = max(bbox[1]+1, bbox[3])
            
            # Use safe bbox validation and casting
            self.detections[idx].bbox = self._validate_and_cast_bbox(bbox, 1)
            # Only update display, bbox_changed signal will be emitted on mouse release
            self.update_display()
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return
        # Polyline drag
        if self._polyline_dragging and self._polyline_drag_start_pos is not None and self._polyline_drag_start_points is not None:
            if self.scaled_pixmap is None:
                return
            if self.selected_section_index is not None and self.selected_polyline_index is not None:
                s_idx = int(self.selected_section_index)
                p_idx = int(self.selected_polyline_index)
                section = self.sections[s_idx]
                polyline = section.polylines[p_idx]
                dx = event.pos().x() - self._polyline_drag_start_pos.x()
                dy = event.pos().y() - self._polyline_drag_start_pos.y()
                new_points = []
                for (x, y) in self._polyline_drag_start_points:
                    if self.scaled_pixmap is not None:
                        img_x, img_y = self.widget_to_image_coords(
                            int(x * self.zoom_factor + (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0] + dx),
                            int(y * self.zoom_factor + (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1] + dy)
                        )
                    else:
                        img_x, img_y = self.widget_to_image_coords(event.pos().x() + dx, event.pos().y() + dy)
                    new_points.append((img_x, img_y))
                polyline.points = new_points
                self.setCursor(Qt.CursorShape.SizeAllCursor)  # Show move cursor during polyline drag
                self.update()
                return
        # Polyline point drag
        if self._polyline_point_drag_idx is not None:
            if self.selected_section_index is not None and self.selected_polyline_index is not None:
                s_idx = int(self.selected_section_index)
                p_idx = int(self.selected_polyline_index)
                section = self.sections[s_idx]
                polyline = section.polylines[p_idx]
                idx = self._polyline_point_drag_idx
                # Convert widget pos to image coords
                img_x, img_y = self.widget_to_image_coords(event.pos().x(), event.pos().y())
                polyline.points[idx] = (img_x, img_y)
                self.setCursor(Qt.CursorShape.SizeAllCursor)  # Show move cursor during point drag
                self.update()
                return
        # Not dragging or resizing: set cursor based on hover
        # Check for polyline point hover first with larger hit area
        if not self.add_object_mode and not self.add_section_mode:
            point_hover = False
            if self.selected_section_index is not None and self.selected_polyline_index is not None:
                s_idx = int(self.selected_section_index)
                p_idx = int(self.selected_polyline_index)
                section = self.sections[s_idx]
                polyline = section.polylines[p_idx]
                
                if polyline.page == self.current_page + 1 and self.scaled_pixmap:
                    widget_points = self.convert_polyline_points_to_widget(polyline.points)
                    
                    # Check if hovering over any point with larger hit area
                    handle_size = max(20, int(25 * self.zoom_factor))
                    for pt in widget_points:
                        if (event.pos() - pt).manhattanLength() <= handle_size:
                            self.setCursor(Qt.CursorShape.PointingHandCursor)  # Different cursor for points
                            point_hover = True
                            break
            
            if not point_hover:
                # Check for bbox hover
                idx = self.get_bbox_at_pos(event.pos())
                if idx is not None:
                    bbox = self.detections[idx].bbox
                    scale = self.zoom_factor
                    x1, y1, x2, y2 = [int(c * scale) for c in bbox]
                    # Adjust mouse pos for pan/centering offset
                    if self.scaled_pixmap:
                        x_offset = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
                        y_offset = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
                        adj_pos = QPoint(event.pos().x() - x_offset, event.pos().y() - y_offset)
                    else:
                        adj_pos = event.pos()
                    handle = self.handle_at_pos(adj_pos, (x1, y1, x2, y2))
                    handle_cursor_map = {
                        'tl': Qt.CursorShape.SizeFDiagCursor,
                        'br': Qt.CursorShape.SizeFDiagCursor,
                        'tr': Qt.CursorShape.SizeBDiagCursor,
                        'bl': Qt.CursorShape.SizeBDiagCursor,
                        'l': Qt.CursorShape.SizeHorCursor,
                        'r': Qt.CursorShape.SizeHorCursor,
                        't': Qt.CursorShape.SizeVerCursor,
                        'b': Qt.CursorShape.SizeVerCursor,
                    }
                    if handle in handle_cursor_map:
                        self.setCursor(handle_cursor_map[handle])
                    else:
                        self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
        if self.is_panning and self.pan_start_pos is not None:
            delta = event.pos() - self.pan_start_pos
            self.image_offset[0] += delta.x()
            self.image_offset[1] += delta.y()
            self.pan_start_pos = event.pos()
            self.update_display()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.add_object_mode and self.drawing_box:
            if event.button() == Qt.MouseButton.LeftButton:
                self.drawing_box = False
                if self.box_start is not None and self.box_end is not None and hasattr(self.box_start, 'isNull') and hasattr(self.box_end, 'isNull') and not self.box_start.isNull() and not self.box_end.isNull():
                    x1 = min(self.box_start.x(), self.box_end.x())
                    y1 = min(self.box_start.y(), self.box_end.y())
                    x2 = max(self.box_start.x(), self.box_end.x())
                    y2 = max(self.box_start.y(), self.box_end.y())
                    # Convert widget coords to image coords
                    img_x1, img_y1 = self.widget_to_image_coords(x1, y1)
                    img_x2, img_y2 = self.widget_to_image_coords(x2, y2)
                    self.manual_box_drawn.emit((int(img_x1), int(img_y1), int(img_x2), int(img_y2)))
                self.box_start = None
                self.box_end = None
                self.update()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                # Cancel object drawing
                self.drawing_box = False
                self.box_start = None
                self.box_end = None
                self.update()
                return
        if self.resizing:
            self.resizing = False
            self.resize_handle = None
            self.resize_start_bbox = None
            self.resize_start_pos = None
            # Emit bbox_changed signal when resizing is finished
            if self.selected_bbox_index is not None:
                self.bbox_changed.emit(self.selected_bbox_index, self.detections[self.selected_bbox_index].bbox)
                self.bbox_edit_finished.emit(self.selected_bbox_index)
            self.update()
            return
        if self.dragging:
            self.dragging = False
            self.drag_offset = None
            self.drag_start_bbox = None
            # Emit bbox_changed signal when dragging is finished
            if self.selected_bbox_index is not None:
                self.bbox_changed.emit(self.selected_bbox_index, self.detections[self.selected_bbox_index].bbox)
                self.bbox_edit_finished.emit(self.selected_bbox_index)
            self.update()
            return
        # End polyline point drag (for both left and right mouse buttons)
        if self._polyline_point_drag_idx is not None:
            if self.selected_section_index is not None and self.selected_polyline_index is not None:
                s_idx = int(self.selected_section_index)
                p_idx = int(self.selected_polyline_index)
                section = self.sections[s_idx]
                polyline = section.polylines[p_idx]
                idx = self._polyline_point_drag_idx
                # Convert widget pos to image coords
                img_x, img_y = self.widget_to_image_coords(event.pos().x(), event.pos().y())
                polyline.points[idx] = (img_x, img_y)
                self._polyline_point_drag_idx = None
                self.update()
                return
        
        # End polyline drag (for both left and right mouse buttons)
        if self._polyline_dragging:
            if self.selected_section_index is not None and self.selected_polyline_index is not None:
                self._polyline_dragging = False
                self._polyline_drag_start_pos = None
                self._polyline_drag_start_points = None
                self.update()
                return
        
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = False
            self.pan_start_pos = None
        else:
            super().mouseReleaseEvent(event)

    def get_page_image_paths(self) -> List[str]:
        """Get paths to all page images for analysis with caching"""
        if not self.pdf_document:
            return []
        if self.temp_dir is None:
            return []
        image_paths = []
        for page_num in range(self.total_pages):
            try:
                # Check if page is already cached
                if page_num in self._page_cache:
                    _, temp_path = self._page_cache[page_num]
                    image_paths.append(temp_path)
                    continue
                
                # Render page if not cached
                result = self._render_page_to_cache(page_num)
                if result:
                    _, temp_path = result
                    image_paths.append(temp_path)
            except Exception as e:
                QMessageBox.critical(None, "Error Converting Page", f"Error converting page {page_num}: {e}")
        return image_paths
    
    def cleanup(self):
        """Clean up temporary files and reset all state variables to prevent memory leaks"""
        # Close and clear PDF document
        if self.pdf_document:
            self.pdf_document.close()
            self.pdf_document = None  # Prevent further access

        # Remove temporary directory
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None

        # Clear page cache
        self._page_cache.clear()
        self._page_cache_rendered.clear()

        # Reset PDF handling state
        self.current_page = 0
        self.total_pages = 0

        # Reset display properties
        self.zoom_factor = 1.0
        self.image_offset = [0, 0]

        # Clear pixmaps to free memory
        if self.original_pixmap:
            self.original_pixmap = None
        if self.scaled_pixmap:
            self.scaled_pixmap = None

        # Clear all data structures that might hold references
        self.detections.clear()
        self.sections.clear()
        self.section_points.clear()

        # Reset pan properties
        self.pan_start_pos = None
        self.is_panning = False

        # Reset drawing modes
        self.add_object_mode = False
        self.drawing_box = False
        self.box_start = None
        self.box_end = None

        # Reset section drawing mode
        self.add_section_mode = False
        self.drawing_section = False

        # Reset drag/resize bbox state
        self.selected_bbox_index = None
        self.dragging = False
        self.resizing = False
        self.resize_handle = None
        self.drag_offset = None
        self.resize_start_bbox = None
        self.resize_start_pos = None

        # Reset polyline selection state
        self.selected_section_index = None
        self.selected_polyline_index = None
        self._polyline_clipboard = None
        self._polyline_dragging = False
        self._polyline_drag_start_pos = None
        self._polyline_drag_start_points = None
        self._polyline_point_drag_idx = None

        # Reset cursor and display
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setText("No PDF loaded")
        self.update()

    def _validate_and_cast_bbox(self, bbox: list, min_size: int = 1) -> Tuple[int, int, int, int]:
        """Validate bbox list and safely cast to Tuple[int, int, int, int]"""
        if len(bbox) >= 4:
            # Ensure all values are valid integers and maintain minimum size
            x1, y1, x2, y2 = [int(round(v)) for v in bbox[:4]]
            # Ensure minimum size
            if x2 - x1 < min_size:
                x2 = x1 + min_size
            if y2 - y1 < min_size:
                y2 = y1 + min_size
            return cast(Tuple[int, int, int, int], (x1, y1, x2, y2))
        else:
            # Fallback: create a valid bbox with minimum size
            return cast(Tuple[int, int, int, int], (0, 0, min_size, min_size))

    def get_bbox_at_pos(self, pos: QPoint) -> Optional[int]:
        """Return index of detection whose bbox contains the given widget pos, or None"""
        if not self.detections or not self.scaled_pixmap:
            return None
        # Calculate offset for pan
        x_offset = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
        y_offset = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
        # Adjust pos for pan and zoom
        x = (pos.x() - x_offset) / self.zoom_factor
        y = (pos.y() - y_offset) / self.zoom_factor
        for idx, detection in enumerate(self.detections):
            x1, y1, x2, y2 = detection.bbox
            if x1 <= x <= x2 and y1 <= y <= y2:
                return idx
        return None

    def get_polyline_point_at_pos(self, pos: QPoint) -> Optional[int]:
        """Return index of polyline point at the given widget pos, or None"""
        if not self.sections or not self.scaled_pixmap:
            return None
        
        # Check if we have a selected polyline
        if self.selected_section_index is None or self.selected_polyline_index is None:
            return None
            
        s_idx = int(self.selected_section_index)
        p_idx = int(self.selected_polyline_index)
        section = self.sections[s_idx]
        polyline = section.polylines[p_idx]
        
        if polyline.page != self.current_page + 1:
            return None
            
        # Convert polyline points to widget coordinates
        widget_points = self.convert_polyline_points_to_widget(polyline.points)
        
        # Check if mouse is over any point
        handle_size = max(20, int(25 * self.zoom_factor))  # Larger hit area for consistency
        for idx, pt in enumerate(widget_points):
            dist = (pos - pt).manhattanLength()
            if dist <= handle_size:
                return idx
        return None    

    def fit_to_window(self):
        """Fit the PDF page to the window size"""
        if not self.original_pixmap:
            return
        widget_width = self.width()
        widget_height = self.height()
        pixmap_width = self.original_pixmap.width()
        pixmap_height = self.original_pixmap.height()
        if pixmap_width == 0 or pixmap_height == 0:
            return
        # Calculate scale to fit both width and height
        scale_w = widget_width / pixmap_width
        scale_h = widget_height / pixmap_height
        self.zoom_factor = min(scale_w, scale_h)
        self.image_offset = [0, 0]
        self.update_display()
        self.zoom_changed.emit(self.zoom_factor)

    def set_add_object_mode(self, enabled: bool):
        self.add_object_mode = enabled
        if enabled:
            # Exit section mode if it was active
            self.add_section_mode = False
            self.section_points = []
            self.drawing_section = False
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.drawing_box = False
            self.box_start = None
            self.box_end = None
        self.update()

    def set_add_section_mode(self, enabled: bool):
        """Enable/disable section drawing mode"""
        self.add_section_mode = enabled
        if enabled:
            # Exit object mode if it was active
            self.add_object_mode = False
            self.drawing_box = False
            self.box_start = None
            self.box_end = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.section_points = []
            self.drawing_section = False
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.section_points = []
            self.drawing_section = False
        self.update()

    def set_sections(self, sections):
        """Set the sections to display"""
        self.sections = sections
        self.update()

    def get_section_at_pos(self, pos: QPoint) -> Optional[int]:
        """Get section index at given position, or None if not found"""
        if not self.sections:
            return None
        
        # Convert widget coordinates to image coordinates
        img_x, img_y = self.widget_to_image_coords(pos.x(), pos.y())
        
        for i, section in enumerate(self.sections):
            for polyline in getattr(section, 'polylines', []):
                if polyline.page != self.current_page + 1:
                    continue
                if not polyline.points or len(polyline.points) < 2:
                    continue
                # Simple point-in-polygon test using ray casting
                if self._point_in_polygon(img_x, img_y, polyline.points):
                    return i
        
        return None

    def _point_in_polygon(self, x: float, y: float, points: List[Tuple[float, float]]) -> bool:
        """Ray casting algorithm to test if point is inside polygon"""
        if len(points) < 3:
            return False
        
        inside = False
        j = len(points) - 1
        
        for i in range(len(points)):
            xi, yi = points[i]
            xj, yj = points[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside

    def keyPressEvent(self, event):
        # Polyline clipboard shortcuts
        if (self.selected_section_index is not None and self.selected_polyline_index is not None):
            if event.key() == Qt.Key.Key_Delete:
                self.delete_selected_polyline()
                return
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_C:
                    self.copy_selected_polyline()
                    return
                elif event.key() == Qt.Key.Key_X:
                    self.cut_selected_polyline()
                    return
                elif event.key() == Qt.Key.Key_V:
                    self.paste_polyline_to_section(self.selected_section_index)
                    return
        if self.add_object_mode and event.key() == Qt.Key.Key_Escape:
            self.set_add_object_mode(False)
            main_window = self.get_main_window()
            if main_window is not None:
                main_window.exit_add_object_mode()
        elif self.add_section_mode and event.key() == Qt.Key.Key_Escape:
            self.set_add_section_mode(False)
            main_window = self.get_main_window()
            if main_window is not None:
                main_window.exit_add_section_mode()
            return  # Prevent further event handling
        super().keyPressEvent(event)

    def widget_to_image_coords(self, x, y):
        """Convert widget coordinates to image coordinates"""
        if not self.scaled_pixmap:
            return x, y
        x_offset = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
        y_offset = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
        img_x = (x - x_offset) / self.zoom_factor
        img_y = (y - y_offset) / self.zoom_factor
        return img_x, img_y

    def image_to_widget_coords(self, x, y):
        """Convert image coordinates to widget coordinates"""
        if not self.scaled_pixmap:
            return x, y
        x_offset = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
        y_offset = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
        widget_x = int(x * self.zoom_factor + x_offset)
        widget_y = int(y * self.zoom_factor + y_offset)
        return widget_x, widget_y

    def convert_polyline_points_to_widget(self, points):
        """Convert a list of image coordinate points to widget coordinates"""
        if not self.scaled_pixmap or not points:
            return []
        
        widget_points = []
        for x, y in points:
            widget_x, widget_y = self.image_to_widget_coords(x, y)
            widget_points.append(QPoint(widget_x, widget_y))
        return widget_points

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        
        # Draw sections
        if self.sections:
            self._draw_sections(painter)
        
        # Draw preview box overlay if in add object mode and drawing
        if self.add_object_mode and self.drawing_box and self.box_start is not None and self.box_end is not None and hasattr(self.box_start, 'isNull') and hasattr(self.box_end, 'isNull') and not self.box_start.isNull() and not self.box_end.isNull():
            # Calculate pixmap offset
            if self.scaled_pixmap:
                offset_start = self.box_start
                offset_end = self.box_end
                preview_rect = QRect(offset_start, offset_end)
                painter.setPen(QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(preview_rect)
        
        # Draw section preview if in add section mode
        if self.add_section_mode and self.drawing_section and self.section_points:
            self._draw_section_preview(painter)
        
        painter.end()

    def safe_int(self, val):
        try:
            return int(val)
        except Exception:
            return 0

    def _draw_sections(self, painter: QPainter):
        """Draw all sections on the viewer"""
        if self.scaled_pixmap is None:
            return
        for s_idx, section in enumerate(self.sections):
            for p_idx, polyline in enumerate(getattr(section, 'polylines', [])):
                if polyline.page != self.current_page + 1:
                    continue
                if not polyline.points or len(polyline.points) < 2:
                    continue
                widget_points = self.convert_polyline_points_to_widget(polyline.points)
                if len(widget_points) < 2:
                    continue
                is_selected = (s_idx == self.selected_section_index and p_idx == self.selected_polyline_index)
                pen_width = max(12, int(16 * self.zoom_factor)) if not is_selected else max(18, int(22 * self.zoom_factor))
                if section.color:
                    color = QColor(section.color)
                else:
                    color = QColor(Qt.GlobalColor.blue)
                if is_selected:
                    color = QColor(Qt.GlobalColor.red)
                    color.setAlpha(200)
                else:
                    color.setAlpha(128)  # 50% opacity
                painter.setPen(QPen(color, pen_width, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygon(widget_points))
                # Draw section name label at the first point with border and background
                label_point = widget_points[0]
                label_font = QFont("Arial", max(14, int(16 * self.zoom_factor)), QFont.Weight.Bold)
                painter.setFont(label_font)
                label_text = section.name
                metrics = painter.fontMetrics()
                text_width = metrics.horizontalAdvance(label_text)
                text_height = metrics.height()
                padding = 8
                rect_x = self.safe_int(label_point.x() + 6)
                rect_y = self.safe_int(label_point.y() - text_height - 6)
                rect_w = self.safe_int(text_width + 2 * padding)
                rect_h = self.safe_int(text_height + 2 * padding // 2)
                painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
                painter.setPen(QPen(section.color if section.color else Qt.GlobalColor.blue, 3))
                painter.drawRect(rect_x, rect_y, rect_w, rect_h)
                painter.setPen(QPen(Qt.GlobalColor.black, 1))
                painter.drawText(rect_x + padding, rect_y + text_height + padding // 4 - 2, label_text)
                # Always show handles for selected polyline
                if is_selected:
                    # Draw larger, more visible handles
                    painter.setBrush(QBrush(Qt.GlobalColor.yellow))  # More visible color
                    painter.setPen(QPen(Qt.GlobalColor.black, max(3, int(4 * self.zoom_factor))))
                    handle_size = max(10, int(14 * self.zoom_factor))  # Reasonable visual handles
                    
                    for i, pt in enumerate(widget_points):
                        # Draw outer circle for better visibility
                        painter.setBrush(QBrush(Qt.GlobalColor.red))
                        painter.drawEllipse(QPoint(self.safe_int(pt.x()), self.safe_int(pt.y())), handle_size + 4, handle_size + 4)
                        # Draw inner circle
                        painter.setBrush(QBrush(Qt.GlobalColor.yellow))
                        painter.drawEllipse(QPoint(self.safe_int(pt.x()), self.safe_int(pt.y())), handle_size, handle_size)
                        
                        # Add point index for debugging
                        if getattr(self, 'debug_mode', False):
                            painter.setPen(QPen(Qt.GlobalColor.black, 1))
                            painter.drawText(self.safe_int(pt.x() + handle_size//2), self.safe_int(pt.y() - handle_size//2), str(i))
                            painter.setPen(QPen(Qt.GlobalColor.black, max(3, int(4 * self.zoom_factor))))

    def _draw_section_preview(self, painter: QPainter):
        """Draw preview of section being drawn"""
        if not self.section_points or len(self.section_points) < 1:
            return
        
        # Convert image coordinates to widget coordinates
        widget_points = self.convert_polyline_points_to_widget(self.section_points)
        
        # Draw lines between points
        painter.setPen(QPen(Qt.GlobalColor.green, max(2, int(3 * self.zoom_factor)), Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        for i in range(len(widget_points) - 1):
            painter.drawLine(widget_points[i], widget_points[i + 1])
        
        # Draw points
        painter.setBrush(QBrush(Qt.GlobalColor.green))
        for point in widget_points:
            painter.drawEllipse(QPoint(self.safe_int(point.x()), self.safe_int(point.y())), 4, 4)

    def get_main_window(self):
        # Helper to find the main window for exit_add_object_mode
        parent = self.parent()
        try:
            from core.main_window import Spectra
        except ImportError:
            Spectra = None
        while parent is not None:
            if Spectra is not None and isinstance(parent, Spectra):
                return parent
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return None

    def display_with_offset(self, pixmap_to_display: Optional[QPixmap] = None):
        """Display pixmap with pan offset and draw manual box preview if needed"""
        # Use provided pixmap or fall back to scaled pixmap
        source_pixmap = pixmap_to_display if pixmap_to_display is not None else self.scaled_pixmap
        
        if source_pixmap is None:
            return
            
        # Create a pixmap the size of the widget
        display_pixmap = QPixmap(self.size())
        display_pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(display_pixmap)
        
        # Calculate position with offset
        x = (self.width() - source_pixmap.width()) // 2 + self.image_offset[0]
        y = (self.height() - source_pixmap.height()) // 2 + self.image_offset[1]
        
        painter.drawPixmap(x, y, source_pixmap)
        painter.end()
        
        self.setPixmap(display_pixmap)
        self.resize(source_pixmap.size())

    def wheelEvent(self, event):
        # Ctrl+Wheel: zoom, Shift+Wheel: pan left/right, else pan up/down
        modifiers = event.modifiers()
        angle = event.angleDelta().y()
        
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Zoom in/out, centered on mouse position
            if not self.scaled_pixmap:
                return
                
            # Get mouse position relative to widget
            mouse_pos = event.position() if hasattr(event, 'position') else event.posF()
            mouse_x, mouse_y = mouse_pos.x(), mouse_pos.y()
            
            # Calculate current image position and size
            img_x = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
            img_y = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
            
            # Calculate mouse position relative to image
            rel_x = (mouse_x - img_x) / self.zoom_factor
            rel_y = (mouse_y - img_y) / self.zoom_factor
                        
            # Perform zoom
            if angle > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            
            # Calculate new image position to keep mouse point fixed
            new_zoom = self.zoom_factor
            new_img_x = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
            new_img_y = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
            
            # Adjust offset to keep the same image point under mouse
            target_x = mouse_x - rel_x * new_zoom
            target_y = mouse_y - rel_y * new_zoom
            
            self.image_offset[0] += int(target_x - new_img_x)
            self.image_offset[1] += int(target_y - new_img_y)
            
            # Single update_display call for zoom operation
            self.update_display()
            self.zoom_changed.emit(self.zoom_factor)
        else:
            # Pan operations (both Shift+Wheel and regular wheel)
            delta = event.angleDelta().y() // 8  # 1 notch = 15 degrees, 120 units
            
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                # Pan left/right
                self.image_offset[0] += int(delta)
            else:
                # Pan up/down
                self.image_offset[1] += int(delta)
            
            # Single update_display call for pan operation
            self.update_display()

    def leaveEvent(self, event):
        if not self.add_object_mode:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def show_polyline_context_menu(self, section_idx, polyline_idx, global_pos):
        menu = QMenu(self)
        cut_action = menu.addAction("Cut Polyline")
        copy_action = menu.addAction("Copy Polyline")
        paste_action = menu.addAction("Paste Polyline")
        delete_action = menu.addAction("Delete Polyline")
        paste_action.setEnabled(self._polyline_clipboard is not None and self.selected_section_index is not None)
        action = menu.exec(global_pos)
        if action == cut_action:
            self.cut_selected_polyline()
        elif action == copy_action:
            self.copy_selected_polyline()
        elif action == paste_action:
            self.paste_polyline_to_section(self.selected_section_index)
        elif action == delete_action:
            self.delete_selected_polyline()
        self.update()

    def cut_selected_polyline(self):
        self.copy_selected_polyline()
        self.delete_selected_polyline()

    def copy_selected_polyline(self):
        if self.selected_section_index is not None and self.selected_polyline_index is not None:
            s_idx = int(self.selected_section_index)
            p_idx = int(self.selected_polyline_index)
            section = self.sections[s_idx]
            polyline = section.polylines[p_idx]
            
            self._polyline_clipboard = _copy.deepcopy(polyline)

    def paste_polyline_to_section(self, section_idx):
        if self._polyline_clipboard is not None and section_idx is not None:
            polyline = _copy.deepcopy(self._polyline_clipboard)
            # Optionally, set to current page
            polyline.page = self.current_page + 1
            self.sections[section_idx].polylines.append(polyline)
            self.selected_polyline_index = len(self.sections[section_idx].polylines) - 1
            self.selected_section_index = section_idx
            self.update()

    def delete_selected_polyline(self):
        if self.selected_section_index is not None and self.selected_polyline_index is not None:
            s_idx = int(self.selected_section_index)
            p_idx = int(self.selected_polyline_index)
            section = self.sections[s_idx]
            if 0 <= p_idx < len(section.polylines):
                del section.polylines[p_idx]
                # Adjust selection
                if p_idx >= len(section.polylines):
                    self.selected_polyline_index = len(section.polylines) - 1 if section.polylines else None
                self.update()

    def paste_polyline_at_pos(self, pos: QPoint):
        """Paste polyline from clipboard at the given widget position, into the first section (or selected section if available)."""
        if self._polyline_clipboard is not None and self.sections:
            polyline = _copy.deepcopy(self._polyline_clipboard)
            # Place first point at pos, keep shape
            if polyline.points:
                # Compute offset from first point to pos (in image coords)
                img_x, img_y = self.widget_to_image_coords(pos.x(), pos.y())
                orig_x, orig_y = polyline.points[0]
                dx = img_x - orig_x
                dy = img_y - orig_y
                polyline.points = [(x + dx, y + dy) for (x, y) in polyline.points]
                polyline.page = self.current_page + 1
                # Paste into selected section if any, else first section
                section_idx = self.selected_section_index if self.selected_section_index is not None else 0
                self.sections[section_idx].polylines.append(polyline)
                self.selected_section_index = section_idx
                self.selected_polyline_index = len(self.sections[section_idx].polylines) - 1
                self.update()

    def show_polyline_point_context_menu(self, point_idx, global_pos):
        menu = QMenu(self)
        delete_action = menu.addAction("Delete Point")
        action = menu.exec(global_pos)
        if action == delete_action:
            s_idx = int(self.selected_section_index)
            p_idx = int(self.selected_polyline_index)
            section = self.sections[s_idx]
            polyline = section.polylines[p_idx]
            if len(polyline.points) > 2:
                del polyline.points[point_idx]
                self.update()

    def show_polyline_add_point_context_menu(self, insert_idx, pos_xy, global_pos):
        menu = QMenu(self)
        add_action = menu.addAction("Add Point")
        action = menu.exec(global_pos)
        if action == add_action:
            s_idx = int(self.selected_section_index)
            p_idx = int(self.selected_polyline_index)
            section = self.sections[s_idx]
            polyline = section.polylines[p_idx]
            # Convert widget coordinates to image coordinates
            img_x, img_y = self.widget_to_image_coords(pos_xy[0], pos_xy[1])
            polyline.points.insert(insert_idx, (img_x, img_y))
            self.update()

    def toggle_debug_mode(self):
        """Toggle debug mode to show hit areas"""
        self.debug_mode = not getattr(self, 'debug_mode', False)
        self.update()
        print(f"Debug mode: {'ON' if self.debug_mode else 'OFF'}")
                