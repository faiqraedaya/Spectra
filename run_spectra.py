#!/usr/bin/env python3
"""
Shortcut launcher for Spectra.
"""
import sys
import subprocess

if __name__ == "__main__":
    # Launch the analyser app as a module
    subprocess.run([sys.executable, '-m', 'spectra.analyser.main'])