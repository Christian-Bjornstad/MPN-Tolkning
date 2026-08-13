import keyring

from mpn_tolkning.services.credentials import CredentialStore


def test_credential_service_uses_provider_scoped_keyring(monkeypatch):
    calls = []
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, user, password: calls.append((service, user, password)),
    )

    CredentialStore().set("COSMIC", "lab@example.org", "secret-value")

    assert calls == [("mpn-tolkning:COSMIC", "lab@example.org", "secret-value")]


def test_credential_lookup_uses_same_provider_scope(monkeypatch):
    monkeypatch.setattr(
        keyring,
        "get_password",
        lambda service, user: f"{service}|{user}",
    )

    value = CredentialStore().get("Franklin", "lab@example.org")

    assert value == "mpn-tolkning:Franklin|lab@example.org"
