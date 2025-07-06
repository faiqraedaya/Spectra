# Spectra

<p align="center">
  <img src="spectra/analyser/assets/images/spectra_splash.png" alt="Spectra Logo" />
</p>
<p style="text-align:center;"></p>

<p align="center">
   <i>
      Smart Parts Evaluation &amp; Counting Tool for Risk Assessments
   </i>
</p>

## Overview 

A P&ID analysis application for detecting and categorizing objects using deep learning models via Roboflow API (local YOLO model support incoming).

Built with PySide6 for an intuitive GUI, allowing easy editing and navigation of PDFs, automatic or manual object additions, live results updates, and robust import/export functionality.

Designed to automate the "Parts Count" methodology for frequency analysis in Quantitative Risk Assessments: a tedious, time-consuming and laborous task.

## Features

- **PDF Analysis**: Load and analyse PDF documents
- **Object Detection & Addition**: Detect objects using Roboflow API or add manually
- **Section Management**: Assign and organise objects by sections
- **Section Drawing**: Draw sections directly on PDF as polylines with interactive tools
- **Frequency Analysis**: Calculate object frequencies by hole size categories
- **Export Results**: Export analysis results to CSV (more export options soon)

## Requirements 
- Python 3.7+
- PySide6
- Roboflow
- Pillow
- PyMuPDF

## Install

1. Clone the repository:
   ```bash
   git clone https://github.com/faiqraedaya/Spectra
   cd "Spectra"
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Roboflow API key:

   On Windows:
   ```bash
   set ROBOFLOW_API_KEY=your_api_key_here
   ```

   On Linux:
   ```bash:
   export ROBOFLOW_API_KEY=your_api_key_here
   ```

## Usage 

1. Launch the application:
   ```bash
   python run_spectra.py
   ```

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