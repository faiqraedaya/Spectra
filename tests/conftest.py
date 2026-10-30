import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_dirs(tmp_path_factory):
    os.environ["SPECTRA_CACHE"] = str(tmp_path_factory.mktemp("cache"))
    os.environ["SPECTRA_DATA"] = str(tmp_path_factory.mktemp("data"))


@pytest.fixture(scope="session")
def synthetic(tmp_path_factory):
    from spectra.core.pdfdoc import PdfDoc
    from spectra.core.synthetic import make_drawing

    path = tmp_path_factory.mktemp("drawings") / "synthetic.pdf"
    drawing = make_drawing(path, seed=3)
    pdf = PdfDoc(path)
    yield drawing, pdf
    pdf.close()
