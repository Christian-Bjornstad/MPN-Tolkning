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


def test_reader_rejects_oversized_input_before_pandas_parses_it(tmp_path, monkeypatch):
    path = tmp_path / "large.tsv"
    path.write_text("Sample\tGene\tHGVSc\tAF\n", encoding="utf-8")
    reader = ArcherTsvReader()
    monkeypatch.setattr(reader, "_file_size", lambda candidate: 51 * 1024 * 1024)
    with pytest.raises(TsvValidationError, match="50 MB"):
        reader.read(path)


def test_reader_rejects_blank_required_values_with_row_number(tmp_path):
    path = tmp_path / "blank.tsv"
    path.write_text("Sample\tGene\tHGVSc\tAF\nSYN-1\t\tNM_004972.4:c.1849G>T\t10\n", encoding="utf-8")
    with pytest.raises(TsvValidationError, match="row 2.*Gene"):
        ArcherTsvReader().read(path)


def test_reader_wraps_invalid_numeric_values_as_validation_errors(tmp_path):
    path = tmp_path / "bad-number.tsv"
    path.write_text("Sample\tGene\tHGVSc\tAF\nSYN-1\tJAK2\tNM_004972.4:c.1849G>T\tnot-a-number\n", encoding="utf-8")
    with pytest.raises(TsvValidationError, match="row 2.*AF/VAF"):
        ArcherTsvReader().read(path)


@pytest.mark.parametrize("vaf", ["-1", "101", "inf"])
def test_reader_rejects_out_of_range_or_non_finite_vaf(tmp_path, vaf):
    path = tmp_path / "bad-vaf.tsv"
    path.write_text(f"Sample\tGene\tHGVSc\tAF\nSYN-1\tJAK2\tNM_004972.4:c.1849G>T\t{vaf}\n", encoding="utf-8")
    with pytest.raises(TsvValidationError, match="row 2.*VAF"):
        ArcherTsvReader().read(path)


def test_reader_rejects_non_positive_genomic_position(tmp_path):
    path = tmp_path / "bad-position.tsv"
    path.write_text("Sample\tGene\tHGVSc\tAF\tChromosome\tPosition\tReference\tAlternate\nSYN-1\tJAK2\tNM_004972.4:c.1849G>T\t10\t9\t0\tG\tT\n", encoding="utf-8")
    with pytest.raises(TsvValidationError, match="row 2.*position"):
        ArcherTsvReader().read(path)


def test_reader_rejects_duplicate_headers(tmp_path):
    path = tmp_path / "duplicates.tsv"
    path.write_text(
        "Sample\tGene\tHGVSc\tAF\tAF\nDIT-1\tCALR\tc.1del\t10\t11\n",
        encoding="utf-8",
    )

    with pytest.raises(TsvValidationError, match="Duplicate columns: AF"):
        ArcherTsvReader().read(path)


def test_reader_rejects_duplicate_patient_variant_identity(tmp_path):
    path = tmp_path / "duplicate-variant.tsv"
    path.write_text(
        "Sample\tGene\tHGVSc\tAF\n"
        "SYN-1\tJAK2\tNM_004972.4:c.1849G>T\t10\n"
        "SYN-1\tJAK2\tNM_004972.4:c.1849G>T\t12\n",
        encoding="utf-8",
    )

    with pytest.raises(TsvValidationError, match="Duplicate patient/variant identity.*rows 2 and 3"):
        ArcherTsvReader().read(path)


@pytest.mark.parametrize("column", ["Position", "DP"])
def test_reader_rejects_fractional_integer_fields(tmp_path, column):
    headers = "Sample\tGene\tHGVSc\tAF\tChromosome\tPosition\tReference\tAlternate\tDP"
    values = ["SYN", "JAK2", "NM_004972.4:c.1849G>T", "10", "9", "5073770", "G", "T", "100"]
    values[headers.split("\t").index(column)] = "123.5"
    path = tmp_path / "fraction.tsv"
    path.write_text(headers + "\n" + "\t".join(values) + "\n", encoding="utf-8")
    with pytest.raises(TsvValidationError, match="row 2"):
        ArcherTsvReader().read(path)
