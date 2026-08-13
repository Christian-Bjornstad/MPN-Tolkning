from pathlib import Path

from mpn_tolkning.core.models import (
    EvidenceResult,
    EvidenceStatus,
    IdentityCheck,
    ProcessingResult,
    VariantRecord,
)


def test_variant_record_preserves_original_fields_and_exposes_vaf():
    row = {
        "Sample": "DIT-1001",
        "Gene": "CALR",
        "HGVSc": "NM_004343.4:c.1099_1150del",
        "AF": "41.2",
    }

    variant = VariantRecord(
        sample="DIT-1001",
        gene="CALR",
        hgvsc=row["HGVSc"],
        vaf=41.2,
        original=row,
    )

    assert variant.original == row
    assert variant.vaf == 41.2


def test_evidence_result_marks_retryable_failure_explicitly():
    result = EvidenceResult(
        provider="CALR-ETdb",
        status=EvidenceStatus.IDENTITY_MISMATCH,
        summary="Returned another allele",
        retryable=True,
        screenshots=(Path("capture.png"),),
    )

    assert result.is_complete is False
    assert result.retryable is True


def test_identity_and_processing_contracts_are_immutable():
    variant = VariantRecord("DIT-1001", "CALR", "NM_004343.4:c.1099_1150del", 41.2)
    identity = IdentityCheck("expected", "observed", matched=False, reason="mismatch")
    result = ProcessingResult((variant,), ("review",))

    assert identity.reason == "mismatch"
    assert result.variants == (variant,)

