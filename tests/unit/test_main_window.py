"""Main window tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QApplication = pytest.importorskip(
    "PySide6.QtWidgets",
    reason="PySide6 runtime libraries unavailable in this environment.",
).QApplication


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


@pytest.fixture(scope="session")
def main_window_class():
    """Return MainWindow class."""
    from estudai.ui.main_window import MainWindow

    return MainWindow


def test_main_window_registers_all_pages(app: QApplication, main_window_class) -> None:
    """Verify that all expected pages are present in the stack."""
    window = main_window_class()

    assert window.stacked_widget.count() == 3
    assert window.stacked_widget.currentWidget() is window.timer_page
    assert window.current_folder_name == "All folders"


def test_sidebar_toggle_changes_visibility(
    app: QApplication, main_window_class
) -> None:
    """Verify that the sidebar toggle button opens and closes the sidebar."""
    window = main_window_class()

    assert window.sidebar.isHidden()
    window.toggle_sidebar()
    assert not window.sidebar.isHidden()
    window.toggle_sidebar()
    assert window.sidebar.isHidden()


def test_page_switching_methods_navigate_correctly(
    app: QApplication, main_window_class
) -> None:
    """Verify that navigation methods point to the right page widgets."""
    window = main_window_class()

    window.switch_to_folders()
    assert window.stacked_widget.currentWidget() is window.folders_page

    window.switch_to_settings()
    assert window.stacked_widget.currentWidget() is window.settings_page

    window.switch_to_settings()
    assert window.stacked_widget.currentWidget() is window.timer_page

    window.switch_to_timer()
    assert window.stacked_widget.currentWidget() is window.timer_page


def test_sidebar_folder_selection_updates_current_folder(
    app: QApplication, main_window_class
) -> None:
    """Verify sidebar folder selection updates the active folder name."""
    window = main_window_class()

    assert window.sidebar_folder_list.count() == 2
    window.switch_to_settings()
    window.handle_sidebar_folder_click(window.sidebar_folder_list.item(0))

    assert window.current_folder_name == "All folders"
    assert window.stacked_widget.currentWidget() is window.timer_page
