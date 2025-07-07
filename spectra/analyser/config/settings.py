"""
Application settings and configuration.
"""

from pathlib import Path

# Application metadata
APP_NAME = "Spectra"
APP_VERSION = "1.2.0"
APP_TITLE = f"{APP_NAME} {APP_VERSION}"

# Window settings
DEFAULT_WINDOW_WIDTH = 1600
DEFAULT_WINDOW_HEIGHT = 900
DEFAULT_WINDOW_X = 100
DEFAULT_WINDOW_Y = 100

# Detection settings
DEFAULT_CONFIDENCE = 0.5
DEFAULT_OVERLAP = 0.3

# File paths
ASSETS_DIR = Path(__file__).parent.parent / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
DATA_DIR = ASSETS_DIR / "data"

SPLASH_SCREEN_PATH = IMAGES_DIR / "spectra_splash.png"
ICON_PATH = IMAGES_DIR / "spectra_icon"
FREQUENCY_CSV_PATH = DATA_DIR / "frequency.csv"

# Environment variables
ROBOFLOW_API_KEY_ENV = "ROBOFLOW_API_KEY"

# Table settings
RESULTS_TABLE_COLUMNS = [
    "Section",
    "Tiny (1-3 mm)",
    "Small (3-10 mm)", 
    "Medium (10-50 mm)",
    "Large (50-150 mm)",
    "FBR (>150 mm)",
    "Total"
]

# Splitter sizes
MAIN_SPLITTER_SIZES = [400, 1200, 400] 