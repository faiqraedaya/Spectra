# Spectra
*Smart Parts Evaluation & Counting Tool for Risk Assessment*

A P&ID analysis application for detecting and categorizing objects using deep learning models with an intuitive GUI, built for frequency analysis in Quantitative Risk Assessments.

## Features

- **PDF Analysis**: Load and analyse PDF documents
- **Object Detection & Addition**: Detect objects using Roboflow API or add manually
- **Section Management**: Assign and organise objects by sections
- **Frequency Analysis**: Calculate object frequencies by hole size categories
- **Export Results**: Export analysis results to CSV (more export options soon)

## Getting Started

1. Install dependencies:
   ```bash
   pip install PySide6 roboflow pillow pymupdf
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

## Project Structure

The codebase is organized into logical modules:
- **Core**: Main application logic and window management
- **UI**: All user interface components
- **Detection**: Object detection and categorization
- **Sections**: Section management and filtering
- **Utils**: Helper functions and calculations
- **Config**: Centralized configuration management 

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

## License

This project is provided under the MIT License.