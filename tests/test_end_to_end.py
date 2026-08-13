from pathlib import Path

from mpn_tolkning.core.context import classify_driver_context
from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.io.tsv_reader import ArcherTsvReader
from mpn_tolkning.reports.patient import PatientReportCoordinator
from mpn_tolkning.reports.review import write_review_workbook
from mpn_tolkning.services.audit import AuditStore
from mpn_tolkning.services.queue import EvidenceQueue, PauseControl


class FakeProvider:
    def __init__(self, name):
        self.name = name

    def search(self, variant, context):
        return EvidenceResult(
            self.name,
            EvidenceStatus.FOUND,
            f"{self.name} synthetic match",
            expected_identity=variant.hgvsc,
            observed_identity=variant.hgvsc,
        )


def test_synthetic_run_imports_reviews_searches_resumes_and_reports(tmp_path):
    variants = ArcherTsvReader().read(Path("tests/fixtures/sample_mpn_variants.tsv"))
    contexts = {stable_variant_key(variant): classify_driver_context(variant) for variant in variants}
    review = write_review_workbook(tmp_path / "review.xlsx", variants, contexts, {})
    fake_provider_set = [
        FakeProvider(name)
        for name in ("CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")
    ]
    audit = AuditStore(tmp_path / "evidence")
    queue = EvidenceQueue(fake_provider_set, audit_callback=audit.save)
    first = queue.run(variants, skip_keys=set(), pause=PauseControl())
    resumed = queue.resume_pending(variants, first)
    reports = PatientReportCoordinator(tmp_path).write_all(variants, resumed)

    assert review.exists()
    assert len(first) == 18
    assert resumed == first
    assert audit.load_all().keys() == first.keys()
    assert len(reports) == 3
    assert all(path.exists() for path in reports.values())
