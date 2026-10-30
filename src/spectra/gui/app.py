"""Spectra GUI entry point."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .theme import apply_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setOrganizationName("Spectra")
    app.setApplicationName("Spectra")
    apply_theme(app)
    from importlib import resources

    with resources.as_file(resources.files("spectra.assets") / "spectra.ico") as ico:
        app.setWindowIcon(QIcon(str(ico)))
    from .main_window import MainWindow

    win = MainWindow()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    for a in args:
        if a.endswith(".spectra.json"):
            win.open_project(a)
    pdfs = [a for a in args if a.lower().endswith(".pdf")]
    if pdfs:
        win.add_drawings(pdfs)
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
