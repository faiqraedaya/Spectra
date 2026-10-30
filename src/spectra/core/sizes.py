"""Pipe size parsing: inch and DN notation, labels and line numbers.

Sizes are held in millimetres as nominal diameter (DN). Inch sizes convert
through the standard NPS to DN table (ISO 6708 / ASME B36.10 equivalents).
"""

from __future__ import annotations

import re

NPS_TO_DN: dict[float, int] = {
    0.25: 8, 0.375: 10, 0.5: 15, 0.75: 20, 1: 25, 1.25: 32, 1.5: 40, 2: 50, 2.5: 65, 3: 80,
    3.5: 90, 4: 100, 5: 125, 6: 150, 8: 200, 10: 250, 12: 300, 14: 350, 16: 400, 18: 450,
    20: 500, 22: 550, 24: 600, 26: 650, 28: 700, 30: 750, 32: 800, 34: 850, 36: 900,
    40: 1000, 42: 1050, 48: 1200,
}  # fmt: skip


def inch_to_dn(inches: float) -> float:
    for nps, dn in NPS_TO_DN.items():
        if abs(nps - inches) < 1e-6:
            return float(dn)
    return round(inches * 25.0, 1)


def dn_to_inch(dn: float) -> float | None:
    for nps, d in NPS_TO_DN.items():
        if abs(d - dn) < 1e-6:
            return nps
    return None


def format_size(mm: float | None) -> str:
    if mm is None:
        return ""
    inch = dn_to_inch(mm)
    return f'DN{mm:g} ({inch:g}")' if inch is not None else f"{mm:g} mm"


_NUM = r"(\d+\s*-\s*\d+/\d+|\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
_INCH = re.compile(_NUM + r"\s*(?:\"|''|”|in\b|inch(?:es)?\b|NB\b|NPS\b)", re.IGNORECASE)
_NPS_PREFIX = re.compile(r"\bNPS\s*" + _NUM, re.IGNORECASE)
_DN = re.compile(r"\bDN\s*(\d+)\b", re.IGNORECASE)
_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.IGNORECASE)
_BARE = re.compile(r"(?<![\w.])" + _NUM + r"(?![\w.])")


def _to_float(num: str) -> float:
    num = num.strip()
    m = re.fullmatch(r"(\d+)\s*(?:-|\s)\s*(\d+)/(\d+)", num)
    if m:
        return int(m[1]) + int(m[2]) / int(m[3])
    m = re.fullmatch(r"(\d+)/(\d+)", num)
    if m:
        return int(m[1]) / int(m[2])
    return float(num)


def parse_size(text: str, bare_numbers: str = "auto") -> tuple[float | None, str]:
    """Find a pipe size in free text.

    Returns (size in mm or None, text with the size removed). bare_numbers
    decides what a number without units means: "inch", "mm", "ignore", or
    "auto" (up to 48 is inches, 50 and above is DN).
    """
    for rx, unit in ((_DN, "mm"), (_MM, "mm"), (_NPS_PREFIX, "in"), (_INCH, "in")):
        m = rx.search(text)
        if m:
            value = _to_float(m[1])
            size = value if unit == "mm" else inch_to_dn(value)
            return size, (text[: m.start()] + text[m.end() :]).strip(" -_,;:")
    if bare_numbers != "ignore":
        m = _BARE.search(text)
        if m:
            value = _to_float(m[1])
            unit = bare_numbers if bare_numbers != "auto" else ("in" if value <= 48 else "mm")
            size = inch_to_dn(value) if unit == "in" else value
            return size, (text[: m.start()] + text[m.end() :]).strip(" -_,;:")
    return None, text.strip()


# Line numbers such as 6"-P-1001-A1A, 150-HC-12345-B1A, 1-1/2"-PG-100-AA1
DEFAULT_LINE_NUMBER = (
    r"^(?P<size>\d+(?:\.\d+)?(?:\s*-\s*\d+/\d+)?|\d+/\d+)\s*(?P<unit>\"|''|NB|mm)?\s*-\s*"
    r"(?P<fluid>[A-Z]{1,5})\s*-\s*(?P<number>[A-Z0-9]{2,8})(?:\s*-\s*(?P<spec>[A-Z0-9]{1,8}))?"
)


def parse_line_number(text: str, pattern: str = DEFAULT_LINE_NUMBER) -> float | None:
    """Pipe size in mm from a line number, or None if text is not one."""
    m = re.match(pattern, text.strip(), re.IGNORECASE)
    if not m:
        return None
    value = _to_float(m["size"])
    unit = (m.groupdict().get("unit") or "").lower()
    if unit == "mm" or (not unit and value >= 15 and value not in NPS_TO_DN):
        return value
    return inch_to_dn(value)
