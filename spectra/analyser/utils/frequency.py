import csv
from collections import defaultdict
from typing import List, Dict, Optional
from detection.categories_map import get_frequency_category

# Column names in the frequency table
HOLE_SIZE_COLS = [
    "Tiny (1-3 mm)",
    "Small (3-10mm)",
    "Medium (10-50 mm)",
    "Large (50-150 mm)",
    "FBR (greater than 150 mm)"
]

class FrequencyTable:
    def __init__(self, csv_path: str):
        self.rows = []
        self._load(csv_path)

    def _load(self, csv_path: str):
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # Normalize fieldnames to strip whitespace and BOM, if present
            if reader.fieldnames is not None:
                def normalize_field(fn):
                    fn = fn.strip()
                    if fn.startswith('\ufeff'):
                        fn = fn.replace('\ufeff', '')
                    if fn == '':
                        return fn
                    if fn.lower() == 'category':
                        return 'Category'
                    return fn
                reader.fieldnames = [normalize_field(fn) for fn in reader.fieldnames]
            for i, row in enumerate(reader):
                # Normalize keys in row
                row = {normalize_field(k): v for k, v in row.items()}
                if i == 0:
                    first_row = row
                row['min_size_mm'] = float(row['min_size_mm'])
                row['max_size_mm'] = float(row['max_size_mm'])
                self.rows.append(row)
            

    def lookup(self, category: str, line_size: float) -> Optional[dict]:
        """
        Find the frequency row for a given category and line size.
        Implements the rules: smallest max_size_mm >= line_size, or largest if above all.
        """
        # Use normalized key for 'Category'
        candidates = [r for r in self.rows if r.get('Category', '').strip() == category]
        if not candidates:
            all_cats = set(r.get('Category', '').strip() for r in self.rows)
            return None
        for row in candidates:
            if row['min_size_mm'] <= line_size <= row['max_size_mm']:
                return row
        return max(candidates, key=lambda r: r['max_size_mm'])


def calculate_section_frequencies(sections, detections, freq_table: FrequencyTable) -> List[Dict]:
    """
    For each section, sum the frequencies for each hole size and total.
    Returns a list of dicts: {section, tiny, small, medium, large, fbr, total}
    """
    import sys
    # Map section name to Section object
    section_map = {s.name: s for s in sections}
    # Group detections by section
    section_detections = defaultdict(list)
    for d in detections:
        section_detections[getattr(d, 'section', 'Unassigned')].append(d)
    results = []
    for section_name, section in section_map.items():
        # Get all detections for this section
        dets = section_detections.get(section_name, [])
        # For each detection, get category and line size
        freq_sums = {col: 0.0 for col in HOLE_SIZE_COLS}
        for d in dets:
            # Determine category
            raw_name = getattr(d, 'name', None)
            category = get_frequency_category(raw_name)
            # Determine line size (override or inherit)
            line_size = d.line_size if getattr(d, 'line_size', None) is not None else section.line_size
            count = getattr(d, 'count', 1)
            
            row = freq_table.lookup(category, line_size)
            
            for col in HOLE_SIZE_COLS:
                try:
                    freq_sums[col] += float(row[col]) * count
                except Exception as e:
                    raise ValueError(f"Error adding frequency: {e}")
            
        total = sum(freq_sums.values())
        results.append({
            'section': section_name,
            'tiny': freq_sums[HOLE_SIZE_COLS[0]],
            'small': freq_sums[HOLE_SIZE_COLS[1]],
            'medium': freq_sums[HOLE_SIZE_COLS[2]],
            'large': freq_sums[HOLE_SIZE_COLS[3]],
            'fbr': freq_sums[HOLE_SIZE_COLS[4]],
            'total': total
        })
    return results 