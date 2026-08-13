from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from mpn_tolkning.core.identity import split_hgvsc
from mpn_tolkning.core.models import VariantRecord


@dataclass(frozen=True)
class ArtifactRule:
    gene: str
    cdna: str
    max_vaf: float | None
    reason: str


def default_artifact_rules() -> list[ArtifactRule]:
    reason = "Intronic JAK2 homopolymer observation; review before reporting."
    return [
        ArtifactRule("JAK2", "c.3291+16dup", None, reason),
        ArtifactRule("JAK2", "c.3291+16del", None, reason),
    ]


def evaluate_artifact(
    variant: VariantRecord,
    rules: Iterable[ArtifactRule],
) -> str:
    _, cdna = split_hgvsc(variant.hgvsc)
    for rule in rules:
        if variant.gene.upper() != rule.gene.upper() or cdna != rule.cdna:
            continue
        if (
            rule.max_vaf is not None
            and variant.vaf is not None
            and variant.vaf > rule.max_vaf
        ):
            continue
        return rule.reason
    return ""
