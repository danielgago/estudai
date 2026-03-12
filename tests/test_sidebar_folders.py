"""Sidebar folder controller tests."""

import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from estudai.ui.sidebar_folders import SidebarFolderController, SidebarFolderTreeWidget

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for widget tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


def test_sidebar_folder_controller_creates_items_and_tracks_checked_ids(
    app: QApplication,
) -> None:
    """Verify created folder items keep the expected label and checked state."""
    folder_list = SidebarFolderTreeWidget()
    controller = SidebarFolderController(folder_list, Qt.UserRole + 1)

    first_item = controller.create_folder_item("bio", "Biology", 2, 50, True)
    second_item = controller.create_folder_item("chem", "Chemistry", 1, 0, False)
    folder_list.addItem(first_item)
    folder_list.addItem(second_item)

    assert first_item.text() == "Biology (2 cards | 50% done)"
    assert second_item.text() == "Chemistry (1 card | 0% done)"
    assert first_item.font().bold() is True
    assert second_item.font().bold() is False
    assert controller.checked_folder_ids() == {"bio"}


def test_sidebar_folder_controller_normalizes_context_menu_selection(
    app: QApplication,
) -> None:
    """Verify context-menu selection is narrowed to the clicked folder item."""
    folder_list = SidebarFolderTreeWidget()
    controller = SidebarFolderController(folder_list, Qt.UserRole + 1)
    first_item = controller.create_folder_item("bio", "Biology", 1, 0, True)
    second_item = controller.create_folder_item("chem", "Chemistry", 1, 0, True)
    folder_list.addItem(first_item)
    folder_list.addItem(second_item)
    first_item.setSelected(True)

    selected_items = controller.normalize_menu_selection(second_item)

    assert selected_items == [second_item]
    assert second_item.isSelected() is True
    assert first_item.isSelected() is False
