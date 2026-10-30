"""Background work without blocking the UI.

A task is a plain function; it receives a progress(i, n) callback and returns
a result that is delivered on the GUI thread. Tasks never touch widgets or
the project directly: the caller applies the result (usually through an
undo command).
"""

from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)


class _Task(QRunnable):
    def __init__(self, fn: Callable, signals: _Signals):
        super().__init__()
        self.fn = fn
        self.signals = signals

    def run(self) -> None:
        try:
            result = self.fn(lambda i, n: self.signals.progress.emit(i, n))
        except Exception:  # surfaced to the user, not swallowed
            self.signals.failed.emit(traceback.format_exc(limit=4))
            return
        self.signals.done.emit(result)


class TaskRunner(QObject):
    started = Signal(str)
    progress = Signal(int, int)
    finished = Signal()
    failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)  # PDFium work is serialised anyway
        self._keep: list[_Signals] = []
        self.busy = False

    def run(self, label: str, fn: Callable, on_done: Callable[[object], None]) -> bool:
        if self.busy:
            return False
        self.busy = True
        sig = _Signals()
        self._keep.append(sig)

        def finish(result):
            self.busy = False
            self._keep.remove(sig)
            self.finished.emit()
            on_done(result)

        def fail(msg):
            self.busy = False
            self._keep.remove(sig)
            self.finished.emit()
            self.failed.emit(label, msg)

        sig.done.connect(finish)
        sig.failed.connect(fail)
        sig.progress.connect(self.progress)
        self.started.emit(label)
        self.pool.start(_Task(fn, sig))
        return True
