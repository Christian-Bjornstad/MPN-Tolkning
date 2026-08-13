from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus, VariantRecord
from mpn_tolkning.providers.base import SearchContext


_AA3_TO_1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}


def _normalize_protein(value: str) -> str:
    clean = str(value or "").strip().replace("(", "").replace(")", "")
    clean = clean.removeprefix("p.").replace("Ter", "*")
    for three, one in _AA3_TO_1.items():
        clean = clean.replace(three, one)
    return clean.replace("fs*", "fs*")


class CalrEtProvider:
    """Exact CALR cDNA lookup against CALR-ETdb.

    Only the cDNA portion is submitted. Patient/sample identifiers and full Archer
    rows never leave the workstation.
    """

    name = "CALR-ETdb"
    SEARCH_URL = "https://www.dsimb.inserm.fr/CALR-ET/php/search_page.php"
    _DOCUMENTED_ALIASES = {
        frozenset(("c.1099_1150del", "c.1092_1143del")),
    }

    def __init__(self, session: requests.Session | None = None, timeout: float = 20.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def _csrf_token(self) -> str:
        response = self.session.get(self.SEARCH_URL, timeout=self.timeout)
        response.raise_for_status()
        field = BeautifulSoup(response.text, "html.parser").select_one(
            'input[name="csrf_token"]'
        )
        return str(field.get("value") or "") if field else ""

    def _post(self, data: dict[str, str]) -> str:
        response = self.session.post(self.SEARCH_URL, data=data, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def search(self, variant: VariantRecord, context: SearchContext) -> EvidenceResult:
        if variant.gene.upper() != "CALR":
            return EvidenceResult(
                self.name,
                EvidenceStatus.INVALID_QUERY,
                "CALR-ETdb accepts CALR variants only.",
                url=self.SEARCH_URL,
            )
        cdna = context.cdna.strip()
        if not cdna.startswith("c."):
            return EvidenceResult(
                self.name,
                EvidenceStatus.INVALID_QUERY,
                "A CALR HGVS cDNA expression is required.",
                url=self.SEARCH_URL,
                expected_identity=cdna,
            )
        try:
            html = self._post(
                {"csrf_token": self._csrf_token(), "nucleotid": cdna, "envoie1": "Submit"}
            )
            return self._parse(html, variant, cdna)
        except requests.RequestException as exc:
            return EvidenceResult(
                self.name,
                EvidenceStatus.ERROR,
                f"CALR-ETdb request failed: {exc}",
                url=self.SEARCH_URL,
                retryable=True,
                expected_identity=cdna,
            )

    def _parse(self, html: str, variant: VariantRecord, submitted_cdna: str) -> EvidenceResult:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("#tabl_result table")
        if table is None:
            return EvidenceResult(
                self.name,
                EvidenceStatus.NOT_FOUND,
                f"No CALR-ETdb entry for {submitted_cdna}.",
                url=self.SEARCH_URL,
                expected_identity=submitted_cdna,
            )

        headers = [cell.get_text(" ", strip=True).lower() for cell in table.select("thead th")]
        row = table.select_one("tbody tr") or table.select_one("tr:nth-of-type(2)")
        cells = row.select("td") if row else []
        if not row or len(cells) < 2:
            return EvidenceResult(
                self.name,
                EvidenceStatus.ERROR,
                "CALR-ETdb returned an unrecognized result table.",
                url=self.SEARCH_URL,
                retryable=True,
                expected_identity=submitted_cdna,
            )
        values = [cell.get_text(" ", strip=True) for cell in cells]
        record = dict(zip(headers, values, strict=False))
        observed = record.get("nucleotide id", "")
        protein = record.get("protein id", "")
        exact = observed == submitted_cdna
        is_alias = frozenset((observed, submitted_cdna)) in self._DOCUMENTED_ALIASES
        protein_matches = bool(variant.hgvsp and protein) and (
            _normalize_protein(variant.hgvsp) == _normalize_protein(protein)
        )
        identity_ok = exact or (is_alias and protein_matches)
        link = row.select_one("a[href]")
        detail_url = urljoin(self.SEARCH_URL, str(link.get("href"))) if link else self.SEARCH_URL
        metadata = {
            "submitted_cdna": submitted_cdna,
            "nucleotide": observed,
            "protein": protein,
            "type": record.get("type", ""),
            "class": record.get("class", ""),
            "mutation": record.get("mutation", ""),
            "cosmic_id": record.get("cosmic", ""),
            "alias_verified": bool(not exact and is_alias and protein_matches),
        }
        if not identity_ok:
            return EvidenceResult(
                self.name,
                EvidenceStatus.IDENTITY_MISMATCH,
                "CALR-ETdb returned a variant that could not be matched exactly.",
                url=detail_url,
                retryable=True,
                expected_identity=submitted_cdna,
                observed_identity=observed,
                metadata=metadata,
            )
        summary_bits = [protein, record.get("type", ""), record.get("class", "")]
        return EvidenceResult(
            self.name,
            EvidenceStatus.FOUND,
            "; ".join(bit for bit in summary_bits if bit),
            url=detail_url,
            expected_identity=submitted_cdna,
            observed_identity=observed,
            metadata=metadata,
        )
