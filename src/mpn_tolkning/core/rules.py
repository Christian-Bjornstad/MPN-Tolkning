from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

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


def configured_artifact_rules(values: Iterable[dict[str, Any]]) -> list[ArtifactRule]:
    """Convert persisted local rules, falling back safely when none are valid."""
    configured: list[ArtifactRule] = []
    try:
        for value in values:
            gene = str(value["gene"]).strip()
            cdna = str(value["cdna"]).strip()
            reason = str(value["reason"]).strip()
            raw_max_vaf = value.get("max_vaf")
            max_vaf = None if raw_max_vaf in {None, ""} else float(raw_max_vaf)
            if not gene or not cdna or not reason or (max_vaf is not None and not 0 <= max_vaf <= 100):
                raise ValueError("invalid artifact rule")
            configured.append(ArtifactRule(gene, cdna, max_vaf, reason))
    except (KeyError, TypeError, ValueError):
        return default_artifact_rules()
    return configured or default_artifact_rules()


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
