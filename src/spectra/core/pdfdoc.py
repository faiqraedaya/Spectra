"""PDF access through PDFium (pypdfium2, Apache-2.0/BSD-3-Clause).

Provides rendering, text words with positions, and vector line art for each
page, all in display space: PDF points, origin at the top-left of the page as
displayed, y pointing down, /Rotate applied. Every coordinate that leaves this
module is in that space, so the rest of Spectra never deals with PDF user
space or render resolution.

PDFium is not thread-safe. All calls go through one module-level lock.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import threading
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as raw

from .geometry import Box

PDFIUM_LOCK = threading.RLock()
VECTOR_CACHE_VERSION = 2
BEZIER_STEPS = 6

FLAG_STROKE = 1
FLAG_FILL = 2
FLAG_CURVE = 4
FLAG_DASHED = 8


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_dir() -> Path:
    base = os.environ.get("SPECTRA_CACHE") or os.environ.get("LOCALAPPDATA")
    root = Path(base) / "Spectra" / "cache" if base else Path.home() / ".cache" / "spectra"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(frozen=True)
class PageGeometry:
    """Maps PDF user space to display space for one page."""

    crop: tuple[float, float, float, float]  # cropbox in user space
    rotation: int  # clockwise degrees: 0, 90, 180 or 270

    @property
    def size(self) -> tuple[float, float]:
        w = self.crop[2] - self.crop[0]
        h = self.crop[3] - self.crop[1]
        return (h, w) if self.rotation in (90, 270) else (w, h)

    def to_display(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x0, y0, x1, y1 = self.crop
        u = x - x0
        v = y1 - y
        w, h = x1 - x0, y1 - y0
        match self.rotation:
            case 90:
                return h - v, u
            case 180:
                return w - u, h - v
            case 270:
                return v, w - u
            case _:
                return u, v

    def to_user(self, X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x0, y0, x1, y1 = self.crop
        w, h = x1 - x0, y1 - y0
        match self.rotation:
            case 90:
                u, v = Y, h - X
            case 180:
                u, v = w - X, h - Y
            case 270:
                u, v = w - Y, X
            case _:
                u, v = X, Y
        return u + x0, y1 - v

    def box_to_display(self, b: tuple[float, float, float, float]) -> Box:
        xs, ys = self.to_display(np.array([b[0], b[2]]), np.array([b[1], b[3]]))
        return (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))


@dataclass(frozen=True)
class Word:
    text: str
    box: Box
    angle: float  # degrees anticlockwise as displayed, 0 = left to right
    size: float  # font size in points
    source: str = "text"  # "text" (PDF text layer) or "annotation" (e.g. AutoCAD SHX comments)


@dataclass
class VectorData:
    """Line art of one page as flat arrays, in display points.

    Curves are flattened into BEZIER_STEPS line pieces each, so that identical
    symbols give identical segments wherever they are placed.
    """

    segs: np.ndarray  # (N, 4) float32: x0, y0, x1, y1
    path: np.ndarray  # (N,) int32: index of the source path object
    width: np.ndarray  # (N,) float32: stroke width in points
    flags: np.ndarray  # (N,) uint8: FLAG_* bits

    @classmethod
    def empty(cls) -> VectorData:
        return cls(
            np.zeros((0, 4), np.float32), np.zeros(0, np.int32), np.zeros(0, np.float32), np.zeros(0, np.uint8)
        )

    def __len__(self) -> int:
        return len(self.segs)

    def subset(self, mask: np.ndarray) -> VectorData:
        return VectorData(self.segs[mask], self.path[mask], self.width[mask], self.flags[mask])


def _matrix(obj) -> tuple[float, float, float, float, float, float]:
    m = raw.FS_MATRIX()
    if not raw.FPDFPageObj_GetMatrix(obj, ctypes.byref(m)):
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return (m.a, m.b, m.c, m.d, m.e, m.f)


def _compose(m1, m2):
    """Matrix of applying m1 then m2 (PDF row-vector convention)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


_BEZ_T = np.linspace(0.0, 1.0, BEZIER_STEPS + 1)[1:]


def _flatten_path(obj) -> list[list[tuple[float, float, bool]]]:
    """Read one path object into subpaths of (x, y, from_curve) points."""
    n = raw.FPDFPath_CountSegments(obj)
    fx, fy = ctypes.c_float(), ctypes.c_float()
    subpaths: list[list[tuple[float, float, bool]]] = []
    cur: list[tuple[float, float, bool]] = []
    start: tuple[float, float] | None = None
    bez: list[tuple[float, float]] = []
    for j in range(n):
        seg = raw.FPDFPath_GetPathSegment(obj, j)
        raw.FPDFPathSegment_GetPoint(seg, ctypes.byref(fx), ctypes.byref(fy))
        x, y = fx.value, fy.value
        t = raw.FPDFPathSegment_GetType(seg)
        if t == raw.FPDF_SEGMENT_MOVETO:
            if len(cur) > 1:
                subpaths.append(cur)
            cur = [(x, y, False)]
            start = (x, y)
            bez = []
        elif t == raw.FPDF_SEGMENT_LINETO:
            cur.append((x, y, False))
        elif t == raw.FPDF_SEGMENT_BEZIERTO:
            bez.append((x, y))
            if len(bez) == 3 and cur:
                p0 = np.array(cur[-1][:2])
                c1, c2, p3 = (np.array(p) for p in bez)
                tt = _BEZ_T[:, None]
                pts = (
                    (1 - tt) ** 3 * p0
                    + 3 * (1 - tt) ** 2 * tt * c1
                    + 3 * (1 - tt) * tt**2 * c2
                    + tt**3 * p3
                )
                cur.extend((float(px), float(py), True) for px, py in pts)
                bez = []
        if raw.FPDFPathSegment_GetClose(seg) and start is not None and cur:
            if (cur[-1][0], cur[-1][1]) != start:
                cur.append((start[0], start[1], False))
    if len(cur) > 1:
        subpaths.append(cur)
    return subpaths


class PdfDoc:
    """An open PDF file. Close it when done, or use it as a context manager."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with PDFIUM_LOCK:
            self._pdf = pdfium.PdfDocument(str(self.path))
            self.n_pages = len(self._pdf)
        self._geom: dict[int, PageGeometry] = {}
        self._vectors: dict[int, VectorData] = {}
        self._words: dict[int, list[Word]] = {}

    def __enter__(self) -> PdfDoc:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        with PDFIUM_LOCK:
            if self._pdf is not None:
                self._pdf.close()
                self._pdf = None

    @cached_property
    def sha256(self) -> str:
        return file_sha256(self.path)

    def geometry(self, index: int) -> PageGeometry:
        if index not in self._geom:
            with PDFIUM_LOCK:
                page = self._pdf[index]
                try:
                    crop = tuple(float(v) for v in page.get_cropbox())
                    rot = int(page.get_rotation()) % 360
                finally:
                    page.close()
            self._geom[index] = PageGeometry(crop, rot)  # type: ignore[arg-type]
        return self._geom[index]

    def page_size(self, index: int) -> tuple[float, float]:
        return self.geometry(index).size

    # --- Rendering ----------------------------------------------------------

    def render(self, index: int, dpi: float, clip: Box | None = None, grey: bool = False) -> np.ndarray:
        """Render a page (or a clip of it, in display points) to an RGB array.

        Returns uint8 (H, W, 3), or (H, W) when grey is True.
        """
        scale = dpi / 72.0
        w, h = self.page_size(index)
        crop = (0.0, 0.0, 0.0, 0.0)
        if clip is not None:
            x0, y0, x1, y1 = (max(0.0, clip[0]), max(0.0, clip[1]), min(w, clip[2]), min(h, clip[3]))
            if x1 <= x0 or y1 <= y0:
                return np.full((1, 1) if grey else (1, 1, 3), 255, np.uint8)
            crop = (x0, h - y1, w - x1, y0)  # left, bottom, right, top amounts to cut
        with PDFIUM_LOCK:
            page = self._pdf[index]
            try:
                bmp = page.render(scale=scale, crop=crop, grayscale=grey, may_draw_forms=True)
                arr = bmp.to_numpy().copy()
            finally:
                page.close()
        if grey:
            return arr[:, :, 0] if arr.ndim == 3 else arr
        if arr.shape[2] == 4:
            arr = arr[:, :, :3]
        return arr[:, :, ::-1].copy() if bmp.mode in ("BGR", "BGRA", "BGRX") else arr

    # --- Text ---------------------------------------------------------------

    def words(self, index: int) -> list[Word]:
        """Words of the PDF text layer, merged with text-bearing annotations."""
        if index in self._words:
            return self._words[index]
        geom = self.geometry(index)
        chars: list[tuple[str, Box, float, float]] = []
        with PDFIUM_LOCK:
            page = self._pdf[index]
            tp = page.get_textpage()
            try:
                n = tp.count_chars()
                for i in range(n):
                    code = raw.FPDFText_GetUnicode(tp, i)
                    ch = chr(code) if code else ""
                    generated = raw.FPDFText_IsGenerated(tp, i) == 1
                    if generated or not ch or ch.isspace():
                        chars.append((" ", (0, 0, 0, 0), 0.0, 0.0))
                        continue
                    l, b, r, t = tp.get_charbox(i)
                    ang = raw.FPDFText_GetCharAngle(tp, i)
                    size = raw.FPDFText_GetFontSize(tp, i)
                    chars.append((ch, geom.box_to_display((l, b, r, t)), float(ang), float(size)))
            finally:
                tp.close()
                page.close()
        words = _group_words(chars, geom.rotation)
        words.extend(self._annotation_words(index))
        self._words[index] = words
        return words

    @cached_property
    def annotations(self):
        """All annotations, per page index, in PDF user space (see annotations.py)."""
        from .annotations import read_annotations

        try:
            return read_annotations(self.path)
        except Exception:  # a damaged annotation tree must not block opening the drawing
            return {}

    def _annotation_words(self, index: int) -> list[Word]:
        out = []
        geom = self.geometry(index)
        for a in self.annotations.get(index, []):
            text = a.text_hint()
            if text and a.is_text_like():
                out.append(Word(text, geom.box_to_display(a.rect), 0.0, 0.0, "annotation"))
        return out

    # --- Vectors ------------------------------------------------------------

    def vectors(self, index: int, use_cache: bool = True) -> VectorData:
        if index in self._vectors:
            return self._vectors[index]
        cache_file = cache_dir() / f"{self.sha256}_{index}_v{VECTOR_CACHE_VERSION}.npz"
        if use_cache and cache_file.exists():
            try:
                with np.load(cache_file) as z:
                    vd = VectorData(z["segs"], z["path"], z["width"], z["flags"])
                self._vectors[index] = vd
                return vd
            except (OSError, KeyError, ValueError):
                pass
        vd = self._extract_vectors(index)
        if use_cache:
            try:
                np.savez_compressed(cache_file, segs=vd.segs, path=vd.path, width=vd.width, flags=vd.flags)
            except OSError:
                pass
        self._vectors[index] = vd
        return vd

    def _extract_vectors(self, index: int) -> VectorData:
        geom = self.geometry(index)
        xs: list[float] = []
        ys: list[float] = []
        seg_rows: list[np.ndarray] = []
        paths: list[np.ndarray] = []
        widths: list[np.ndarray] = []
        flags: list[np.ndarray] = []
        identity = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        path_counter = 0

        def handle_path(obj, m):
            nonlocal path_counter
            fillmode = ctypes.c_int()
            stroke = ctypes.c_int()
            raw.FPDFPath_GetDrawMode(obj, ctypes.byref(fillmode), ctypes.byref(stroke))
            if not stroke.value and fillmode.value == raw.FPDF_FILLMODE_NONE:
                return  # clipping or invisible path
            w = ctypes.c_float()
            raw.FPDFPageObj_GetStrokeWidth(obj, ctypes.byref(w))
            scale = abs(m[0] * m[3] - m[1] * m[2]) ** 0.5
            f = (FLAG_STROKE if stroke.value else 0) | (FLAG_FILL if fillmode.value else 0)
            if raw.FPDFPageObj_GetDashCount(obj) > 0:
                f |= FLAG_DASHED
            for sub in _flatten_path(obj):
                arr = np.array(sub, dtype=np.float64)
                px = m[0] * arr[:, 0] + m[2] * arr[:, 1] + m[4]
                py = m[1] * arr[:, 0] + m[3] * arr[:, 1] + m[5]
                dx, dy = geom.to_display(px, py)
                rows = np.stack([dx[:-1], dy[:-1], dx[1:], dy[1:]], axis=1)
                curve = arr[1:, 2] > 0
                keep = (rows[:, 0] != rows[:, 2]) | (rows[:, 1] != rows[:, 3])
                rows, curve = rows[keep], curve[keep]
                if not len(rows):
                    continue
                seg_rows.append(rows.astype(np.float32))
                paths.append(np.full(len(rows), path_counter, np.int32))
                widths.append(np.full(len(rows), w.value * scale, np.float32))
                flags.append((f | np.where(curve, FLAG_CURVE, 0)).astype(np.uint8))
            path_counter += 1

        def walk(obj, parent):
            t = raw.FPDFPageObj_GetType(obj)
            if t == raw.FPDF_PAGEOBJ_PATH:
                handle_path(obj, _compose(_matrix(obj), parent))
            elif t == raw.FPDF_PAGEOBJ_FORM:
                m = _compose(_matrix(obj), parent)
                for k in range(raw.FPDFFormObj_CountObjects(obj)):
                    walk(raw.FPDFFormObj_GetObject(obj, k), m)

        with PDFIUM_LOCK:
            page = self._pdf[index]
            try:
                for i in range(raw.FPDFPage_CountObjects(page)):
                    walk(raw.FPDFPage_GetObject(page, i), identity)
            finally:
                page.close()
        del xs, ys
        if not seg_rows:
            return VectorData.empty()
        return VectorData(
            np.concatenate(seg_rows), np.concatenate(paths), np.concatenate(widths), np.concatenate(flags)
        )


def _group_words(chars: list[tuple[str, Box, float, float]], rotation: int) -> list[Word]:
    """Join characters into words, splitting on spaces, angle changes and gaps."""
    words: list[Word] = []
    buf: list[tuple[str, Box, float, float]] = []

    def flush():
        if buf:
            x0 = min(c[1][0] for c in buf)
            y0 = min(c[1][1] for c in buf)
            x1 = max(c[1][2] for c in buf)
            y1 = max(c[1][3] for c in buf)
            # PDFium reports the angle in user space, clockwise; convert to
            # display space, anticlockwise.
            ang = (-np.degrees(buf[0][2]) - rotation) % 360
            ang = float(ang - 360 if ang > 180 else ang)
            size = max(c[3] for c in buf)
            words.append(Word("".join(c[0] for c in buf), (x0, y0, x1, y1), round(ang, 1), size))
            buf.clear()

    for ch in chars:
        if ch[0] == " ":
            flush()
            continue
        if buf:
            prev = buf[-1]
            gap_limit = 0.6 * max(prev[3], ch[3], 1.0)
            pb, cb = prev[1], ch[1]
            gap = max(cb[0] - pb[2], pb[0] - cb[2], cb[1] - pb[3], pb[1] - cb[3])
            if abs(prev[2] - ch[2]) > 0.05 or gap > gap_limit:
                flush()
        buf.append(ch)
    flush()
    return words
