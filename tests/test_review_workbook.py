from openpyxl import load_workbook
import pytest

from mpn_tolkning.core.context import classify_driver_context
from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.reports.review import (
    ReviewWorkbookError,
    load_skip_keys,
    write_review_workbook,
)


def _contexts(variants):
    return {
        stable_variant_key(variant): classify_driver_context(variant)
        for variant in variants
    }


def test_review_workbook_preserves_rows_and_adds_skip_control(tmp_path, sample_variants):
    path = write_review_workbook(
        tmp_path / "review.xlsx",
        sample_variants,
        _contexts(sample_variants),
        {},
    )
    workbook = load_workbook(path)

    assert workbook.sheetnames == ["All Variants", "Artifacts Removed"]
    headers = [cell.value for cell in workbook["All Variants"][1]]
    assert headers[:4] == ["Sample", "Gene", "HGVSc", "HGVSp"]
    assert "Skip Database Search (X)" in headers
    assert "Stable Variant Key" in headers
    stable_column = headers.index("Stable Variant Key") + 1
    assert workbook["All Variants"].column_dimensions[
        workbook["All Variants"].cell(1, stable_column).column_letter
    ].hidden


def test_artifact_removed_sheet_excludes_configured_artifact(tmp_path, sample_variants):
    artifact_key = stable_variant_key(sample_variants[1])
    path = write_review_workbook(
        tmp_path / "review.xlsx",
        sample_variants,
        _contexts(sample_variants),
        {artifact_key: "Configured test artifact"},
    )
    workbook = load_workbook(path, read_only=True)

    assert workbook["All Variants"].max_row == 4
    assert workbook["Artifacts Removed"].max_row == 3


def test_skip_selection_round_trips_by_sample_and_stable_key(tmp_path, sample_variants):
    path = write_review_workbook(
        tmp_path / "review.xlsx",
        sample_variants,
        _contexts(sample_variants),
        {},
    )
    workbook = load_workbook(path)
    sheet = workbook["All Variants"]
    headers = [cell.value for cell in sheet[1]]
    skip_col = headers.index("Skip Database Search (X)") + 1
    sheet.cell(2, skip_col, "x")
    workbook.save(path)

    assert load_skip_keys(path) == {
        f"{sample_variants[0].sample}|{stable_variant_key(sample_variants[0])}"
    }


def test_duplicate_review_identity_fails_closed(tmp_path, sample_variants):
    path = write_review_workbook(
        tmp_path / "review.xlsx",
        [sample_variants[0], sample_variants[0]],
        _contexts(sample_variants),
        {},
    )

    with pytest.raises(ReviewWorkbookError, match="Duplicate review identity"):
        load_skip_keys(path)
