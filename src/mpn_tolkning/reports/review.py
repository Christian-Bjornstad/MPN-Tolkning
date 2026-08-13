from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.models import DriverContext, VariantRecord


APP_COLUMNS = (
    "Stable Variant Key",
    "Driver Context",
    "Artifact Reason",
    "Review Warning",
    "Skip Database Search (X)",
    "CALR-ETdb",
    "MTBP",
    "Franklin",
    "ClinVar",
    "OncoKB",
    "COSMIC",
)

HEADER_FILL = PatternFill("solid", fgColor="123C3C")
DRIVER_FILL = PatternFill("solid", fgColor="D9ECE8")
WARNING_FILL = PatternFill("solid", fgColor="FFF0D2")
ARTIFACT_FILL = PatternFill("solid", fgColor="E4E9E8")


class ReviewWorkbookError(ValueError):
    """The review workbook is missing or contains ambiguous application data."""


def write_review_workbook(
    path: Path,
    variants: Iterable[VariantRecord],
    contexts: Mapping[str, DriverContext],
    artifact_reasons: Mapping[str, str],
) -> Path:
    variant_list = list(variants)
    original_headers = _original_headers(variant_list)
    headers = [*original_headers, *APP_COLUMNS]

    workbook = Workbook()
    all_variants = workbook.active
    all_variants.title = "All Variants"
    artifacts_removed = workbook.create_sheet("Artifacts Removed")

    _write_sheet(
        all_variants,
        headers,
        original_headers,
        variant_list,
        contexts,
        artifact_reasons,
    )
    _write_sheet(
        artifacts_removed,
        headers,
        original_headers,
        [
            variant
            for variant in variant_list
            if not artifact_reasons.get(stable_variant_key(variant), "")
        ],
        contexts,
        artifact_reasons,
    )
    return _save_atomically(workbook, Path(path))


def load_skip_keys(path: Path) -> set[str]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    if "All Variants" not in workbook.sheetnames:
        raise ReviewWorkbookError("Missing 'All Variants' sheet.")
    sheet = workbook["All Variants"]
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    required = ("Sample", "Stable Variant Key", "Skip Database Search (X)")
    missing = [header for header in required if header not in headers]
    if missing:
        raise ReviewWorkbookError("Missing review columns: " + ", ".join(missing))

    indexes = {header: headers.index(header) for header in required}
    identities: set[str] = set()
    skipped: set[str] = set()
    for row in sheet.iter_rows(min_row=2, values_only=True):
        sample = str(row[indexes["Sample"]] or "").strip()
        stable_key = str(row[indexes["Stable Variant Key"]] or "").strip()
        if not sample or not stable_key:
            continue
        identity = f"{sample}|{stable_key}"
        if identity in identities:
            raise ReviewWorkbookError(f"Duplicate review identity: {identity}")
        identities.add(identity)
        selection = str(row[indexes["Skip Database Search (X)"]] or "").strip()
        if selection.upper() == "X":
            skipped.add(identity)
    return skipped


def _write_sheet(
    sheet,
    headers: list[str],
    original_headers: list[str],
    variants: list[VariantRecord],
    contexts: Mapping[str, DriverContext],
    artifact_reasons: Mapping[str, str],
) -> None:
    sheet.append(headers)
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center")

    for variant in variants:
        key = stable_variant_key(variant)
        context = contexts.get(key, DriverContext())
        artifact_reason = artifact_reasons.get(key, "")
        warning = context.detail if context.needs_review else ""
        values = [variant.original.get(header, "") for header in original_headers]
        values.extend(
            [
                key,
                context.label,
                artifact_reason,
                warning,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        sheet.append(values)
        fill = (
            ARTIFACT_FILL
            if artifact_reason
            else WARNING_FILL
            if context.needs_review
            else DRIVER_FILL
            if context.label
            else None
        )
        if fill:
            for cell in sheet[sheet.max_row]:
                cell.fill = fill

    sheet.freeze_panes = "E2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 24
    for column, header in enumerate(headers, start=1):
        letter = get_column_letter(column)
        sheet.column_dimensions[letter].width = _column_width(header)
        if header == "Stable Variant Key":
            sheet.column_dimensions[letter].hidden = True
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=False)


def _original_headers(variants: list[VariantRecord]) -> list[str]:
    headers: list[str] = []
    for variant in variants:
        for header in variant.original:
            if header not in headers:
                headers.append(header)
    return headers or ["Sample", "Gene", "HGVSc", "AF"]


def _column_width(header: str) -> float:
    if header in {"HGVSc", "HGVSp", "Driver Context", "Artifact Reason"}:
        return 28
    if header in {"Review Warning", "Skip Database Search (X)"}:
        return 24
    return min(max(len(header) + 3, 11), 18)


def _save_atomically(workbook: Workbook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp{path.suffix}")
    workbook.save(temporary)
    temporary.replace(path)
    return path
