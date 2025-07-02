import sys

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from config.settings import SPLASH_SCREEN_PATH

from .main_window import Spectra

def main():
    app = QApplication(sys.argv)
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