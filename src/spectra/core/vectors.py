"""Symbol geometry from CAD vector line art.

CAD exports draw every copy of a symbol block with the same strokes. This
module finds the strokes that make up one symbol (snapping) so the rest of
Spectra can work with exact symbol boxes and geometric templates instead of
hand-drawn rectangles.

All distances are in PDF points.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import Box, mm_to_pt
from .pdfdoc import VectorData

# A stroke longer than this is treated as a pipe or equipment outline, not part
# of a small symbol. 20 mm covers valves, fittings and instrument bubbles.
SYMBOL_MAX_STROKE = mm_to_pt(20.0)
SYMBOL_MAX_EXTENT = mm_to_pt(30.0)
JOIN_GAP = mm_to_pt(0.5)


@dataclass
class PageVectors:
    """VectorData plus derived arrays for spatial queries."""

    data: VectorData

    def __post_init__(self) -> None:
        s = self.data.segs.astype(np.float64)
        self.s = s
        self.lo = np.minimum(s[:, :2], s[:, 2:])
        self.hi = np.maximum(s[:, :2], s[:, 2:])
        self.length = np.hypot(s[:, 2] - s[:, 0], s[:, 3] - s[:, 1])
        self._keys: np.ndarray | None = None
        self._key_q: float | None = None

    def __len__(self) -> int:
        return len(self.s)

    def in_box(self, b: Box, fully: bool = False) -> np.ndarray:
        """Indices of segments whose bbox intersects (or lies inside) b."""
        if fully:
            m = (self.lo[:, 0] >= b[0]) & (self.lo[:, 1] >= b[1]) & (self.hi[:, 0] <= b[2]) & (self.hi[:, 1] <= b[3])
        else:
            m = (self.hi[:, 0] >= b[0]) & (self.hi[:, 1] >= b[1]) & (self.lo[:, 0] <= b[2]) & (self.lo[:, 1] <= b[3])
        return np.flatnonzero(m)

    def bbox(self, idx: np.ndarray) -> Box:
        return (
            float(self.lo[idx, 0].min()),
            float(self.lo[idx, 1].min()),
            float(self.hi[idx, 0].max()),
            float(self.hi[idx, 1].max()),
        )

    def endpoint_keys(self, q: float) -> np.ndarray:
        """Sorted unique quantised endpoint keys, for fast template checks."""
        if self._keys is None or self._key_q != q:
            pts = np.concatenate([self.s[:, :2], self.s[:, 2:]])
            self._keys = np.unique(_quant_keys(pts, q))
            self._key_q = q
        return self._keys


def _quant_keys(pts: np.ndarray, q: float) -> np.ndarray:
    ix = np.round(pts[..., 0] / q).astype(np.int64)
    iy = np.round(pts[..., 1] / q).astype(np.int64)
    return (ix << 32) + (iy & 0xFFFFFFFF)


def point_segment_distance(px: np.ndarray, py: np.ndarray, segs: np.ndarray) -> np.ndarray:
    """Distance from points (P,) to segments (S, 4); returns (P, S)."""
    x0, y0, x1, y1 = (segs[:, k][None, :] for k in range(4))
    dx, dy = x1 - x0, y1 - y0
    len2 = dx * dx + dy * dy
    t = ((px[:, None] - x0) * dx + (py[:, None] - y0) * dy) / np.where(len2 == 0, 1, len2)
    t = np.clip(t, 0.0, 1.0)
    cx, cy = x0 + t * dx, y0 + t * dy
    return np.hypot(px[:, None] - cx, py[:, None] - cy)


def _segments_cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """(A, B) boolean: proper intersection of segments a (A,4) and b (B,4)."""

    def orient(px, py, qx, qy, rx, ry):
        return np.sign((qx - px) * (ry - py) - (qy - py) * (rx - px))

    ax0, ay0, ax1, ay1 = (a[:, k][:, None] for k in range(4))
    bx0, by0, bx1, by1 = (b[:, k][None, :] for k in range(4))
    o1 = orient(ax0, ay0, ax1, ay1, bx0, by0)
    o2 = orient(ax0, ay0, ax1, ay1, bx1, by1)
    o3 = orient(bx0, by0, bx1, by1, ax0, ay0)
    o4 = orient(bx0, by0, bx1, by1, ax1, ay1)
    return (o1 * o2 < 0) & (o3 * o4 < 0)


def components(pv: PageVectors, idx: np.ndarray, gap: float = JOIN_GAP) -> list[np.ndarray]:
    """Group segments into connected clusters: touching, crossing or within gap."""
    n = len(idx)
    if n == 0:
        return []
    segs = pv.s[idx]
    parent = np.arange(n)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ends_x = np.concatenate([segs[:, 0], segs[:, 2]])
    ends_y = np.concatenate([segs[:, 1], segs[:, 3]])
    chunk = 512
    for start in range(0, 2 * n, chunk):
        d = point_segment_distance(ends_x[start : start + chunk], ends_y[start : start + chunk], segs)
        ii, jj = np.nonzero(d <= gap)
        for i, j in zip((ii + start) % n, jj):
            ri, rj = find(int(i)), find(int(j))
            if ri != rj:
                parent[ri] = rj
    for start in range(0, n, chunk):
        c = _segments_cross(segs[start : start + chunk], segs)
        ii, jj = np.nonzero(c)
        for i, j in zip(ii + start, jj):
            ri, rj = find(int(i)), find(int(j))
            if ri != rj:
                parent[ri] = rj
    roots = np.array([find(i) for i in range(n)])
    return [idx[roots == r] for r in np.unique(roots)]


def prune_tails(pv: PageVectors, idx: np.ndarray, min_len: float = mm_to_pt(3.0), gap: float = JOIN_GAP) -> np.ndarray:
    """Remove connection lines hanging off a symbol.

    A tail is a straight stroke of at least min_len attached to the rest of
    the cluster at one end only, with the other end free (for example the
    tapping line from a pipe to an instrument bubble). Strokes free at both
    ends (a check valve bar crossing the body) or attached at both ends (an
    actuator stem) stay. Repeats until no tail is left.
    """
    from .pdfdoc import FLAG_CURVE

    keep = np.asarray(idx)
    while len(keep) > 1:
        segs = pv.s[keep]
        straight = (pv.data.flags[keep] & FLAG_CURVE) == 0
        long_enough = pv.length[keep] >= min_len
        removed = False
        for k in np.flatnonzero(straight & long_enough):
            others = np.delete(segs, k, axis=0)
            ends = segs[k].reshape(2, 2)
            d = point_segment_distance(ends[:, 0], ends[:, 1], others)
            attached = (d <= gap).any(axis=1)
            if attached.sum() == 1:
                keep = np.delete(keep, k)
                removed = True
                break
        if not removed:
            break
    return keep


def snap_point(
    pv: PageVectors,
    x: float,
    y: float,
    search: float = mm_to_pt(15.0),
    max_extent: float = SYMBOL_MAX_EXTENT,
    max_stroke: float = SYMBOL_MAX_STROKE,
) -> tuple[Box, np.ndarray] | None:
    """Find the symbol at or nearest to (x, y).

    Picks the largest stroke cluster that encloses the point (for example an
    instrument bubble rather than the letters inside it), otherwise the
    nearest cluster, then adds every short stroke inside its box.
    Returns the symbol box and the segment indices, or None.
    """
    window = (x - search, y - search, x + search, y + search)
    idx = pv.in_box(window)
    idx = idx[pv.length[idx] <= max_stroke]
    if not len(idx):
        return None
    comps = [prune_tails(pv, c) for c in components(pv, idx)]
    comps = [c for c in comps if max(_extent(pv.bbox(c))) <= max_extent]
    if not comps:
        return None
    thin = mm_to_pt(0.3)
    best: np.ndarray | None = None
    best_area = -1.0
    for c in comps:
        b = pv.bbox(c)
        w, h = _extent(b)
        if min(w, h) < thin:
            continue  # a lone straight stroke is part of a symbol, not a whole one
        if b[0] - 1 <= x <= b[2] + 1 and b[1] - 1 <= y <= b[3] + 1 and w * h > best_area:
            best, best_area = c, w * h
    if best is None:
        px, py = np.array([x]), np.array([y])
        dist = [float(point_segment_distance(px, py, pv.s[c]).min()) for c in comps]
        order = np.argsort(dist)
        nearest = [comps[i] for i in order if dist[i] <= mm_to_pt(5.0)]
        if not nearest:
            return None
        best = nearest[0]
        # A symbol made of separate parts (a flange's two bars): the point lies
        # between or beside two nearby clusters rather than inside either.
        b0 = pv.bbox(best)
        slack = mm_to_pt(1.5) if min(_extent(b0)) < thin else 0.0
        pair_area = None
        for other in nearest[1:4]:
            u = np.union1d(best, other)
            b = pv.bbox(u)
            w, h = _extent(b)
            if b[0] - slack <= x <= b[2] + slack and b[1] - slack <= y <= b[3] + slack and max(w, h) <= mm_to_pt(12.0):
                if pair_area is None or w * h < pair_area:
                    pair_area, chosen = w * h, u
        if pair_area is not None:
            best = chosen
    box = pv.bbox(best)
    inner = pv.in_box(box, fully=True)
    inner = inner[pv.length[inner] <= max_stroke]
    members = np.union1d(best, inner)
    return pv.bbox(members), members


def _extent(b: Box) -> tuple[float, float]:
    return (b[2] - b[0], b[3] - b[1])


def snap_box(pv: PageVectors, rough: Box, margin: float = 1.0) -> tuple[Box, np.ndarray] | None:
    """Tighten a hand-drawn box to the strokes that lie fully inside it."""
    b = (rough[0] - margin, rough[1] - margin, rough[2] + margin, rough[3] + margin)
    idx = pv.in_box(b, fully=True)
    if not len(idx):
        return None
    return pv.bbox(idx), idx
