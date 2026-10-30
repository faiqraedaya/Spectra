"""Drawing view: PDF page, counted items and section regions.

Scene units are PDF points in display space, the same coordinates the core
uses, so nothing here converts between render resolutions except the
background pixmaps. The page is rendered once at a base resolution, and the
visible area is re-rendered sharply after zooming in.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QFont, QImage, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QMenu,
    QStyleOptionGraphicsItem,
)

from ..core.project import Item
from .theme import Tokens as T

BASE_MAX_PX = 4200  # long side of the base render
DETAIL_MAX_DPI = 600
EDGE_PX = 5


def _qimage(arr: np.ndarray) -> QImage:
    h, w = arr.shape[:2]
    return QImage(np.ascontiguousarray(arr).data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class _RenderWorker(QObject):
    done = Signal(str, int, float, object, object, int)  # doc, page, dpi, clip, image, generation

    def __init__(self, state):
        super().__init__()
        self.state = state

    @Slot(str, int, float, object, int)
    def render(self, doc_id: str, page: int, dpi: float, clip, generation: int) -> None:
        try:
            arr = self.state.ws.pdf(doc_id).render(page, dpi, clip=clip)
        except Exception:
            return
        self.done.emit(doc_id, page, dpi, clip, _qimage(arr), generation)


class ItemGraphic(QGraphicsRectItem):
    def __init__(self, view: PageView, item: Item):
        super().__init__()
        self.view = view
        self.item_id = item.id
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self._resize: tuple[bool, bool, bool, bool] | None = None
        self._start: QRectF | None = None
        self.update_from(item)

    def update_from(self, item: Item) -> None:
        x0, y0, x1, y1 = item.box
        self.prepareGeometryChange()
        self.setPos(0, 0)
        self.setRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        cls = self.view.state.project.taxonomy.get(item.cls)
        self.colour = QColor(cls.colour)
        self.proposed = item.status != "accepted"
        size = self.view.state.project.effective_size(item)
        self.no_size = size is None and cls.category is not None
        self.label = cls.name + (f" · {size:g}" if size else "")
        self.setToolTip(f"{cls.name}\n{'Proposed' if self.proposed else 'Accepted'} · {item.source}"
                        + (f" · score {item.score:.2f}" if item.source in ('library', 'model', 'similar') else "")
                        + (f"\nSize {size:g} mm" if size else "\nNo size")
                        + (f"\nTag {item.tag}" if item.tag else "")
                        + (f"\nLabel: {item.meta['label']}" if item.meta.get("label") else ""))
        self.update()

    def scene_box(self) -> tuple[float, float, float, float]:
        r = self.rect().translated(self.pos())
        return (r.left(), r.top(), r.right(), r.bottom())

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        selected = self.isSelected()
        pen = QPen(self.colour, 2.5 if selected else 1.5)
        pen.setCosmetic(True)
        if self.proposed:
            pen.setStyle(Qt.PenStyle.DashLine)
        fill = QColor(self.colour)
        fill.setAlpha(60 if selected else (36 if self.proposed else 16))
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRect(self.rect())
        lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
        if self.no_size or (lod * self.rect().height() > 14 and lod > 1.2) or selected:
            painter.save()
            tl = painter.worldTransform().map(self.rect().topLeft())
            painter.resetTransform()
            if self.no_size:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(T.WARNING))
                painter.drawEllipse(tl, 3.5, 3.5)
            if (lod * self.rect().height() > 14 and lod > 1.2) or selected:
                f = QFont(T.FONT_FAMILY)
                f.setPixelSize(11)
                painter.setFont(f)
                painter.setPen(QColor(self.colour).darker(130))
                painter.drawText(QPointF(tl.x() + (8 if self.no_size else 0), tl.y() - 4), self.label)
            painter.restore()

    # --- Resize by dragging an edge or corner --------------------------------

    def _edges_at(self, pos: QPointF) -> tuple[bool, bool, bool, bool]:
        r = self.rect()
        k = EDGE_PX / max(self.view.transform().m11(), 1e-6)
        return (abs(pos.x() - r.left()) < k, abs(pos.y() - r.top()) < k, abs(pos.x() - r.right()) < k,
                abs(pos.y() - r.bottom()) < k)

    def hoverMoveEvent(self, event) -> None:  # noqa: N802
        if not self.isSelected():
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        l, t, r, b = self._edges_at(event.pos())
        if (l and t) or (r and b):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (r and t) or (l and b):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif l or r:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif t or b:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._start = QRectF(self.rect().translated(self.pos()))
        if self.isSelected() and event.button() == Qt.MouseButton.LeftButton:
            edges = self._edges_at(event.pos())
            if any(edges):
                self._resize = edges
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._resize:
            r = QRectF(self.rect())
            p = event.pos()
            l, t, rr, b = self._resize
            if l:
                r.setLeft(min(p.x(), r.right() - 1))
            if rr:
                r.setRight(max(p.x(), r.left() + 1))
            if t:
                r.setTop(min(p.y(), r.bottom() - 1))
            if b:
                r.setBottom(max(p.y(), r.top() + 1))
            self.prepareGeometryChange()
            self.setRect(r)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._resize = None
        super().mouseReleaseEvent(event)
        end = self.rect().translated(self.pos())
        if self._start is not None and end != self._start:
            self.view.geometry_edited.emit(self.item_id, self.scene_box())
        self._start = None

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)
        self.view.item_menu_requested.emit(event.screenPos())


class SectionGraphic(QGraphicsPathItem):
    def __init__(self, points, closed: bool, colour: str, name: str):
        super().__init__()
        path = QPainterPath(QPointF(*points[0]))
        for p in points[1:]:
            path.lineTo(QPointF(*p))
        if closed:
            path.closeSubpath()
        self.setPath(path)
        c = QColor(colour)
        c.setAlpha(90)
        pen = QPen(c, 7)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        if closed:
            f = QColor(colour)
            f.setAlpha(18)
            self.setBrush(f)
        self.name = name
        self.anchor = QPointF(*points[0])
        self.text_colour = QColor(colour).darker(140)
        self.setZValue(5)
        self.setToolTip(f"Section {name}")

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        painter.save()
        p = painter.worldTransform().map(self.anchor)
        painter.resetTransform()
        f = QFont(T.FONT_FAMILY)
        f.setPixelSize(12)
        f.setWeight(QFont.Weight.DemiBold)
        painter.setFont(f)
        painter.setPen(self.text_colour)
        painter.drawText(QPointF(p.x() + 6, p.y() - 6), self.name)
        painter.restore()


class PageView(QGraphicsView):
    geometry_edited = Signal(str, object)  # item id, box
    add_requested = Signal(object, bool)  # box, snapped-from-click
    section_drawn = Signal(object, bool)  # points, closed
    item_menu_requested = Signal(object)
    zoom_changed = Signal(float)
    mode_changed = Signal(str)
    _render = Signal(str, int, float, object, int)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.mode = "select"
        self._graphics: dict[str, ItemGraphic] = {}
        self._sections: list[SectionGraphic] = []
        self._base: QGraphicsPixmapItem | None = None
        self._detail: QGraphicsPixmapItem | None = None
        self._base_dpi = 72.0
        self._generation = 0
        self._pan_from = None
        self._space = False
        self._syncing = False
        self._add_start: QPointF | None = None
        self._rubber: QGraphicsRectItem | None = None
        self._section_pts: list[tuple[float, float]] = []
        self._section_preview: QGraphicsPathItem | None = None

        self._thread = QThread(self)
        self._worker = _RenderWorker(state)
        self._worker.moveToThread(self._thread)
        self._render.connect(self._worker.render)
        self._worker.done.connect(self._on_rendered)
        self._thread.start()
        self._detail_timer = QTimer(self, singleShot=True, interval=180)
        self._detail_timer.timeout.connect(self._request_detail)

        self.scene().selectionChanged.connect(self._on_scene_selection)
        state.page_changed.connect(self.load_page)
        state.items_changed.connect(self.refresh_items)
        state.sections_changed.connect(self.refresh_sections)
        state.selection_changed.connect(self._sync_selection)

    def shutdown(self) -> None:
        self._thread.quit()
        self._thread.wait(3000)

    # --- Page ---------------------------------------------------------------

    def load_page(self) -> None:
        s = self.scene()
        s.clear()
        self._graphics.clear()
        self._sections.clear()
        self._base = self._detail = None
        self._section_pts = []
        self._section_preview = None
        self._rubber = None
        self._generation += 1
        st = self.state
        if st.doc_id is None:
            s.setSceneRect(QRectF(0, 0, 100, 100))
            return
        w, h = st.ws.pdf(st.doc_id).page_size(st.page)
        s.setSceneRect(QRectF(0, 0, w, h))
        paper = s.addRect(QRectF(0, 0, w, h), QPen(Qt.PenStyle.NoPen), QBrush(QColor(T.CANVAS)))
        paper.setZValue(-10)
        self._base_dpi = min(150.0, BASE_MAX_PX * 72.0 / max(w, h))
        self._render.emit(st.doc_id, st.page, self._base_dpi, None, self._generation)
        self.refresh_sections()
        self.refresh_items()
        self.fit_page()

    @Slot(str, int, float, object, object, int)
    def _on_rendered(self, doc_id, page, dpi, clip, image: QImage, generation) -> None:
        if generation != self._generation or doc_id != self.state.doc_id or page != self.state.page:
            return
        pix = QGraphicsPixmapItem(QPixmap.fromImage(image))
        pix.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        pix.setScale(72.0 / dpi)
        if clip is None:
            pix.setZValue(-5)
            if self._base is not None:
                self.scene().removeItem(self._base)
            self._base = pix
            self._detail_timer.start()
        else:
            pix.setPos(clip[0], clip[1])
            pix.setZValue(-4)
            if self._detail is not None:
                self.scene().removeItem(self._detail)
            self._detail = pix
        self.scene().addItem(pix)

    def _request_detail(self) -> None:
        if self.state.doc_id is None or self._base is None:
            return
        scale = self.transform().m11() * self.devicePixelRatioF()
        dpi = min(72.0 * scale, DETAIL_MAX_DPI)
        if dpi <= self._base_dpi * 1.15:
            if self._detail is not None:
                self.scene().removeItem(self._detail)
                self._detail = None
            return
        vis = self.mapToScene(self.viewport().rect()).boundingRect().intersected(self.sceneRect())
        if vis.isEmpty():
            return
        m = 0.1 * max(vis.width(), vis.height())
        clip = (max(0.0, vis.left() - m), max(0.0, vis.top() - m),
                min(self.sceneRect().right(), vis.right() + m), min(self.sceneRect().bottom(), vis.bottom() + m))
        self._render.emit(self.state.doc_id, self.state.page, dpi, clip, self._generation)

    # --- Items and sections -----------------------------------------------------

    def refresh_items(self) -> None:
        items = {i.id: i for i in self.state.page_items()}
        for gid in list(self._graphics):
            if gid not in items:
                self.scene().removeItem(self._graphics.pop(gid))
        for it in items.values():
            g = self._graphics.get(it.id)
            if g is None:
                g = ItemGraphic(self, it)
                g.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, self.mode == "select")
                self._graphics[it.id] = g
                self.scene().addItem(g)
            else:
                g.update_from(it)
        self._sync_selection()

    def refresh_sections(self) -> None:
        for g in self._sections:
            self.scene().removeItem(g)
        self._sections.clear()
        st = self.state
        for sec in st.project.sections:
            for r in sec.regions:
                if r.doc == st.doc_id and r.page == st.page and len(r.points) >= 2:
                    g = SectionGraphic(r.points, r.closed, sec.colour, sec.name)
                    self._sections.append(g)
                    self.scene().addItem(g)
        self.refresh_items()  # item labels show inherited sizes

    def _on_scene_selection(self) -> None:
        if self._syncing:
            return
        ids = [g.item_id for g in self.scene().selectedItems() if isinstance(g, ItemGraphic)]
        self.state.select(ids)

    def _sync_selection(self) -> None:
        self._syncing = True
        try:
            want = set(self.state.selected)
            for gid, g in self._graphics.items():
                if g.isSelected() != (gid in want):
                    g.setSelected(gid in want)
        finally:
            self._syncing = False

    def centre_on(self, item: Item, min_zoom: float = 2.0) -> None:
        x0, y0, x1, y1 = item.box
        if self.transform().m11() < min_zoom:
            self.set_zoom(min_zoom)
        self.centerOn(QPointF((x0 + x1) / 2, (y0 + y1) / 2))
        self._detail_timer.start()

    # --- Zoom and pan ---------------------------------------------------------------

    def fit_page(self) -> None:
        r = self.sceneRect()
        if r.width() > 0:
            self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom_changed.emit(self.transform().m11())
            self._detail_timer.start()

    def set_zoom(self, z: float) -> None:
        z = max(0.05, min(z, 12.0))
        f = z / self.transform().m11()
        self.scale(f, f)
        self.zoom_changed.emit(z)
        self._detail_timer.start()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - event.angleDelta().y())
            return
        factor = 1.0015 ** event.angleDelta().y()
        z = self.transform().m11() * factor
        if 0.05 <= z <= 12.0:
            self.scale(factor, factor)
            self.zoom_changed.emit(z)
        self._detail_timer.start()

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(dx, dy)
        self._detail_timer.start()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._detail_timer.start()

    # --- Modes ------------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._cancel_section()
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag if mode == "select" else QGraphicsView.DragMode.NoDrag)
        for g in self._graphics.values():
            g.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, mode == "select")
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor if mode == "select" else Qt.CursorShape.CrossCursor)
        self.mode_changed.emit(mode)

    def _cancel_section(self) -> None:
        self._section_pts = []
        if self._section_preview is not None:
            self.scene().removeItem(self._section_preview)
            self._section_preview = None

    def _update_section_preview(self, cursor: QPointF | None = None) -> None:
        pts = [QPointF(*p) for p in self._section_pts] + ([cursor] if cursor is not None else [])
        if not pts:
            return
        path = QPainterPath(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        if self._section_preview is None:
            pen = QPen(QColor(T.ACTION), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._section_preview = self.scene().addPath(path, pen)
            self._section_preview.setZValue(20)
        else:
            self._section_preview.setPath(path)

    def _finish_section(self) -> None:
        pts = self._section_pts
        if len(pts) >= 2:
            first = self.mapFromScene(QPointF(*pts[0]))
            last = self.mapFromScene(QPointF(*pts[-1]))
            closed = len(pts) >= 3 and (first - last).manhattanLength() < 10
            if closed:
                pts = pts[:-1]
            self.section_drawn.emit(list(pts), closed)
        self._cancel_section()

    # --- Mouse and keys -----------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton or (self._space and event.button() == Qt.MouseButton.LeftButton):
            self._pan_from = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        p = self.mapToScene(event.position().toPoint())
        if self.mode == "add" and event.button() == Qt.MouseButton.LeftButton:
            self._add_start = p
            return
        if self.mode == "section":
            if event.button() == Qt.MouseButton.LeftButton:
                self._section_pts.append((p.x(), p.y()))
                self._update_section_preview()
            elif event.button() == Qt.MouseButton.RightButton:
                if self._section_pts:
                    self._section_pts.pop()
                    self._update_section_preview()
                else:
                    self.set_mode("select")
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._pan_from is not None:
            d = event.position() - self._pan_from
            self._pan_from = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        p = self.mapToScene(event.position().toPoint())
        if self.mode == "add" and self._add_start is not None:
            r = QRectF(self._add_start, p).normalized()
            if self._rubber is None:
                pen = QPen(QColor(T.ACTION), 1.5, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self._rubber = self.scene().addRect(r, pen)
                self._rubber.setZValue(20)
            else:
                self._rubber.setRect(r)
            return
        if self.mode == "section" and self._section_pts:
            self._update_section_preview(p)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._pan_from is not None:
            self._pan_from = None
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor if self.mode == "select" else Qt.CursorShape.CrossCursor)
            return
        if self.mode == "add" and self._add_start is not None and event.button() == Qt.MouseButton.LeftButton:
            p = self.mapToScene(event.position().toPoint())
            start = self._add_start
            self._add_start = None
            if self._rubber is not None:
                self.scene().removeItem(self._rubber)
                self._rubber = None
            screen_dist = (self.mapFromScene(start) - self.mapFromScene(p)).manhattanLength()
            if screen_dist < 6:
                self.add_requested.emit((p.x(), p.y(), p.x(), p.y()), True)
            else:
                r = QRectF(start, p).normalized()
                self.add_requested.emit((r.left(), r.top(), r.right(), r.bottom()), False)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.mode == "section":
            self._finish_section()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self.mode == "section" and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish_section()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.set_mode("select")
            self.scene().clearSelection()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = False
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor if self.mode == "select" else Qt.CursorShape.CrossCursor)
            return
        super().keyReleaseEvent(event)
