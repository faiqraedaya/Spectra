"""
Spatial indexing utilities for efficient section assignment
"""
from typing import List, Tuple, Optional, Dict, Any
import rtree
from sections.sections import Section, Polyline


class SpatialIndex:
    """R-tree based spatial index for efficient section assignment"""
    
    def __init__(self):
        self.index = rtree.index.Index()
        self.section_data = {}  # Maps index ID to section data
        self.next_id = 0
        self._dirty = True  # Track if index needs rebuilding
        
    def add_section(self, section: Section, section_id: str):
        """Add a section's polylines to the spatial index"""
        if not section.polylines:
            return
            
        # Get bounding box for the section
        bbox = section.get_bounding_box()
        if bbox is None:
            return
            
        # Add to R-tree with section metadata
        index_id = self.next_id
        self.next_id += 1
        
        self.index.insert(index_id, bbox)
        self.section_data[index_id] = {
            'section_name': section.name,
            'section_id': section_id,
            'bbox': bbox,
            'polylines': section.polylines
        }
        
    def remove_section(self, section_name: str):
        """Remove a section from the spatial index"""
        to_remove = []
        for index_id, data in self.section_data.items():
            if data['section_name'] == section_name:
                to_remove.append(index_id)
                
        for index_id in to_remove:
            self.index.delete(index_id, self.section_data[index_id]['bbox'])
            del self.section_data[index_id]
            
    def clear(self):
        """Clear the entire spatial index"""
        self.index = rtree.index.Index()
        self.section_data.clear()
        self.next_id = 0
        self._dirty = True
        
    def rebuild_from_sections(self, sections: List[Section]):
        """Rebuild the spatial index from a list of sections"""
        self.clear()
        for section in sections:
            self.add_section(section, section.name)
        self._dirty = False
        
    def find_intersecting_sections(self, bbox: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
        """Find all sections that intersect with the given bounding box"""
        if self._dirty:
            return []
            
        # Query R-tree for intersecting bounding boxes
        intersecting_ids = list(self.index.intersection(bbox))
        
        # Return section data for intersecting sections
        return [self.section_data[index_id] for index_id in intersecting_ids]
        
    def get_section_for_bbox(self, bbox: Tuple[float, float, float, float], 
                           sections_list: List[Section]) -> str:
        """Find the most recently added section that intersects with the bbox"""
        if self._dirty:
            self.rebuild_from_sections(sections_list)
            
        # Get all intersecting sections
        intersecting_sections = self.find_intersecting_sections(bbox)
        
        if not intersecting_sections:
            return "Unassigned"
            
        # Sort by section order in the original list (most recent first)
        section_order = {section.name: i for i, section in enumerate(reversed(sections_list))}
        
        # Find the most recently added intersecting section
        best_section = None
        best_order = -1
        
        for section_data in intersecting_sections:
            section_name = section_data['section_name']
            order = section_order.get(section_name, -1)
            
            if order > best_order:
                # Check detailed intersection
                if self._detailed_intersection_check(section_data['polylines'], bbox):
                    best_section = section_name
                    best_order = order
                    
        return best_section if best_section else "Unassigned"
        
    def _detailed_intersection_check(self, polylines: List[Polyline], 
                                   bbox: Tuple[float, float, float, float]) -> bool:
        """Perform detailed intersection check between polylines and bbox"""
        from sections.sections import polyline_intersects_bbox
        
        for polyline in polylines:
            if polyline_intersects_bbox(polyline.points, bbox):
                return True
        return False


class SpatialIndexManager:
    """Manager for spatial indexing with caching and optimization"""
    
    def __init__(self):
        self.spatial_index = SpatialIndex()
        self._sections_hash = None
        self._last_sections_count = 0
        
    def get_section_for_bbox(self, bbox: Tuple[float, float, float, float], 
                           sections_list: List[Section]) -> str:
        """Get section for bbox with automatic index management"""
        # Check if we need to rebuild the index
        current_hash = self._hash_sections(sections_list)
        current_count = len(sections_list)
        
        if (self._sections_hash != current_hash or 
            self._last_sections_count != current_count):
            self.spatial_index.rebuild_from_sections(sections_list)
            self._sections_hash = current_hash
            self._last_sections_count = current_count
            
        return self.spatial_index.get_section_for_bbox(bbox, sections_list)
        
    def _hash_sections(self, sections_list: List[Section]) -> int:
        """Create a hash of sections for cache invalidation"""
        return hash(tuple((s.name, len(s.polylines), s.get_bounding_box()) 
                         for s in sections_list))
        
    def invalidate_cache(self):
        """Invalidate the spatial index cache"""
        self._sections_hash = None
        self._last_sections_count = 0
        self.spatial_index._dirty = True


# Global instance for easy access
_spatial_index_manager = SpatialIndexManager()


def get_section_for_bbox_spatial(bbox: Tuple[float, float, float, float], 
                                sections_list: List[Section]) -> str:
    """Spatial-indexed version of get_section_for_bbox"""
    return _spatial_index_manager.get_section_for_bbox(bbox, sections_list)


def invalidate_spatial_cache():
    """Invalidate the spatial index cache"""
    _spatial_index_manager.invalidate_cache() 