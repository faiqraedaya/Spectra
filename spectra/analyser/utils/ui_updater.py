"""
UI Update Manager with debouncing to prevent repeated table updates.
"""
from typing import Optional, Callable, Dict, Any
from PySide6.QtCore import QTimer, QObject, Signal
from PySide6.QtWidgets import QApplication


class UIUpdateManager(QObject):
    """
    Manages UI updates with debouncing to prevent repeated calls.
    Uses a timer-based approach to coalesce multiple update requests.
    """
    
    # Signal emitted when updates are ready to be applied
    updates_ready = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._apply_updates)
        
        # Track which updates are pending
        self._pending_updates: Dict[str, bool] = {}
        
        # Default debounce delay in milliseconds
        self._debounce_delay = 50
        
    def request_update(self, update_type: str, delay: Optional[int] = None):
        """
        Request an update of a specific type.
        
        Args:
            update_type: String identifier for the type of update
            delay: Optional custom delay in milliseconds
        """
        self._pending_updates[update_type] = True
        
        # Start or restart the timer
        if delay is not None:
            self._update_timer.start(delay)
        else:
            self._update_timer.start(self._debounce_delay)
    
    def request_immediate_update(self, update_type: str):
        """
        Request an immediate update without debouncing.
        Useful for critical updates that can't be delayed.
        
        Args:
            update_type: String identifier for the type of update
        """
        self._pending_updates[update_type] = True
        self._apply_updates()
    
    def _apply_updates(self):
        """Apply all pending updates and clear the pending list."""
        if not self._pending_updates:
            return
            
        # Emit signal to notify that updates are ready
        self.updates_ready.emit()
        
        # Clear pending updates
        self._pending_updates.clear()
    
    def has_pending_updates(self, update_type: str) -> bool:
        """Check if a specific update type is pending."""
        return self._pending_updates.get(update_type, False)
    
    def clear_pending_updates(self):
        """Clear all pending updates."""
        self._pending_updates.clear()
        self._update_timer.stop()
    
    def set_debounce_delay(self, delay: int):
        """Set the default debounce delay in milliseconds."""
        self._debounce_delay = delay


# Global instance for the application
_global_update_manager: Optional[UIUpdateManager] = None


def get_update_manager() -> UIUpdateManager:
    """Get the global update manager instance."""
    global _global_update_manager
    if _global_update_manager is None:
        _global_update_manager = UIUpdateManager()
    return _global_update_manager


def request_update(update_type: str, delay: Optional[int] = None):
    """Request an update using the global update manager."""
    get_update_manager().request_update(update_type, delay)


def request_immediate_update(update_type: str):
    """Request an immediate update using the global update manager."""
    get_update_manager().request_immediate_update(update_type)


def clear_pending_updates():
    """Clear all pending updates."""
    get_update_manager().clear_pending_updates()


# Update type constants
UPDATE_SECTIONS_TABLE = "sections_table"
UPDATE_OBJECTS_TABLE = "objects_table"
UPDATE_RESULTS_TABLE = "results_table"
UPDATE_SECTION_FILTER = "section_filter"
UPDATE_NAVIGATION = "navigation"
UPDATE_ZOOM = "zoom" 