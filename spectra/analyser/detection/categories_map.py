# categories_map.py

# List of all frequency categories from frequency.csv
FREQUENCY_CATEGORIES = [
    "Steel Pipes",
    "Flexible Piping",
    "Flanged Joints",
    "Manual Valves",
    "Actuated Valves",
    "Instrument Connection",
    "Process Pressure Vessel",
    "Centrifugal Pumps",
    "Reciprocating Pumps",
    "Centrifugal Compressor",
    "Reciprocating Compressor",
    "Shell & Tube (Shell HC)",
    "Shell & Tube (Tube HC)",
    "Plate & Frame / PCHE",
    "Air Cooler",
    "Filters",
    "Pig Traps",
    "Pressure Vessel (Other)",
    "Degasser",
    "Expanders",
    "Xmas Tree",
    "Turbine",
    "SSIV Assembly",
]

# Example mapping from program object types to frequency categories
# Expand this as needed for your object types
OBJECT_TO_FREQUENCY_CATEGORY = {
    "manual valve": "Manual Valves",
    "actuated valve": "Actuated Valves",
    "check valve": "Manual Valves",  # Example: map check valves to manual
    "relief valve": "Manual Valves",  # Example: map relief valves to manual
    "flange": "Flanged Joints",
    "strainer": "Filters",
    "piping": "Steel Pipes",
    "pipe": "Steel Pipes",
    "flexible piping": "Flexible Piping",
    "instrument": "Instrument Connection",
    "expander": "Expanders",
    "centrifugal pump": "Centrifugal Pumps",
    "reciprocating pump": "Reciprocating Pumps",
    "centrifugal compressor": "Centrifugal Compressor",
    "reciprocating compressor": "Reciprocating Compressor",
    "shell & tube (shell hc)": "Shell & Tube (Shell HC)",
    "shell & tube (tube hc)": "Shell & Tube (Tube HC)",
    "plate & frame": "Plate & Frame / PCHE",
    "pche": "Plate & Frame / PCHE",
    "air cooler": "Air Cooler",
    "filter": "Filters",
    "pig trap": "Pig Traps",
    "pressure vessel": "Pressure Vessel (Other)",
    "degasser": "Degasser",
    "xmas tree": "Xmas Tree",
    "turbine": "Turbine",
    "ssiv assembly": "SSIV Assembly",
    # Add more as needed
}

def get_frequency_category(object_type):
    """
    Map a program object type (string) to a frequency category from the frequency table.
    Returns None if not found.
    """
    if not object_type:
        return None
    key = str(object_type).strip().lower()
    result = OBJECT_TO_FREQUENCY_CATEGORY.get(key)
    if result is not None:
        return result
    # Try direct match to frequency categories (case-insensitive)
    for cat in FREQUENCY_CATEGORIES:
        if key == cat.strip().lower():
            return cat
    print(f"[DEBUG] get_frequency_category: No mapping for '{object_type}' (key: '{key}')", flush=True)
    return None

def get_all_frequency_categories():
    """
    Return a list of all frequency categories from the frequency table.
    """
    return FREQUENCY_CATEGORIES.copy()

# Hardcoded mapping from categories.csv
_CATEGORIES_RAW = [
    ("1", "Manual Valve"),
    ("2", "Manual Valve"),
    ("3", "Manual Valve"),
    ("4", "Manual Valve"),
    ("5", "Manual Valve"),
    ("6", "Manual Valve"),
    ("7", "Manual Valve"),
    ("8", "Manual Valve"),
    ("9", "Manual Valve"),
    ("10", "Manual Valve"),
    ("11", "Manual Valve"),
    ("12", "Manual Valve"),
    ("13", "Manual Valve"),
    ("14", "Manual Valve"),
    ("15", "Manual Valve"),
    ("16", "Relief Valve"),
    ("17", "Spectacle Blind"),
    ("18", "Spectacle Blind"),
    ("19", "Spectacle Blind"),
    ("20", "Expander"),
    ("21", "Flange"),
    ("22", "Strainer"),
    ("23", "Piping"),
    ("24", "Check Valve"),
    ("25", "Actuated Valve"),
    ("26", "Instrument"),
    ("27", "Instrument"),
    ("28", "Instrument"),
    ("29", "Instrument"),
    ("30", "Instrument"),
    ("31", "Instrument"),
    ("32", "Instrument"),
    ("Pneumatic valve", "Actuated Valve"),
    ("Two way on-off solenoid valve", "Actuated Valve"),
]

# Build a case-insensitive mapping
def _build_mapping():
    mapping = {}
    for k, v in _CATEGORIES_RAW:
        mapping[str(k).strip().lower()] = v
    return mapping

_CATEGORIES_MAP = _build_mapping()


def get_category(key):
    """
    Get the category for a given key (number or string), case-insensitive.
    Returns 'Unknown' if not found.
    """
    if key is None:
        return "Unknown"
    return _CATEGORIES_MAP.get(str(key).strip().lower(), "Unknown")


def get_all_categories():
    """
    Return a sorted list of all unique categories.
    """
    return sorted(set(_CATEGORIES_MAP.values())) 