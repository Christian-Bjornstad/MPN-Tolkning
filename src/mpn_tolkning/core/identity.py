from __future__ import annotations

from mpn_tolkning.core.models import IdentityConfidence, VariantRecord

__all__ = ["IdentityConfidence", "split_hgvsc", "stable_variant_key", "variant_identity_confidence"]


def split_hgvsc(value: str) -> tuple[str, str]:
    cleaned = str(value or "").strip()
    if ":" not in cleaned:
        return "", cleaned
    transcript, cdna = cleaned.rsplit(":", 1)
    return transcript.strip(), cdna.strip()


def stable_variant_key(variant: VariantRecord) -> str:
    if (
        variant.chromosome
        and variant.position is not None
        and variant.reference
        and variant.alternate
    ):
        chromosome = variant.chromosome.removeprefix("chr").removeprefix("CHR")
        return (
            f"grch37:{chromosome}:{variant.position}:"
            f"{variant.reference.upper()}:{variant.alternate.upper()}"
        )

    transcript, cdna = split_hgvsc(variant.hgvsc)
    if transcript:
        return f"transcript:{transcript}:{cdna}"
    return f"reduced:{variant.gene.upper()}:{cdna}"


def variant_identity_confidence(variant: VariantRecord) -> IdentityConfidence:
    if all((variant.chromosome, variant.position is not None, variant.reference, variant.alternate)):
        return IdentityConfidence.GENOMIC
    transcript, _ = split_hgvsc(variant.hgvsc)
    if transcript:
        return IdentityConfidence.TRANSCRIPT
    return IdentityConfidence.REDUCED
