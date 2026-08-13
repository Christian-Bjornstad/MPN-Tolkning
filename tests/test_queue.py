from collections import defaultdict

from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.services.queue import EvidenceQueue, PauseControl


class FakeProvider:
    def __init__(self, name="Fake", status=EvidenceStatus.FOUND):
        self.name = name
        self.status = status
        self.calls = []

    def search(self, variant, context):
        self.calls.append((variant.sample, variant.gene, context.cdna))
        return EvidenceResult(
            self.name,
            self.status,
            f"{self.name} {variant.gene}",
            retryable=not self.status in {EvidenceStatus.FOUND, EvidenceStatus.NOT_FOUND},
        )


def test_queue_runs_patient_variant_provider_order_and_saves_each_result(
    sample_variants,
):
    first = FakeProvider("First")
    second = FakeProvider("Second")
    saved = []
    queue = EvidenceQueue(
        [first, second],
        audit_callback=lambda key, result: saved.append((key, result.provider)),
    )

    results = queue.run(sample_variants, skip_keys=set(), pause=PauseControl())

    assert len(results) == len(sample_variants) * 2
    by_variant = defaultdict(list)
    for key, provider in saved:
        by_variant["|".join(key.split("|")[:-1])].append(provider)
    assert all(order == ["First", "Second"] for order in by_variant.values())


def test_queue_honors_review_skip_keys(sample_variants):
    provider = FakeProvider()
    first = sample_variants[0]
    skip = {f"{first.sample}|grch37:19:13054615:AAG:A"}

    results = EvidenceQueue([provider]).run(
        sample_variants,
        skip_keys=skip,
        pause=PauseControl(),
    )

    assert len(results) == len(sample_variants) - 1
    assert all(call[0] != first.sample for call in provider.calls)


def test_resume_keeps_complete_results_and_retries_errors(sample_variants):
    provider = FakeProvider("ClinVar", EvidenceStatus.FOUND)
    queue = EvidenceQueue([provider])
    complete_key = queue.result_key(sample_variants[0], "ClinVar")
    error_key = queue.result_key(sample_variants[1], "ClinVar")
    existing = {
        complete_key: EvidenceResult("ClinVar", EvidenceStatus.FOUND, "old match"),
        error_key: EvidenceResult(
            "ClinVar",
            EvidenceStatus.ERROR,
            "timeout",
            retryable=True,
        ),
    }

    merged = queue.resume_pending(sample_variants[:2], existing)

    assert merged[complete_key].summary == "old match"
    assert merged[error_key].summary == "ClinVar JAK2"
    assert provider.calls == [("DIT-1002", "JAK2", "c.1849G>T")]


def test_stop_requested_before_run_prevents_provider_calls(sample_variants):
    provider = FakeProvider()
    pause = PauseControl()
    pause.request_stop()

    results = EvidenceQueue([provider]).run(sample_variants, set(), pause)

    assert results == {}
    assert provider.calls == []
