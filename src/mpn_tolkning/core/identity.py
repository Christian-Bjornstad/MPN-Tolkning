from __future__ import annotations

from mpn_tolkning.core.models import VariantRecord


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
