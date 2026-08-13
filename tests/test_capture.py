from pathlib import Path

from PIL import Image

from mpn_tolkning.services.capture import screenshot_path, validate_capture


def test_capture_rejects_missing_small_and_blank_files(tmp_path):
    assert validate_capture(tmp_path / "missing.png").reason == "unreadable"
    Image.new("RGB", (20, 20), "white").save(tmp_path / "small.png")
    assert validate_capture(tmp_path / "small.png").reason == "too_small"
    Image.new("RGB", (300, 120), "white").save(tmp_path / "blank.png")
    assert validate_capture(tmp_path / "blank.png").reason == "low_content"


def test_capture_accepts_content_and_filename_contains_no_patient_id(tmp_path):
    image = Image.new("RGB", (300, 120), "white")
    for x in range(0, 300, 2):
        for y in range(120):
            image.putpixel((x, y), (10, 80, 90))
    output = screenshot_path(tmp_path, "grch37:9:5073770:G:T", "ClinVar", 1)
    image.save(output)
    validation = validate_capture(output)
    assert validation.valid
    assert output.name == "3221216b78f71079_clinvar_01.png"
    assert "DIT" not in output.name
