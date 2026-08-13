from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mpn_tolkning.core.models import EvidenceResult, VariantRecord


@dataclass(frozen=True)
class SearchContext:
    stable_key: str
    transcript: str
    cdna: str
    build: str = "GRCh37"


class Provider(Protocol):
    name: str

    def search(
        self,
        variant: VariantRecord,
        context: SearchContext,
    ) -> EvidenceResult: ...
