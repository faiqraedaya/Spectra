"""
Test for PDF Viewer caching functionality to prevent unnecessary re-rendering.
"""
import sys
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock

# Add the parent directory to the path to import the PDF viewer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from spectra.analyser.ui.pdf_viewer import PDFViewer


def test_page_caching_prevents_re_rendering():
    """Test that page caching prevents unnecessary re-rendering"""
    viewer = PDFViewer()
    
    # Mock PDF document and temp directory
    viewer.pdf_document = Mock()
    viewer.pdf_document.__len__ = Mock(return_value=3)
    viewer.temp_dir = tempfile.mkdtemp()
    viewer.total_pages = 3
    viewer.current_page = 0
    
    try:
        # Mock the page rendering
        mock_page = Mock()
        mock_pixmap = Mock()
        mock_pixmap.tobytes.return_value = b"fake_image_data"
        
        with patch('PIL.Image.open') as mock_pil_open, \
             patch('PySide6.QtGui.QPixmap') as mock_qpixmap:
            
            # Mock PIL Image
            mock_pil_image = Mock()
            mock_pil_open.return_value = mock_pil_image
            
            # Mock QPixmap
            mock_qpixmap_instance = Mock()
            mock_qpixmap.return_value = mock_qpixmap_instance
            
            # Mock page.get_pixmap
            mock_page.get_pixmap.return_value = mock_pixmap
            viewer.pdf_document.__getitem__ = Mock(return_value=mock_page)
            
            # First render - should call the rendering code
            viewer.render_current_page()
            
            # Verify that get_pixmap was called once
            mock_page.get_pixmap.assert_called_once()
            
            # Second render - should use cache and NOT call rendering code
            viewer.render_current_page()
            
            # Verify that get_pixmap was still only called once (not called again)
            mock_page.get_pixmap.assert_called_once()
            
            # Verify cache was populated
            assert 0 in viewer._page_cache
            assert 0 in viewer._page_cache_rendered
            
    finally:
        # Cleanup
        if viewer.temp_dir and os.path.exists(viewer.temp_dir):
            shutil.rmtree(viewer.temp_dir)


def test_get_page_image_paths_uses_cache():
    """Test that get_page_image_paths uses cached pages when available"""
    viewer = PDFViewer()
    
    # Mock PDF document and temp directory
    viewer.pdf_document = Mock()
    viewer.pdf_document.__len__ = Mock(return_value=2)
    viewer.temp_dir = tempfile.mkdtemp()
    viewer.total_pages = 2
    
    try:
        # Pre-populate cache for page 0
        mock_pixmap = Mock()
        temp_path = os.path.join(viewer.temp_dir, "page_0.png")
        viewer._page_cache[0] = (mock_pixmap, temp_path)
        viewer._page_cache_rendered.add(0)
        
        # Mock the page rendering for page 1
        mock_page = Mock()
        mock_pixmap_data = Mock()
        mock_pixmap_data.tobytes.return_value = b"fake_image_data"
        
        with patch('PIL.Image.open') as mock_pil_open, \
             patch('PySide6.QtGui.QPixmap') as mock_qpixmap:
            
            # Mock PIL Image
            mock_pil_image = Mock()
            mock_pil_open.return_value = mock_pil_image
            
            # Mock QPixmap
            mock_qpixmap_instance = Mock()
            mock_qpixmap.return_value = mock_qpixmap_instance
            
            # Mock page.get_pixmap
            mock_page.get_pixmap.return_value = mock_pixmap_data
            viewer.pdf_document.__getitem__ = Mock(return_value=mock_page)
            
            # Get all page image paths
            image_paths = viewer.get_page_image_paths()
            
            # Should have 2 paths
            assert len(image_paths) == 2
            
            # Page 0 should use cached path
            assert image_paths[0] == temp_path
            
            # Page 1 should be newly rendered
            assert image_paths[1].endswith("page_1.png")
            
            # Verify that get_pixmap was only called once (for page 1)
            mock_page.get_pixmap.assert_called_once()
            
    finally:
        # Cleanup
        if viewer.temp_dir and os.path.exists(viewer.temp_dir):
            shutil.rmtree(viewer.temp_dir)


def test_cache_cleared_on_load_pdf():
    """Test that cache is cleared when loading a new PDF"""
    viewer = PDFViewer()
    
    # Pre-populate cache
    viewer._page_cache[0] = (Mock(), "fake_path")
    viewer._page_cache_rendered.add(0)
    
    # Mock load_pdf
    with patch.object(viewer, 'pdf_document', Mock()), \
         patch.object(viewer, 'temp_dir', tempfile.mkdtemp()), \
         patch.object(viewer, 'render_current_page'):
        
        viewer.load_pdf("fake_path.pdf")
        
        # Verify cache was cleared
        assert len(viewer._page_cache) == 0
        assert len(viewer._page_cache_rendered) == 0


def test_cache_cleared_on_cleanup():
    """Test that cache is cleared during cleanup"""
    viewer = PDFViewer()
    
    # Pre-populate cache
    viewer._page_cache[0] = (Mock(), "fake_path")
    viewer._page_cache_rendered.add(0)
    
    # Mock cleanup dependencies
    viewer.pdf_document = Mock()
    viewer.temp_dir = tempfile.mkdtemp()
    
    try:
        viewer.cleanup()
        
        # Verify cache was cleared
        assert len(viewer._page_cache) == 0
        assert len(viewer._page_cache_rendered) == 0
        
    finally:
        # Cleanup temp dir
        if viewer.temp_dir and os.path.exists(viewer.temp_dir):
            shutil.rmtree(viewer.temp_dir)


if __name__ == "__main__":
    # Run tests
    test_page_caching_prevents_re_rendering()
    test_get_page_image_paths_uses_cache()
    test_cache_cleared_on_load_pdf()
    test_cache_cleared_on_cleanup()
    print("All caching tests passed!") 