from mpn_tolkning.core.identity import stable_variant_key
from mpn_tolkning.core.models import EvidenceStatus
from mpn_tolkning.providers.base import SearchContext
from mpn_tolkning.providers.identity import ClinGenAlleleProvider, CivicProvider, MetaKbProvider


def _context(variant):
    transcript, cdna = variant.hgvsc.split(":", 1)
    return SearchContext(stable_variant_key(variant), transcript, cdna)


def test_clingen_resolves_hgvs_to_caid(monkeypatch, jak2_variant):
    provider = ClinGenAlleleProvider()
    captured = {}

    def fake_get(hgvs):
        captured["hgvs"] = hgvs
        return {"@id": "https://reg.clinicalgenome.org/allele/CA123456"}

    monkeypatch.setattr(provider, "_get_json", fake_get)
    result = provider.search(jak2_variant, _context(jak2_variant))

    assert captured["hgvs"] == jak2_variant.hgvsc
    assert result.status is EvidenceStatus.FOUND
    assert result.metadata["caid"] == "CA123456"


def test_clingen_missing_id_is_incomplete_not_a_false_hit(monkeypatch, jak2_variant):
    provider = ClinGenAlleleProvider()
    monkeypatch.setattr(provider, "_get_json", lambda hgvs: {"message": "unexpected"})
    result = provider.search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.ERROR
    assert result.retryable is True


def test_civic_requires_an_exact_observed_identity(monkeypatch, jak2_variant):
    provider = CivicProvider(enabled=True)
    monkeypatch.setattr(
        provider,
        "_search_records",
        lambda variant: [{"name": "V617F", "gene": "JAK2", "id": 12}],
    )
    result = provider.search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.FOUND
    assert result.observed_identity == "JAK2 V617F"


def test_optional_provider_is_disabled_by_default(jak2_variant):
    result = CivicProvider().search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.CANCELLED
    assert "disabled" in result.summary.lower()


def test_metakb_never_calls_a_partial_match_exact(monkeypatch, jak2_variant):
    provider = MetaKbProvider(enabled=True)
    monkeypatch.setattr(
        provider,
        "_search_records",
        lambda variant: [{"gene": "JAK2", "name": "V617I", "url": "https://example.invalid"}],
    )
    result = provider.search(jak2_variant, _context(jak2_variant))
    assert result.status is EvidenceStatus.NOT_FOUND
