"""
UI Update Manager with intelligent batching and coalescing to prevent excessive UI updates.
"""
from typing import Optional, Callable, Dict, Any, Set
from PySide6.QtCore import QTimer, QObject, Signal, QMutex, QMutexLocker
from PySide6.QtWidgets import QApplication


class UIUpdateManager(QObject):
    """
    Manages UI updates with intelligent batching and coalescing to prevent repeated calls.
    Uses a timer-based approach with priority-based update handling.
    """
    
    # Signal emitted when updates are ready to be applied; carries a snapshot of update types
    updates_ready = Signal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._apply_updates)
        
        # Thread-safe tracking of pending updates
        self._mutex = QMutex()
        self._pending_updates: Set[str] = set()
        self._high_priority_updates: Set[str] = set()
        
        # Default debounce delay in milliseconds (optimized for 60 FPS)
        self._debounce_delay = 16  # ~60 FPS for smooth UI
        self._high_priority_delay = 8  # Higher priority updates get faster response
        
        # Update coalescing - group related updates
        self._update_groups = {
            # Core data updates that trigger multiple UI updates
            "data_changed": {"sections_table", "objects_table", "results_table", "section_filter"},
            # Display updates that can be batched together
            "display_update": {"navigation", "zoom", "viewer"},
            # Critical updates that need immediate response
            "critical": {"error", "progress", "status"}
        }
        
    def request_update(self, update_type: str, delay: Optional[int] = None, priority: str = "normal"):
        """
        Request an update of a specific type with priority handling.
        
        Args:
            update_type: String identifier for the type of update
            delay: Optional custom delay in milliseconds
            priority: "normal", "high", or "critical"
        """
        with QMutexLocker(self._mutex):
            self._pending_updates.add(update_type)
            
            # Handle priority-based updates
            if priority == "critical":
                self._high_priority_updates.add(update_type)
                # Critical updates get immediate processing
                self._update_timer.start(0)
                return
            elif priority == "high":
                self._high_priority_updates.add(update_type)
                delay = delay or self._high_priority_delay
            else:
                delay = delay or self._debounce_delay
            
            # Start or restart the timer
            if not self._update_timer.isActive():
                self._update_timer.start(delay)
    
    def request_group_update(self, group_name: str, delay: Optional[int] = None):
        """
        Request all updates in a group at once for better coalescing.
        
        Args:
            group_name: Name of the update group
            delay: Optional custom delay in milliseconds
        """
        if group_name in self._update_groups:
            with QMutexLocker(self._mutex):
                self._pending_updates.update(self._update_groups[group_name])
                delay = delay or self._debounce_delay
                if not self._update_timer.isActive():
                    self._update_timer.start(delay)
    
    def request_immediate_update(self, update_type: str):
        """
        Request an immediate update without debouncing.
        Useful for critical updates that can't be delayed.
        
        Args:
            update_type: String identifier for the type of update
        """
        with QMutexLocker(self._mutex):
            self._pending_updates.add(update_type)
            self._high_priority_updates.add(update_type)
        self._apply_updates()
    
    def _apply_updates(self):
        """Apply all pending updates with intelligent coalescing."""
        with QMutexLocker(self._mutex):
            if not self._pending_updates:
                return
            
            # Process high priority updates first
            updates_to_apply = self._high_priority_updates.copy()
            self._high_priority_updates.clear()
            
            # Add normal priority updates
            updates_to_apply.update(self._pending_updates)
            self._pending_updates.clear()
        
        # Apply updates outside of mutex to avoid deadlock
        if updates_to_apply:
            # Emit signal to notify that updates are ready, include the snapshot
            self.updates_ready.emit(updates_to_apply)
    
    def has_pending_updates(self, update_type: str) -> bool:
        """Check if a specific update type is pending."""
        with QMutexLocker(self._mutex):
            return update_type in self._pending_updates or update_type in self._high_priority_updates
    
    def has_pending_group_updates(self, group_name: str) -> bool:
        """Check if any updates in a group are pending."""
        if group_name not in self._update_groups:
            return False
        
        with QMutexLocker(self._mutex):
            group_updates = self._update_groups[group_name]
            return bool(self._pending_updates.intersection(group_updates) or 
                       self._high_priority_updates.intersection(group_updates))
    
    def clear_pending_updates(self):
        """Clear all pending updates."""
        with QMutexLocker(self._mutex):
            self._pending_updates.clear()
            self._high_priority_updates.clear()
            self._update_timer.stop()
    
    def set_debounce_delay(self, delay: int):
        """Set the default debounce delay in milliseconds."""
        self._debounce_delay = delay
    
    def set_high_priority_delay(self, delay: int):
        """Set the high priority delay in milliseconds."""
        self._high_priority_delay = delay


# Global instance for the application
_global_update_manager: Optional[UIUpdateManager] = None


def get_update_manager() -> UIUpdateManager:
    """Get the global update manager instance."""
    global _global_update_manager
    if _global_update_manager is None:
        _global_update_manager = UIUpdateManager()
    return _global_update_manager


def request_update(update_type: str, delay: Optional[int] = None, priority: str = "normal"):
    """Request an update using the global update manager."""
    get_update_manager().request_update(update_type, delay, priority)


def request_group_update(group_name: str, delay: Optional[int] = None):
    """Request a group update using the global update manager."""
    get_update_manager().request_group_update(group_name, delay)


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
UPDATE_VIEWER = "viewer"
UPDATE_ERROR = "error"
UPDATE_PROGRESS = "progress"
UPDATE_STATUS = "status" 