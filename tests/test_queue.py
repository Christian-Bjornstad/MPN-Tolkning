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


def test_provider_can_decline_variants_without_invalid_retry_results(sample_variants):
    class CalrOnlyProvider(FakeProvider):
        def supports(self, variant):
            return variant.gene == "CALR"

    provider = CalrOnlyProvider("CALR-ETdb")
    results = EvidenceQueue([provider]).run(sample_variants, set(), PauseControl())

    assert len(results) == 1
    assert provider.calls == [("DIT-1001", "CALR", "c.1099_1150del")]


def test_provider_exception_is_audited_and_does_not_abort_remaining_units(sample_variants):
    class BrokenProvider:
        name = "Broken"

        def search(self, variant, context):
            raise RuntimeError("provider exploded")

    healthy = FakeProvider("Healthy")
    saved = []
    queue = EvidenceQueue(
        [BrokenProvider(), healthy],
        audit_callback=lambda key, result: saved.append((key, result)),
    )
    results = queue.run(sample_variants[:2], set(), PauseControl())
    broken = [result for result in results.values() if result.provider == "Broken"]
    assert len(broken) == 2
    assert all(result.status is EvidenceStatus.ERROR and result.retryable for result in broken)
    assert len(healthy.calls) == 2
    assert len(saved) == 4


def test_queue_connects_pause_and_stop_callbacks_to_provider(sample_variants):
    class Provider:
        name = "ClinVar"
        pause_checkpoint = lambda self: None
        stop_requested = lambda self: False

        def search(self, variant, context):
            return EvidenceResult(
                self.name,
                EvidenceStatus.CANCELLED if self.stop_requested() else EvidenceStatus.FOUND,
                "state",
            )

    pause = PauseControl()
    provider = Provider()
    queue = EvidenceQueue([provider])
    pause.request_stop()
    queue.run(sample_variants[:1], set(), pause)
    assert provider.stop_requested()
