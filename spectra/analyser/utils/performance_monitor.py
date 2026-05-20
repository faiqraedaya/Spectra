"""
Performance monitoring utilities for section assignment
"""
import time
import functools
from typing import Dict, List, Any, Optional
from collections import defaultdict


class PerformanceMonitor:
    """Monitor performance of section assignment operations"""
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.active_timers = {}
        
    def start_timer(self, operation: str):
        """Start timing an operation"""
        self.active_timers[operation] = time.time()
        
    def end_timer(self, operation: str, metadata: Optional[Dict[str, Any]] = None):
        """End timing an operation and record metrics"""
        if operation not in self.active_timers:
            return
            
        duration = time.time() - self.active_timers[operation]
        self.metrics[operation].append({
            'duration': duration,
            'metadata': metadata or {}
        })
        del self.active_timers[operation]
        
    def get_average_duration(self, operation: str) -> float:
        """Get average duration for an operation"""
        if operation not in self.metrics or not self.metrics[operation]:
            return 0.0
        return sum(m['duration'] for m in self.metrics[operation]) / len(self.metrics[operation])
        
    def get_total_count(self, operation: str) -> int:
        """Get total count for an operation"""
        return len(self.metrics.get(operation, []))
        
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of all performance metrics"""
        summary = {}
        for operation, measurements in self.metrics.items():
            if measurements:
                durations = [m['duration'] for m in measurements]
                summary[operation] = {
                    'count': len(measurements),
                    'avg_duration': sum(durations) / len(durations),
                    'min_duration': min(durations),
                    'max_duration': max(durations),
                    'total_duration': sum(durations)
                }
        return summary
        
    def clear_metrics(self):
        """Clear all performance metrics"""
        self.metrics.clear()
        self.active_timers.clear()


# Global performance monitor instance
_performance_monitor = PerformanceMonitor()


def monitor_performance(operation: str):
    """Decorator to monitor performance of functions"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _performance_monitor.start_timer(operation)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Extract relevant metadata
                metadata = {}
                if args and hasattr(args[0], 'sections_list'):
                    metadata['sections_count'] = len(args[0].sections_list)
                if args and hasattr(args[0], 'detections'):
                    metadata['detections_count'] = len(args[0].detections)
                _performance_monitor.end_timer(operation, metadata)
        return wrapper
    return decorator


def get_performance_stats() -> Dict[str, Any]:
    """Get current performance statistics"""
    return _performance_monitor.get_performance_summary()


def clear_performance_stats():
    """Clear performance statistics"""
    _performance_monitor.clear_metrics()


def log_performance_improvement(old_duration: float, new_duration: float, operation: str):
    """Log performance improvement"""
    if old_duration > 0:
        improvement = ((old_duration - new_duration) / old_duration) * 100
        print(f"Performance improvement for {operation}: {improvement:.1f}% "
              f"({old_duration:.3f}s -> {new_duration:.3f}s)")
    else:
        print(f"Performance for {operation}: {new_duration:.3f}s") 