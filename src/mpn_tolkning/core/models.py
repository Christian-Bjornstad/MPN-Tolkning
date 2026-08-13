from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class EvidenceStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    INVALID_QUERY = "invalid_query"
    IDENTITY_MISMATCH = "identity_mismatch"
    INCOMPLETE_CAPTURE = "incomplete_capture"
    ERROR = "error"
    CANCELLED = "cancelled"


class IdentityConfidence(StrEnum):
    GENOMIC = "genomic GRCh37 allele"
    TRANSCRIPT = "transcript-qualified HGVS"
    REDUCED = "reduced gene/cDNA identity"


@dataclass(frozen=True)
class VariantRecord:
    sample: str
    gene: str
    hgvsc: str
    vaf: float | None
    hgvsp: str = ""
    chromosome: str = ""
    position: int | None = None
    reference: str = ""
    alternate: str = ""
    depth: int | None = None
    cosmic_id: str = ""
    original: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriverContext:
    label: str = ""
    detail: str = ""
    needs_review: bool = False


@dataclass(frozen=True)
class IdentityCheck:
    expected: str
    observed: str
    matched: bool
    reason: str = ""


@dataclass(frozen=True)
class EvidenceResult:
    provider: str
    status: EvidenceStatus
    summary: str
    url: str = ""
    retryable: bool = False
    expected_identity: str = ""
    observed_identity: str = ""
    screenshots: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.status in {EvidenceStatus.FOUND, EvidenceStatus.NOT_FOUND}


@dataclass(frozen=True)
class ProcessingResult:
    variants: tuple[VariantRecord, ...]
    warnings: tuple[str, ...] = ()
