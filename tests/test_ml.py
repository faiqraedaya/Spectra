"""Tiled ONNX inference plumbing, dataset export and evaluation."""

import json
import shutil
from pathlib import Path

import pytest

from spectra.core.dataset import ExportSettings, PageSource, export_coco
from spectra.core.detectors import ModelCard, OnnxDetector, detect_page
from spectra.core.evaluation import Det, evaluate
from spectra.core.geometry import iou
from spectra.core.project import Item

DATA = Path(__file__).parent / "data"


@pytest.fixture
def const_model(tmp_path):
    shutil.copy(DATA / "const_model.onnx", tmp_path / "model.onnx")
    ModelCard(["valve", "flange"], resolution=64, dpi=72, overlap=16).save(tmp_path / "model_card.json")
    return OnnxDetector(tmp_path)


def test_decode_follows_rfdetr_layout(const_model):
    import numpy as np

    dets = const_model.predict_tile(np.zeros((64, 64, 3), np.uint8), threshold=0.4)
    # query 0: class 0 (score 0.998) centred; query 1: class 1 at 0.5; query 2 is background
    assert [(c, round(s, 3)) for _, c, s in dets] == [(0, 0.998), (1, 0.5)]
    assert dets[0][0] == pytest.approx((28.8, 28.8, 35.2, 35.2))


def test_tiled_detection_maps_tiles_to_page_points(const_model, synthetic):
    _, pdf = synthetic
    cands = detect_page(pdf, 0, const_model, threshold=0.9)
    assert cands and all(c.label == "valve" for c in cands)
    w, h = pdf.page_size(0)
    # every detection is the centre of a non-blank 64 px tile at 72 dpi (1 px = 1 pt)
    for c in cands:
        cx, cy = (c.box[0] + c.box[2]) / 2, (c.box[1] + c.box[3]) / 2
        assert 0 < cx < w and 0 < cy < h
        assert round((cx - 32) % 48) in (0, 48) or cx > w - 33


def test_export_coco_round_trips_boxes(synthetic, tmp_path):
    drawing, pdf = synthetic
    items = [Item("d", t.page, t.box, t.cls) for t in drawing.truth if t.page == 0]
    meta = export_coco(
        [PageSource(str(pdf.path), pdf.sha256, 0, items, split="train")],
        tmp_path,
        ExportSettings(dpi=150, tile=512, overlap=128, empty_keep=0.0),
    )
    coco = json.loads((tmp_path / "train" / "_annotations.coco.json").read_text())
    assert meta["classes"] == sorted({i.cls for i in items})
    images = {im["id"]: im for im in coco["images"]}
    k = 72 / 150
    covered = set()
    for a in coco["annotations"]:
        name = images[a["image_id"]]["file_name"]
        tx, ty = (int(v) for v in name.rsplit(".", 1)[0].split("_")[-2:])
        x, y, w, h = a["bbox"]
        page_box = ((tx + x) * k, (ty + y) * k, (tx + x + w) * k, (ty + y + h) * k)
        cls = coco["categories"][a["category_id"]]["name"]
        match = [it for it in items if it.cls == cls and iou(page_box, it.box) > 0.55]
        assert match
        covered.update(it.id for it in match)
    assert covered == {it.id for it in items}  # every item appears whole in at least one tile
    assert (tmp_path / "train" / images[0]["file_name"]).exists()


def test_evaluation_counts_no_edit_rate():
    truth = [Det("p", (0, 0, 10, 10), "valve"), Det("p", (20, 0, 30, 10), "valve"), Det("p", (40, 0, 50, 10), "flange")]
    preds = [
        Det("p", (0, 0, 10, 10), "valve", 0.9),  # perfect
        Det("p", (20, 0, 33, 10), "valve", 0.8),  # IoU 0.77: usable without edit
        Det("p", (40, 0, 54, 12), "flange", 0.7),  # IoU 0.6: found, but needs a box edit
        Det("p", (60, 0, 70, 10), "valve", 0.6),  # false positive
    ]
    r = evaluate(truth, preds)
    assert r.found_rate == 1.0
    assert r.no_edit_rate == 0.5
    assert r.per_class["valve"].precision == pytest.approx(2 / 3)
    assert r.per_class["valve"].ap50 == pytest.approx(1.0)
