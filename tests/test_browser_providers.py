from pathlib import Path

from PIL import Image
import pytest

from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.models import EvidenceStatus
from mpn_tolkning.providers.base import SearchContext
from mpn_tolkning.providers.browser import (
    REQUIRED_BROWSER_PROVIDERS,
    CosmicProvider,
    ClinVarProvider,
    FranklinProvider,
    MtbpProvider,
    OncoKbProvider,
)


class FakeBrowser:
    def __init__(self, observed, *, blank=False):
        self.observed = observed
        self.blank = blank
        self.provider = ""
        self.urls = []
        self.closed = False

    def start(self, provider):
        self.provider = provider

    def navigate(self, url):
        self.urls.append(url)

    def evaluate(self, expression):
        return self.observed

    def screenshot(self, path, clip=None):
        image = Image.new("RGB", (500, 240), "white")
        if not self.blank:
            for x in range(0, 500, 2):
                for y in range(240):
                    image.putpixel((x, y), (11, 75, 82))
        image.save(path)
        return path

    def close(self):
        self.closed = True


def _context(variant):
    transcript, cdna = variant.hgvsc.split(":", 1)
    return SearchContext(stable_variant_key(variant), transcript, cdna)


def test_required_browser_provider_order():
    assert REQUIRED_BROWSER_PROVIDERS == ("MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")


@pytest.mark.parametrize(
    "provider_type,observed",
    [
        (MtbpProvider, {"gene": "JAK2", "hgvsc": "NM_004972.4:c.1849G>T"}),
        (FranklinProvider, {"transcript": "NM_004972.4", "cdna": "c.1849G>T", "assembly": "hg19", "mode": "somatic"}),
        (ClinVarProvider, {"build": "GRCh37", "chromosome": "9", "position": 5073770, "reference": "G", "alternate": "T"}),
        (OncoKbProvider, {"gene": "JAK2", "alteration": "V617F"}),
        (CosmicProvider, {"cosmic_id": "COSV67569040", "build": "GRCh37"}),
    ],
)
def test_browser_providers_require_exact_identity_and_valid_capture(
    tmp_path, jak2_variant, provider_type, observed
):
    browser = FakeBrowser(observed)
    provider = provider_type(lambda: browser, tmp_path)
    result = provider.search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.FOUND
    assert len(result.screenshots) == 1
    assert result.screenshots[0].exists()
    assert browser.closed


def test_clinvar_rejects_wrong_build_even_when_allele_matches(tmp_path, jak2_variant):
    browser = FakeBrowser({"build": "GRCh38", "chromosome": "9", "position": 5073770, "reference": "G", "alternate": "T"})
    result = ClinVarProvider(lambda: browser, tmp_path).search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.IDENTITY_MISMATCH
    assert not result.screenshots


def test_franklin_rejects_germline_or_grch38_context(tmp_path, jak2_variant):
    browser = FakeBrowser({"transcript": "NM_004972.4", "cdna": "c.1849G>T", "assembly": "hg38", "mode": "germline"})
    result = FranklinProvider(lambda: browser, tmp_path).search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.IDENTITY_MISMATCH


def test_cosmic_prefers_imported_cosv_identity(tmp_path, jak2_variant):
    browser = FakeBrowser({"cosmic_id": "COSV00000000", "build": "GRCh37"})
    result = CosmicProvider(lambda: browser, tmp_path).search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.IDENTITY_MISMATCH


def test_blank_screenshot_turns_verified_page_into_incomplete_capture(tmp_path, jak2_variant):
    browser = FakeBrowser({"gene": "JAK2", "alteration": "V617F"}, blank=True)
    result = OncoKbProvider(lambda: browser, tmp_path).search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.INCOMPLETE_CAPTURE
    assert result.retryable


def test_pause_and_stop_are_cooperative(tmp_path, jak2_variant):
    checkpoints = []
    browser = FakeBrowser({"gene": "JAK2", "alteration": "V617F"})
    provider = OncoKbProvider(
        lambda: browser,
        tmp_path,
        pause_checkpoint=lambda: checkpoints.append("pause"),
        stop_requested=lambda: True,
    )
    result = provider.search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.CANCELLED
    assert checkpoints == ["pause"]
    assert not browser.urls


def test_mtbp_uses_generated_pseudonym_not_sample_id(tmp_path, jak2_variant):
    browser = FakeBrowser({"gene": "JAK2", "hgvsc": jak2_variant.hgvsc})
    result = MtbpProvider(lambda: browser, tmp_path).search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.FOUND
    assert jak2_variant.sample not in " ".join(browser.urls)
    assert result.metadata["pseudonym"].startswith("MPN-")
