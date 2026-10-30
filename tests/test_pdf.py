import numpy as np
import pytest

from spectra.core.pdfdoc import PdfDoc
from spectra.core.pdfwriter import PdfWriter


@pytest.fixture(scope="module")
def rotated(tmp_path_factory):
    w = PdfWriter()
    for rot in (0, 90, 180, 270):
        p = w.new_page(600, 400, rotate=rot)
        p.line(100, 100, 200, 100)
        p.text(50, 300, "PT-1001", size=10)
        p.annotation({"Subtype": "/Square", "Rect": p.rect_to_pdf(400, 50, 420, 70), "Subj": "SHX Text", "Contents": "LT 200"})
    path = tmp_path_factory.mktemp("pdf") / "rot.pdf"
    w.save(path)
    with PdfDoc(path) as doc:
        yield doc


@pytest.mark.parametrize(
    "page, expected",
    [(0, (100, 100, 200, 100)), (1, (300, 100, 300, 200)), (2, (500, 300, 400, 300)), (3, (100, 500, 100, 400))],
)
def test_vectors_follow_page_rotation(rotated, page, expected):
    seg = rotated.vectors(page, use_cache=False).segs[0]
    assert np.allclose(seg, expected, atol=0.01)


@pytest.mark.parametrize("page", range(4))
def test_vectors_agree_with_rendering(rotated, page):
    """Strokes extracted from the PDF land on the dark pixels PDFium renders."""
    img = rotated.render(page, 72)
    x0, y0, x1, y1 = rotated.vectors(page).segs[0]
    mx, my = int(round((x0 + x1) / 2)), int(round((y0 + y1) / 2))
    assert img[my - 1 : my + 2, mx - 1 : mx + 2].min() < 128


def test_render_clip_is_in_display_points(rotated):
    img = rotated.render(0, 144, clip=(90, 90, 210, 110))
    assert img.shape[:2] == (40, 240)
    ys, xs = np.nonzero(img.min(axis=2) < 128)
    assert (xs.min(), xs.max()) == (20, 219) and set(ys) <= {19, 20}


def test_words_with_angle_and_shx_annotation_text(rotated):
    words0 = {w.text: w for w in rotated.words(0)}
    assert words0["PT-1001"].angle == 0.0
    assert words0["LT 200"].source == "annotation"
    words1 = {w.text: w for w in rotated.words(1)}
    assert words1["PT-1001"].angle == -90.0
