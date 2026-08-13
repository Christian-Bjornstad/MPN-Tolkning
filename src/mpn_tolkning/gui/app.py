from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mpn_tolkning.core.context import classify_driver_context
from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.models import EvidenceResult, VariantRecord
from mpn_tolkning.core.rules import default_artifact_rules, evaluate_artifact
from mpn_tolkning.gui.workers import ImportWorker, ReportWorker, SearchWorker
from mpn_tolkning.providers.browser import (
    CosmicProvider,
    ClinVarProvider,
    FranklinProvider,
    MtbpProvider,
    OncoKbProvider,
    edge_browser_factory,
)
from mpn_tolkning.providers.calr_et import CalrEtProvider
from mpn_tolkning.reports.patient import PatientReportCoordinator
from mpn_tolkning.reports.review import write_review_workbook
from mpn_tolkning.services.capture import screenshot_path
from mpn_tolkning.services.edge_cdp import EdgeCdpSession
from mpn_tolkning.services.queue import EvidenceQueue
from mpn_tolkning.services.settings import AppSettings, REQUIRED_PROVIDERS


class Palette:
    DEEP_TEAL = "#123C3C"
    TEAL = "#0F766E"
    AMBER = "#D97706"
    BACKGROUND = "#F4F8F7"
    SURFACE = "#FFFFFF"
    TEXT = "#17302F"
    MUTED = "#61716F"
    BORDER = "#D6E2E0"


class MainWindow(QMainWindow):
    PAGE_NAMES = ("Import", "Driver Review", "Evidence", "Reports", "Settings")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MPN Tolkning")
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "variant-lens.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(1120, 720)
        self.resize(1380, 860)
        self.settings = AppSettings.load()
        self.variants: tuple[VariantRecord, ...] = ()
        self.evidence_results: dict[str, EvidenceResult] = {}
        self.import_path: Path | None = None
        self.review_workbook: Path | None = None
        self._threads: list[QThread] = []
        self._workers: list[object] = []
        self._search_worker: SearchWorker | None = None
        self.metric_values: dict[str, QLabel] = {}
        self.provider_status_labels: dict[str, QLabel] = {}

        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.sidebar = self._build_sidebar()
        shell.addWidget(self.sidebar)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(30, 22, 30, 24)
        workspace_layout.setSpacing(18)
        workspace_layout.addWidget(self._build_topbar())
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._build_import_page())
        self.page_stack.addWidget(self._build_review_page())
        self.page_stack.addWidget(self._build_evidence_page())
        self.page_stack.addWidget(self._build_reports_page())
        self.page_stack.addWidget(self._build_settings_page())
        workspace_layout.addWidget(self.page_stack, 1)
        shell.addWidget(workspace, 1)

        self.setStyleSheet(self._style_sheet())
        self._navigate(0)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(206)
        sidebar.setMaximumWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 24, 18, 20)
        layout.setSpacing(8)
        mark = QLabel("⌕")
        mark.setObjectName("brandMark")
        mark.setAccessibleName("Variant Lens mark")
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "variant-lens-48.png"
        if icon_path.is_file():
            mark.setText("")
            mark.setPixmap(QPixmap(str(icon_path)))
        brand = QLabel("MPN\nTolkning")
        brand.setObjectName("brand")
        brand_row = QHBoxLayout()
        brand_row.addWidget(mark)
        brand_row.addWidget(brand, 1)
        layout.addLayout(brand_row)
        descriptor = QLabel("Guided variant evidence workbench")
        descriptor.setWordWrap(True)
        descriptor.setObjectName("sidebarMuted")
        layout.addWidget(descriptor)
        layout.addSpacing(22)
        self.nav_buttons: list[QPushButton] = []
        for index, name in enumerate(self.PAGE_NAMES):
            button = QPushButton(name)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setMinimumHeight(43)
            button.clicked.connect(lambda checked=False, page=index: self._navigate(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)
        privacy = QLabel("LOCAL WORKSPACE\nNo patient identifiers are submitted to evidence sources.")
        privacy.setObjectName("privacyNote")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        return sidebar

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        title_group = QVBoxLayout()
        self.page_eyebrow = QLabel("WORKBENCH / IMPORT")
        self.page_eyebrow.setObjectName("eyebrow")
        self.page_title = QLabel("Import Archer variants")
        self.page_title.setObjectName("pageTitle")
        title_group.addWidget(self.page_eyebrow)
        title_group.addWidget(self.page_title)
        layout.addLayout(title_group)
        layout.addStretch(1)
        self.status_badge = QLabel("Ready")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAccessibleName("Application status")
        layout.addWidget(self.status_badge)
        return bar

    def _page(self, title: str, text: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        intro = QLabel(text)
        intro.setObjectName("bodyMuted")
        intro.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(intro)
        return page, layout

    def _build_import_page(self) -> QWidget:
        page, layout = self._page(
            "Start with an Archer TSV",
            "Import processed MPN panel variants. Every original column is retained; JAK2, CALR and MPL receive focused driver context while unexpected genes remain visible.",
        )
        drop = QFrame()
        drop.setObjectName("dropZone")
        drop_layout = QVBoxLayout(drop)
        drop_layout.setContentsMargins(28, 34, 28, 34)
        icon = QLabel("TSV")
        icon.setObjectName("fileGlyph")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel("Choose an Archer processed-variant file")
        label.setObjectName("dropTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.import_path_label = QLabel("Tab-separated .tsv files · no source file is modified")
        self.import_path_label.setObjectName("bodyMuted")
        self.import_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.import_path_label.setWordWrap(True)
        self.import_button = QPushButton("Choose TSV file")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setMinimumHeight(44)
        self.import_button.setMinimumWidth(180)
        self.import_button.clicked.connect(self._choose_import)
        drop_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(label)
        drop_layout.addWidget(self.import_path_label)
        drop_layout.addWidget(self.import_button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(drop)
        safeguards = self._card("Import safeguards")
        safeguards.layout().addWidget(QLabel("✓ Semantic header matching\n✓ Duplicate-column detection\n✓ GRCh37 allele identity preserved\n✓ Original TSV values retained in the review workbook"))
        layout.addWidget(safeguards)
        layout.addStretch(1)
        return page

    def _metric_card(self, key: str, label: str) -> QFrame:
        card = self._card(label.upper())
        value = QLabel("0")
        value.setObjectName("metricValue")
        card.layout().addWidget(value)
        self.metric_values[key] = value
        return card

    def _build_review_page(self) -> QWidget:
        page, layout = self._page(
            "Driver review",
            "Prioritize canonical MPN drivers, confirm artifacts, and keep every imported observation traceable.",
        )
        metrics = QHBoxLayout()
        metrics.addWidget(self._metric_card("variants", "Variants"))
        metrics.addWidget(self._metric_card("samples", "Samples"))
        metrics.addWidget(self._metric_card("drivers", "Driver context"))
        metrics.addWidget(self._metric_card("review", "Needs review"))
        layout.addLayout(metrics)
        self.review_filter = QLineEdit()
        self.review_filter.setAccessibleName("Filter MPN variants")
        self.review_filter.setPlaceholderText("Filter sample, gene, HGVS, driver context…")
        self.review_filter.setClearButtonEnabled(True)
        self.review_filter.setMinimumHeight(40)
        self.review_filter.textChanged.connect(self._filter_variants)
        layout.addWidget(self.review_filter)

        split = QHBoxLayout()
        self.variant_table = QTableWidget(0, 7)
        self.variant_table.setAccessibleName("MPN variant review table")
        self.variant_table.setHorizontalHeaderLabels(("Sample", "Gene", "HGVSc", "HGVSp", "VAF", "Context", "Review"))
        self.variant_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.variant_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.variant_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.variant_table.verticalHeader().setVisible(False)
        self.variant_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.variant_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.variant_table.itemSelectionChanged.connect(self._update_variant_lens)
        split.addWidget(self.variant_table, 3)
        lens = self._card("VARIANT LENS")
        lens.setMinimumWidth(300)
        self.variant_title = QLabel("Select a variant")
        self.variant_title.setObjectName("lensTitle")
        self.variant_title.setWordWrap(True)
        self.driver_context_label = QLabel("Driver context and evidence readiness will appear here.")
        self.driver_context_label.setObjectName("bodyMuted")
        self.driver_context_label.setWordWrap(True)
        self.variant_identity_label = QLabel("")
        self.variant_identity_label.setObjectName("monoText")
        self.variant_identity_label.setWordWrap(True)
        lens.layout().addWidget(self.variant_title)
        lens.layout().addWidget(self.variant_identity_label)
        lens.layout().addWidget(self.driver_context_label)
        lens.layout().addStretch(1)
        split.addWidget(lens, 1)
        layout.addLayout(split, 1)
        return page

    def _build_evidence_page(self) -> QWidget:
        page, layout = self._page(
            "Evidence collection",
            "Provider pages run in isolated Microsoft Edge profiles. A result counts only after identity verification and a valid capture.",
        )
        provider_grid = QGridLayout()
        for index, provider in enumerate(REQUIRED_PROVIDERS):
            card = self._card(provider)
            status = QLabel("Ready")
            status.setObjectName("providerReady")
            status.setAccessibleName(f"{provider} status")
            card.layout().addWidget(status)
            self.provider_status_labels[provider] = status
            provider_grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(provider_grid)
        controls = QHBoxLayout()
        self.start_search_button = QPushButton("Start evidence search")
        self.start_search_button.setObjectName("primaryButton")
        self.start_search_button.setMinimumHeight(44)
        self.start_search_button.clicked.connect(self._start_search)
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.stop_button = QPushButton("Stop")
        self.pause_button.clicked.connect(lambda: self._search_worker and self._search_worker.pause())
        self.resume_button.clicked.connect(lambda: self._search_worker and self._search_worker.resume())
        self.stop_button.clicked.connect(lambda: self._search_worker and self._search_worker.stop())
        for button in (self.start_search_button, self.pause_button, self.resume_button, self.stop_button):
            button.setMinimumHeight(44)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.evidence_table = QTableWidget(0, 4)
        self.evidence_table.setHorizontalHeaderLabels(("Provider", "Status", "Identity", "Summary"))
        self.evidence_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.evidence_table.verticalHeader().setVisible(False)
        self.evidence_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.evidence_table, 1)
        return page

    def _build_reports_page(self) -> QWidget:
        page, layout = self._page(
            "Reports and handoff",
            "Review workbooks and patient evidence workbooks are written incrementally. Locked files remain pending and can be reconciled later.",
        )
        output_card = self._card("OUTPUT DIRECTORY")
        self.output_path_label = QLabel(self.settings.output_directory or "Chosen automatically beside the imported TSV")
        self.output_path_label.setObjectName("monoText")
        self.output_path_label.setWordWrap(True)
        output_card.layout().addWidget(self.output_path_label)
        choose = QPushButton("Choose output folder")
        choose.setMinimumHeight(40)
        choose.clicked.connect(self._choose_output_directory)
        output_card.layout().addWidget(choose, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(output_card)
        reports = QHBoxLayout()
        self.review_report_card = self._report_card("Review workbook", "Not created yet")
        self.patient_report_card = self._report_card("Patient reports", "No reports yet")
        reports.addWidget(self.review_report_card)
        reports.addWidget(self.patient_report_card)
        layout.addLayout(reports)
        self.generate_reports_button = QPushButton("Generate / reconcile reports")
        self.generate_reports_button.setObjectName("primaryButton")
        self.generate_reports_button.setMinimumHeight(44)
        self.generate_reports_button.clicked.connect(self._start_reports)
        layout.addWidget(self.generate_reports_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _build_settings_page(self) -> QWidget:
        page, layout = self._page(
            "Settings",
            "Choose evidence sources and browser behavior. Passwords are stored separately in Windows Credential Manager.",
        )
        providers = self._card("EVIDENCE SOURCES")
        self.provider_checks: dict[str, QCheckBox] = {}
        for name in REQUIRED_PROVIDERS:
            check = QCheckBox(name)
            check.setChecked(name in self.settings.selected_providers)
            self.provider_checks[name] = check
            providers.layout().addWidget(check)
        layout.addWidget(providers)
        browser = self._card("BROWSER")
        self.background_check = QCheckBox("Run evidence Edge windows minimized")
        self.background_check.setChecked(self.settings.browser_background)
        browser.layout().addWidget(self.background_check)
        browser.layout().addWidget(QLabel("Reference build is locked to GRCh37 / hg19 for this workflow."))
        layout.addWidget(browser)
        save = QPushButton("Save settings")
        save.setObjectName("primaryButton")
        save.setMinimumHeight(44)
        save.clicked.connect(self._save_settings)
        layout.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _card(self, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        caption = QLabel(label)
        caption.setObjectName("cardLabel")
        layout.addWidget(caption)
        return card

    def _report_card(self, title: str, initial: str) -> QFrame:
        card = self._card(title.upper())
        status = QLabel(initial)
        status.setObjectName("reportStatus")
        status.setWordWrap(True)
        card.layout().addWidget(status)
        card.status_label = status
        return card

    def _navigate(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        titles = ("Import Archer variants", "Review MPN drivers", "Collect verified evidence", "Generate workbooks", "Configure the workbench")
        self.page_eyebrow.setText(f"WORKBENCH / {self.PAGE_NAMES[index].upper()}")
        self.page_title.setText(titles[index])
        for position, button in enumerate(self.nav_buttons):
            current = position == index
            button.setChecked(current)
            button.setProperty("current", current)
            button.setAccessibleName(f"{button.text()} page" + (", current" if current else ""))
            button.style().unpolish(button)
            button.style().polish(button)
        self.nav_buttons[index].setFocus(Qt.FocusReason.OtherFocusReason)

    def set_variants(self, variants) -> None:
        self.variants = tuple(variants)
        self.variant_table.setRowCount(len(self.variants))
        driver_count = 0
        review_count = 0
        for row, variant in enumerate(self.variants):
            context = classify_driver_context(variant)
            driver_count += bool(context.label)
            review_count += context.needs_review
            values = (
                variant.sample,
                variant.gene,
                variant.hgvsc,
                variant.hgvsp,
                "" if variant.vaf is None else f"{variant.vaf:g}",
                context.label or "Unclassified",
                "Review" if context.needs_review else "Ready",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (2, 3):
                    item.setFont(QFont("Consolas", 9))
                if context.needs_review:
                    item.setBackground(QColor("#FFF4E5"))
                self.variant_table.setItem(row, column, item)
        self.metric_values["variants"].setText(str(len(self.variants)))
        self.metric_values["samples"].setText(str(len({variant.sample for variant in self.variants})))
        self.metric_values["drivers"].setText(str(driver_count))
        self.metric_values["review"].setText(str(review_count))
        if self.variants:
            self.variant_table.selectRow(0)
        self._filter_variants(self.review_filter.text())

    def _filter_variants(self, query: str) -> None:
        needle = query.strip().casefold()
        for row in range(self.variant_table.rowCount()):
            haystack = " ".join(
                self.variant_table.item(row, column).text()
                for column in range(self.variant_table.columnCount())
                if self.variant_table.item(row, column)
            ).casefold()
            self.variant_table.setRowHidden(row, bool(needle and needle not in haystack))

    def _update_variant_lens(self) -> None:
        row = self.variant_table.currentRow()
        if not 0 <= row < len(self.variants):
            return
        variant = self.variants[row]
        context = classify_driver_context(variant)
        protein = variant.hgvsp.replace("p.Val617Phe", "V617F") if variant.hgvsp else ""
        display_protein = "frameshift" if "fs" in protein and len(protein) > 14 else protein
        self.variant_title.setText(f"{variant.gene} · {display_protein}".strip(" ·"))
        self.variant_identity_label.setText(
            f"{variant.hgvsc}\n{variant.hgvsp}\n{stable_variant_key(variant)}"
        )
        self.driver_context_label.setText(
            (context.label + "\n" + context.detail).strip()
            or "No predefined MPN driver label. Keep visible for qualified review."
        )

    def _choose_import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose Archer TSV", "", "TSV files (*.tsv *.txt);;All files (*)")
        if filename:
            self.load_file(Path(filename))

    def load_file(self, path: Path) -> None:
        self.import_path = Path(path)
        self.import_path_label.setText(str(self.import_path))
        self._set_status("Importing…", busy=True)
        thread = QThread(self)
        worker = ImportWorker(self.import_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._import_completed)
        worker.failed.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._discard_worker(worker))
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._discard_thread(thread))
        self._threads.append(thread)
        self._workers.append(worker)
        thread.start()

    def _import_completed(self, variants) -> None:
        self.set_variants(variants)
        output = self._output_directory()
        contexts = {stable_variant_key(v): classify_driver_context(v) for v in self.variants}
        rules = default_artifact_rules()
        artifacts = {stable_variant_key(v): evaluate_artifact(v, rules) for v in self.variants}
        self.review_workbook = write_review_workbook(output / "MPN_Variant_Review.xlsx", self.variants, contexts, artifacts)
        self.review_report_card.status_label.setText(str(self.review_workbook))
        self._set_status(f"Imported {len(self.variants)} variants")
        self._navigate(1)

    def _output_directory(self) -> Path:
        if self.settings.output_directory:
            target = Path(self.settings.output_directory)
        elif self.import_path:
            target = self.import_path.parent / "MPN_Output"
        else:
            target = Path.cwd() / "MPN_Output"
        target.mkdir(parents=True, exist_ok=True)
        self.output_path_label.setText(str(target))
        return target

    def _choose_output_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose output directory", str(self._output_directory()))
        if directory:
            self.settings.output_directory = directory
            self.settings.save()
            self.output_path_label.setText(directory)

    def _providers(self):
        output = self._output_directory()
        profile_root = AppSettings.default_path().parent / "browser_profiles"
        captures = output / "evidence_captures"
        factory = edge_browser_factory(profile_root)
        selected = {name for name, check in self.provider_checks.items() if check.isChecked()}
        providers = []
        if "CALR-ETdb" in selected:
            providers.append(CalrEtProvider(require_capture=True, capture_callback=self._capture_calr_result))
        classes = {
            "MTBP": MtbpProvider,
            "Franklin": FranklinProvider,
            "ClinVar": ClinVarProvider,
            "OncoKB": OncoKbProvider,
            "COSMIC": CosmicProvider,
        }
        for name in REQUIRED_PROVIDERS[1:]:
            if name in selected:
                providers.append(classes[name](factory, captures))
        return providers

    def _capture_calr_result(self, variant: VariantRecord, context, url: str):
        session = EdgeCdpSession(AppSettings.default_path().parent / "browser_profiles", background=self.settings.browser_background)
        target = screenshot_path(self._output_directory() / "evidence_captures", context.stable_key, "CALR-ETdb", 1)
        try:
            session.start("CALR-ETdb")
            session.navigate(CalrEtProvider.SEARCH_URL)
            cdna = json.dumps(context.cdna)
            submitted = session.evaluate(
                "(() => { const input=document.querySelector('input[name=nucleotid]');"
                " if(!input) return false; input.value=" + cdna + ";"
                " input.dispatchEvent(new Event('input',{bubbles:true}));"
                " const form=input.closest('form'); if(!form) return false; form.submit(); return true; })()"
            )
            if not submitted:
                raise ValueError("CALR-ETdb cDNA form was not available")
            time.sleep(2)
            body = str(session.evaluate("document.body?.innerText || ''") or "")
            if context.cdna not in body:
                raise ValueError("CALR-ETdb capture did not show the submitted cDNA")
            session.screenshot(target)
            return (target,)
        finally:
            session.close()

    def _start_search(self) -> None:
        if not self.variants:
            self._show_error("Import an Archer TSV before starting evidence collection.")
            return
        providers = self._providers()
        if not providers:
            self._show_error("Select at least one evidence provider in Settings.")
            return
        queue = EvidenceQueue(providers)
        thread = QThread(self)
        worker = SearchWorker(queue, self.variants)
        self._search_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.state_changed.connect(self._search_state_changed)
        worker.completed.connect(self._search_completed)
        worker.failed.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._discard_worker(worker))
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._discard_thread(thread))
        self._threads.append(thread)
        self._workers.append(worker)
        thread.start()

    def _search_state_changed(self, state: str) -> None:
        labels = {"running": "Searching…", "paused": "Paused", "stopped": "Stopped", "complete": "Evidence complete"}
        self._set_status(labels.get(state, state.title()), busy=state == "running")

    def _search_completed(self, results) -> None:
        self.evidence_results = dict(results)
        self.evidence_table.setRowCount(len(self.evidence_results))
        provider_states: dict[str, str] = {}
        for row, result in enumerate(self.evidence_results.values()):
            values = (result.provider, result.status.value, result.observed_identity or result.expected_identity, result.summary)
            for column, value in enumerate(values):
                self.evidence_table.setItem(row, column, QTableWidgetItem(str(value)))
            provider_states[result.provider] = result.status.value.replace("_", " ").title()
        for provider, label in self.provider_status_labels.items():
            label.setText(provider_states.get(provider, "Ready"))
        self._start_reports()

    def _start_reports(self) -> None:
        if not self.variants:
            self._show_error("Import variants before generating reports.")
            return
        coordinator = PatientReportCoordinator(self._output_directory())
        thread = QThread(self)
        worker = ReportWorker(coordinator, self.variants, self.evidence_results)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._reports_completed)
        worker.failed.connect(self._show_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._discard_worker(worker))
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._discard_thread(thread))
        self._threads.append(thread)
        self._workers.append(worker)
        thread.start()

    def _reports_completed(self, output) -> None:
        self.patient_report_card.status_label.setText(f"{len(output)} patient workbook(s) written to\n{self._output_directory()}")
        self._set_status("Reports ready")

    def _save_settings(self) -> None:
        self.settings.selected_providers = [name for name, check in self.provider_checks.items() if check.isChecked()]
        self.settings.browser_background = self.background_check.isChecked()
        self.settings.save()
        self._set_status("Settings saved")

    def _set_status(self, text: str, *, busy: bool = False) -> None:
        self.status_badge.setText(text)
        self.status_badge.setProperty("busy", busy)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    def _show_error(self, message: str) -> None:
        self._set_status("Needs attention")
        if self.isVisible():
            QMessageBox.warning(self, "MPN Tolkning", message)

    def _discard_thread(self, thread: QThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)

    def _discard_worker(self, worker: object) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def closeEvent(self, event) -> None:
        if self._search_worker is not None:
            self._search_worker.stop()
        for thread in self._threads:
            thread.quit()
        super().closeEvent(event)

    def _style_sheet(self) -> str:
        return f"""
        * {{ font-family: 'Segoe UI'; color: {Palette.TEXT}; font-size: 10pt; }}
        QMainWindow, QWidget {{ background: {Palette.BACKGROUND}; }}
        QLabel {{ background: transparent; }}
        #sidebar {{ background: {Palette.DEEP_TEAL}; border: 0; }}
        #brandMark {{ color: #FFFFFF; font-size: 34px; font-weight: 700; background: {Palette.TEAL}; border-radius: 12px; min-width: 48px; min-height: 48px; qproperty-alignment: AlignCenter; }}
        #brand {{ color: #FFFFFF; font-size: 17px; font-weight: 700; line-height: 1.1; }}
        #sidebarMuted {{ color: #BFD3D0; font-size: 9pt; }}
        #privacyNote {{ color: #BFD3D0; font-size: 8pt; border-top: 1px solid #35605D; padding-top: 14px; }}
        #navButton {{ color: #DCEBE9; background: transparent; border: 0; border-radius: 8px; text-align: left; padding: 0 14px; font-weight: 600; }}
        #navButton:hover {{ background: #1A4A48; }}
        #navButton[current="true"] {{ color: #FFFFFF; background: {Palette.TEAL}; border-left: 4px solid #F2B24C; padding-left: 10px; }}
        #navButton:focus {{ border: 2px solid #F2B24C; }}
        #eyebrow, #cardLabel {{ color: {Palette.TEAL}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
        #pageTitle {{ color: {Palette.DEEP_TEAL}; font-size: 22pt; font-weight: 700; }}
        #sectionTitle {{ color: {Palette.DEEP_TEAL}; font-size: 16pt; font-weight: 700; }}
        #bodyMuted {{ color: {Palette.MUTED}; }}
        #statusBadge, #providerReady {{ background: #E0F0ED; color: #075E57; border: 1px solid #BAD9D4; border-radius: 12px; padding: 6px 11px; font-weight: 600; }}
        #statusBadge[busy="true"] {{ background: #FFF4E5; color: #914C00; border-color: #F0C27B; }}
        #card {{ background: {Palette.SURFACE}; border: 1px solid {Palette.BORDER}; border-radius: 12px; }}
        #metricValue {{ color: {Palette.DEEP_TEAL}; font-size: 24pt; font-weight: 700; }}
        #dropZone {{ background: #FBFDFC; border: 2px dashed #93B8B3; border-radius: 14px; }}
        #dropTitle, #lensTitle {{ color: {Palette.DEEP_TEAL}; font-size: 14pt; font-weight: 700; }}
        #fileGlyph {{ color: #FFFFFF; background: {Palette.TEAL}; border-radius: 10px; min-width: 58px; min-height: 58px; font-size: 11pt; font-weight: 700; }}
        #primaryButton {{ color: #FFFFFF; background: {Palette.TEAL}; border: 0; border-radius: 8px; padding: 0 18px; font-weight: 700; }}
        #primaryButton:hover {{ background: #0B665F; }}
        QPushButton {{ background: #FFFFFF; border: 1px solid #AFC5C2; border-radius: 8px; padding: 8px 14px; font-weight: 600; }}
        QPushButton:hover {{ border-color: {Palette.TEAL}; background: #F7FBFA; }}
        QPushButton:focus, QLineEdit:focus, QTableWidget:focus, QCheckBox:focus {{ border: 2px solid {Palette.AMBER}; }}
        QLineEdit {{ background: #FFFFFF; border: 1px solid #BFD0CE; border-radius: 8px; padding: 0 12px; selection-background-color: {Palette.TEAL}; }}
        QTableWidget {{ background: #FFFFFF; alternate-background-color: #F7FAF9; border: 1px solid {Palette.BORDER}; border-radius: 10px; gridline-color: #E5ECEA; selection-background-color: #D8ECE8; selection-color: {Palette.DEEP_TEAL}; }}
        QHeaderView::section {{ color: #FFFFFF; background: {Palette.DEEP_TEAL}; border: 0; border-right: 1px solid #35605D; padding: 9px; font-weight: 700; }}
        #monoText {{ font-family: 'Consolas'; color: #39504E; background: #F5F8F7; border-radius: 6px; padding: 8px; }}
        #reportStatus {{ color: {Palette.DEEP_TEAL}; font-size: 12pt; font-weight: 600; }}
        QCheckBox {{ spacing: 10px; min-height: 30px; }}
        QCheckBox::indicator {{ width: 18px; height: 18px; }}
        QCheckBox::indicator:checked {{ background: {Palette.TEAL}; border: 2px solid {Palette.TEAL}; border-radius: 4px; }}
        """


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MPN Tolkning")
    app.setOrganizationName("Christian Bjørnstad")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
