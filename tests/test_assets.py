from pathlib import Path

from PIL import Image


def test_windows_icon_contains_small_and_large_sizes():
    path = Path("src/mpn_tolkning/assets/variant-lens.ico")
    with Image.open(path) as icon:
        assert {(16, 16), (32, 32), (256, 256)}.issubset(set(icon.info["sizes"]))


def test_public_docs_do_not_contain_fixture_patient_ids():
    public = Path("README.md").read_text(encoding="utf-8") + Path("site/index.html").read_text(encoding="utf-8")
    assert "DIT-1001" not in public
    assert "DIT-1002" not in public


def test_pages_site_mentions_all_required_evidence_sources():
    page = Path("site/index.html").read_text(encoding="utf-8")
    for provider in ("CALR-ETdb", "MTBP", "Franklin", "ClinVar", "OncoKB", "COSMIC"):
        assert provider in page


def test_public_screenshot_has_desktop_dimensions():
    with Image.open("docs/assets/mpn-tolkning-workbench.png") as screenshot:
        assert screenshot.size == (1440, 900)
