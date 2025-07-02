import io
import os
import shutil
import tempfile
from typing import List, Tuple, Optional, cast

from PIL import Image
from PySide6.QtCore import QRect, Qt, Signal, QPoint
from PySide6.QtGui import QFont, QMouseEvent, QPainter, QPen, QPixmap, QBrush
from PySide6.QtWidgets import QLabel, QMessageBox
import fitz

class PDFViewer(QLabel):
    """PDF Viewer with zoom and pan"""
    # UI Signals
    zoom_changed = Signal(float)
    bbox_right_clicked = Signal(int)  # index of detection in self.detections
    manual_box_drawn = Signal(tuple)  # (x1, y1, x2, y2)
    bbox_changed = Signal(int, tuple)  # index, new bbox
    background_right_clicked = Signal(QPoint)  # position of right click on background
    bbox_edit_finished = Signal(int)  # index of detection finished editing

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

        # Display properties
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.zoom_step = 0.1

        # Pan properties
        self.pan_start_pos = None
        self.image_offset = [0, 0]
        self.is_panning = False

        # Current display
        self.original_pixmap = None
        self.scaled_pixmap = None
        self.detections = []

        # Enable mouse tracking for pan
        self.setMouseTracking(True)

        # Add Object (manual) mode
        self.add_object_mode = False
        self.drawing_box = False
        self.box_start = None
        self.box_end = None

        # Drag/resize bbox
        self.selected_bbox_index = None
        self.dragging = False
        self.resizing = False
        self.resize_handle = None
        self.drag_offset = None
        self.resize_start_bbox = None
        self.resize_start_pos = None
        self.handle_size = 16  # Make handles larger for easier grabbing
        

    def load_pdf(self, pdf_path: str) -> bool:
        """Load PDF and convert pages to images"""
        try:
            # Clean up previous temp directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

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
        """Render current PDF page to image"""
        if not self.pdf_document or self.current_page >= self.total_pages:
            return
        if self.temp_dir is None:
            return
        try:
            # Get page
            page = self.pdf_document[self.current_page]
            
            # Render at high DPI for quality
            mat = fitz.Matrix(2.0, 2.0)  # 2x scaling for better quality
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image then to QPixmap
            img_data = pix.tobytes("ppm")
            pil_image = Image.open(io.BytesIO(img_data))
            
            # Convert PIL to QPixmap
            temp_path = os.path.join(self.temp_dir, f"temp_page_{self.current_page}.png")
            pil_image.save(temp_path)
            
            self.original_pixmap = QPixmap(temp_path)
            self.update_display()
            
        except Exception as e:
            QMessageBox.critical(None, "Error Rendering Page", f"Error rendering page: {e}")
        
    def set_page(self, page_num: int):
        """Set current page (0-indexed)"""
        if 0 <= page_num < self.total_pages:
            self.current_page = page_num
            self.image_offset = [0, 0]
            self.render_current_page()
        
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

    def update_display(self):
        """Update the display with current zoom and pan"""
        if not self.original_pixmap:
            return
        # Apply zoom
        zoomed_size = self.original_pixmap.size() * self.zoom_factor
        # Always work on a copy for drawing
        base_pixmap = self.original_pixmap.scaled(
            zoomed_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.scaled_pixmap = QPixmap(base_pixmap)
        # Draw detections if any
        if self.detections:
            self.draw_detections()
        self.display_with_offset()
        # Ensure cursor is correct after display update
        if self.add_object_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def draw_detections(self):
        """Draw detection bounding boxes on the scaled pixmap, with selection/handles"""
        if not self.scaled_pixmap or not self.detections:
            return
        painter = QPainter(self.scaled_pixmap)
        painter.setFont(QFont("Arial", max(8, int(10 * self.zoom_factor))))
        scale_factor = self.zoom_factor
        for idx, detection in enumerate(self.detections):
            bbox = detection.bbox
            x1, y1, x2, y2 = [int(coord * scale_factor) for coord in bbox]
            # Draw rectangle (transparent fill, just outline)
            if idx == self.selected_bbox_index:
                pen = QPen(Qt.GlobalColor.blue, max(3, int(3 * scale_factor)))
            else:
                pen = QPen(Qt.GlobalColor.red, max(2, int(2 * scale_factor)))
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # Transparent fill
            painter.drawRect(x1, y1, x2-x1, y2-y1)
            # Draw label background
            label = f"{detection.name}: {detection.confidence:.2f}"
            label_width = max(150, int(150 * scale_factor))
            label_height = max(20, int(20 * scale_factor))
            painter.fillRect(x1, y1-label_height, label_width, label_height, Qt.GlobalColor.red)
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
        if self.add_object_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                self.drawing_box = True
                self.box_start = event.pos()
                self.box_end = event.pos()
                self.setCursor(Qt.CursorShape.CrossCursor)  # Always show plus cursor in add object mode
            elif event.button() == Qt.MouseButton.RightButton:
                self.set_add_object_mode(False)
                main_window = self.get_main_window()
                if main_window is not None:
                    main_window.exit_add_object_mode()
            elif event.button() == Qt.MouseButton.MiddleButton and not self.drawing_box:
                self.is_panning = True
                self.pan_start_pos = event.pos()
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on a handle or bbox
            idx = self.get_bbox_at_pos(event.pos())
            if idx is not None:
                self.selected_bbox_index = idx
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
                if handle:
                    self.resizing = True
                    self.resize_handle = handle
                    self.resize_start_bbox = tuple(self.detections[idx].bbox)  # always tuple
                    self.resize_start_pos = event.pos()
                else:
                    # Start dragging
                    self.dragging = True
                    px, py = int(event.pos().x()), int(event.pos().y())
                    self.drag_offset = (px - x1, py - y1, x2 - px, y2 - py)
            else:
                self.selected_bbox_index = None  # Deselect if clicking empty space
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            idx = self.get_bbox_at_pos(event.pos())
            if idx is not None:
                self.bbox_right_clicked.emit(idx)
            else:
                if hasattr(self, 'background_right_clicked'):
                    self.background_right_clicked.emit(event.pos())
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.pan_start_pos = event.pos()
            self.update()

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
            self.detections[idx].bbox = cast(Tuple[int, int, int, int], tuple(int(round(v)) for v in bbox[:4]))
            self.update_display()
            self.bbox_changed.emit(idx, self.detections[idx].bbox)
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
        if self.dragging and self.selected_bbox_index is not None and self.drag_offset is not None:
            idx = self.selected_bbox_index
            bbox = list(self.detections[idx].bbox)
            scale = self.zoom_factor
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            px, py = int(event.pos().x()), int(event.pos().y())
            dx = (px - self.drag_offset[0]) / scale
            dy = (py - self.drag_offset[1]) / scale
            bbox[0] = int(round(dx))
            bbox[1] = int(round(dy))
            bbox[2] = bbox[0] + w
            bbox[3] = bbox[1] + h
            # Clamp to image bounds
            bbox[0] = max(0, min(bbox[0], bbox[2]-1))
            bbox[1] = max(0, min(bbox[1], bbox[3]-1))
            bbox[2] = max(bbox[0]+1, bbox[2])
            bbox[3] = max(bbox[1]+1, bbox[3])
            self.detections[idx].bbox = cast(Tuple[int, int, int, int], tuple(int(round(v)) for v in bbox[:4]))
            self.update_display()
            self.bbox_changed.emit(idx, self.detections[idx].bbox)
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return
        # Not dragging or resizing: set cursor based on hover
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
        if self.add_object_mode and self.drawing_box and event.button() == Qt.MouseButton.LeftButton:
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
        if self.resizing:
            self.resizing = False
            self.resize_handle = None
            self.resize_start_bbox = None
            self.resize_start_pos = None
            self.update()
            if self.selected_bbox_index is not None:
                self.bbox_edit_finished.emit(self.selected_bbox_index)
            return
        if self.dragging:
            self.dragging = False
            self.drag_offset = None
            self.update()
            if self.selected_bbox_index is not None:
                self.bbox_edit_finished.emit(self.selected_bbox_index)
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = False
            self.pan_start_pos = None
        else:
            super().mouseReleaseEvent(event)

    def get_page_image_paths(self) -> List[str]:
        """Get paths to all page images for analysis"""
        if not self.pdf_document:
            return []
        if self.temp_dir is None:
            return []
        image_paths = []
        for page_num in range(self.total_pages):
            try:
                page = self.pdf_document[page_num]
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)  # type: ignore[attr-defined]
                img_data = pix.tobytes("ppm")
                pil_image = Image.open(io.BytesIO(img_data))
                temp_path = os.path.join(self.temp_dir, f"page_{page_num}.png")
                pil_image.save(temp_path)
                image_paths.append(temp_path)
            except Exception as e:
                QMessageBox.critical(None, "Error Converting Page", f"Error converting page {page_num}: {e}")
        return image_paths
    
    def cleanup(self):
        """Clean up temporary files"""
        if self.pdf_document:
            self.pdf_document.close()
        
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
    
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
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.drawing_box = False
            self.box_start = None
            self.box_end = None
        self.update()

    def keyPressEvent(self, event):
        if self.add_object_mode and event.key() == Qt.Key.Key_Escape:
            self.set_add_object_mode(False)
            main_window = self.get_main_window()
            if main_window is not None:
                main_window.exit_add_object_mode()
        super().keyPressEvent(event)

    def widget_to_image_coords(self, x, y):
        # Calculate offset for pan
        if not self.scaled_pixmap:
            return x, y
        x_offset = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
        y_offset = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
        img_x = (x - x_offset) / self.zoom_factor
        img_y = (y - y_offset) / self.zoom_factor
        return img_x, img_y

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw preview box overlay if in add object mode and drawing
        if self.add_object_mode and self.drawing_box and self.box_start is not None and self.box_end is not None and hasattr(self.box_start, 'isNull') and hasattr(self.box_end, 'isNull') and not self.box_start.isNull() and not self.box_end.isNull():
            # Calculate pixmap offset
            if self.scaled_pixmap:
                x = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
                y = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
                painter = QPainter(self)
                offset_start = self.box_start
                offset_end = self.box_end
                preview_rect = QRect(offset_start, offset_end)
                painter.setPen(QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(preview_rect)
                painter.end()

    def get_main_window(self):
        # Helper to find the main window for exit_add_object_mode
        parent = self.parent()
        try:
            from analyser import PIDRecognitionTool
        except ImportError:
            PIDRecognitionTool = None
        while parent is not None:
            if PIDRecognitionTool is not None and isinstance(parent, PIDRecognitionTool):
                return parent
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return None

    def display_with_offset(self):
        """Display pixmap with pan offset and draw manual box preview if needed"""
        if not self.scaled_pixmap:
            return
        # Create a pixmap the size of the widget
        display_pixmap = QPixmap(self.size())
        display_pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(display_pixmap)
        # Calculate position with offset
        x = (self.width() - self.scaled_pixmap.width()) // 2 + self.image_offset[0]
        y = (self.height() - self.scaled_pixmap.height()) // 2 + self.image_offset[1]
        painter.drawPixmap(x, y, self.scaled_pixmap)
        painter.end()
        self.setPixmap(display_pixmap)
        self.resize(self.scaled_pixmap.size())

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
            
            # Store old zoom
            old_zoom = self.zoom_factor
            
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
            
            self.update_display()
            self.zoom_changed.emit(self.zoom_factor)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Pan left/right
            delta = event.angleDelta().y() // 8  # 1 notch = 15 degrees, 120 units
            self.image_offset[0] += int(delta)
            self.update_display()
        else:
            # Pan up/down
            delta = event.angleDelta().y() // 8
            self.image_offset[1] += int(delta)
            self.update_display()

    def leaveEvent(self, event):
        if not self.add_object_mode:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)
                