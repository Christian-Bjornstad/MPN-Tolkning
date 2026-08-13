from mpn_tolkning.reports.patient import PatientReportCoordinator


def test_coordinator_marks_locked_workbook_pending_and_retries(tmp_path, calr_variant, monkeypatch):
    coordinator = PatientReportCoordinator(tmp_path)
    original_save = coordinator._save
    calls = 0

    def flaky_save(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("workbook open")
        return original_save(*args, **kwargs)

    monkeypatch.setattr(coordinator, "_save", flaky_save)
    coordinator.update_patient("DIT-1001", [calr_variant], [])
    assert coordinator.pending_samples == {"DIT-1001"}
    coordinator.reconcile()
    assert coordinator.pending_samples == set()
    assert (tmp_path / "DIT-1001_MPN_Tolkning.xlsx").exists()


def test_write_all_updates_each_sample_without_losing_evidence(tmp_path, sample_variants):
    coordinator = PatientReportCoordinator(tmp_path)
    output = coordinator.write_all(sample_variants, [])
    assert set(output) == {"DIT-1001", "DIT-1002", "DIT-1003"}
    assert all(path.exists() for path in output.values())
