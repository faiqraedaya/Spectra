"""Minimal PDF writer for synthetic test drawings.

Writes vector line art, base-14 text and arbitrary annotation dictionaries
(for example Bluebeam-style Count markups). It exists so tests and the demo
drawing do not depend on client data or on an extra PDF library.

Coordinates passed to the drawing methods are display coordinates in points
(origin top-left, y down) for an unrotated page; they are converted to PDF
user space (origin bottom-left, y up) on output.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field
from pathlib import Path


def _pdf_str(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({escaped})"


def _pdf_value(v: object) -> str:
    """Serialise a small Python value to PDF syntax.

    str values starting with '/' are names; other str values are literal
    strings. Wrap a value in Raw to emit it verbatim.
    """
    if isinstance(v, Raw):
        return v.text
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return v if v.startswith("/") else _pdf_str(v)
    if isinstance(v, (list, tuple)):
        return "[" + " ".join(_pdf_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "<<" + " ".join(f"/{k} {_pdf_value(x)}" for k, x in v.items()) + ">>"
    raise TypeError(f"cannot serialise {type(v)}")


@dataclass
class Raw:
    text: str


@dataclass
class PageBuilder:
    width: float
    height: float
    rotate: int = 0
    ops: list[str] = field(default_factory=list)
    annots: list[dict] = field(default_factory=list)

    def _y(self, y: float) -> float:
        return self.height - y

    def line_width(self, w: float) -> None:
        self.ops.append(f"{w:.3f} w")

    def dash(self, on: float = 0.0, off: float = 0.0) -> None:
        self.ops.append(f"[{on:.2f} {off:.2f}] 0 d" if on else "[] 0 d")

    def polyline(self, pts: list[tuple[float, float]], close: bool = False, fill: bool = False) -> None:
        x, y = pts[0]
        parts = [f"{x:.3f} {self._y(y):.3f} m"]
        parts += [f"{x:.3f} {self._y(y):.3f} l" for x, y in pts[1:]]
        if close:
            parts.append("h")
        parts.append("B" if fill else ("s" if close else "S"))
        self.ops.append(" ".join(parts))

    def line(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.polyline([(x0, y0), (x1, y1)])

    def circle(self, cx: float, cy: float, r: float, fill: bool = False) -> None:
        k = 0.5523 * r
        y = self._y(cy)
        self.ops.append(
            f"{cx + r:.3f} {y:.3f} m "
            f"{cx + r:.3f} {y + k:.3f} {cx + k:.3f} {y + r:.3f} {cx:.3f} {y + r:.3f} c "
            f"{cx - k:.3f} {y + r:.3f} {cx - r:.3f} {y + k:.3f} {cx - r:.3f} {y:.3f} c "
            f"{cx - r:.3f} {y - k:.3f} {cx - k:.3f} {y - r:.3f} {cx:.3f} {y - r:.3f} c "
            f"{cx + k:.3f} {y - r:.3f} {cx + r:.3f} {y - k:.3f} {cx + r:.3f} {y:.3f} c "
            + ("b" if fill else "s")
        )

    def text(self, x: float, y: float, s: str, size: float = 7.0, angle: float = 0.0) -> None:
        """Text with its baseline starting at (x, y); angle in degrees anticlockwise."""
        a = math.radians(angle)
        c, si = math.cos(a), math.sin(a)
        self.ops.append(
            f"BT /F1 {size:.2f} Tf {c:.5f} {si:.5f} {-si:.5f} {c:.5f} {x:.3f} {self._y(y):.3f} Tm "
            f"{_pdf_str(s)} Tj ET"
        )

    def annotation(self, d: dict) -> None:
        self.annots.append(d)

    def rect_to_pdf(self, x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [x0, self._y(y1), x1, self._y(y0)]

    def point_to_pdf(self, x: float, y: float) -> tuple[float, float]:
        return (x, self._y(y))


class PdfWriter:
    def __init__(self) -> None:
        self.pages: list[PageBuilder] = []

    def new_page(self, width: float, height: float, rotate: int = 0) -> PageBuilder:
        p = PageBuilder(width, height, rotate)
        self.pages.append(p)
        return p

    def save(self, path: str | Path, compress: bool = True) -> None:
        objs: list[bytes] = []

        def add(body: bytes) -> int:
            objs.append(body)
            return len(objs)

        catalog = add(b"")
        pages = add(b"")
        font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        kids: list[int] = []
        for p in self.pages:
            content = "\n".join(p.ops).encode("latin-1")
            if compress:
                data = zlib.compress(content)
                stream = add(
                    f"<< /Length {len(data)} /Filter /FlateDecode >>\nstream\n".encode() + data + b"\nendstream"
                )
            else:
                stream = add(f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream")
            annot_refs = []
            page_num = len(objs) + 1 + len(p.annots)
            for a in p.annots:
                d = dict(a)
                d.setdefault("Type", "/Annot")
                d["P"] = Raw(f"{page_num} 0 R")
                annot_refs.append(add(_pdf_value(d).encode("latin-1")))
            page = add(
                (
                    f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {p.width:.3f} {p.height:.3f}] "
                    f"/Rotate {p.rotate} /Resources << /Font << /F1 {font} 0 R >> >> "
                    f"/Contents {stream} 0 R "
                    + (f"/Annots [{' '.join(f'{r} 0 R' for r in annot_refs)}] " if annot_refs else "")
                    + ">>"
                ).encode()
            )
            assert page == page_num
            kids.append(page)
        objs[catalog - 1] = f"<< /Type /Catalog /Pages {pages} 0 R >>".encode()
        objs[pages - 1] = (
            f"<< /Type /Pages /Count {len(kids)} /Kids [{' '.join(f'{k} 0 R' for k in kids)}] >>".encode()
        )

        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
        out += f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        Path(path).write_bytes(bytes(out))
