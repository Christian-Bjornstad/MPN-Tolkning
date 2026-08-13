from pathlib import Path

import pytest

from mpn_tolkning.io.tsv_reader import ArcherTsvReader


@pytest.fixture
def sample_variants():
    return ArcherTsvReader().read(Path("tests/fixtures/sample_mpn_variants.tsv"))


@pytest.fixture
def calr_variant(sample_variants):
    return next(variant for variant in sample_variants if variant.gene == "CALR")


@pytest.fixture
def jak2_variant(sample_variants):
    return next(variant for variant in sample_variants if variant.gene == "JAK2")


@pytest.fixture
def fixture_html():
    return lambda name: (Path("tests/fixtures") / name).read_text(encoding="utf-8")
