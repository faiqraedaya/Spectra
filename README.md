# Spectra Analyser

A PDF analysis application for detecting and categorizing objects in technical drawings.

## Project Structure

```
spectra/analyser/
├── assets/                 # Static assets
│   ├── images/            # Image files (splash screens, icons)
│   └── data/              # Data files (CSV, configuration)
├── core/                  # Core application logic
│   ├── app.py            # Main application entry point
│   └── main_window.py    # Main window implementation
├── ui/                    # User interface components
│   ├── pdf_viewer.py     # PDF viewing and annotation
│   ├── dialogs/          # Dialog windows
│   └── widgets/          # Custom widget components
├── detection/             # Object detection functionality
│   ├── types.py          # Detection data types
│   ├── categories_map.py # Category mapping logic
│   └── roboflow.py       # Roboflow API integration
├── sections/              # Section management
│   └── sections.py       # Section data and operations
├── utils/                 # Utility functions
│   └── frequency.py      # Frequency calculations
├── config/                # Configuration and settings
│   └── settings.py       # Application settings
├── main.py               # Application entry point
└── run_analyser.py       # Shortcut launcher (recommended)
```

## Key Features

- **PDF Analysis**: Load and analyze PDF documents
- **Object Detection**: Detect objects using Roboflow API
- **Section Management**: Organize detections by sections
- **Frequency Analysis**: Calculate object frequencies by size categories
- **Export Results**: Export analysis results to CSV

## Getting Started

1. Install dependencies:
   ```bash
   pip install PySide6 ultralytics
   ```

2. Set up Roboflow API key:
   ```bash
   export ROBOFLOW_API_KEY="your_api_key_here"
   ```

3. **Recommended:** Launch the app from the project root using the shortcut:
   ```bash
   python run_analyser.py
   ```
   This ensures all imports work correctly.

   Or, to run directly as a module:
   ```bash
   python -m spectra.analyser.main
   ```

## Configuration

Application settings are centralized in `config/settings.py`:
- Window dimensions and positioning
- Default detection parameters
- File paths for assets
- Table configurations

## Development

The codebase is organized into logical modules:
- **Core**: Main application logic and window management
- **UI**: All user interface components
- **Detection**: Object detection and categorization
- **Sections**: Section management and filtering
- **Utils**: Helper functions and calculations
- **Config**: Centralized configuration management 