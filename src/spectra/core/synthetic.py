"""Synthetic CAD-style P&IDs with ground truth and Bluebeam-style markups.

Used by the tests and the demo. Symbols follow common ISO 10628 / ISA 5.1
shapes, drawn as vector strokes the way a CAD export draws block references.
The ground truth lists every symbol box; the markups mimic an engineer's
Bluebeam Count markups (type and size in the label, one vertex per item,
with some items deliberately left unmarked).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import Box, mm_to_pt
from .pdfwriter import PageBuilder, PdfWriter

MM = mm_to_pt(1.0)

# Symbol strokes in mm, centred on the symbol origin with the pipe along x.
# Each entry: list of (kind, data) where kind is "poly", "closed", "fill",
# "circle", "fcircle".
SYMBOLS: dict[str, list[tuple[str, object]]] = {
    "gate_valve": [("closed", [(-3, -2), (0, 0), (-3, 2)]), ("closed", [(3, -2), (0, 0), (3, 2)])],
    "globe_valve": [
        ("closed", [(-3, -2), (0, 0), (-3, 2)]),
        ("closed", [(3, -2), (0, 0), (3, 2)]),
        ("fcircle", (0, 0, 0.9)),
    ],
    "ball_valve": [
        ("closed", [(-3, -2), (0, 0), (-3, 2)]),
        ("closed", [(3, -2), (0, 0), (3, 2)]),
        ("circle", (0, 0, 1.3)),
    ],
    "check_valve": [
        ("closed", [(-3, -2), (0, 0), (-3, 2)]),
        ("fill", [(3, -2), (0, 0), (3, 2)]),
        ("poly", [(0, -2.6), (0, 2.6)]),
    ],
    "actuated_valve": [
        ("closed", [(-3, -2), (0, 0), (-3, 2)]),
        ("closed", [(3, -2), (0, 0), (3, 2)]),
        ("poly", [(0, 0), (0, -5)]),
        ("closed", [(-2.5, -5), (2.5, -5), (2.5, -7.5), (-2.5, -7.5)]),
    ],
    "control_valve": [
        ("closed", [(-3, -2), (0, 0), (-3, 2)]),
        ("closed", [(3, -2), (0, 0), (3, 2)]),
        ("poly", [(0, 0), (0, -4.5)]),
        ("poly", [(-3, -4.5), (3, -4.5)]),
        ("arc", (0, -4.5, 3.0)),
    ],
    "relief_valve": [
        ("closed", [(-2, 3), (2, 3), (0, 0)]),
        ("closed", [(3, -2), (3, 2), (0, 0)]),
        ("poly", [(0, 0), (0, -2), (-1, -2.5), (1, -3.2), (-1, -3.9), (1, -4.6), (0, -5)]),
    ],
    "flange": [("poly", [(-0.6, -2.5), (-0.6, 2.5)]), ("poly", [(0.6, -2.5), (0.6, 2.5)])],
    "reducer": [("closed", [(-2, -2), (2, -1.2), (2, 1.2), (-2, 2)])],
    "spectacle_blind": [
        ("circle", (-1.6, 0, 1.4)),
        ("fcircle", (1.6, 0, 1.4)),
        ("poly", [(-0.2, 0), (0.2, 0)]),
    ],
    "instrument": [("circle", (0, 0, 5.0))],
    "off_page_connector": [("closed", [(-6, -3), (3, -3), (6, 0), (3, 3), (-6, 3)])],
}

# How each synthetic symbol is counted (used for labels and the demo).
PARTS_LABEL = {
    "gate_valve": "Manual Valve",
    "globe_valve": "Manual Valve",
    "ball_valve": "Manual Valve",
    "check_valve": "Check Valve",
    "actuated_valve": "Actuated Valve",
    "control_valve": "Actuated Valve",
    "relief_valve": "Relief Valve",
    "flange": "Flange",
    "instrument": "Instrument",
}

TO_CLASS = {
    "gate_valve": "manual_valve",
    "globe_valve": "manual_valve",
    "ball_valve": "manual_valve",
    "check_valve": "check_valve",
    "actuated_valve": "actuated_valve",
    "control_valve": "actuated_valve",
    "relief_valve": "relief_valve",
    "flange": "flange",
    "instrument": "instrument",
    "reducer": "reducer",
    "spectacle_blind": "spectacle_blind",
    "off_page_connector": "off_page_connector",
}

INCH_SIZES = [1, 2, 3, 4, 6, 8, 10, 12]


@dataclass
class TruthItem:
    symbol: str
    cls: str
    page: int
    box: Box
    size_in: float | None
    tag: str = ""


@dataclass
class SyntheticDrawing:
    path: Path
    truth: list[TruthItem] = field(default_factory=list)
    marked: list[TruthItem] = field(default_factory=list)


def _tf(pts, x, y, rot, mirror, scale):
    out = []
    a = math.radians(rot)
    c, s = round(math.cos(a)), round(math.sin(a))
    for px, py in pts:
        if mirror:
            px = -px
        rx, ry = c * px - s * py, s * px + c * py
        out.append((x + rx * MM * scale, y + ry * MM * scale))
    return out


def draw_symbol(p: PageBuilder, name: str, x: float, y: float, rot: int = 0, mirror: bool = False, scale: float = 1.0) -> Box:
    """Draw a symbol at (x, y) points; returns its box in display points."""
    xs: list[float] = []
    ys: list[float] = []
    for kind, data in SYMBOLS[name]:
        if kind in ("poly", "closed", "fill"):
            pts = _tf(data, x, y, rot, mirror, scale)
            p.polyline(pts, close=kind != "poly", fill=kind == "fill")
            xs += [q[0] for q in pts]
            ys += [q[1] for q in pts]
        elif kind in ("circle", "fcircle"):
            cx, cy, r = data  # type: ignore[misc]
            (qx, qy), = _tf([(cx, cy)], x, y, rot, mirror, scale)
            rr = r * MM * scale
            p.circle(qx, qy, rr, fill=kind == "fcircle")
            xs += [qx - rr, qx + rr]
            ys += [qy - rr, qy + rr]
        elif kind == "arc":
            cx, cy, r = data  # type: ignore[misc]
            pts = [(cx + r * math.cos(t), cy - r * math.sin(t)) for t in [k * math.pi / 12 for k in range(13)]]
            pts = _tf(pts, x, y, rot, mirror, scale)
            p.polyline(pts)
            xs += [q[0] for q in pts]
            ys += [q[1] for q in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _half_extent(name: str, rot: int) -> float:
    """Half the symbol length along the pipe, in points."""
    xs = []
    for kind, data in SYMBOLS[name]:
        if kind in ("circle", "fcircle", "arc"):
            cx, cy, r = data  # type: ignore[misc]
            xs += [cx - r, cx + r] if rot in (0, 180) else [cy - r, cy + r]
        else:
            for px, py in data:  # type: ignore[union-attr]
                xs.append(px if rot in (0, 180) else py)
    return max(abs(v) for v in xs) * MM


def make_drawing(
    path: str | Path,
    seed: int = 1,
    pages: int = 2,
    mark_fraction: float = 0.85,
    rotate_second_page: bool = True,
    style_scale: float = 1.0,
) -> SyntheticDrawing:
    """Write an A1 landscape synthetic P&ID set and return its ground truth."""
    rnd = random.Random(seed)
    w, h = 841 * MM, 594 * MM
    writer = PdfWriter()
    result = SyntheticDrawing(Path(path))
    tag_no = 1000

    for page_index in range(pages):
        rotate = 90 if (rotate_second_page and page_index == 1) else 0
        # Content is authored in unrotated coordinates; a 90-degree /Rotate
        # page is authored portrait so it displays landscape.
        pw, ph = (h, w) if rotate == 90 else (w, h)
        p = writer.new_page(pw, ph, rotate=rotate)
        p.line_width(0.7)
        p.polyline([(10 * MM, 10 * MM), (pw - 10 * MM, 10 * MM), (pw - 10 * MM, ph - 10 * MM), (10 * MM, ph - 10 * MM)], close=True)
        p.text(pw - 180 * MM, ph - 20 * MM, f"SYNTHETIC P&ID  DWG-{seed:03d}-{page_index + 1:02d}", size=14)
        page_truth: list[TruthItem] = []

        # Horizontal pipe runs with inline components, and vertical branches.
        n_runs = 9
        for r in range(n_runs):
            y = (40 + r * (ph / MM - 80) / (n_runs - 1)) * MM
            size = rnd.choice(INCH_SIZES)
            p.line_width(0.5)
            p.text(30 * MM, y - 2 * MM, f'{size}"-P-{1000 + 10 * r + page_index}-A1A', size=6)
            x = 80 * MM
            p.line_width(0.35)
            sequence = [rnd.choice(["gate_valve", "globe_valve", "ball_valve", "check_valve", "actuated_valve",
                                    "control_valve", "flange", "flange", "reducer", "spectacle_blind"])
                        for _ in range(rnd.randint(6, 10))]
            start = x
            for name in sequence:
                gap = rnd.uniform(25, 60) * MM
                rot = rnd.choice([0, 180])
                mirror = rnd.random() < 0.3
                hx = _half_extent(name, rot) * style_scale
                cx = x + gap + hx
                if cx + hx > pw - 60 * MM:
                    break
                p.line(start, y, cx - hx, y)
                box = draw_symbol(p, name, cx, y, rot, mirror, style_scale)
                tag = ""
                if name.endswith("valve"):
                    prefix = {"actuated_valve": "ESDV", "control_valve": "FV", "check_valve": "NRV"}.get(name, "HV")
                    tag = f"{prefix}-{tag_no}"
                    tag_no += 1
                    p.text(cx - 5 * MM, y + 6 * MM, tag, size=5)
                page_truth.append(TruthItem(name, TO_CLASS[name], page_index, box, size, tag))
                start = cx + hx
                x = cx + hx
            p.line(start, y, pw - 40 * MM, y)
            end_box = draw_symbol(p, "off_page_connector", pw - 34 * MM, y, 0, False, style_scale)
            page_truth.append(TruthItem("off_page_connector", "off_page_connector", page_index, end_box, None))

            # One instrument tapping per run.
            ix = rnd.uniform(120, pw / MM - 120) * MM
            iy = y - 20 * MM
            if not any(t.box[0] - 8 * MM < ix < t.box[2] + 8 * MM for t in page_truth if abs((t.box[1] + t.box[3]) / 2 - y) < 3 * MM):
                p.line(ix, y, ix, iy + 5 * MM * style_scale)
                box = draw_symbol(p, "instrument", ix, iy, 0, False, style_scale)
                fn = rnd.choice(["PT", "TT", "FT", "LT", "PI"])
                p.text(ix - 2.2 * MM, iy - 0.3 * MM, fn, size=6)
                p.text(ix - 3.0 * MM, iy + 2.6 * MM, str(tag_no), size=5)
                page_truth.append(TruthItem("instrument", "instrument", page_index, box, size, f"{fn}-{tag_no}"))
                tag_no += 1

            # Occasional relief valve on a vertical branch.
            if rnd.random() < 0.5:
                rx = rnd.uniform(120, pw / MM - 120) * MM
                if not any(t.box[0] - 10 * MM < rx < t.box[2] + 10 * MM for t in page_truth):
                    # Rotated 180 degrees so the inlet faces the pipe above.
                    p.line(rx, y, rx, y + 15 * MM - 3 * MM * style_scale)
                    box = draw_symbol(p, "relief_valve", rx, y + 15 * MM, 180, False, style_scale)
                    p.line(rx - 3 * MM * style_scale, y + 15 * MM, rx - 18 * MM, y + 15 * MM)
                    page_truth.append(TruthItem("relief_valve", "relief_valve", page_index, box, max(1, size // 4), f"PSV-{tag_no}"))
                    tag_no += 1

        # Bluebeam-style Count markups, grouped by label.
        groups: dict[str, list[TruthItem]] = {}
        for t in page_truth:
            label = PARTS_LABEL.get(t.symbol)
            if label is None or rnd.random() > mark_fraction:
                continue
            size_txt = f'{t.size_in:g}"' if t.size_in else ""
            groups.setdefault(f"{label} {size_txt}".strip(), []).append(t)
            result.marked.append(t)
        for label, items in groups.items():
            pts = []
            for t in items:
                cx = (t.box[0] + t.box[2]) / 2 + rnd.uniform(-1.0, 1.0) * MM
                cy = (t.box[1] + t.box[3]) / 2 + rnd.uniform(-1.0, 1.0) * MM
                pts.append(_display_to_user(cx, cy, pw, ph, rotate))
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            p.annotation(
                {
                    "Subtype": "/PolyLine",
                    "Rect": [min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5],
                    "Vertices": [v for q in pts for v in q],
                    "Subj": "Count Measurement",
                    "Label": label,
                    "IT": "/PolyLineCount",
                    "NumCounts": len(pts),
                    "CountStyle": "/Circle",
                    "C": [1, 0, 0],
                    "T": "Engineer",
                    "Contents": f"{len(pts)} Count",
                }
            )
        result.truth.extend(page_truth)
    writer.save(path)
    # Truth boxes were computed in authoring coordinates; convert for rotated pages.
    for t in result.truth:
        if rotate_second_page and t.page == 1:
            pw, ph = h, w
            x0, y0, x1, y1 = t.box
            # authoring (u, v) -> display (H - v, u) for /Rotate 90, H = authoring height
            t.box = (ph - y1, x0, ph - y0, x1)
    return result


def _display_to_user(x: float, y: float, pw: float, ph: float, rotate: int) -> tuple[float, float]:
    """Authoring coordinates (top-left origin, unrotated) to PDF user space."""
    return (x, ph - y)
