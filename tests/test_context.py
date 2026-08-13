from mpn_tolkning.core.context import classify_driver_context
from mpn_tolkning.core.models import VariantRecord


def test_jak2_v617f_is_labeled_as_driver_context():
    context = classify_driver_context(
        VariantRecord(
            "DIT-1",
            "JAK2",
            "NM_004972.4:c.1849G>T",
            18.6,
            hgvsp="p.Val617Phe",
        )
    )

    assert (context.label, context.needs_review) == ("JAK2 V617F driver", False)


def test_jak2_exon12_variant_is_flagged_for_review():
    context = classify_driver_context(
        VariantRecord(
            "DIT-1",
            "JAK2",
            "NM_004972.4:c.1624_1629del",
            12.0,
            hgvsp="p.Asn542_Glu543del",
        )
    )

    assert context.label == "JAK2 exon 12 driver candidate"
    assert context.needs_review is True


def test_calr_exon9_frameshift_is_candidate_until_database_verification():
    context = classify_driver_context(
        VariantRecord(
            "DIT-1",
            "CALR",
            "NM_004343.4:c.1099_1150del",
            41.2,
            hgvsp="p.Lys367ArgfsTer51",
        )
    )

    assert context.label == "CALR exon 9 frameshift candidate"
    assert context.needs_review is True


def test_mpl_w515_variant_is_labeled_as_hotspot():
    context = classify_driver_context(
        VariantRecord(
            "DIT-1",
            "MPL",
            "NM_005373.2:c.1544G>T",
            7.1,
            hgvsp="p.Trp515Leu",
        )
    )

    assert context.label == "MPL W515 hotspot"
    assert context.needs_review is False


def test_non_triad_gene_remains_visible_without_driver_label():
    context = classify_driver_context(
        VariantRecord("DIT-1", "TET2", "NM_001127208.2:c.3954+1G>A", 12.0)
    )
    assert context.label == ""
