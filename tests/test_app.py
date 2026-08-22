import pytest
from PySide6.QtWidgets import QApplication
from spectra.analyser.core.main_window import Spectra
from spectra.analyser.config.settings import APP_TITLE

@pytest.fixture(scope="session")
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_spectra_window_title(app):
    window = Spectra()
    expected_title = f"{APP_TITLE} - New Project"
    assert window.windowTitle() == expected_title
    window.close() 