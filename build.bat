python -m nuitka ^
    --output-dir=dist ^
    --output-filename=spectra.exe ^
    --onefile ^
    --enable-plugin=pyside6 ^
    --windows-icon-from-ico=src/spectra/analyser/assets/images/spectra_logo.ico ^
    --include-data-dir=src/spectra/analyser/assets=assets ^
    src/spectra/analyser/main.py