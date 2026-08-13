import json
from pathlib import Path

from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.services.audit import AuditStore


def test_audit_filename_contains_hash_not_sample_identifier(tmp_path):
    store = AuditStore(tmp_path)

    path = store.save(
        "DIT-1001|grch37:9:5073770:G:T|ClinVar",
        EvidenceResult("ClinVar", EvidenceStatus.FOUND, "match"),
    )

    assert "DIT-1001" not in path.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["result"]["provider"] == "ClinVar"
    assert payload["result"]["status"] == "found"


def test_audit_round_trip_restores_screenshot_paths(tmp_path):
    store = AuditStore(tmp_path)
    result = EvidenceResult(
        "CALR-ETdb",
        EvidenceStatus.FOUND,
        "Type 1-like",
        screenshots=(Path("capture.png"),),
        metadata={"class": "Class A"},
    )
    store.save("patient|variant|CALR-ETdb", result)

    loaded = AuditStore(tmp_path).load_all()

    restored = loaded["patient|variant|CALR-ETdb"]
    assert restored.screenshots == (Path("capture.png"),)
    assert restored.metadata["class"] == "Class A"
