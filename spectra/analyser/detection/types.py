from typing import Tuple, Optional
from dataclasses import dataclass

@dataclass
class Detection:
    """Data class for detection results"""
    name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    page_num: int
    section: str = "Unassigned"
    source: str = "model"  # 'model' or 'manual'
    line_size: Optional[float] = None  # Optional per-object line size override
    count: int = 1  # Number of identical objects in the box

    def to_dict(self):
        return {
            'name': self.name,
            'confidence': self.confidence,
            'bbox': list(self.bbox),
            'page_num': self.page_num,
            'section': self.section,
            'source': self.source,
            'line_size': self.line_size,
            'count': self.count
        }

    @staticmethod
    def from_dict(data):
        return Detection(
            name=data.get('name', ''),
            confidence=data.get('confidence', 0.0),
            bbox=tuple(data.get('bbox', (0, 0, 0, 0))),
            page_num=data.get('page_num', 1),
            section=data.get('section', 'Unassigned'),
            source=data.get('source', 'model'),
            line_size=data.get('line_size', None),
            count=data.get('count', 1)
        )