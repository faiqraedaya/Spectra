import sys

from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QApplication, QSplashScreen
import os

from config.settings import SPLASH_SCREEN_PATH

from .main_window import Spectra

def main():
    app = QApplication(sys.argv)
    # Set application icon
    icon_path = os.path.join(os.path.dirname(__file__), '../assets/images/spectra_logo.ico')
    app.setWindowIcon(QIcon(icon_path))
    # Show splash screen
    pixmap = QPixmap(str(SPLASH_SCREEN_PATH))
    splash = QSplashScreen(pixmap)
    splash.show()
    app.processEvents()  # Ensure splash screen is shown

    window = Spectra()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()