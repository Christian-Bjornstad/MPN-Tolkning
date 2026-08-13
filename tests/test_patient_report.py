from openpyxl import load_workbook

from mpn_tolkning.core.models import EvidenceResult, EvidenceStatus
from mpn_tolkning.reports.patient import write_patient_report


def test_calr_patient_report_uses_mpn_name_and_provider_order(tmp_path, calr_variant):
    evidence_set = [
        EvidenceResult(provider, EvidenceStatus.FOUND, f"{provider} match")
        for provider in ("CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")
    ]
    path = write_patient_report(tmp_path, "DIT-1001", [calr_variant], evidence_set)
    assert path.name == "DIT-1001_MPN_Tolkning.xlsx"
    workbook = load_workbook(path)
    assert workbook.sheetnames[:2] == ["Oversikt", "Vedlegg"]
    sheet = workbook[workbook.sheetnames[2]]
    captions = [cell.value for row in sheet.iter_rows() for cell in row if isinstance(cell.value, str)]
    indexes = [captions.index(name) for name in ("CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC")]
    assert indexes == sorted(indexes)


def test_report_contains_driver_context_and_review_disclaimer(tmp_path, jak2_variant):
    path = write_patient_report(tmp_path, "DIT-1002", [jak2_variant], [])
    workbook = load_workbook(path, data_only=True)
    overview = workbook["Oversikt"]
    text = " ".join(str(cell.value or "") for row in overview.iter_rows() for cell in row)
    assert "JAK2 V617F driver" in text
    assert "qualified" in text.lower()
    assert "research" in text.lower()


def test_unsafe_evidence_url_is_not_made_clickable(tmp_path, jak2_variant):
    evidence = [EvidenceResult("Example", EvidenceStatus.FOUND, "match", url="file:///secret")]
    path = write_patient_report(tmp_path, "DIT-1002", [jak2_variant], evidence)
    workbook = load_workbook(path)
    sheet = workbook[workbook.sheetnames[2]]
    hyperlinks = [cell.hyperlink for row in sheet.iter_rows() for cell in row if cell.hyperlink]
    assert hyperlinks == []
