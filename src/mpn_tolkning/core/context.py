from __future__ import annotations

from mpn_tolkning.core.identity import split_hgvsc
from mpn_tolkning.core.models import DriverContext, VariantRecord


def classify_driver_context(variant: VariantRecord) -> DriverContext:
    gene = variant.gene.upper()
    _, cdna = split_hgvsc(variant.hgvsc)
    protein = variant.hgvsp.replace("Ter", "*")

    if gene == "JAK2":
        if cdna == "c.1849G>T" or protein in {"p.Val617Phe", "p.V617F"}:
            return DriverContext(
                "JAK2 V617F driver",
                "Established MPN driver context; qualified review remains required.",
            )
        if cdna.startswith("c.1624_") or "Asn542_Glu543" in protein:
            return DriverContext(
                "JAK2 exon 12 driver candidate",
                "Candidate exon 12 driver; verify exact allele and disease context.",
                needs_review=True,
            )

    if gene == "CALR" and _is_calr_exon9_frameshift(cdna, protein):
        return DriverContext(
            "CALR exon 9 frameshift candidate",
            "CALR-ETdb subtype and identity verification are pending.",
            needs_review=True,
        )

    if gene == "MPL" and ("Trp515" in protein or "W515" in protein):
        return DriverContext(
            "MPL W515 hotspot",
            "Established MPN hotspot context; qualified review remains required.",
        )

    return DriverContext()


def _is_calr_exon9_frameshift(cdna: str, protein: str) -> bool:
    frameshift = "fs" in protein
    exon9_region = any(str(position) in cdna for position in range(1090, 1235))
    indel = "del" in cdna or "ins" in cdna or "dup" in cdna
    return frameshift and exon9_region and indel
