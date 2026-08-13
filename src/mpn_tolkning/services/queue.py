from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping

from mpn_tolkning.core.identity import split_hgvsc, stable_variant_key
from mpn_tolkning.core.models import EvidenceResult, VariantRecord
from mpn_tolkning.providers.base import Provider, SearchContext


class PauseControl:
    def __init__(self) -> None:
        self._paused = threading.Event()
        self._stopped = threading.Event()

    def request_pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def request_stop(self) -> None:
        self._stopped.set()
        self._paused.clear()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def checkpoint(self) -> bool:
        while self._paused.is_set() and not self._stopped.is_set():
            self._stopped.wait(0.1)
        return not self._stopped.is_set()


class EvidenceQueue:
    def __init__(
        self,
        providers: Iterable[Provider],
        *,
        audit_callback: Callable[[str, EvidenceResult], object] | None = None,
    ) -> None:
        self.providers = list(providers)
        self.audit_callback = audit_callback

    @staticmethod
    def review_key(variant: VariantRecord) -> str:
        return f"{variant.sample}|{stable_variant_key(variant)}"

    @classmethod
    def result_key(cls, variant: VariantRecord, provider: str) -> str:
        return f"{cls.review_key(variant)}|{provider}"

    def run(
        self,
        variants: Iterable[VariantRecord],
        skip_keys: set[str],
        pause: PauseControl,
    ) -> dict[str, EvidenceResult]:
        return self._run(variants, skip_keys, pause, existing={})

    def resume_pending(
        self,
        variants: Iterable[VariantRecord],
        existing_results: Mapping[str, EvidenceResult],
        *,
        skip_keys: set[str] | None = None,
        pause: PauseControl | None = None,
    ) -> dict[str, EvidenceResult]:
        return self._run(
            variants,
            skip_keys or set(),
            pause or PauseControl(),
            existing=dict(existing_results),
        )

    def _run(
        self,
        variants: Iterable[VariantRecord],
        skip_keys: set[str],
        pause: PauseControl,
        existing: dict[str, EvidenceResult],
    ) -> dict[str, EvidenceResult]:
        results = dict(existing)
        grouped: OrderedDict[str, list[VariantRecord]] = OrderedDict()
        for variant in variants:
            grouped.setdefault(variant.sample, []).append(variant)

        for patient_variants in grouped.values():
            for variant in patient_variants:
                if pause.stopped:
                    return results
                if self.review_key(variant) in skip_keys:
                    continue
                context = self._context(variant)
                for provider in self.providers:
                    if not pause.checkpoint():
                        return results
                    key = self.result_key(variant, provider.name)
                    prior = results.get(key)
                    if prior is not None and prior.is_complete:
                        continue
                    result = provider.search(variant, context)
                    results[key] = result
                    if self.audit_callback is not None:
                        self.audit_callback(key, result)
        return results

    @staticmethod
    def _context(variant: VariantRecord) -> SearchContext:
        transcript, cdna = split_hgvsc(variant.hgvsc)
        return SearchContext(
            stable_key=stable_variant_key(variant),
            transcript=transcript,
            cdna=cdna,
        )
