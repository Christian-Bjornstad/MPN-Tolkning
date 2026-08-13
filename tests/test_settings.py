import json

from mpn_tolkning.services.settings import AppSettings


def test_settings_default_to_independent_mpn_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert AppSettings.default_path() == tmp_path / ".mpn-tolkning" / "config.json"


def test_saved_settings_never_contain_passwords(tmp_path):
    path = tmp_path / "config.json"
    settings = AppSettings(cosmic_email="lab@example.org")

    settings.save(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["cosmic_email"] == "lab@example.org"
    assert all("password" not in key.lower() for key in payload)


def test_settings_round_trip_provider_and_artifact_preferences(tmp_path):
    path = tmp_path / "config.json"
    settings = AppSettings(
        selected_providers=["CALR-ETdb", "ClinVar"],
        artifact_rules=[
            {
                "gene": "JAK2",
                "cdna": "c.3291+16dup",
                "max_vaf": 5.0,
                "reason": "review",
            }
        ],
    )
    settings.save(path)

    loaded = AppSettings.load(path)

    assert loaded.selected_providers == ["CALR-ETdb", "ClinVar"]
    assert loaded.artifact_rules[0]["max_vaf"] == 5.0


def test_corrupt_settings_fail_safe_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("not-json", encoding="utf-8")

    settings = AppSettings.load(path)

    assert "CALR-ETdb" in settings.selected_providers
