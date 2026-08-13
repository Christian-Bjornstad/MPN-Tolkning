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
    assert len(list(tmp_path.glob("DIT-1001-*_MPN_Tolkning.xlsx"))) == 1


def test_write_all_updates_each_sample_without_losing_evidence(tmp_path, sample_variants):
    coordinator = PatientReportCoordinator(tmp_path)
    output = coordinator.write_all(sample_variants, [])
    assert set(output) == {"DIT-1001", "DIT-1002", "DIT-1003"}
    assert all(path.exists() for path in output.values())


def test_report_filenames_do_not_collide_after_sanitizing(tmp_path, calr_variant):
    from dataclasses import replace

    variants = [replace(calr_variant, sample="A/B"), replace(calr_variant, sample="A_B")]
    output = PatientReportCoordinator(tmp_path).write_all(variants, {})
    assert len({path.name for path in output.values()}) == 2
