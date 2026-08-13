from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from typing import Sequence

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from mpn_tolkning.core.models import EvidenceResult, VariantRecord
from mpn_tolkning.io.tsv_reader import ArcherTsvReader
from mpn_tolkning.reports.patient import PatientReportCoordinator
from mpn_tolkning.services.queue import EvidenceQueue, PauseControl


class ImportWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.completed.emit(ArcherTsvReader().read(self.path))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class SearchWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    state_changed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        queue: EvidenceQueue,
        variants: Sequence[VariantRecord],
        skip_keys: set[str] | None = None,
    ):
        super().__init__()
        self.queue = queue
        self.variants = tuple(variants)
        self.skip_keys = skip_keys or set()
        self.pause_control = PauseControl()

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.state_changed.emit("running")
            self.completed.emit(self.queue.run(self.variants, self.skip_keys, self.pause_control))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.state_changed.emit("stopped" if self.pause_control.stopped else "complete")
            self.finished.emit()

    @pyqtSlot()
    def pause(self) -> None:
        self.pause_control.request_pause()
        self.state_changed.emit("paused")

    @pyqtSlot()
    def resume(self) -> None:
        self.pause_control.resume()
        self.state_changed.emit("running")

    @pyqtSlot()
    def stop(self) -> None:
        self.pause_control.request_stop()


class ReportWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        coordinator: PatientReportCoordinator,
        variants: Sequence[VariantRecord],
        evidence: Sequence[EvidenceResult] | Mapping[str, EvidenceResult],
    ):
        super().__init__()
        self.coordinator = coordinator
        self.variants = tuple(variants)
        self.evidence = dict(evidence) if isinstance(evidence, Mapping) else tuple(evidence)

    @pyqtSlot()
    def run(self) -> None:
        try:
            output = self.coordinator.write_all(self.variants, self.evidence)
            output.update(self.coordinator.reconcile())
            self.completed.emit(output)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
