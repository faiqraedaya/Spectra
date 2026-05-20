"""
Test for UI Update Manager debouncing functionality.
"""
import sys
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Add the parent directory to the path to import the modules
sys.path.insert(0, '..')

from spectra.analyser.utils.ui_updater import (
    UIUpdateManager,
    get_update_manager,
    request_update,
    UPDATE_SECTIONS_TABLE,
    UPDATE_OBJECTS_TABLE,
    UPDATE_RESULTS_TABLE
)


def test_ui_updater():
    """Test the UI update manager debouncing functionality."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Get the global update manager
    update_manager = get_update_manager()
    
    # Track how many times updates are applied
    update_count = 0
    
    def on_updates_ready():
        nonlocal update_count
        update_count += 1
        print(f"Updates applied (count: {update_count})")
    
    # Connect the signal
    update_manager.updates_ready.connect(on_updates_ready)
    
    print("Testing UI Update Manager debouncing...")
    print("Requesting multiple rapid updates...")
    
    # Request multiple rapid updates
    for i in range(10):
        request_update(UPDATE_SECTIONS_TABLE)
        request_update(UPDATE_OBJECTS_TABLE)
        request_update(UPDATE_RESULTS_TABLE)
        print(f"Requested update {i+1}")
    
    # Wait for the debounce timer to expire
    print("Waiting for debounce timer...")
    time.sleep(0.1)  # Wait 100ms (longer than the 50ms debounce delay)
    
    # Process events to trigger the timer
    app.processEvents()
    
    print(f"Final update count: {update_count}")
    
    if update_count == 1:
        print("✅ SUCCESS: Multiple rapid updates were coalesced into a single update")
    else:
        print(f"❌ FAILED: Expected 1 update, got {update_count}")
    
    # Test immediate updates
    print("\nTesting immediate updates...")
    update_count = 0
    
    # Request immediate updates
    for i in range(5):
        update_manager.request_immediate_update(UPDATE_SECTIONS_TABLE)
        print(f"Requested immediate update {i+1}")
    
    print(f"Immediate update count: {update_count}")
    
    if update_count == 5:
        print("✅ SUCCESS: Immediate updates were applied separately")
    else:
        print(f"❌ FAILED: Expected 5 immediate updates, got {update_count}")
    
    print("\nTest completed!")


if __name__ == "__main__":
    test_ui_updater() 