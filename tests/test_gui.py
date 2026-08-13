import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from mpn_tolkning.gui.app import MainWindow, Palette


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_workbench_has_approved_navigation(qt_app):
    window = MainWindow()
    assert [button.text() for button in window.nav_buttons] == [
        "Import", "Driver Review", "Evidence", "Reports", "Settings"
    ]
    assert window.page_stack.count() == 5


def test_driver_table_and_filter_have_accessible_names(qt_app):
    window = MainWindow()
    assert window.variant_table.accessibleName() == "MPN variant review table"
    assert window.review_filter.accessibleName() == "Filter MPN variants"


def test_window_respects_approved_minimum_size(qt_app):
    window = MainWindow()
    assert window.minimumWidth() == 1120
    assert window.minimumHeight() == 720


def test_sidebar_and_primary_actions_meet_target_sizes(qt_app):
    window = MainWindow()
    assert 190 <= window.sidebar.minimumWidth() <= 226
    assert window.import_button.minimumHeight() >= 44
    assert window.start_search_button.minimumHeight() >= 44


def test_imported_variants_populate_metrics_table_and_filter(qt_app, sample_variants):
    window = MainWindow()
    window.set_variants(sample_variants)
    assert window.variant_table.rowCount() == 3
    assert window.metric_values["variants"].text() == "3"
    assert window.metric_values["samples"].text() == "3"

    window.review_filter.setText("CALR")
    QApplication.processEvents()
    visible = sum(not window.variant_table.isRowHidden(row) for row in range(3))
    assert visible == 1


def test_table_selection_updates_variant_lens(qt_app, sample_variants):
    window = MainWindow()
    window.set_variants(sample_variants)
    window.variant_table.selectRow(1)
    QApplication.processEvents()
    assert "JAK2" in window.variant_title.text()
    assert "V617F" in window.driver_context_label.text()


def test_theme_contains_approved_semantic_palette(qt_app):
    window = MainWindow()
    style = window.styleSheet().upper()
    for color in (Palette.DEEP_TEAL, Palette.TEAL, Palette.AMBER, Palette.BACKGROUND):
        assert color.upper() in style


def test_navigation_changes_page_and_marks_current_button(qt_app):
    window = MainWindow()
    window.nav_buttons[2].click()
    assert window.page_stack.currentIndex() == 2
    assert window.nav_buttons[2].property("current") is True
    assert window.nav_buttons[2].accessibleName() == "Evidence page, current"
