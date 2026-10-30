"""Tags from the drawing text: instrument bubbles and valve tags.

Instrument bubbles carry the function letters above the loop number inside
the circle ("PT" over "1006" gives PT-1006). Other tags sit next to their
symbol ("ESDV-2001"); each such text goes to the nearest item, one tag per
item, nearest pairs first.
"""

from __future__ import annotations

import math
import re

from .geometry import Box, centre, expand, intersection, mm_to_pt
from .pdfdoc import Word
from .project import Item

DEFAULT_TAG = r"^[A-Z]{1,6}-?\d{2,6}[A-Z]?$"
SEARCH = mm_to_pt(12.0)
_LETTERS = re.compile(r"^[A-Z]{1,5}$")
_NUMBER = re.compile(r"^\d{2,6}[A-Z]?$")


def _gap(a: Box, b: Box) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def assign_tags(items: list[Item], words: list[Word], pattern: str = DEFAULT_TAG, bubble_classes=("instrument",)) -> int:
    """Set Item.tag where empty. Returns the number of tags set."""
    rx = re.compile(pattern or DEFAULT_TAG)
    n = 0
    used: set[int] = set()
    # 1. Text inside instrument bubbles.
    for it in items:
        if it.tag or it.cls not in bubble_classes:
            continue
        inside = [(k, w) for k, w in enumerate(words) if k not in used and intersection(w.box, it.box) > 0.6 * _area(w.box)]
        letters = [(k, w) for k, w in inside if _LETTERS.match(w.text)]
        numbers = [(k, w) for k, w in inside if _NUMBER.match(w.text)]
        whole = [(k, w) for k, w in inside if rx.match(w.text)]
        if whole:
            k, w = whole[0]
            it.tag, it.meta["tag_from"] = w.text, "bubble"
            used.add(k)
            n += 1
        elif letters and numbers:
            (kl, wl), (kn, wn) = letters[0], numbers[0]
            it.tag, it.meta["tag_from"] = f"{wl.text}-{wn.text}", "bubble"
            used.update((kl, kn))
            n += 1
    # 2. Tags beside symbols: nearest pairs first, one tag per item.
    cands = [(k, w) for k, w in enumerate(words) if k not in used and rx.match(w.text)]
    pairs = []
    for i, it in enumerate(items):
        if it.tag:
            continue
        zone = expand(it.box, SEARCH)
        for k, w in cands:
            if intersection(zone, w.box) > 0:
                pairs.append((_gap(it.box, w.box), i, k))
    pairs.sort()
    taken_items: set[int] = set()
    for d, i, k in pairs:
        if i in taken_items or k in used:
            continue
        items[i].tag = words[k].text
        items[i].meta["tag_from"] = "nearby text"
        taken_items.add(i)
        used.add(k)
        n += 1
    return n


def _area(b: Box) -> float:
    return max(1e-9, (b[2] - b[0]) * (b[3] - b[1]))


def tag_prefix(tag: str) -> str:
    m = re.match(r"^([A-Z]+)", tag or "")
    return m.group(1) if m else ""


def centre_distance(a: Box, b: Box) -> float:
    (ax, ay), (bx, by) = centre(a), centre(b)
    return math.hypot(ax - bx, ay - by)
