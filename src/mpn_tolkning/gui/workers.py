from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from typing import Sequence

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from mpn_tolkning.core.models import EvidenceResult, VariantRecord
from mpn_tolkning.core.context import classify_driver_context
from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.rules import configured_artifact_rules, evaluate_artifact
from mpn_tolkning.io.tsv_reader import ArcherTsvReader
from mpn_tolkning.reports.patient import PatientReportCoordinator
from mpn_tolkning.reports.review import ReviewWorkbookError, load_skip_keys, write_review_workbook
from mpn_tolkning.services.queue import EvidenceQueue, PauseControl


class ImportWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, path: Path, output_directory: Path, artifact_rules: list[dict]):
        super().__init__()
        self.path = Path(path)
        self.output_directory = Path(output_directory)
        self.artifact_rules = list(artifact_rules)

    @pyqtSlot()
    def run(self) -> None:
        try:
            variants = ArcherTsvReader().read(self.path)
            contexts = {stable_variant_key(item): classify_driver_context(item) for item in variants}
            rules = configured_artifact_rules(self.artifact_rules)
            artifacts = {stable_variant_key(item): evaluate_artifact(item, rules) for item in variants}
            workbook = self.output_directory / "MPN_Variant_Review.xlsx"
            if workbook.exists():
                try:
                    load_skip_keys(workbook, variants)
                except ReviewWorkbookError:
                    counter = 2
                    while workbook.exists():
                        workbook = self.output_directory / f"MPN_Variant_Review_{counter}.xlsx"
                        counter += 1
            if not workbook.exists():
                workbook = write_review_workbook(workbook, variants, contexts, artifacts)
            self.completed.emit((variants, workbook))
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
        existing_results: dict[str, EvidenceResult] | None = None,
    ):
        super().__init__()
        self.queue = queue
        self.variants = tuple(variants)
        self.skip_keys = skip_keys or set()
        self.existing_results = existing_results or {}
        self.pause_control = PauseControl()

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.state_changed.emit("running")
            if self.existing_results:
                results = self.queue.resume_pending(
                    self.variants,
                    self.existing_results,
                    skip_keys=self.skip_keys,
                    pause=self.pause_control,
                )
            else:
                results = self.queue.run(self.variants, self.skip_keys, self.pause_control)
            self.completed.emit(results)
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
