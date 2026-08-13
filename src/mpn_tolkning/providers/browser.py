from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote, urlparse

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


def edge_browser_factory(
    profile_root: Path,
    *,
    background: bool = True,
    timeout_ms: int = 45_000,
) -> Callable[[], EdgeCdpSession]:
    return lambda: EdgeCdpSession(profile_root, background=background, timeout_ms=timeout_ms)


_SNAPSHOT_EXPRESSION = """
(() => ({
  url: location.href,
  title: document.title || '',
  text: (document.body?.innerText || '').replace(/\\s+/g, ' ').trim()
}))()
"""


class BrowserProvider:
    name = ""
    allowed_hosts: tuple[str, ...] = ()

    def __init__(
        self,
        browser_factory: Callable[[], object],
        capture_root: Path,
        *,
        pause_checkpoint: Callable[[], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
        analysis_timeout_ms: int = 1_200_000,
    ):
        self.browser_factory = browser_factory
        self.capture_root = Path(capture_root)
        self.pause_checkpoint = pause_checkpoint or (lambda: None)
        self.stop_requested = stop_requested or (lambda: False)
        self.analysis_timeout_ms = analysis_timeout_ms

    def search(self, variant: VariantRecord, context: SearchContext) -> EvidenceResult:
        self.pause_checkpoint()
        if self.stop_requested():
            return EvidenceResult(self.name, EvidenceStatus.CANCELLED, "Evidence collection stopped by the user.")
        problem = self._validate_query(variant, context)
        if problem:
            return EvidenceResult(self.name, EvidenceStatus.INVALID_QUERY, problem)

        url = self._url(variant, context)
        expected = self._expected_identity(variant, context)
        browser = None
        try:
            browser = self.browser_factory()
            browser.start(self.name)
            browser.navigate(url)
            raw = browser.evaluate(_SNAPSHOT_EXPRESSION)
            if not isinstance(raw, dict):
                raise ValueError("the provider page did not return a readable snapshot")
            snapshot_mode = any(key in raw for key in ("url", "title", "text"))
            state = self._page_state(raw) if snapshot_mode else "result"
            page_url = str(raw.get("url") or url)
            if state == "login":
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.ERROR,
                    f"{self.name} requires sign-in in its isolated Edge profile.",
                    url=self._retain_url(page_url),
                    retryable=True,
                    expected_identity=expected,
                )
            if state == "not_found":
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.NOT_FOUND,
                    f"{self.name} explicitly reported no matching result.",
                    url=self._retain_url(page_url),
                    expected_identity=expected,
                )
            observed = self._extract_observed(raw, variant, context) if snapshot_mode else raw
            if snapshot_mode and not observed and state == "unknown" and self._interact(browser, variant, context, raw):
                raw = browser.evaluate(_SNAPSHOT_EXPRESSION)
                if not isinstance(raw, dict):
                    raise ValueError("the provider result did not return a readable snapshot")
                state = self._page_state(raw)
                page_url = str(raw.get("url") or page_url)
                if state == "login":
                    return EvidenceResult(
                        self.name,
                        EvidenceStatus.ERROR,
                        f"{self.name} requires sign-in in its isolated Edge profile.",
                        url=self._retain_url(page_url),
                        retryable=True,
                        expected_identity=expected,
                    )
                if state == "not_found":
                    return EvidenceResult(
                        self.name,
                        EvidenceStatus.NOT_FOUND,
                        f"{self.name} explicitly reported no matching result.",
                        url=self._retain_url(page_url),
                        expected_identity=expected,
                    )
                observed = self._extract_observed(raw, variant, context)
            if not observed:
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.ERROR,
                    f"{self.name} loaded, but no canonical result identity could be extracted.",
                    url=self._retain_url(page_url),
                    retryable=True,
                    expected_identity=expected,
                    metadata={"page_state": state},
                )
            observed_label = self._observed_identity(observed)
            if not self._matches(observed, variant, context):
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.IDENTITY_MISMATCH,
                    f"{self.name} result identity did not match the imported variant.",
                    url=self._retain_url(page_url),
                    retryable=True,
                    expected_identity=expected,
                    observed_identity=observed_label,
                    metadata={"observed": observed},
                )
            target = screenshot_path(
                self.capture_root,
                f"{variant.sample}|{context.stable_key}",
                self.name,
                1,
            )
            browser.screenshot(target)
            capture = validate_capture(target)
            if not capture.valid:
                target.unlink(missing_ok=True)
                return EvidenceResult(
                    self.name,
                    EvidenceStatus.INCOMPLETE_CAPTURE,
                    f"Verified {self.name} page had an invalid screenshot: {capture.reason}.",
                    url=self._retain_url(page_url),
                    retryable=True,
                    expected_identity=expected,
                    observed_identity=observed_label,
                    metadata={"capture_reason": capture.reason, **self._metadata(variant, context)},
                )
            return EvidenceResult(
                self.name,
                EvidenceStatus.FOUND,
                f"Verified {self.name} evidence for {observed_label}.",
                url=self._retain_url(page_url),
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
                url=self._retain_url(url),
                retryable=True,
                expected_identity=expected,
            )
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        return "" if variant.gene and context.cdna else "Gene and HGVS cDNA are required."

    def _metadata(self, variant: VariantRecord, context: SearchContext) -> dict:
        return {}

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        raise NotImplementedError

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        raise NotImplementedError

    def _extract_observed(
        self, snapshot: dict, variant: VariantRecord, context: SearchContext
    ) -> dict:
        raise NotImplementedError

    def _retain_url(self, value: str) -> str:
        parsed = urlparse(value)
        return value if parsed.scheme == "https" and parsed.hostname in self.allowed_hosts else ""

    def _interact(
        self,
        browser: object,
        variant: VariantRecord,
        context: SearchContext,
        snapshot: dict,
    ) -> bool:
        return False

    def _page_state(self, snapshot: dict) -> str:
        url = str(snapshot.get("url") or "").lower()
        title = str(snapshot.get("title") or "").lower()
        text = str(snapshot.get("text") or "").lower()
        if any(marker in url for marker in ("/login", "/signin", "auth0", "keycloak")) or any(
            marker in title for marker in ("sign in", "log in", "login")
        ):
            return "login"
        if any(
            marker in text
            for marker in (
                "no items found",
                "no results found",
                "no matching result",
                "0 results",
            )
        ):
            return "not_found"
        return "unknown"

    def _observed_identity(self, observed: dict) -> str:
        return " ".join(str(value) for value in observed.values() if value not in (None, ""))

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        raise NotImplementedError


class MtbpProvider(BrowserProvider):
    name = "MTBP"
    allowed_hosts = ("mtbp.org", "www.mtbp.org")

    def _pseudonym(self, variant: VariantRecord, context: SearchContext) -> str:
        local_key = f"{variant.sample}|{context.stable_key}"
        return "MPN-" + hashlib.sha256(local_key.encode("utf-8")).hexdigest()[:10].upper()

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        return "https://mtbp.org/analyse/"

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"{variant.gene} {variant.hgvsc}"

    def _extract_observed(self, snapshot: dict, variant: VariantRecord, context: SearchContext) -> dict:
        url = str(snapshot.get("url") or "")
        text = str(snapshot.get("text") or "")
        if not re.search(r"/patients/[^/]+/report/\d+/?", url):
            return {}
        hgvsc = re.search(r"(?:NM|NR)_\d+(?:\.\d+)?:c\.[A-Za-z0-9_+>*=-]+", text)
        gene = re.search(rf"\b{re.escape(variant.gene)}\b", text, re.IGNORECASE)
        return {"gene": gene.group(0).upper(), "hgvsc": hgvsc.group(0)} if gene and hgvsc else {}

    def _interact(self, browser: object, variant: VariantRecord, context: SearchContext, snapshot: dict) -> bool:
        pseudonym = json.dumps(self._pseudonym(variant, context))
        query = json.dumps(variant.hgvsc)
        submitted = browser.evaluate(
            "(() => {"
            "const set=(selector,value)=>{const el=document.querySelector(selector);if(!el)return false;"
            "const proto=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
            "const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;setter?setter.call(el,value):el.value=value;"
            "el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return true;};"
            f"if(!set('#analysis-id',{pseudonym})||!set('#variant-input',{query}))return false;"
            "const cancer=[...document.querySelectorAll('[role=treeitem]')].find(el=>(el.innerText||'').trim()==='Blood');"
            "if(!cancer)return false;cancer.click();const run=document.querySelector('#run-analysis');if(!run)return false;run.click();return true;})()"
        )
        if not submitted:
            raise ValueError("MTBP analysis form was not available")
        deadline = time.monotonic() + self.analysis_timeout_ms / 1000
        while time.monotonic() < deadline:
            self.pause_checkpoint()
            if self.stop_requested():
                raise ValueError("MTBP search was stopped")
            current = str(browser.evaluate("location.href") or "")
            if re.search(r"/patients/[^/]+/report/\d+/?", current):
                return True
            body = str(browser.evaluate("document.body?.innerText || ''") or "").lower()
            if "cannot be mapped to genomic coordinates" in body or "no results found" in body:
                return True
            time.sleep(0.5)
        raise EdgeCdpTimeout("MTBP report did not complete before the analysis timeout")

    def _retain_url(self, value: str) -> str:
        return ""

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        return str(observed.get("gene", "")).upper() == variant.gene.upper() and str(observed.get("hgvsc", "")) == variant.hgvsc

    def _metadata(self, variant: VariantRecord, context: SearchContext) -> dict:
        return {"pseudonym": self._pseudonym(variant, context)}


class FranklinProvider(BrowserProvider):
    name = "Franklin"
    allowed_hosts = ("franklin.genoox.com",)

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        query = quote(f"{context.transcript}:{context.cdna}")
        return f"https://franklin.genoox.com/clinical-db/variant/snp/chr?query={query}&assembly=hg19&mode=somatic"

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"somatic hg19 {context.transcript}:{context.cdna}"

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        if not context.transcript or not context.cdna:
            return "Franklin requires transcript-qualified HGVS cDNA."
        return ""

    def _extract_observed(self, snapshot: dict, variant: VariantRecord, context: SearchContext) -> dict:
        parsed = urlparse(str(snapshot.get("url") or ""))
        if parsed.path.rstrip("/") == "/clinical-db/variant/snp/chr":
            return {}
        text = str(snapshot.get("text") or "")
        transcript = re.search(r"(?:NM|NR)_\d+(?:\.\d+)?", text)
        cdna = re.search(r"c\.[A-Za-z0-9_+>*=-]+", text)
        assembly = re.search(r"\b(?:hg19|GRCh37)\b", text, re.IGNORECASE)
        mode = re.search(r"\bsomatic\b", text, re.IGNORECASE)
        if not all((transcript, cdna, assembly, mode)):
            return {}
        return {"transcript": transcript.group(0), "cdna": cdna.group(0), "assembly": assembly.group(0), "mode": mode.group(0)}

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        return (
            str(observed.get("transcript", "")) == context.transcript
            and str(observed.get("cdna", "")) == context.cdna
            and str(observed.get("assembly", "")).lower() in {"hg19", "grch37"}
            and str(observed.get("mode", "")).lower() == "somatic"
        )


class ClinVarProvider(BrowserProvider):
    name = "ClinVar"
    allowed_hosts = ("www.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov")

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        if not all((variant.chromosome, variant.position, variant.reference, variant.alternate)):
            return "ClinVar requires a complete GRCh37 chromosome/position/ref/alt identity."
        return ""

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        query = quote(f"{variant.chromosome}[chr] AND {variant.position}[chrpos37]")
        return f"https://www.ncbi.nlm.nih.gov/clinvar/?term={query}"

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"GRCh37 {variant.chromosome}:{variant.position} {variant.reference}>{variant.alternate}"

    def _extract_observed(self, snapshot: dict, variant: VariantRecord, context: SearchContext) -> dict:
        text = str(snapshot.get("text") or "")
        match = re.search(
            r"(?:GRCh37|hg19)\s*[:;,]?\s*(?:chr)?([0-9XYM]+)\s*:\s*(\d+)\s*([ACGT]+)\s*>\s*([ACGT]+)",
            text,
            re.IGNORECASE,
        )
        if not match:
            location = re.search(r"(?:chr)?([0-9XYM]+)\s*:\s*(\d+)\s*\((?:GRCh37|hg19)\)", text, re.IGNORECASE)
            allele = re.search(rf"{re.escape(context.transcript)}:{re.escape(context.cdna)}", text) if context.transcript else None
            if location and allele:
                chromosome, position = location.groups()
                return {
                    "build": "GRCh37",
                    "chromosome": chromosome,
                    "position": position,
                    "reference": variant.reference,
                    "alternate": variant.alternate,
                }
        if not match:
            return {}
        chromosome, position, reference, alternate = match.groups()
        return {"build": "GRCh37", "chromosome": chromosome, "position": position, "reference": reference, "alternate": alternate}

    def _interact(self, browser: object, variant: VariantRecord, context: SearchContext, snapshot: dict) -> bool:
        if "/clinvar/search" not in str(snapshot.get("url") or "").lower():
            return False
        exact = json.dumps(context.cdna)
        href = browser.evaluate(
            "(() => {const expected=" + exact + ";"
            "const links=[...document.querySelectorAll('a[href]')].filter(a=>(a.innerText||'').includes(expected));"
            "return links.length===1?links[0].href:'';})()"
        )
        parsed = urlparse(str(href or ""))
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts or "/clinvar/variation/" not in parsed.path:
            return False
        browser.navigate(str(href))
        return True

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
    allowed_hosts = ("www.oncokb.org", "oncokb.org")

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"https://www.oncokb.org/gene/{quote(variant.gene)}/{quote(_protein_short(variant.hgvsp))}"

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return f"{variant.gene} {_protein_short(variant.hgvsp)}"

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        if not variant.gene or not _protein_short(variant.hgvsp):
            return "OncoKB requires a gene and protein alteration."
        return ""

    def _extract_observed(self, snapshot: dict, variant: VariantRecord, context: SearchContext) -> dict:
        parsed = urlparse(str(snapshot.get("url") or ""))
        match = re.fullmatch(r"/gene/([^/]+)/([^/?#]+)", parsed.path.rstrip("/"), re.IGNORECASE)
        if not match:
            return {}
        return {"gene": unquote(match.group(1)), "alteration": unquote(match.group(2))}

    def _matches(self, observed: dict, variant: VariantRecord, context: SearchContext) -> bool:
        return str(observed.get("gene", "")).upper() == variant.gene.upper() and str(observed.get("alteration", "")).upper() == _protein_short(variant.hgvsp).upper()


class CosmicProvider(BrowserProvider):
    name = "COSMIC"
    allowed_hosts = ("cancer.sanger.ac.uk",)

    def _validate_query(self, variant: VariantRecord, context: SearchContext) -> str:
        if not variant.cosmic_id and not all((variant.chromosome, variant.position, variant.reference, variant.alternate)):
            return "COSMIC requires an imported COSV ID or complete GRCh37 allele."
        return ""

    def _url(self, variant: VariantRecord, context: SearchContext) -> str:
        query = variant.cosmic_id or f"{variant.chromosome}:{variant.position}:{variant.reference}>{variant.alternate}"
        return f"https://cancer.sanger.ac.uk/cosmic/search?q={quote(query)}"

    def _expected_identity(self, variant: VariantRecord, context: SearchContext) -> str:
        return variant.cosmic_id or f"GRCh37 {variant.chromosome}:{variant.position} {variant.reference}>{variant.alternate}"

    def _extract_observed(self, snapshot: dict, variant: VariantRecord, context: SearchContext) -> dict:
        url = str(snapshot.get("url") or "")
        text = str(snapshot.get("text") or "")
        if "/cosmic/search" in url.lower():
            return {}
        build = re.search(r"\b(?:GRCh37|hg19)\b", text, re.IGNORECASE)
        if not build:
            return {}
        if variant.cosmic_id:
            cosmic = re.search(r"\bCOSV\d+\b", text, re.IGNORECASE)
            return {"cosmic_id": cosmic.group(0).upper(), "build": build.group(0)} if cosmic else {}
        allele = re.search(r"(?:chr)?([0-9XYM]+):(\d+)\s*([ACGT]+)\s*>\s*([ACGT]+)", text, re.IGNORECASE)
        if not allele:
            return {}
        chromosome, position, reference, alternate = allele.groups()
        return {"build": build.group(0), "chromosome": chromosome, "position": position, "reference": reference, "alternate": alternate}

    def _interact(self, browser: object, variant: VariantRecord, context: SearchContext, snapshot: dict) -> bool:
        tokens = (
            [variant.cosmic_id]
            if variant.cosmic_id
            else [variant.chromosome.removeprefix("chr"), str(variant.position), variant.reference, variant.alternate]
        )
        expected_tokens = json.dumps(tokens)
        href = browser.evaluate(
            "(() => { const tokens=" + expected_tokens + ";"
            "const links=[...document.querySelectorAll('a[href]')].filter(a=>"
            "{const value=((a.innerText||'')+' '+a.href).toUpperCase();"
            "return tokens.every(token=>value.includes(String(token).toUpperCase()));});"
            "return links.length===1?links[0].href:''; })()"
        )
        parsed = urlparse(str(href or ""))
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.allowed_hosts
            or "/cosmic/search" in parsed.path.lower()
        ):
            return False
        browser.navigate(str(href))
        return True

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
