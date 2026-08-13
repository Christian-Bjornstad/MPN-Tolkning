from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from mpn_tolkning.core.models import VariantRecord


class TsvValidationError(ValueError):
    """The input file cannot be mapped to the required Archer semantics."""


class ArcherTsvReader:
    aliases = {
        "sample": ("Sample", "Sample ID", "DIT"),
        "gene": ("Gene", "Symbol", "GeneName"),
        "hgvsc": ("HGVSc", "HGVS.c", "Coding Change"),
        "vaf": ("AF", "VAF", "Allele Frequency"),
        "hgvsp": ("HGVSp", "HGVS.p", "Protein Change"),
        "chromosome": ("Chromosome", "Chr"),
        "position": ("Position", "Pos"),
        "reference": ("Reference", "Ref"),
        "alternate": ("Alternate", "Alt"),
        "depth": ("DP", "Depth"),
        "cosmic_id": ("COSMICID", "COSMIC ID", "COSV"),
    }
    required = ("sample", "gene", "hgvsc", "vaf")
    required_labels = {
        "sample": "Sample",
        "gene": "Gene",
        "hgvsc": "HGVSc",
        "vaf": "AF/VAF",
    }

    def read(self, path: Path) -> list[VariantRecord]:
        path = Path(path)
        headers = self._read_headers(path)
        duplicates = sorted({header for header in headers if headers.count(header) > 1})
        if duplicates:
            raise TsvValidationError("Duplicate columns: " + ", ".join(duplicates))

        resolved = {
            semantic: self._resolve_header(headers, semantic)
            for semantic in self.aliases
        }
        missing = [
            self.required_labels[semantic]
            for semantic in self.required
            if resolved[semantic] is None
        ]
        if missing:
            raise TsvValidationError("Missing required columns: " + ", ".join(missing))

        frame = pd.read_csv(path, sep="\t")
        variants: list[VariantRecord] = []
        for raw in frame.to_dict(orient="records"):
            original = {key: self._native(value) for key, value in raw.items()}
            variants.append(
                VariantRecord(
                    sample=self._text(raw.get(resolved["sample"])),
                    gene=self._text(raw.get(resolved["gene"])).upper(),
                    hgvsc=self._text(raw.get(resolved["hgvsc"])),
                    vaf=self._vaf(raw.get(resolved["vaf"])),
                    hgvsp=self._text(raw.get(resolved["hgvsp"])),
                    chromosome=self._text(raw.get(resolved["chromosome"])),
                    position=self._integer(raw.get(resolved["position"])),
                    reference=self._text(raw.get(resolved["reference"])).upper(),
                    alternate=self._text(raw.get(resolved["alternate"])).upper(),
                    depth=self._integer(raw.get(resolved["depth"])),
                    cosmic_id=self._text(raw.get(resolved["cosmic_id"])),
                    original=original,
                )
            )
        return variants

    @staticmethod
    def _read_headers(path: Path) -> list[str]:
        with path.open("r", encoding="utf-8-sig") as stream:
            first_line = stream.readline().rstrip("\r\n")
        if not first_line:
            raise TsvValidationError("The TSV file is empty.")
        return first_line.split("\t")

    def _resolve_header(self, headers: list[str], semantic: str) -> str | None:
        return next((alias for alias in self.aliases[semantic] if alias in headers), None)

    @classmethod
    def _text(cls, value: Any) -> str:
        if cls._missing(value):
            return ""
        return str(value).strip()

    @classmethod
    def _integer(cls, value: Any) -> int | None:
        if cls._missing(value):
            return None
        return int(float(value))

    @classmethod
    def _vaf(cls, value: Any) -> float | None:
        if cls._missing(value):
            return None
        number = float(value)
        return number * 100 if 0 <= number <= 1 else number

    @classmethod
    def _native(cls, value: Any) -> Any:
        if cls._missing(value):
            return ""
        return value.item() if hasattr(value, "item") else value

    @staticmethod
    def _missing(value: Any) -> bool:
        return value is None or (
            isinstance(value, float) and math.isnan(value)
        )
