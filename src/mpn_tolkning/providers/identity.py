from __future__ import annotations

import re
from urllib.parse import quote

import requests

from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus, VariantRecord
from mpn_tolkning.providers.base import SearchContext


_AA3_TO_1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}


def _short_protein(value: str) -> str:
    clean = str(value or "").strip().replace("(", "").replace(")", "").removeprefix("p.")
    for three, one in _AA3_TO_1.items():
        clean = clean.replace(three, one)
    return clean.replace("Ter", "*")


class ClinGenAlleleProvider:
    name = "ClinGen Allele Registry"
    API_URL = "https://reg.clinicalgenome.org/allele"

    def __init__(self, session: requests.Session | None = None, timeout: float = 20.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    def _get_json(self, hgvs: str) -> dict:
        response = self.session.get(
            self.API_URL,
            params={"hgvs": hgvs},
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return {"_status": 404}
        if response.status_code == 400:
            return {"_status": 400, **response.json()}
        response.raise_for_status()
        return response.json()

    def search(self, variant: VariantRecord, context: SearchContext) -> EvidenceResult:
        query = variant.hgvsc.strip()
        landing = (
            "https://reg.clinicalgenome.org/redmine/projects/registry/"
            f"genboree_registry/landing?search={quote(query)}"
        )
        if not query:
            return EvidenceResult(self.name, EvidenceStatus.INVALID_QUERY, "HGVS cDNA is required.", url=landing)
        try:
            data = self._get_json(query)
        except (requests.RequestException, ValueError) as exc:
            return EvidenceResult(self.name, EvidenceStatus.ERROR, f"ClinGen request failed: {exc}", url=landing, retryable=True)
        if data.get("_status") == 404:
            return EvidenceResult(self.name, EvidenceStatus.NOT_FOUND, f"No CAid for {query}.", url=landing, expected_identity=query)
        if data.get("_status") == 400:
            return EvidenceResult(self.name, EvidenceStatus.INVALID_QUERY, str(data.get("message") or "ClinGen rejected the HGVS query."), url=landing, expected_identity=query)
        caid = str(data.get("@id") or "").rstrip("/").rsplit("/", 1)[-1]
        if not caid.startswith("CA"):
            return EvidenceResult(self.name, EvidenceStatus.ERROR, "ClinGen response did not contain a CAid.", url=landing, retryable=True, expected_identity=query, metadata={"response": data})
        url = (
            "https://reg.clinicalgenome.org/redmine/projects/registry/"
            f"genboree_registry/by_caid?caid={quote(caid)}"
        )
        return EvidenceResult(self.name, EvidenceStatus.FOUND, f"Normalized allele {caid}", url=url, expected_identity=query, observed_identity=query, metadata={"caid": caid})


class _OptionalExactProvider:
    name = ""
    search_url = ""

    def __init__(self, enabled: bool = False, session: requests.Session | None = None, timeout: float = 20.0):
        self.enabled = enabled
        self.session = session or requests.Session()
        self.timeout = timeout

    def search(self, variant: VariantRecord, context: SearchContext) -> EvidenceResult:
        expected_name = _short_protein(variant.hgvsp)
        expected = f"{variant.gene.upper()} {expected_name}".strip()
        url = self._manual_url(variant)
        if not self.enabled:
            return EvidenceResult(self.name, EvidenceStatus.CANCELLED, f"{self.name} is disabled by default.", url=url, expected_identity=expected)
        if not variant.gene or not expected_name:
            return EvidenceResult(self.name, EvidenceStatus.INVALID_QUERY, "Gene and protein change are required for exact matching.", url=url, expected_identity=expected)
        try:
            records = self._search_records(variant)
        except (requests.RequestException, ValueError, KeyError) as exc:
            return EvidenceResult(self.name, EvidenceStatus.ERROR, f"{self.name} request failed: {exc}", url=url, retryable=True, expected_identity=expected)
        for record in records:
            gene = str(record.get("gene") or record.get("featureName") or "").upper()
            name = _short_protein(str(record.get("name") or record.get("variantName") or ""))
            if gene == variant.gene.upper() and name.upper() == expected_name.upper():
                observed = f"{gene} {name}"
                return EvidenceResult(self.name, EvidenceStatus.FOUND, f"Exact {self.name} match: {observed}", url=str(record.get("url") or record.get("link") or url), expected_identity=expected, observed_identity=observed, metadata={"record": record})
        return EvidenceResult(self.name, EvidenceStatus.NOT_FOUND, f"No exact {self.name} match for {expected}.", url=url, expected_identity=expected, metadata={"candidate_count": len(records)})

    def _manual_url(self, variant: VariantRecord) -> str:
        return self.search_url.format(query=quote(f"{variant.gene} {_short_protein(variant.hgvsp)}"))


class CivicProvider(_OptionalExactProvider):
    name = "CIViC"
    search_url = "https://civicdb.org/search?query={query}"
    API_URL = "https://civicdb.org/api/graphql"

    def _search_records(self, variant: VariantRecord) -> list[dict]:
        query = """
        query Browse($featureName: String!, $variantName: String!, $first: Int) {
          browseMolecularProfiles(featureName: $featureName, variantName: $variantName, first: $first) {
            nodes { id name link variants { name } }
          }
        }
        """
        response = self.session.post(
            self.API_URL,
            json={"query": query, "variables": {"featureName": variant.gene, "variantName": _short_protein(variant.hgvsp), "first": 5}},
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise ValueError(str(payload["errors"][0]))
        nodes = (((payload.get("data") or {}).get("browseMolecularProfiles") or {}).get("nodes") or [])
        records = []
        for node in nodes:
            variants = node.get("variants") or []
            for item in variants:
                records.append({"gene": variant.gene, "name": item.get("name"), "id": node.get("id"), "url": f"https://civicdb.org{node.get('link', '')}"})
        return records


class MetaKbProvider(_OptionalExactProvider):
    name = "MetaKB"
    search_url = "https://search.cancervariants.org/?q={query}"
    API_URL = "https://search.cancervariants.org/api/v2/search"

    def _search_records(self, variant: VariantRecord) -> list[dict]:
        response = self.session.get(
            self.API_URL,
            params={"q": f"{variant.gene} {_short_protein(variant.hgvsp)}"},
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        records = payload.get("data") or payload.get("results") or []
        return records if isinstance(records, list) else []
