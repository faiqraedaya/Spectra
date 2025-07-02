#!/usr/bin/env python3
"""
Test script to verify the modular structure imports correctly.
"""

def test_imports():
    """Test that all modular components can be imported successfully."""
    try:
        print("Testing modular imports...")
        
        # Test UI components
        print("  Testing UI components...")
        from ui.menus import MenuManager
        print("    ✓ MenuManager imported successfully")
        
        from ui.panels.viewer_panel import ViewerPanel
        print("    ✓ ViewerPanel imported successfully")
        
        from ui.panels.sections_panel import SectionsPanel
        print("    ✓ SectionsPanel imported successfully")
        
        from ui.panels.objects_panel import ObjectsPanel
        print("    ✓ ObjectsPanel imported successfully")
        
        from ui.panels.results_panel import ResultsPanel
        print("    ✓ ResultsPanel imported successfully")
        
        from ui.dialogs.detection_dialog import DetectionDialog
        print("    ✓ DetectionDialog imported successfully")
        
        # Test Core components
        print("  Testing Core components...")
        from core.project_manager import ProjectManager
        print("    ✓ ProjectManager imported successfully")
        
        from core.detection_manager import DetectionManager
        print("    ✓ DetectionManager imported successfully")
        
        from core.analysis_manager import AnalysisManager
        print("    ✓ AnalysisManager imported successfully")
        
        # Test Modular Main Window
        print("  Testing Modular Main Window...")
        from core.main_window_modular import SpectraModular
        print("    ✓ SpectraModular imported successfully")
        
        print("\n✅ All modular components imported successfully!")
        return True
        
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

def test_instantiation():
    """Test that components can be instantiated (basic test)."""
    try:
        print("\nTesting component instantiation...")
        
        # Create a mock main window for testing
        class MockMainWindow:
            def __init__(self):
                self.detections = []
                self.sections_list = []
                self.api_key = None
                self.confidence = 0.5
                self.overlap = 0.3
                self.current_pdf_path = None
                self.undo_stack = []
                self.redo_stack = []
                self.frequency_table = None
                
            def update_objects_table(self): pass
            def update_sections_table(self): pass
            def update_section_filter_dropdown(self): pass
            def update_results_table(self): pass
            def update_navigation_controls(self): pass
            def apply_section_filter(self): pass
            def get_filtered_detections(self): return []
            def menuBar(self): return None
            def setMenuBar(self, menu_bar): pass
            def cursor(self): return None
            def width(self): return 800
            def height(self): return 600
        
        mock_window = MockMainWindow()
        
        # Test manager instantiation
        print("  Testing managers...")
        from ui.menus import MenuManager
        menu_manager = MenuManager(mock_window)
        print("    ✓ MenuManager instantiated")
        
        from core.project_manager import ProjectManager
        project_manager = ProjectManager(mock_window)
        print("    ✓ ProjectManager instantiated")
        
        from core.detection_manager import DetectionManager
        detection_manager = DetectionManager(mock_window)
        print("    ✓ DetectionManager instantiated")
        
        from core.analysis_manager import AnalysisManager
        analysis_manager = AnalysisManager(mock_window)
        print("    ✓ AnalysisManager instantiated")
        
        # Test panel instantiation
        print("  Testing panels...")
        from ui.panels.viewer_panel import ViewerPanel
        viewer_panel = ViewerPanel(mock_window)
        print("    ✓ ViewerPanel instantiated")
        
        from ui.panels.sections_panel import SectionsPanel
        sections_panel = SectionsPanel(mock_window)
        print("    ✓ SectionsPanel instantiated")
        
        from ui.panels.objects_panel import ObjectsPanel
        objects_panel = ObjectsPanel(mock_window)
        print("    ✓ ObjectsPanel instantiated")
        
        from ui.panels.results_panel import ResultsPanel
        results_panel = ResultsPanel(mock_window)
        print("    ✓ ResultsPanel instantiated")
        
        print("\n✅ All components instantiated successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Instantiation error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("MODULAR STRUCTURE TEST")
    print("=" * 50)
    
    import_success = test_imports()
    instantiation_success = test_instantiation()
    
    print("\n" + "=" * 50)
    if import_success and instantiation_success:
        print("🎉 ALL TESTS PASSED!")
        print("The modular structure is working correctly.")
    else:
        print("❌ SOME TESTS FAILED!")
        print("Please check the error messages above.")
    print("=" * 50) 