"""Item sizes from line numbers printed along the pipework.

Heuristic: a valve or fitting sits on a pipe run; the run's line number is
printed parallel to the pipe, close to it, somewhere along the same straight
line. For each item we find the pipe strokes that touch it, then the nearest
parallel line number lying on that pipe's axis. The chosen text is recorded
on the item so the size can be traced and checked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .geometry import Box, centre, expand, mm_to_pt
from .pdfdoc import Word
from .sizes import DEFAULT_LINE_NUMBER, parse_line_number
from .vectors import PageVectors

PIPE_MIN_STROKE = mm_to_pt(8.0)
AXIS_OFFSET = mm_to_pt(8.0)
SEARCH_ALONG = mm_to_pt(1200.0)
FALLBACK_RADIUS = mm_to_pt(40.0)


@dataclass(frozen=True)
class LineNumber:
    text: str
    box: Box
    angle: float
    size_mm: float


def find_line_numbers(words: list[Word], pattern: str = "") -> list[LineNumber]:
    out = []
    for w in words:
        size = parse_line_number(w.text, pattern or DEFAULT_LINE_NUMBER)
        if size is not None:
            out.append(LineNumber(w.text, w.box, w.angle, size))
    return out


def _axis_of(pv: PageVectors, box: Box) -> list[tuple[float, float, float, float]]:
    """Directions and positions of pipe strokes touching the item box."""
    idx = pv.in_box(expand(box, 1.0))
    idx = idx[pv.length[idx] >= PIPE_MIN_STROKE]
    axes = []
    for i in idx:
        x0, y0, x1, y1 = pv.s[i]
        L = pv.length[i]
        axes.append((x0, y0, (x1 - x0) / L, (y1 - y0) / L))
    return axes


def infer_size(box: Box, pv: PageVectors | None, numbers: list[LineNumber]) -> LineNumber | None:
    if not numbers:
        return None
    cx, cy = centre(box)
    best: tuple[float, LineNumber] | None = None
    for ox, oy, dx, dy in _axis_of(pv, box) if pv is not None else []:
        pipe_angle = math.degrees(math.atan2(-dy, dx)) % 180
        for ln in numbers:
            if abs(((ln.angle % 180) - pipe_angle + 90) % 180 - 90) > 10:
                continue
            tx, ty = centre(ln.box)
            along = (tx - cx) * dx + (ty - cy) * dy
            across = abs((tx - ox) * dy - (ty - oy) * dx)
            if across <= AXIS_OFFSET and abs(along) <= SEARCH_ALONG:
                if best is None or abs(along) < best[0]:
                    best = (abs(along), ln)
    if best is not None:
        return best[1]
    dists = [math.hypot(centre(ln.box)[0] - cx, centre(ln.box)[1] - cy) for ln in numbers]
    k = int(np.argmin(dists))
    return numbers[k] if dists[k] <= FALLBACK_RADIUS else None
