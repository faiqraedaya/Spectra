@echo off
rem Build a single-folder Windows distribution of Spectra with Nuitka (Apache-2.0).
rem Run from the repository root in a uv environment:  uv run --with nuitka build.bat
python -m nuitka ^
    --standalone ^
    --output-dir=dist ^
    --output-filename=Spectra.exe ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=src/spectra/assets/spectra.ico ^
    --include-package-data=spectra ^
    --include-package=onnxruntime ^
    src/spectra/gui/app.py
