"""CALR-only extension of the pinned Archer browser workflow."""
from __future__ import annotations

import re
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from mpn_tolkning.core.models import VariantRecord as CalrVariant
from mpn_tolkning.providers.calr_et import CalrEtProvider
from mpn_tolkning.workstation.core.models import DatabaseEvidence, VariantRecord
from mpn_tolkning.workstation.services.evidence_audit import audit_digest, persist_evidence_result


DATABASE = "CALR-ETdb"


def _query(variant: VariantRecord) -> str:
    return variant.hgvsc.rsplit(":", 1)[-1].strip()


def _valid_query(cdna: str) -> bool:
    # CALR-ETdb accepts at most 50 characters. Genomic coordinates are not a
    # supported search field and are never substituted for missing HGVS cDNA.
    return len(cdna) <= 50 and bool(re.fullmatch(r"c\.[*+-]?\d[0-9A-Za-z_*+()>=?-]*", cdna))


def search_calr_variants(service, variants, artifact_directory: Path, *, progress=None):
    results: dict[str, DatabaseEvidence] = {}
    pending = []
    artifact_directory.mkdir(parents=True, exist_ok=True)
    for variant in variants:
        service._check_cancelled()
        if variant.symbol.upper() != "CALR":
            item = DatabaseEvidence(DATABASE, "not_applicable", "CALR variants only.")
        elif not _valid_query(_query(variant)):
            item = DatabaseEvidence(DATABASE, "invalid_query", "CALR HGVS cDNA is required; genomic search is unsupported.")
        else:
            pending.append(variant)
            continue
        results[service.variant_key(variant)] = persist_evidence_result(
            artifact_directory, DATABASE, variant, item, started_at=time.monotonic()
        )
    if not pending:
        return results

    sync_browser, _, _ = service._browser_api()
    with sync_browser() as runtime:
        context = runtime.chromium.launch_persistent_context(
            str(service.profile_directory(DATABASE)), channel=service.channel,
            headless=False, accept_downloads=False,
            viewport={"width": 1440, "height": 1000}, background=service.browser_background,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            for index, variant in enumerate(pending):
                service._check_cancelled()
                started = time.monotonic()
                cdna = _query(variant)
                if progress:
                    progress(f"CALR-ETdb lookup {index + 1}/{len(pending)}: {cdna}")
                try:
                    item = _search_page(service, page, variant, artifact_directory)
                except Exception as exc:
                    item = DatabaseEvidence(DATABASE, "error", f"CALR-ETdb lookup failed: {exc}", accession=cdna)
                results[service.variant_key(variant)] = persist_evidence_result(
                    artifact_directory, DATABASE, variant, item,
                    query_attempts=[cdna], started_at=started,
                )
                if index + 1 < len(pending):
                    service._wait_between_queries(page, DATABASE, progress=progress)
        finally:
            context.close()
    return results


def _search_page(service, page, variant: VariantRecord, directory: Path) -> DatabaseEvidence:
    cdna = _query(variant)
    page.goto(CalrEtProvider.SEARCH_URL, wait_until="domcontentloaded", timeout=service.navigation_timeout_ms)
    page.locator('input[name="nucleotid"]').fill(cdna)
    page.locator('input[name="envoie1"]').click()
    page.locator("#search, section > center").wait_for(state="visible", timeout=service.navigation_timeout_ms)
    service._check_cancelled()
    # Parse the same DOM that will be captured, rather than a separate HTTP
    # session whose result could differ from the browser's displayed variant.
    html = page.evaluate("document.documentElement.outerHTML")
    record = CalrVariant(sample="", gene="CALR", hgvsc=cdna, hgvsp=variant.hgvsp, vaf=None)
    parsed = CalrEtProvider()._parse(html, record, cdna)
    item = DatabaseEvidence(
        DATABASE, parsed.status.value, parsed.summary, accession=cdna,
        clinical_significance="; ".join(str(parsed.metadata[key]) for key in ("type", "class") if parsed.metadata.get(key)) if parsed.status.value == "found" else "",
        url=parsed.url,
        raw={
            **parsed.metadata, "query": cdna,
            "expected_identity": cdna, "observed_identity": parsed.observed_identity,
            "identity_verification": {"accepted": parsed.status.value == "found", "method": "CALR cDNA"},
        },
    )
    if item.status not in {"found", "not_found"}:
        return item
    screenshots = []
    digest = audit_digest(DATABASE, variant)
    captures = [("Result", "#tabl_result")]
    try:
        for label, selector in captures:
            service._check_cancelled()
            path = directory / f"{digest}-{label.lower()}.png"
            if item.status == "not_found":
                page.screenshot(path=str(path), full_page=True)
            else:
                page.locator(selector).screenshot(path=str(path))
            validation = service.capture_validator(path)
            if not validation.valid:
                raise RuntimeError(validation.reason)
            screenshots.append({"label": f"CALR-ETdb {label}", "path": str(path), "validation": asdict(validation)})
        if item.status == "found":
            target = urlparse(item.url)
            if target.scheme != "https" or target.hostname != "www.dsimb.inserm.fr" or target.path != "/CALR-ET/php/variant_page.php":
                item.url = CalrEtProvider.SEARCH_URL
                raise RuntimeError("Unexpected CALR detail URL.")
            page.goto(item.url, wait_until="domcontentloaded", timeout=service.navigation_timeout_ms)
            text = page.locator("#table_overview").inner_text()
            if parsed.observed_identity not in text.split():
                item.status = "identity_mismatch"
                item.summary = "CALR detail page does not show the verified cDNA variant."
                item.clinical_significance = ""
                item.raw["identity_verification"]["accepted"] = False
                return item
            service._check_cancelled()
            path = directory / f"{digest}-detail.png"
            page.locator("#table_overview").screenshot(path=str(path))
            validation = service.capture_validator(path)
            if not validation.valid:
                raise RuntimeError(validation.reason)
            screenshots.append({"label": "CALR-ETdb Variant detail", "path": str(path), "validation": asdict(validation)})
    except Exception as exc:
        item.status = "partial_capture"
        item.summary = f"CALR-ETdb screenshot capture incomplete: {exc}"
        item.clinical_significance = ""
    item.raw["screenshots"] = screenshots
    return item
