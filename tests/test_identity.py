from mpn_tolkning.core.identity import (
    IdentityConfidence,
    split_hgvsc,
    stable_variant_key,
    variant_identity_confidence,
)
from mpn_tolkning.core.models import VariantRecord


def test_split_hgvsc_returns_transcript_and_cdna_only_query():
    assert split_hgvsc("NM_004343.4:c.1099_1150del") == (
        "NM_004343.4",
        "c.1099_1150del",
    )


def test_split_hgvsc_preserves_cdna_without_transcript():
    assert split_hgvsc(" c.1849G>T ") == ("", "c.1849G>T")


def test_stable_key_prefers_grch37_allele():
    variant = VariantRecord(
        "DIT-1",
        "JAK2",
        "NM_004972.4:c.1849G>T",
        18.6,
        chromosome="chr9",
        position=5073770,
        reference="g",
        alternate="t",
    )

    assert stable_variant_key(variant) == "grch37:9:5073770:G:T"


def test_stable_key_falls_back_to_transcript_identity():
    variant = VariantRecord("DIT-1", "CALR", "NM_004343.4:c.1099_1150del", 41.2)
    assert stable_variant_key(variant) == "transcript:NM_004343.4:c.1099_1150del"


def test_identity_confidence_marks_cdna_without_transcript_as_reduced():
    variant = VariantRecord("DIT-1", "JAK2", "c.1849G>T", 18.6)

    assert stable_variant_key(variant) == "reduced:JAK2:c.1849G>T"
    assert variant_identity_confidence(variant) is IdentityConfidence.REDUCED
