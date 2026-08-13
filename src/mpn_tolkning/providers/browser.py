from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus, VariantRecord
from mpn_tolkning.providers.base import SearchContext
from mpn_tolkning.services.capture import screenshot_path, validate_capture
from mpn_tolkning.services.edge_cdp import EdgeCdpError, EdgeCdpSession, EdgeCdpTimeout


REQUIRED_BROWSER_PROVIDERS = ("MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")

_AA3_TO_1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}


def _protein_short(value: str) -> str:
    clean = str(value or "").strip().replace("(", "").replace(")", "").removeprefix("p.")
    for three, one in _AA3_TO_1.items():
        clean = clean.replace(three, one)
    return clean.replace("Ter", "*")


def edge_browser_factory(profile_root: Path) -> Callable[[], EdgeCdpSession]:
    return lambda: EdgeCdpSession(profile_root, background=True)


class BrowserProvider:
    name = ""

    def __init__(
        self,
        browser_factory: Callable[[], object],
        capture_root: Path,
        *,
        pause_checkpoint: Callable[[], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ):
        self.browser_factory = browser_factory
        self.capture_root = Path(capture_root)
        self.pause_checkpoint = pause_checkpoint or (lambda: None)
        self.stop_requested = stop_requested or (lambda: False)

    def search(self, variant: VariantRecord, context: SearchContext) -> EvidenceResult:
        self.pause_checkpoint()
        if self.stop_requested():
            return EvidenceResult(self.name, EvidenceStatus.CANCELLED, "Evidence collection stopped by the user.")
        problem = self._validate_query(variant, context)
        if problem:
            return EvidenceResult(self.name, EvidenceStatus.INVALID_QUERY, problem)

        browser = self.browser_factory()
        url = self._url(variant, context)
        expected = self._expected_identity(variant, context)
        try:
            browser.start(self.name)
            browser.navigate(url)
            observed = browser.evaluate(self._identity_expression(variant, context))
            if not isinstance(observed, dict) or not observed:
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.NOT_FOUND,
                    f"No {self.name} result was visible for the requested variant.",
                    url=url,
                    expected_identity=expected,
                )
            observed_label = self._observed_identity(observed)
            if not self._matches(observed, variant, context):
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.IDENTITY_MISMATCH,
                    f"{self.name} result identity did not match the imported variant.",
                    url=url,
                    retryable=True,
                    expected_identity=expected,
                    observed_identity=observed_label,
                    metadata={"observed": observed},
                )
            target = screenshot_path(self.capture_root, context.stable_key, self.name, 1)
            browser.screenshot(target)
            capture = validate_capture(target)
            if not capture.valid:
                target.unlink(missing_ok=True)
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.INCOMPLETE_CAPTURE,
                    f"Verified {self.name} page had an invalid screenshot: {capture.reason}.",
                    url=url,
                    retryable=True,
                    expected_identity=expected,
                    observed_identity=observed_label,
                    metadata={"capture_reason": capture.reason, **self._metadata(variant, context)},
                )
            return EvidenceResult(
                self.name,
                EvidenceStatus.FOUND,
                f"Verified {self.name} evidence for {observed_label}.",
                url=url,
                expected_identity=expected,
                observed_identity=observed_label,
                screenshots=(target,),
                metadata={"observed": observed, **self._metadata(variant, context)},
            )
        except (EdgeCdpError, EdgeCdpTimeout, OSError, ValueError) as exc:
            return EvidenceResult(
                self.name,
                EvidenceStatus.ERROR,
                f"{self.name} browser lookup failed: {exc}",
                url=url,
                retryable=True,
                expected_identity=expected,
            )
        finally:
            browser.close()

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        return "" if variant.gene and context.cdna else "Gene and HGVS cDNA are required."

    def _metadata(self, variant: VariantRecord, context: SearchContext) -> dict:
        return {}

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        raise NotImplementedError

    def _identity_expression(self, variant: VariantRecord, context: SearchContext) -> str:
        raise NotImplementedError

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        raise NotImplementedError

    def _observed_identity(self, observed: dict) -> str:
        return " ".join(str(value) for value in observed.values() if value not in (None, ""))

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        raise NotImplementedError


def _body_probe(fields: dict[str, str]) -> str:
    """Return fields only when every exact token occurs in the rendered page text."""
    payload = json.dumps(fields)
    return (
        "(() => { const text=(document.body?.innerText||'').replace(/\\s+/g,' ').toUpperCase();"
        f" const expected={payload};"
        " return Object.values(expected).every(v => text.includes(String(v).toUpperCase())) ? expected : {}; })()"
    )


class MtbpProvider(BrowserProvider):
    name = "MTBP"

    def _pseudonym(self, context: SearchContext) -> str:
        return "MPN-" + hashlib.sha256(context.stable_key.encode("utf-8")).hexdigest()[:10].upper()

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"https://mtbp.org/analyse/?case={self._pseudonym(context)}&variant={quote(variant.hgvsc)}"

    def _identity_expression(self, variant: VariantRecord, context: SearchContext) -> str:
        return _body_probe({"gene": variant.gene, "hgvsc": variant.hgvsc})

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"{variant.gene} {variant.hgvsc}"

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        return str(observed.get("gene", "")).upper() == variant.gene.upper() and str(observed.get("hgvsc", "")) == variant.hgvsc

    def _metadata(self, variant: VariantRecord, context: SearchContext) -> dict:
        return {"pseudonym": self._pseudonym(context)}


class FranklinProvider(BrowserProvider):
    name = "Franklin"

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        query = quote(f"{context.transcript}:{context.cdna}")
        return f"https://franklin.genoox.com/clinical-db/variant/snp/chr?query={query}&assembly=hg19&mode=somatic"

    def _identity_expression(self, variant: VariantRecord, context: SearchContext) -> str:
        return _body_probe({"transcript": context.transcript, "cdna": context.cdna, "assembly": "hg19", "mode": "somatic"})

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"somatic hg19 {context.transcript}:{context.cdna}"

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        return (
            str(observed.get("transcript", "")) == context.transcript
            and str(observed.get("cdna", "")) == context.cdna
            and str(observed.get("assembly", "")).lower() in {"hg19", "grch37"}
            and str(observed.get("mode", "")).lower() == "somatic"
        )


class ClinVarProvider(BrowserProvider):
    name = "ClinVar"

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        if not all((variant.chromosome, variant.position, variant.reference, variant.alternate)):
            return "ClinVar requires a complete GRCh37 chromosome/position/ref/alt identity."
        return ""

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        query = quote(f"{variant.chromosome}[chr] AND {variant.position}[chrpos37]")
        return f"https://www.ncbi.nlm.nih.gov/clinvar/?term={query}"

    def _identity_expression(self, variant: VariantRecord, context: SearchContext) -> str:
        return _body_probe({"build": "GRCh37", "chromosome": variant.chromosome, "position": str(variant.position), "reference": variant.reference, "alternate": variant.alternate})

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"GRCh37 {variant.chromosome}:{variant.position} {variant.reference}>{variant.alternate}"

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        return (
            str(observed.get("build", "")).lower() in {"grch37", "hg19"}
            and str(observed.get("chromosome", "")).removeprefix("chr") == variant.chromosome.removeprefix("chr")
            and str(observed.get("position")) == str(variant.position)
            and str(observed.get("reference", "")).upper() == variant.reference.upper()
            and str(observed.get("alternate", "")).upper() == variant.alternate.upper()
        )


class OncoKbProvider(BrowserProvider):
    name = "OncoKB"

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"https://www.oncokb.org/gene/{quote(variant.gene)}/{quote(_protein_short(variant.hgvsp))}"

    def _identity_expression(self, variant: VariantRecord, context: SearchContext) -> str:
        fields = {"gene": variant.gene, "alteration": _protein_short(variant.hgvsp)}
        probe = _body_probe(fields)
        return (
            "(() => { document.querySelectorAll('[aria-label*=close i],.cookie button,.modal button')"
            ".forEach(b => { if (/close|accept|agree/i.test(b.innerText||b.getAttribute('aria-label')||'')) b.click(); });"
            f" return ({probe}); }})()"
        )

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"{variant.gene} {_protein_short(variant.hgvsp)}"

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        return str(observed.get("gene", "")).upper() == variant.gene.upper() and str(observed.get("alteration", "")).upper() == _protein_short(variant.hgvsp).upper()


class CosmicProvider(BrowserProvider):
    name = "COSMIC"

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        if not variant.cosmic_id and not all((variant.chromosome, variant.position, variant.reference, variant.alternate)):
            return "COSMIC requires an imported COSV ID or complete GRCh37 allele."
        return ""

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        query = variant.cosmic_id or f"{variant.chromosome}:{variant.position}:{variant.reference}>{variant.alternate}"
        return f"https://cancer.sanger.ac.uk/cosmic/search?q={quote(query)}"

    def _identity_expression(self, variant: VariantRecord, context: SearchContext) -> str:
        fields = {"cosmic_id": variant.cosmic_id, "build": "GRCh37"} if variant.cosmic_id else {
            "build": "GRCh37", "chromosome": variant.chromosome, "position": str(variant.position), "reference": variant.reference, "alternate": variant.alternate
        }
        return _body_probe(fields)

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return variant.cosmic_id or f"GRCh37 {variant.chromosome}:{variant.position} {variant.reference}>{variant.alternate}"

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        build_ok = str(observed.get("build", "")).lower() in {"grch37", "hg19"}
        if variant.cosmic_id:
            return build_ok and str(observed.get("cosmic_id", "")).upper() == variant.cosmic_id.upper()
        return (
            build_ok
            and str(observed.get("chromosome", "")).removeprefix("chr") == variant.chromosome.removeprefix("chr")
            and str(observed.get("position")) == str(variant.position)
            and str(observed.get("reference", "")).upper() == variant.reference.upper()
            and str(observed.get("alternate", "")).upper() == variant.alternate.upper()
        )
