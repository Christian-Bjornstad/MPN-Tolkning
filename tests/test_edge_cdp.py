from pathlib import Path

from mpn_tolkning.services.edge_cdp import EdgeCdpSession, build_edge_arguments


def test_edge_arguments_use_provider_isolated_profile_and_background_window(tmp_path):
    args = build_edge_arguments(
        Path("C:/Program Files/Edge/msedge.exe"),
        tmp_path / "franklin",
        9222,
        background=True,
    )
    joined = " ".join(args)
    assert f"--user-data-dir={tmp_path / 'franklin'}" in joined
    assert "--remote-debugging-address=127.0.0.1" in args
    assert "--start-minimized" in args
    assert "--window-position=-32000,-32000" in args


def test_session_creates_separate_provider_profiles(tmp_path, monkeypatch):
    launched = []
    session = EdgeCdpSession(tmp_path)
    monkeypatch.setattr(session, "_launch", lambda profile: launched.append(profile))

    session.start("ClinVar")
    session.close()
    session.start("Franklin")

    assert launched == [tmp_path / "clinvar", tmp_path / "franklin"]


def test_provider_name_cannot_escape_profile_root(tmp_path, monkeypatch):
    session = EdgeCdpSession(tmp_path)
    monkeypatch.setattr(session, "_launch", lambda profile: None)
    session.start("../../COSMIC")
    assert session.profile_directory == tmp_path / "cosmic"
