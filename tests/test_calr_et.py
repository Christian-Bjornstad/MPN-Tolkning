from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.models import EvidenceStatus, VariantRecord
from mpn_tolkning.providers.base import SearchContext
from mpn_tolkning.providers.calr_et import CalrEtProvider
from PIL import Image


def _variant(cdna="c.1099_1150del", protein="p.Leu367ThrfsTer46"):
    return VariantRecord(
        sample="TEST-1",
        gene="CALR",
        hgvsc=f"NM_004343.4:{cdna}",
        hgvsp=protein,
        vaf=0.4,
    )


def _context(variant):
    return SearchContext(
        stable_key=stable_variant_key(variant),
        transcript="NM_004343.4",
        cdna=variant.hgvsc.split(":", 1)[1],
    )


def test_calr_et_posts_only_cdna_and_parses_exact_hit(monkeypatch, fixture_html):
    provider = CalrEtProvider()
    variant = _variant()
    submitted = {}
    monkeypatch.setattr(provider, "_csrf_token", lambda: "safe-token")

    def fake_post(data):
        submitted.update(data)
        return fixture_html("calr_et_type1.html")

    monkeypatch.setattr(provider, "_post", fake_post)
    result = provider.search(variant, _context(variant))

    assert submitted["nucleotid"] == "c.1099_1150del"
    assert "NM_004343" not in submitted["nucleotid"]
    assert submitted["csrf_token"] == "safe-token"
    assert result.status is EvidenceStatus.FOUND
    assert result.observed_identity == "c.1099_1150del"
    assert result.metadata["type"] == "Type 1-like"
    assert result.metadata["class"] == "Class A"
    assert result.metadata["cosmic_id"] == "COSV57116546"
    assert result.url.endswith("variant_page.php?num_var=var20")


def test_calr_et_returns_not_found_for_empty_result(monkeypatch, fixture_html):
    provider = CalrEtProvider()
    variant = _variant()
    monkeypatch.setattr(provider, "_csrf_token", lambda: "token")
    monkeypatch.setattr(provider, "_post", lambda data: fixture_html("calr_et_not_found.html"))

    result = provider.search(variant, _context(variant))
    assert result.status is EvidenceStatus.NOT_FOUND


def test_calr_et_rejects_non_calr_without_network(monkeypatch):
    provider = CalrEtProvider()
    variant = VariantRecord("TEST-2", "JAK2", "NM_004972.4:c.1849G>T", 0.2)
    monkeypatch.setattr(provider, "_csrf_token", lambda: (_ for _ in ()).throw(AssertionError()))

    result = provider.search(variant, _context(variant))
    assert result.status is EvidenceStatus.INVALID_QUERY


def test_calr_et_accepts_documented_cdna_alias_only_when_protein_matches(
    monkeypatch, fixture_html
):
    provider = CalrEtProvider()
    variant = _variant(cdna="c.1092_1143del")
    monkeypatch.setattr(provider, "_csrf_token", lambda: "token")
    monkeypatch.setattr(provider, "_post", lambda data: fixture_html("calr_et_type1.html"))

    result = provider.search(variant, _context(variant))
    assert result.status is EvidenceStatus.FOUND
    assert result.metadata["alias_verified"] is True


def test_calr_et_rejects_alias_when_protein_does_not_match(monkeypatch, fixture_html):
    provider = CalrEtProvider()
    variant = _variant(cdna="c.1092_1143del", protein="p.Trp515Leu")
    monkeypatch.setattr(provider, "_csrf_token", lambda: "token")
    monkeypatch.setattr(provider, "_post", lambda data: fixture_html("calr_et_type1.html"))

    result = provider.search(variant, _context(variant))
    assert result.status is EvidenceStatus.IDENTITY_MISMATCH
    assert result.retryable is True


def test_calr_et_required_capture_rejects_http_only_hit(monkeypatch, fixture_html):
    provider = CalrEtProvider(require_capture=True)
    variant = _variant()
    monkeypatch.setattr(provider, "_csrf_token", lambda: "token")
    monkeypatch.setattr(provider, "_post", lambda data: fixture_html("calr_et_type1.html"))
    result = provider.search(variant, _context(variant))
    assert result.status is EvidenceStatus.INCOMPLETE_CAPTURE
    assert result.retryable


def test_calr_et_capture_callback_must_return_content(tmp_path, monkeypatch, fixture_html):
    capture = tmp_path / "calr.png"

    def capture_result(variant, context, url):
        image = Image.new("RGB", (400, 180), "white")
        for x in range(0, 400, 2):
            for y in range(180):
                image.putpixel((x, y), (10, 80, 90))
        image.save(capture)
        return (capture,)

    provider = CalrEtProvider(require_capture=True, capture_callback=capture_result)
    variant = _variant()
    monkeypatch.setattr(provider, "_csrf_token", lambda: "token")
    monkeypatch.setattr(provider, "_post", lambda data: fixture_html("calr_et_type1.html"))
    result = provider.search(variant, _context(variant))
    assert result.status is EvidenceStatus.FOUND
    assert result.screenshots == (capture,)
