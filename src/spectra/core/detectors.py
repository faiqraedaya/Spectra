"""Learned symbol detection with an ONNX model, tiled over full drawings.

The model is any RF-DETR export (Apache-2.0) with outputs "dets" (normalised
cx, cy, w, h per query) and "labels" (per-class logits, background in the
last slot). A model folder holds model.onnx and model_card.json:

    {"classes": ["manual_valve", ...], "resolution": 512, "dpi": 200,
     "overlap": 128, "large_classes": ["vessel", ...], "background_class_id": -1}

Pages are rendered at the card's DPI and cut into resolution-sized tiles, so
a 6 mm valve is about 47 px whatever the sheet size. Tile detections are
mapped back to page points and merged (see geometry.merge_candidates).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .geometry import Candidate, merge_candidates, tile_grid
from .pdfdoc import PdfDoc

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
EDGE_MARGIN_PX = 4


@dataclass
class ModelCard:
    classes: list[str]
    resolution: int = 512
    dpi: float = 200.0
    overlap: int = 128
    large_classes: list[str] = field(default_factory=list)
    background_class_id: int | None = -1
    name: str = ""
    trained_on: str = ""
    metrics: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> ModelCard:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.__dict__, indent=1), encoding="utf-8")


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -88, 88)))


class OnnxDetector:
    def __init__(self, model_dir: str | Path, threads: int | None = None):
        import onnxruntime as ort

        model_dir = Path(model_dir)
        self.card = ModelCard.load(model_dir / "model_card.json")
        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(model_dir / "model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        names = [o.name for o in self.session.get_outputs()]
        self._boxes = next(i for i, n in enumerate(names) if "dets" in n)
        self._logits = next(i for i, n in enumerate(names) if "labels" in n)

    def predict_tile(self, rgb: np.ndarray, threshold: float) -> list[tuple[tuple[float, float, float, float], int, float]]:
        """Detections on one tile: (x0, y0, x1, y1) in tile pixels, class index, score."""
        r = self.card.resolution
        img = rgb if rgb.shape[:2] == (r, r) else _resize(rgb, r)
        x = ((img.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD).transpose(2, 0, 1)[None]
        out = self.session.run(None, {self.input_name: x})
        boxes, logits = out[self._boxes][0], out[self._logits][0]
        scores = _sigmoid(logits)
        if self.card.background_class_id is not None:
            scores = np.delete(scores, self.card.background_class_id % scores.shape[1], axis=1)
        q, c = np.nonzero(scores > threshold)
        sx, sy = rgb.shape[1], rgb.shape[0]
        res = []
        for qi, ci in zip(q, c):
            cx, cy, w, h = boxes[qi]
            res.append(((float((cx - w / 2) * sx), float((cy - h / 2) * sy), float((cx + w / 2) * sx), float((cy + h / 2) * sy)), int(ci), float(scores[qi, ci])))
        return res


def _resize(rgb: np.ndarray, size: int) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.fromarray(rgb).resize((size, size), Image.BILINEAR))


def detect_page(pdf: PdfDoc, page: int, det: OnnxDetector, threshold: float = 0.35, progress=None) -> list[Candidate]:
    """Tiled detection over a whole page; boxes in display points."""
    card = det.card
    img = pdf.render(page, card.dpi)
    h, w = img.shape[:2]
    tiles = tile_grid(w, h, card.resolution, card.overlap)
    k = 72.0 / card.dpi
    cands: list[Candidate] = []
    for n, t in enumerate(tiles):
        crop = img[t.y : t.y + t.size, t.x : t.x + t.size]
        if crop.shape[0] != t.size or crop.shape[1] != t.size:  # page smaller than a tile
            pad = np.full((t.size, t.size, 3), 255, np.uint8)
            pad[: crop.shape[0], : crop.shape[1]] = crop
            crop = pad
        if crop.min() > 245:  # blank paper
            continue
        inner = t.inner_edges()
        for (x0, y0, x1, y1), ci, score in det.predict_tile(crop, threshold):
            truncated = (
                (inner[0] and x0 <= EDGE_MARGIN_PX)
                or (inner[1] and y0 <= EDGE_MARGIN_PX)
                or (inner[2] and x1 >= t.size - EDGE_MARGIN_PX)
                or (inner[3] and y1 >= t.size - EDGE_MARGIN_PX)
            )
            box = ((t.x + x0) * k, (t.y + y0) * k, (t.x + x1) * k, (t.y + y1) * k)
            cands.append(Candidate(box, card.classes[ci], score, truncated))
        if progress:
            progress(n + 1, len(tiles))
    if card.large_classes:
        cands += _large_pass(pdf, page, det, threshold)
    return merge_candidates(cands)


def _large_pass(pdf: PdfDoc, page: int, det: OnnxDetector, threshold: float) -> list[Candidate]:
    """Whole page at low resolution, for equipment larger than the tile overlap."""
    w, h = pdf.page_size(page)
    r = det.card.resolution
    dpi = 72.0 * r / max(w, h)
    img = pdf.render(page, dpi)
    canvas = np.full((r, r, 3), 255, np.uint8)
    canvas[: img.shape[0], : img.shape[1]] = img[:r, :r]
    k = 72.0 / dpi
    out = []
    for (x0, y0, x1, y1), ci, score in det.predict_tile(canvas, threshold):
        name = det.card.classes[ci]
        if name in det.card.large_classes:
            out.append(Candidate((x0 * k, y0 * k, x1 * k, y1 * k), name, score))
    return out
