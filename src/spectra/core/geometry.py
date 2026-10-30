"""Box geometry, tiling and detection merging.

All boxes are (x0, y0, x1, y1) with x0 <= x1 and y0 <= y1. Within Spectra the
unit is the PDF point (1/72 in) in display space: origin at the top-left of
the page as displayed, y pointing down, page rotation already applied.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

type Box = tuple[float, float, float, float]

MM_PER_PT = 25.4 / 72.0


def mm_to_pt(mm: float) -> float:
    return mm / MM_PER_PT


def pt_to_mm(pt: float) -> float:
    return pt * MM_PER_PT


def normalise(box: Sequence[float]) -> Box:
    x0, y0, x1, y1 = box
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def centre(b: Box) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def intersection(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def iou(a: Box, b: Box) -> float:
    inter = intersection(a, b)
    if inter == 0.0:
        return 0.0
    return inter / (area(a) + area(b) - inter)


def ios(a: Box, b: Box) -> float:
    """Intersection over the smaller box.

    Used instead of IoU when one box may be a truncated copy of the other,
    for example a symbol cut by a tile edge: IoU is low, IoS is close to 1.
    """
    inter = intersection(a, b)
    if inter == 0.0:
        return 0.0
    return inter / max(min(area(a), area(b)), 1e-9)


def union(a: Box, b: Box) -> Box:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def expand(b: Box, d: float) -> Box:
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def contains_point(b: Box, x: float, y: float) -> bool:
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def point_in_polygon(x: float, y: float, poly: Sequence[tuple[float, float]]) -> bool:
    """Even-odd ray casting test."""
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def segment_intersects_box(p: tuple[float, float], q: tuple[float, float], b: Box) -> bool:
    """Liang-Barsky clip test: does segment p-q touch box b?"""
    x0, y0 = p
    dx, dy = q[0] - x0, q[1] - y0
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, x0 - b[0]), (dx, b[2] - x0), (-dy, y0 - b[1]), (dy, b[3] - y0)):
        if pk == 0:
            if qk < 0:
                return False
            continue
        r = qk / pk
        if pk < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


def polyline_intersects_box(points: Sequence[tuple[float, float]], b: Box) -> bool:
    if len(points) == 1:
        return contains_point(b, *points[0])
    return any(segment_intersects_box(points[i], points[i + 1], b) for i in range(len(points) - 1))


# --- Tiling -----------------------------------------------------------------


@dataclass(frozen=True)
class Tile:
    """A square window on a rendered page, in pixels of that render."""

    x: int
    y: int
    size: int
    page_w: int
    page_h: int

    @property
    def box(self) -> Box:
        return (self.x, self.y, self.x + self.size, self.y + self.size)

    def inner_edges(self) -> tuple[bool, bool, bool, bool]:
        """Which edges (left, top, right, bottom) lie inside the page.

        A detection touching an inner edge may be truncated; one touching a
        page edge is not.
        """
        return (
            self.x > 0,
            self.y > 0,
            self.x + self.size < self.page_w,
            self.y + self.size < self.page_h,
        )


def tile_grid(width: int, height: int, tile: int, overlap: int) -> list[Tile]:
    """Cover a width x height image with overlapping square tiles.

    The last tile in each row and column is shifted back to end on the page
    edge, so tiles never need padding unless the page is smaller than a tile.
    """
    if overlap >= tile:
        raise ValueError("overlap must be smaller than the tile size")
    stride = tile - overlap

    def starts(extent: int) -> list[int]:
        if extent <= tile:
            return [0]
        n = math.ceil((extent - tile) / stride) + 1
        s = [i * stride for i in range(n)]
        s[-1] = extent - tile
        return sorted(set(s))

    return [Tile(x, y, tile, width, height) for y in starts(height) for x in starts(width)]


# --- Merging ---------------------------------------------------------------


@dataclass
class Candidate:
    """A detection in page coordinates before merging."""

    box: Box
    label: str
    score: float
    truncated: bool = False
    alternatives: dict[str, float] = field(default_factory=dict)


def merge_candidates(
    cands: Iterable[Candidate],
    ios_threshold: float = 0.5,
    cross_class_ios: float = 0.7,
) -> list[Candidate]:
    """Merge duplicate detections from overlapping tiles.

    1. Truncated boxes are dropped when a whole box of the same class
       overlaps them (the overlap guarantees a neighbour saw the symbol whole).
    2. Greedy non-maximum merging per class using intersection over smaller;
       absorbed boxes widen the kept box and keep the higher score.
    3. Boxes of different classes at the same spot keep the higher score and
       record the runner-up for the review panel.
    """
    items = sorted(cands, key=lambda c: c.score, reverse=True)
    whole = [c for c in items if not c.truncated]
    items = [
        c
        for c in items
        if not (
            c.truncated
            and any(w.label == c.label and ios(w.box, c.box) >= ios_threshold for w in whole)
        )
    ]

    kept: list[Candidate] = []
    for c in items:
        for k in kept:
            if k.label == c.label and ios(k.box, c.box) >= ios_threshold:
                k.box = union(k.box, c.box) if c.truncated or k.truncated else k.box
                k.truncated = k.truncated and c.truncated
                break
        else:
            kept.append(Candidate(c.box, c.label, c.score, c.truncated, dict(c.alternatives)))

    result: list[Candidate] = []
    for c in kept:  # already in descending score order
        for r in result:
            if r.label != c.label and ios(r.box, c.box) >= cross_class_ios:
                r.alternatives[c.label] = max(r.alternatives.get(c.label, 0.0), c.score)
                break
        else:
            result.append(c)
    return result
