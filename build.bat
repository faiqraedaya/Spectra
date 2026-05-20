python -m nuitka ^
    --output-dir=dist ^
    --output-filename=spectra.exe ^
    --onefile ^
    --enable-plugin=pyside6 ^
    --windows-icon-from-ico=spectra/analyser/assets/images/spectra_logo.ico ^
    --include-data-dir=spectra/analyser/assets=assets ^
    spectra/analyser/main.py