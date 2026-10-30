"""Application state shared by the panels, with undoable edits.

Every change to items or sections goes through an undo command, so the
whole session can be undone step by step and the views refresh from one
signal.
"""

from __future__ import annotations

import copy
from dataclasses import replace

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from ..core.frequency import Results, calculate
from ..core.project import Item, Project, Section
from ..core.workspace import Workspace

AUTO_SOURCES = ("library", "model", "similar")


class ItemsCommand(QUndoCommand):
    """Replace a set of items by id: add, change or remove in one step."""

    def __init__(self, state: AppState, before: list[Item], after: list[Item], text: str):
        super().__init__(text)
        self.state = state
        self.before = [copy.deepcopy(i) for i in before]
        self.after = [copy.deepcopy(i) for i in after]

    def _apply(self, remove: list[Item], put: list[Item]) -> None:
        items = self.state.project.items
        index = {it.id: k for k, it in enumerate(items)}
        put_ids = {i.id for i in put}
        for it in put:
            if it.id in index:
                items[index[it.id]] = copy.deepcopy(it)
            else:
                items.append(copy.deepcopy(it))
        drop = {i.id for i in remove} - put_ids
        if drop:
            items[:] = [i for i in items if i.id not in drop]
        self.state.items_changed.emit()

    def _rejected(self) -> int:
        """Automatic detections this command deletes (counted against the no-edit rate)."""
        kept = {i.id for i in self.after}
        return sum(1 for i in self.before if i.id not in kept and i.source in AUTO_SOURCES)

    def redo(self) -> None:
        self._apply(self.before, self.after)
        self._count(+1)

    def undo(self) -> None:
        self._apply(self.after, self.before)
        self._count(-1)

    def _count(self, sign: int) -> None:
        n = self._rejected()
        if n:
            stats = self.state.project.stats
            stats["auto_rejected"] = stats.get("auto_rejected", 0) + sign * n


class SectionsCommand(QUndoCommand):
    def __init__(self, state: AppState, before: list[Section], after: list[Section], text: str,
                 item_before: list[Item] | None = None, item_after: list[Item] | None = None):
        super().__init__(text)
        self.state = state
        self.before = copy.deepcopy(before)
        self.after = copy.deepcopy(after)
        self.items = ItemsCommand(state, item_before or [], item_after or [], text) if item_before or item_after else None

    def redo(self) -> None:
        self.state.project.sections = copy.deepcopy(self.after)
        if self.items:
            self.items.redo()
        self.state.sections_changed.emit()

    def undo(self) -> None:
        self.state.project.sections = copy.deepcopy(self.before)
        if self.items:
            self.items.undo()
        self.state.sections_changed.emit()


class AppState(QObject):
    items_changed = Signal()
    sections_changed = Signal()
    page_changed = Signal()  # current document or page
    project_changed = Signal()  # new or opened project, documents added
    selection_changed = Signal()
    busy_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.ws = Workspace()
        self.undo = QUndoStack(self)
        self.doc_id: str | None = None
        self.page = 0
        self.selected: list[str] = []
        self.current_class = "manual_valve"
        self.library = None  # SymbolLibrary in use
        self.model_dir: str | None = None
        self.dirty = False
        self.undo.cleanChanged.connect(lambda clean: setattr(self, "dirty", not clean))
        self._results: Results | None = None
        self.items_changed.connect(self._invalidate)
        self.sections_changed.connect(self._invalidate)

    @property
    def project(self) -> Project:
        return self.ws.project

    def set_project(self, project: Project) -> None:
        self.ws.close()
        self.ws = Workspace(project)
        self.undo.clear()
        self.doc_id = project.documents[0].id if project.documents else None
        self.page = 0
        self.selected = []
        self._results = None
        self.project_changed.emit()
        self.page_changed.emit()

    def go_to(self, doc_id: str, page: int) -> None:
        if doc_id == self.doc_id and page == self.page:
            return
        self.doc_id, self.page = doc_id, page
        self.selected = []
        self.page_changed.emit()
        self.selection_changed.emit()

    def select(self, ids: list[str]) -> None:
        if ids != self.selected:
            self.selected = ids
            self.selection_changed.emit()

    def selected_items(self) -> list[Item]:
        ids = set(self.selected)
        return [i for i in self.project.items if i.id in ids]

    def page_items(self) -> list[Item]:
        if self.doc_id is None:
            return []
        return self.project.page_items(self.doc_id, self.page)

    # --- Edits ----------------------------------------------------------------

    def add_items(self, items: list[Item], text: str) -> None:
        if items:
            self.undo.push(ItemsCommand(self, [], items, text))

    def change_items(self, items: list[Item], text: str, **changes) -> None:
        """Change fields on items; marks proposals the reviewer altered as edited."""
        if not items:
            return
        after = []
        for it in items:
            new = replace(copy.deepcopy(it), **changes)
            if it.source in ("library", "model", "similar", "bluebeam") and any(
                k in changes and getattr(it, k) != v for k, v in changes.items() if k in ("cls", "box", "size_mm")
            ):
                new.edited = True
            after.append(new)
        self.undo.push(ItemsCommand(self, items, after, text))

    def delete_items(self, items: list[Item]) -> None:
        if items:
            self.undo.push(ItemsCommand(self, items, [], f"Delete {len(items)} item(s)"))
            self.select([])

    def set_sections(self, sections: list[Section], text: str, item_before=None, item_after=None) -> None:
        self.undo.push(SectionsCommand(self, self.project.sections, sections, text, item_before, item_after))

    # --- Derived --------------------------------------------------------------------

    def _invalidate(self) -> None:
        self._results = None

    def results(self, include_proposed: bool = False) -> Results:
        if include_proposed:
            return calculate(self.project, self.ws.table, include_proposed=True)
        if self._results is None:
            self._results = calculate(self.project, self.ws.table)
        return self._results

    def auto_kept_rate(self) -> tuple[float, int]:
        """Share of automatic detections the reviewer kept unchanged (the 90 % target)."""
        auto = [i for i in self.project.items if i.source in AUTO_SOURCES and i.status == "accepted"]
        rejected = self.project.stats.get("auto_rejected", 0)
        total = len(auto) + rejected
        if not total:
            return 0.0, 0
        return sum(not i.edited for i in auto) / total, total
