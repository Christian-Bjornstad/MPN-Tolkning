from pathlib import Path

import pytest

from mpn_tolkning.io.tsv_reader import ArcherTsvReader, TsvValidationError


def test_reader_retains_all_original_columns():
    variants = ArcherTsvReader().read(Path("tests/fixtures/sample_mpn_variants.tsv"))

    assert [variant.gene for variant in variants] == ["CALR", "JAK2", "MPL"]
    assert variants[0].original["AO"] == 759
    assert variants[0].depth == 1842


def test_reader_supports_documented_semantic_aliases(tmp_path):
    path = tmp_path / "aliases.tsv"
    path.write_text(
        "Sample ID\tSymbol\tHGVS.c\tVAF\nP-1\tjak2\tNM_004972.4:c.1849G>T\t0.186\n",
        encoding="utf-8",
    )

    [variant] = ArcherTsvReader().read(path)

    assert variant.sample == "P-1"
    assert variant.gene == "JAK2"
    assert variant.vaf == 18.6


def test_reader_reports_missing_semantic_fields(tmp_path):
    path = tmp_path / "bad.tsv"
    path.write_text("Sample\tGene\nDIT-1\tCALR\n", encoding="utf-8")

    with pytest.raises(TsvValidationError, match=r"HGVSc.*AF/VAF"):
        ArcherTsvReader().read(path)


def test_reader_rejects_duplicate_headers(tmp_path):
    path = tmp_path / "duplicates.tsv"
    path.write_text(
        "Sample\tGene\tHGVSc\tAF\tAF\nDIT-1\tCALR\tc.1del\t10\t11\n",
        encoding="utf-8",
    )

    with pytest.raises(TsvValidationError, match="Duplicate columns: AF"):
        ArcherTsvReader().read(path)
