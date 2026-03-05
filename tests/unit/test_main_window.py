"""Main window tests."""

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from estudai.services.folder_storage import list_persisted_folders
from estudai.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an isolated app data directory for each test."""
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(tmp_path / "app-data"))


def test_main_window_registers_all_pages(app: QApplication) -> None:
    """Verify that all expected pages are present in the stack."""
    window = MainWindow()

    assert window.stacked_widget.count() == 2
    assert window.stacked_widget.currentWidget() is window.timer_page
    assert window.current_folder_name == "No folders selected"


def test_sidebar_toggle_changes_visibility(app: QApplication) -> None:
    """Verify that the sidebar toggle button opens and closes the sidebar."""
    window = MainWindow()

    assert window.sidebar.isHidden()
    window.toggle_sidebar()
    assert not window.sidebar.isHidden()
    window.toggle_sidebar()
    assert window.sidebar.isHidden()


def test_page_switching_methods_navigate_correctly(app: QApplication) -> None:
    """Verify that navigation methods point to the right page widgets."""
    window = MainWindow()

    window.switch_to_settings()
    assert window.stacked_widget.currentWidget() is window.settings_page

    window.switch_to_settings()
    assert window.stacked_widget.currentWidget() is window.timer_page

    window.switch_to_timer()
    assert window.stacked_widget.currentWidget() is window.timer_page


def test_sidebar_folder_selection_updates_current_folder(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify folder checkbox updates selected flashcard scope."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "What is DNA?,Genetic material.\n",
        encoding="utf-8",
    )
    window.add_folder(biology_folder)
    folder_item = window.sidebar_folder_list.item(0)

    folder_item.setCheckState(Qt.Unchecked)
    assert window.current_folder_name == "No folders selected"
    assert len(window.loaded_flashcards) == 0

    folder_item.setCheckState(Qt.Checked)
    assert window.current_folder_name == "biology"
    assert len(window.loaded_flashcards) == 1


def test_add_folder_loads_csv_flashcards(app: QApplication, tmp_path: Path) -> None:
    """Verify adding a folder loads CSV flashcards and updates selection context."""
    window = MainWindow()
    flashcards_folder = tmp_path / "biology"
    flashcards_folder.mkdir()
    (flashcards_folder / "cards.csv").write_text(
        "What is DNA?,Genetic material.\nWhat is RNA?,Messenger molecule.\n",
        encoding="utf-8",
    )

    added = window.add_folder(flashcards_folder)
    folder_item = window.sidebar_folder_list.item(0)
    window.handle_sidebar_folder_click(folder_item)
    persisted = list_persisted_folders()

    assert added is True
    assert window.sidebar_folder_list.count() == 1
    assert window.current_folder_name == "biology"
    assert len(window.loaded_flashcards) == 2
    assert len(persisted) == 1
    assert (Path(persisted[0].stored_path) / "cards.csv").exists()
    assert window.stacked_widget.currentWidget() is window.timer_page
    assert window.timer_page.folder_context_label.text() == "Folder: biology (2 cards)"


def test_folder_copy_persists_after_source_deletion(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify copied folder data is still available after source deletion."""
    source_folder = tmp_path / "Desktop" / "chemistry"
    source_folder.mkdir(parents=True)
    (source_folder / "cards.csv").write_text(
        "What is NaCl?,Salt.\n",
        encoding="utf-8",
    )

    first_window = MainWindow()
    assert first_window.add_folder(source_folder) is True
    shutil.rmtree(source_folder)

    second_window = MainWindow()
    assert second_window.sidebar_folder_list.count() == 1

    second_window.handle_sidebar_folder_click(second_window.sidebar_folder_list.item(0))
    assert second_window.current_folder_name == "chemistry"
    assert len(second_window.loaded_flashcards) == 1
    assert (
        second_window.timer_page.folder_context_label.text()
        == "Folder: chemistry (1 cards)"
    )


def test_multiple_checked_folders_aggregate_flashcards(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify checking multiple folders aggregates flashcards in timer scope."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    chemistry_folder = tmp_path / "chemistry"
    biology_folder.mkdir()
    chemistry_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "DNA?,Genetic material.\n", encoding="utf-8"
    )
    (chemistry_folder / "cards.csv").write_text("NaCl?,Salt.\n", encoding="utf-8")

    assert window.add_folder(biology_folder) is True
    assert window.add_folder(chemistry_folder) is True
    assert window.current_folder_name == "2 folders selected"
    assert len(window.loaded_flashcards) == 2

    first_item = window.sidebar_folder_list.item(0)
    first_item.setCheckState(Qt.Unchecked)
    assert len(window.loaded_flashcards) == 1


def test_sidebar_folder_context_actions_rename_and_delete(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify sidebar helpers rename and delete folders from context-menu actions."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "DNA?,Genetic material.\n", encoding="utf-8"
    )
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)

    monkeypatch.setattr(
        "estudai.ui.main_window.QInputDialog.getText",
        lambda *args, **kwargs: ("Biology Updated", True),
    )
    window.rename_sidebar_folder(folder_item)
    renamed_item = window.sidebar_folder_list.item(0)
    assert renamed_item.text() == "Biology Updated"

    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    window.delete_sidebar_folders([renamed_item])
    assert list_persisted_folders() == []
