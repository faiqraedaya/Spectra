"""
Test for PDF Viewer cleanup functionality to prevent memory leaks.
"""
import sys
import os
import tempfile
import shutil
from unittest.mock import Mock, patch

# Add the parent directory to the path to import the PDF viewer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from spectra.analyser.ui.pdf_viewer import PDFViewer


def test_cleanup_resets_all_state():
    """Test that cleanup method resets all state variables"""
    viewer = PDFViewer()
    
    # Set some state to simulate a loaded PDF
    viewer.pdf_document = Mock()
    viewer.current_page = 5
    viewer.total_pages = 10
    viewer.temp_dir = tempfile.mkdtemp()
    viewer.zoom_factor = 2.5
    viewer.image_offset = [100, 200]
    viewer.original_pixmap = Mock()
    viewer.scaled_pixmap = Mock()
    viewer.detections = [Mock(), Mock()]
    viewer.sections = [Mock(), Mock()]
    viewer.section_points = [(1, 2), (3, 4)]
    viewer.add_object_mode = True
    viewer.drawing_box = True
    viewer.box_start = (10, 20)
    viewer.box_end = (30, 40)
    viewer.add_section_mode = True
    viewer.drawing_section = True
    viewer.selected_bbox_index = 1
    viewer.dragging = True
    viewer.resizing = True
    viewer.resize_handle = "top-left"
    viewer.drag_offset = (5, 10)
    viewer.resize_start_bbox = (0, 0, 100, 100)
    viewer.resize_start_pos = (50, 50)
    viewer.selected_section_index = 2
    viewer.selected_polyline_index = 3
    viewer._polyline_clipboard = [Mock()]
    viewer._polyline_dragging = True
    viewer._polyline_drag_start_pos = (15, 25)
    viewer._polyline_drag_start_points = [(1, 1), (2, 2)]
    viewer._polyline_point_drag_idx = 1
    
    # Call cleanup
    viewer.cleanup()
    
    # Verify all state is reset
    assert viewer.pdf_document is None
    assert viewer.current_page == 0
    assert viewer.total_pages == 0
    assert viewer.temp_dir is None
    assert viewer.zoom_factor == 1.0
    assert viewer.image_offset == [0, 0]
    assert viewer.original_pixmap is None
    assert viewer.scaled_pixmap is None
    assert len(viewer.detections) == 0
    assert len(viewer.sections) == 0
    assert len(viewer.section_points) == 0
    assert not viewer.add_object_mode
    assert not viewer.drawing_box
    assert viewer.box_start is None
    assert viewer.box_end is None
    assert not viewer.add_section_mode
    assert not viewer.drawing_section
    assert viewer.selected_bbox_index is None
    assert not viewer.dragging
    assert not viewer.resizing
    assert viewer.resize_handle is None
    assert viewer.drag_offset is None
    assert viewer.resize_start_bbox is None
    assert viewer.resize_start_pos is None
    assert viewer.selected_section_index is None
    assert viewer.selected_polyline_index is None
    assert viewer._polyline_clipboard is None
    assert not viewer._polyline_dragging
    assert viewer._polyline_drag_start_pos is None
    assert viewer._polyline_drag_start_points is None
    assert viewer._polyline_point_drag_idx is None
    
    # Verify the is_clean method returns True
    assert viewer.is_clean()


def test_cleanup_removes_temp_directory():
    """Test that cleanup removes the temporary directory"""
    viewer = PDFViewer()
    
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    viewer.temp_dir = temp_dir
    
    # Verify directory exists
    assert os.path.exists(temp_dir)
    
    # Call cleanup
    viewer.cleanup()
    
    # Verify directory is removed
    assert not os.path.exists(temp_dir)
    assert viewer.temp_dir is None


def test_cleanup_closes_pdf_document():
    """Test that cleanup closes the PDF document"""
    viewer = PDFViewer()
    
    # Create a mock PDF document
    mock_doc = Mock()
    viewer.pdf_document = mock_doc
    
    # Call cleanup
    viewer.cleanup()
    
    # Verify close was called
    mock_doc.close.assert_called_once()
    assert viewer.pdf_document is None


def test_destructor_calls_cleanup():
    """Test that the destructor calls cleanup"""
    viewer = PDFViewer()
    
    # Set some state
    viewer.pdf_document = Mock()
    viewer.temp_dir = tempfile.mkdtemp()
    
    # Mock the cleanup method
    with patch.object(viewer, 'cleanup') as mock_cleanup:
        # Call destructor
        viewer.__del__()
        
        # Verify cleanup was called
        mock_cleanup.assert_called_once()


if __name__ == "__main__":
    print("Running PDF Viewer cleanup tests...")
    
    test_cleanup_resets_all_state()
    print("✓ test_cleanup_resets_all_state passed")
    
    test_cleanup_removes_temp_directory()
    print("✓ test_cleanup_removes_temp_directory passed")
    
    test_cleanup_closes_pdf_document()
    print("✓ test_cleanup_closes_pdf_document passed")
    
    test_destructor_calls_cleanup()
    print("✓ test_destructor_calls_cleanup passed")
    
    print("All tests passed!") 