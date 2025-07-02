#!/usr/bin/env python3
"""
Spectra Analyser - Main entry point
"""

import sys
import os

# Add the current directory to Python path so relative imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.app import main

if __name__ == "__main__":
    main() 