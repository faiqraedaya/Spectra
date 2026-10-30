"""Export reviewed drawings as a COCO detection dataset of page tiles.

Layout follows the Roboflow COCO convention RF-DETR reads:

    <out>/train/_annotations.coco.json + images
    <out>/valid/...
    <out>/test/...
    <out>/dataset.json   class list, render settings, sources and a content hash

Splits are assigned per sheet (never per tile), so tiles of one sheet can
never appear in both training and test data. The assignment is a stable hash
of the file's SHA-256 and page number unless set explicitly. For a test of
unseen drawing styles, keep whole clients in a separate project and pass
split="test" for their pages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .geometry import Box, intersection, tile_grid
from .pdfdoc import PdfDoc
from .project import Item

SPLITS = ("train", "valid", "test")


@dataclass
class PageSource:
    pdf_path: str
    sha256: str
    page: int
    items: list[Item]
    split: str = ""  # empty: assigned by hash


@dataclass
class ExportSettings:
    dpi: float = 200.0
    tile: int = 512
    overlap: int = 128
    min_visible: float = 0.6  # drop a box from a tile if less than this fraction is inside it
    empty_keep: float = 0.15  # fraction of tiles without objects to keep
    split_fractions: tuple[float, float, float] = (0.8, 0.1, 0.1)
    image_format: str = "png"
    classes: list[str] = field(default_factory=list)  # empty: all classes present, sorted


def assign_split(sha256: str, fractions: tuple[float, float, float]) -> str:
    u = int(hashlib.sha256(sha256.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if u < fractions[0]:
        return "train"
    if u < fractions[0] + fractions[1]:
        return "valid"
    return "test"


def export_coco(sources: list[PageSource], out_dir: str | Path, settings: ExportSettings, progress=None) -> dict:
    from PIL import Image

    out = Path(out_dir)
    classes = settings.classes or sorted({i.cls for s in sources for i in s.items})
    cat_id = {c: k for k, c in enumerate(classes)}
    coco = {s: {"images": [], "annotations": [], "categories": [{"id": k, "name": c, "supercategory": c} for c, k in cat_id.items()]} for s in SPLITS}
    for s in SPLITS:
        (out / s).mkdir(parents=True, exist_ok=True)
    k = settings.dpi / 72.0
    ann_id = 0
    stats = {s: {"images": 0, "boxes": 0} for s in SPLITS}
    docs: dict[str, PdfDoc] = {}
    try:
        for n, src in enumerate(sources):
            split = src.split or assign_split(f"{src.sha256}:{src.page}", settings.split_fractions)
            pdf = docs.setdefault(src.pdf_path, PdfDoc(src.pdf_path))
            img = pdf.render(src.page, settings.dpi)
            h, w = img.shape[:2]
            boxes_px = [(tuple(v * k for v in it.box), it.cls) for it in src.items if it.cls in cat_id]
            for t in tile_grid(w, h, settings.tile, settings.overlap):
                tb: Box = t.box
                anns = []
                for b, cls in boxes_px:
                    inter = intersection(b, tb)
                    full = (b[2] - b[0]) * (b[3] - b[1])
                    if full <= 0 or inter / full < settings.min_visible:
                        continue
                    x0, y0 = max(b[0], tb[0]) - t.x, max(b[1], tb[1]) - t.y
                    x1, y1 = min(b[2], tb[2]) - t.x, min(b[3], tb[3]) - t.y
                    anns.append((cat_id[cls], [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)]))
                name = f"{src.sha256[:12]}_p{src.page + 1}_{t.x}_{t.y}.{settings.image_format}"
                if not anns:
                    keep = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < settings.empty_keep
                    if not keep:
                        continue
                crop = img[t.y : t.y + t.size, t.x : t.x + t.size]
                if crop.shape[:2] != (t.size, t.size):
                    pad = np.full((t.size, t.size, 3), 255, np.uint8)
                    pad[: crop.shape[0], : crop.shape[1]] = crop
                    crop = pad
                Image.fromarray(crop).save(out / split / name)
                image_id = len(coco[split]["images"])
                coco[split]["images"].append({"id": image_id, "file_name": name, "width": t.size, "height": t.size})
                for cid, bbox in anns:
                    coco[split]["annotations"].append(
                        {"id": ann_id, "image_id": image_id, "category_id": cid, "bbox": bbox, "area": bbox[2] * bbox[3], "iscrowd": 0}
                    )
                    ann_id += 1
                stats[split]["images"] += 1
                stats[split]["boxes"] += len(anns)
            if progress:
                progress(n + 1, len(sources))
    finally:
        for d in docs.values():
            d.close()
    for s in SPLITS:
        (out / s / "_annotations.coco.json").write_text(json.dumps(coco[s]), encoding="utf-8")
    meta = {
        "classes": classes,
        "dpi": settings.dpi,
        "tile": settings.tile,
        "overlap": settings.overlap,
        "sources": [{"sha256": s.sha256, "page": s.page, "split": s.split or assign_split(f"{s.sha256}:{s.page}", settings.split_fractions),
                     "items": len(s.items)} for s in sources],
        "stats": stats,
    }
    meta["hash"] = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:16]
    (out / "dataset.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta
