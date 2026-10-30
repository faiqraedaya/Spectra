"""Find every copy of a symbol from one example (vector template matching).

A template is the set of strokes inside one symbol box, stored relative to
the box centre. Matching tries the 8 right-angle rotations and mirror images
(how CAD blocks are placed on P&IDs): for each page stroke with the same
length as the template's anchor stroke it proposes a placement, then checks
that the other template strokes exist on the page. Scoring is the fraction of
template stroke length found, so a match tolerates extra strokes (pipes
running through a valve) but not missing ones.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from .geometry import Box, iou, ios
from .vectors import PageVectors

# The 8 orientation-preserving and mirroring right-angle transforms (2x2).
DIHEDRAL = [
    np.array(m, dtype=np.float64)
    for m in (
        [[1, 0], [0, 1]],
        [[0, -1], [1, 0]],
        [[-1, 0], [0, -1]],
        [[0, 1], [-1, 0]],
        [[-1, 0], [0, 1]],
        [[1, 0], [0, -1]],
        [[0, 1], [1, 0]],
        [[0, -1], [-1, 0]],
    )
]


@dataclass
class Template:
    segs: np.ndarray  # (M, 4) relative to the box centre, in points
    half: tuple[float, float]  # half width and half height of the symbol box
    label: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    source: str = ""  # free text, e.g. "drawing.pdf p3"

    @classmethod
    def from_page(cls, pv: PageVectors, idx: np.ndarray, box: Box, label: str = "", source: str = "") -> Template:
        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        segs = pv.s[idx] - np.array([cx, cy, cx, cy])
        return cls(segs.astype(np.float64), ((box[2] - box[0]) / 2.0, (box[3] - box[1]) / 2.0), label, source=source)

    @property
    def lengths(self) -> np.ndarray:
        return np.hypot(self.segs[:, 2] - self.segs[:, 0], self.segs[:, 3] - self.segs[:, 1])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "source": self.source,
            "half": list(self.half),
            "segs": np.round(self.segs, 3).tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Template:
        return cls(
            np.array(d["segs"], dtype=np.float64).reshape(-1, 4),
            (float(d["half"][0]), float(d["half"][1])),
            d.get("label", ""),
            d.get("id", uuid.uuid4().hex[:12]),
            d.get("source", ""),
        )

    def signature(self, q: float = 0.5) -> frozenset:
        """Orientation-independent identity, for spotting duplicate templates."""
        best: tuple | None = None
        for m in DIHEDRAL:
            p = np.round((self.segs[:, :2] @ m.T) / q).astype(int).tolist()
            r = np.round((self.segs[:, 2:] @ m.T) / q).astype(int).tolist()
            key = tuple(sorted(tuple(min(a, b) + max(a, b)) for a, b in zip(map(tuple, p), map(tuple, r))))
            if best is None or key < best:
                best = key
        return frozenset(best or ())


@dataclass
class Match:
    box: Box
    score: float
    transform: int  # index into DIHEDRAL
    template_id: str
    label: str


def find_matches(
    tpl: Template,
    pv: PageVectors,
    min_score: float = 0.9,
    min_precision: float = 0.9,
    tol: float = 0.6,
    chunk: int = 4096,
) -> list[Match]:
    """All placements of tpl on the page with at least min_score of its stroke length found."""
    if len(tpl.segs) == 0 or len(pv) == 0:
        return []
    lengths = tpl.lengths
    total = lengths.sum()
    if total <= 0:
        return []

    # Pick the anchor stroke: among the longer template strokes, the one whose
    # length is rarest on the page, to keep the number of hypotheses small.
    order = np.argsort(-lengths)[: min(6, len(lengths))]
    counts = [int(np.count_nonzero(np.abs(pv.length - lengths[k]) <= tol)) for k in order]
    a = int(order[int(np.argmin(counts))])
    cand = np.flatnonzero(np.abs(pv.length - lengths[a]) <= tol)
    if not len(cand):
        return []

    ta0, ta1 = tpl.segs[a, :2], tpl.segs[a, 2:]
    page_keys = pv.endpoint_keys(0.5)

    hyps_t: list[np.ndarray] = []
    hyps_m: list[int] = []
    for mi, m in enumerate(DIHEDRAL):
        a0, a1 = m @ ta0, m @ ta1
        da = a1 - a0
        c0, c1 = pv.s[cand, :2], pv.s[cand, 2:]
        dc = c1 - c0
        # forward: a0->c0, a1->c1; reverse: a0->c1, a1->c0
        fwd = np.all(np.abs(dc - da) <= tol, axis=1)
        rev = np.all(np.abs(-dc - da) <= tol, axis=1)
        if fwd.any():
            hyps_t.append(c0[fwd] - a0)
            hyps_m += [mi] * int(fwd.sum())
        if rev.any():
            hyps_t.append(c1[rev] - a0)
            hyps_m += [mi] * int(rev.sum())
    if not hyps_t:
        return []
    T = np.concatenate(hyps_t)
    M = np.array(hyps_m)

    results: list[Match] = []
    for mi in np.unique(M):
        m = DIHEDRAL[mi]
        p0 = tpl.segs[:, :2] @ m.T  # (S, 2)
        p1 = tpl.segs[:, 2:] @ m.T
        all_t = T[M == mi]
        recall_parts = []
        # Chunks bound memory on dense pages (many strokes share the anchor length).
        for start in range(0, len(all_t), chunk):
            t = all_t[start : start + chunk]  # (H, 2)
            # Quick rejection on the longest strokes first: most placements
            # suggested by an anchor of common length fail here.
            quick = order[: min(4, len(order))]
            qhit = _hits(page_keys, p0[quick], t) & _hits(page_keys, p1[quick], t)
            possible = (qhit * lengths[quick][None, :]).sum(axis=1) + (total - lengths[quick].sum()) >= min_score * total
            rec = np.zeros(len(t))
            if possible.any():
                tt = t[possible]
                found = _hits(page_keys, p0, tt) & _hits(page_keys, p1, tt)
                rec[possible] = (found * lengths[None, :]).sum(axis=1) / total
            recall_parts.append(rec)
        recall = np.concatenate(recall_parts)
        t = all_t
        good = np.flatnonzero(recall >= min_score)
        hw, hh = np.abs(m @ np.array(tpl.half))
        for g in good:
            cx, cy = t[g]
            box = (cx - hw, cy - hh, cx + hw, cy + hh)
            precision = _precision(pv, box, p0 + t[g], p1 + t[g], float(recall[g] * total), tol)
            if precision < min_precision:
                continue
            results.append(Match(box, float(recall[g] * precision), int(mi), tpl.id, tpl.label))
    return suppress(results)


def _precision(pv: PageVectors, box: Box, e0: np.ndarray, e1: np.ndarray, found_len: float, tol: float) -> float:
    """Penalise strokes attached to the matched symbol that the template lacks.

    A globe valve is a gate valve plus a centre dot: the gate template finds
    all its strokes in a globe valve, so recall alone cannot tell them apart.
    Strokes inside the box that touch or cross the matched strokes but are
    not in the template count against the match. Detached strokes, such as
    tag text inside an instrument bubble, do not.
    """
    from .vectors import SYMBOL_MAX_STROKE, point_segment_distance

    near = pv.in_box((box[0] - tol, box[1] - tol, box[2] + tol, box[3] + tol))
    near = near[pv.length[near] <= SYMBOL_MAX_STROKE]
    if not len(near):
        return 1.0
    segs = pv.s[near]
    tpl_pts = np.concatenate([e0, e1])
    d0 = np.hypot(segs[:, None, 0] - tpl_pts[None, :, 0], segs[:, None, 1] - tpl_pts[None, :, 1]).min(axis=1)
    d1 = np.hypot(segs[:, None, 2] - tpl_pts[None, :, 0], segs[:, None, 3] - tpl_pts[None, :, 1]).min(axis=1)
    explained = (d0 <= 2 * tol) & (d1 <= 2 * tol)
    if explained.all() or not explained.any():
        return 1.0
    matched = segs[explained]
    other = segs[~explained]
    other_len = pv.length[near][~explained]

    # Contact points between each unexplained stroke and the matched strokes.
    # Contacts on the box boundary are pipe or signal connections and are
    # ignored; contacts inside the box mean the symbol has extra parts
    # (an actuator stem at the body centre, a check valve bar).
    inner = (box[0] + 2 * tol, box[1] + 2 * tol, box[2] - 2 * tol, box[3] - 2 * tol)

    def inside(px, py):
        return (px > inner[0]) & (px < inner[2]) & (py > inner[1]) & (py < inner[3])

    extra_mask = np.zeros(len(other), dtype=bool)
    for k in (0, 2):  # endpoints of unexplained strokes touching matched strokes
        px, py = other[:, k], other[:, k + 1]
        hit = (point_segment_distance(px, py, matched) <= tol).any(axis=1)
        extra_mask |= hit & inside(px, py)
    for k in (0, 2):  # matched endpoints touching unexplained strokes
        px, py = matched[:, k], matched[:, k + 1]
        hit = point_segment_distance(px, py, other) <= tol  # (matched, other)
        extra_mask |= (hit & inside(px, py)[:, None]).any(axis=0)
    ix, iy, crosses = _crossing_points(other, matched)
    extra_mask |= (crosses & inside(ix, iy)).any(axis=1)
    extra = float(other_len[extra_mask].sum())
    return found_len / (found_len + extra) if found_len > 0 else 0.0


def _crossing_points(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Intersection points of every a-b segment pair (A, B) and a mask of proper crossings."""
    p = a[:, None, :2]
    r = a[:, None, 2:] - a[:, None, :2]
    q = b[None, :, :2]
    s = b[None, :, 2:] - b[None, :, :2]
    rxs = r[..., 0] * s[..., 1] - r[..., 1] * s[..., 0]
    qp = q - p
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qp[..., 0] * s[..., 1] - qp[..., 1] * s[..., 0]) / rxs
        u = (qp[..., 0] * r[..., 1] - qp[..., 1] * r[..., 0]) / rxs
    ok = (rxs != 0) & (t > 0) & (t < 1) & (u > 0) & (u < 1)
    t = np.where(ok, t, 0.0)
    ix = p[..., 0] + t * r[..., 0]
    iy = p[..., 1] + t * r[..., 1]
    return ix, iy, ok


def match_library(
    templates: list[Template],
    pv: PageVectors,
    min_score: float = 0.9,
    min_precision: float = 0.9,
) -> list[Match]:
    """Run several templates on a page; where they overlap, the most specific wins.

    A gate valve body appears inside an actuated valve symbol. When both
    templates match at one place, the one with more stroke length (the
    actuated valve) is the right answer.
    """
    all_matches: list[tuple[float, Match]] = []
    for tpl in templates:
        size = float(tpl.lengths.sum())
        all_matches += [(size, m) for m in find_matches(tpl, pv, min_score, min_precision)]
    all_matches.sort(key=lambda sm: (-sm[0] * sm[1].score, -sm[1].score))
    kept: list[Match] = []
    for _, m in all_matches:
        if all(ios(m.box, k.box) < 0.6 for k in kept):
            kept.append(m)
    return kept


def _hits(page_keys: np.ndarray, pts: np.ndarray, t: np.ndarray) -> np.ndarray:
    """(H, S) mask: template points pts (S, 2) placed at offsets t (H, 2) land on a stroke endpoint."""
    keys = _keys(pts[None, :, :] + t[:, None, :])
    pos = np.clip(np.searchsorted(page_keys, keys), 0, len(page_keys) - 1)
    return page_keys[pos] == keys


def _keys(pts: np.ndarray) -> np.ndarray:
    ix = np.round(pts[..., 0] / 0.5).astype(np.int64)
    iy = np.round(pts[..., 1] / 0.5).astype(np.int64)
    return (ix << 32) + (iy & 0xFFFFFFFF)


def suppress(matches: list[Match], iou_threshold: float = 0.5) -> list[Match]:
    """Keep the best-scoring match among overlapping ones.

    Symmetric symbols match under several transforms at the same place; those
    collapse to one match here.
    """
    kept: list[Match] = []
    for m in sorted(matches, key=lambda m: (-m.score, m.transform)):
        if all(iou(m.box, k.box) < iou_threshold for k in kept):
            kept.append(m)
    return kept
