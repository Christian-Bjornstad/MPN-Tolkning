import mpn_tolkning


def test_package_version_starts_at_0_1_0():
    assert mpn_tolkning.__version__ == "0.1.0"


def test_entrypoint_launches_synchronized_archer_workstation(monkeypatch):
    from mpn_tolkning.__main__ import main
    from mpn_tolkning.workstation.gui import app
    called = []
    monkeypatch.setattr(app, "main", lambda: called.append(True))
    main()
    assert called == [True]
