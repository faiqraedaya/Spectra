"""Pipe connectivity from vector strokes, and isolatable sections from it.

Pipework on a CAD P&ID is drawn as straight strokes that end on a symbol or
on another pipe. The network joins:

- stroke to stroke where an end touches another stroke's end or body (a tee);
  strokes that merely cross are not joined, the usual CAD convention;
- stroke to item where an end touches the item's box or the stroke runs
  through it.

Isolation valves (actuated valves whose tag marks them as shutdown or
isolation valves) are cut points: each connected part of the network left
after removing them is a proposed isolatable section. Boundary valves stay
unassigned so the study's own convention decides which side they count in.

Sections are proposed per sheet; continuations across off-page connectors
are left to the reviewer (merge sections by giving them the same name).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from .geometry import Box, expand, mm_to_pt
from .pdfdoc import FLAG_CURVE, FLAG_DASHED
from .project import Item
from .vectors import PageVectors, _segments_cross, point_segment_distance

DEFAULT_BOUNDARY_TAGS = r"^(ESDV|SDV|ESV|SSV|XV|EIV|BDV|HIPPS|ZV)\b"
MIN_PIPE = mm_to_pt(2.0)
TOUCH = 1.0  # points


@dataclass
class ProposedSection:
    items: list[str]  # item ids
    strokes: np.ndarray  # (n, 4) pipe strokes, for display
    boundaries: list[str] = field(default_factory=list)  # boundary valve ids touching this section
    size_mm: float | None = None


def is_boundary(item: Item, pattern: str = DEFAULT_BOUNDARY_TAGS) -> bool:
    return item.cls == "actuated_valve" and bool(re.match(pattern, (item.tag or "").upper()))


def propose_sections(pv: PageVectors, items: list[Item], boundary_pattern: str = DEFAULT_BOUNDARY_TAGS,
                     counted: set[str] | None = None) -> list[ProposedSection]:
    """Isolatable sections on one sheet. Items must all be on this sheet."""
    if not items or not len(pv):
        return []
    boxes = np.array([it.box for it in items], dtype=np.float64)

    # Pipe strokes: straight, solid, not part of a symbol drawing.
    straight = (pv.data.flags & (FLAG_CURVE | FLAG_DASHED)) == 0
    cand = np.flatnonzero(straight & (pv.length >= MIN_PIPE))
    lo, hi = pv.lo[cand], pv.hi[cand]
    inside_any = np.zeros(len(cand), dtype=bool)
    for b in boxes:
        inside_any |= (lo[:, 0] >= b[0] - 0.5) & (lo[:, 1] >= b[1] - 0.5) & (hi[:, 0] <= b[2] + 0.5) & (hi[:, 1] <= b[3] + 0.5)
    pipes = cand[~inside_any]
    segs = pv.s[pipes]
    n_s, n_i = len(pipes), len(items)
    parent = np.arange(n_s + n_i)

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # stroke-stroke: an end on another stroke (end or body); proper crossings
    # are not joins. A uniform grid keeps this near-linear on dense sheets.
    cell = mm_to_pt(10.0)
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    glo = np.floor((np.minimum(segs[:, :2], segs[:, 2:]) - TOUCH) / cell).astype(int)
    ghi = np.floor((np.maximum(segs[:, :2], segs[:, 2:]) + TOUCH) / cell).astype(int)
    for j in range(n_s):
        for gx in range(glo[j, 0], ghi[j, 0] + 1):
            for gy in range(glo[j, 1], ghi[j, 1] + 1):
                grid[(gx, gy)].append(j)
    for j in range(n_s):
        for x, y in (segs[j, :2], segs[j, 2:]):
            near = grid.get((int(np.floor(x / cell)), int(np.floor(y / cell))), [])
            if len(near) < 2:
                continue
            near_arr = np.array(near)
            d = point_segment_distance(np.array([x]), np.array([y]), segs[near_arr])[0]
            for k in near_arr[d <= TOUCH]:
                if k != j:
                    union(j, int(k))

    # stroke-item: an end touching the item box, or the stroke running through it
    boundary = np.array([is_boundary(it, boundary_pattern) for it in items])
    item_ports: dict[int, set[int]] = defaultdict(set)
    for k, b in enumerate(boxes):
        bb = expand(tuple(b), TOUCH)
        near = np.flatnonzero((pv.hi[pipes, 0] >= bb[0]) & (pv.lo[pipes, 0] <= bb[2]) & (pv.hi[pipes, 1] >= bb[1]) & (pv.lo[pipes, 1] <= bb[3]))
        for j in near:
            x0, y0, x1, y1 = segs[j]
            end_in = any(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for x, y in ((x0, y0), (x1, y1)))
            through = _crosses_box(segs[j], bb)
            if end_in or through:
                item_ports[k].add(int(j))
                if not boundary[k]:
                    union(n_s + k, int(j))

    groups: dict[int, list[int]] = defaultdict(list)
    for k in range(n_i):
        if not boundary[k]:
            groups[find(n_s + k)].append(k)
    stroke_groups: dict[int, list[int]] = defaultdict(list)
    for j in range(n_s):
        stroke_groups[find(j)].append(j)

    out = []
    for root, members in groups.items():
        member_items = [items[k] for k in members]
        if counted is not None and not any(it.cls in counted for it in member_items):
            continue
        strokes = segs[stroke_groups.get(root, [])]
        bounds = [items[k].id for k in range(n_i) if boundary[k] and any(find(j) == root for j in item_ports[k])]
        sizes = Counter(it.size_mm for it in member_items if it.size_mm)
        out.append(ProposedSection([it.id for it in member_items], strokes, bounds, sizes.most_common(1)[0][0] if sizes else None))
    out.sort(key=lambda s: (-len(s.items)))
    return out


def _crosses_box(seg: np.ndarray, b: Box) -> bool:
    """True if the stroke passes through the box (enters one side and leaves another)."""
    x0, y0, x1, y1 = seg
    edges = np.array([[b[0], b[1], b[2], b[1]], [b[2], b[1], b[2], b[3]], [b[2], b[3], b[0], b[3]], [b[0], b[3], b[0], b[1]]])
    return int(_segments_cross(np.array([seg]), edges).sum()) >= 2
