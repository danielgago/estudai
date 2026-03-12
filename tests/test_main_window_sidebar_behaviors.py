"""Additional sidebar behavior tests for main window."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from estudai.services.folder_storage import PersistedFolder, list_persisted_folders
from estudai.services.study_progress import (
    FlashcardProgress,
    FlashcardProgressEntry,
    load_folder_progress,
    save_progress_entries,
)
from estudai.ui.main_window import MainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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


def _add_sample_folder(
    window: MainWindow, tmp_path: Path, name: str = "biology"
) -> None:
    """Create and add a sample folder with one flashcard."""
    folder = tmp_path / name
    folder.mkdir()
    (folder / "cards.csv").write_text("Q?,A.\n", encoding="utf-8")
    assert window.add_folder(folder) is True


def test_inline_rename_triggers_editor(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify rename action starts inline editor through timer callback."""
    window = MainWindow()
    _add_sample_folder(window, tmp_path)
    folder_item = window.sidebar_folder_list.item(0)
    edited_items: list[object] = []

    monkeypatch.setattr(
        "estudai.ui.main_window.QTimer.singleShot",
        lambda _delay, callback: callback(),
    )
    monkeypatch.setattr(
        window.sidebar_folder_list, "editItem", lambda item: edited_items.append(item)
    )

    window.rename_sidebar_folder(folder_item)

    assert edited_items == [folder_item]
    assert window._renaming_folder_id == folder_item.data(Qt.UserRole)


def test_inline_rename_invalid_name_shows_warning(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify invalid inline rename surfaces warning and keeps persisted value."""
    window = MainWindow()
    _add_sample_folder(window, tmp_path)
    folder_item = window.sidebar_folder_list.item(0)
    warnings: list[str] = []

    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.warning",
        lambda *_args: warnings.append("warning"),
    )
    window.rename_sidebar_folder(folder_item)
    folder_item.setText("   ")

    assert warnings
    assert window.sidebar_folder_list.item(0).text() == "biology (1 card | 0% done)"


def test_sidebar_editor_closed_clears_tracking(app: QApplication) -> None:
    """Verify editor close handler clears rename tracking state."""
    window = MainWindow()
    window._renaming_folder_id = "x"
    window._renaming_original_name = "y"

    window.handle_sidebar_editor_closed(None)

    assert window._renaming_folder_id is None
    assert window._renaming_original_name is None


def test_sidebar_click_ignores_non_folder_item(app: QApplication) -> None:
    """Verify clicking placeholder item does not navigate away."""
    window = MainWindow()
    window.switch_to_settings()
    placeholder_item = window.sidebar_folder_list.item(0)

    window.handle_sidebar_folder_click(placeholder_item)

    assert window.stacked_widget.currentWidget() is window.settings_page


def test_open_sidebar_menu_rename_action_uses_expected_labels(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify context menu labels and rename dispatch are correct."""
    window = MainWindow()
    _add_sample_folder(window, tmp_path)
    folder_item = window.sidebar_folder_list.item(0)
    called: list[str] = []

    class _FakeAction:
        def __init__(self, text: str) -> None:
            self.text = text
            self.tooltip = ""
            self.enabled = True

        def setToolTip(self, value: str) -> None:  # noqa: N802
            self.tooltip = value

        def setEnabled(self, enabled: bool) -> None:  # noqa: N802
            self.enabled = enabled

    class _FakeMenu:
        last_instance = None

        def __init__(self, *_args, **_kwargs) -> None:
            self.actions: list[_FakeAction] = []
            _FakeMenu.last_instance = self

        def addAction(self, text: str) -> _FakeAction:  # noqa: N802
            action = _FakeAction(text)
            self.actions.append(action)
            return action

        def exec(self, *_args, **_kwargs):  # noqa: A003
            return self.actions[0]

    monkeypatch.setattr("estudai.ui.main_window.QMenu", _FakeMenu)
    monkeypatch.setattr(window.sidebar_folder_list, "itemAt", lambda _pos: folder_item)
    monkeypatch.setattr(
        window, "rename_sidebar_folder", lambda _item: called.append("rename")
    )
    monkeypatch.setattr(
        window,
        "forget_sidebar_folder_progress",
        lambda _items: called.append("forget"),
    )
    monkeypatch.setattr(
        window, "delete_sidebar_folders", lambda _items: called.append("delete")
    )

    window.open_sidebar_folder_menu(QPoint(0, 0))

    assert called == ["rename"]
    assert [action.text for action in _FakeMenu.last_instance.actions] == [
        "Rename",
        "Forget progress",
        "Delete",
    ]
    assert [action.tooltip for action in _FakeMenu.last_instance.actions] == [
        "Rename",
        "Reset folder progress",
        "Delete",
    ]


def test_open_sidebar_menu_forget_progress_dispatch_and_cancel_reset(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify forget-progress dispatch and cancellation preserve persisted counts."""
    window = MainWindow()
    _add_sample_folder(window, tmp_path, "biology")
    _add_sample_folder(window, tmp_path, "chemistry")
    first_item = window.sidebar_folder_list.item(0)
    second_item = window.sidebar_folder_list.item(1)
    first_folder_id = first_item.data(Qt.UserRole)
    assert first_folder_id is not None
    called: list[str] = []

    save_progress_entries(
        [
            FlashcardProgressEntry(
                folder_id=first_folder_id,
                flashcard_id="card-1",
                progress=FlashcardProgress(correct_count=2, wrong_count=1),
            )
        ]
    )

    class _FakeAction:
        def __init__(self, text: str) -> None:
            self.text = text
            self.enabled = True

        def setToolTip(self, _value: str) -> None:  # noqa: N802
            pass

        def setEnabled(self, enabled: bool) -> None:  # noqa: N802
            self.enabled = enabled

    class _FakeMenu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.actions: list[_FakeAction] = []

        def addAction(self, text: str) -> _FakeAction:  # noqa: N802
            action = _FakeAction(text)
            self.actions.append(action)
            return action

        def exec(self, *_args, **_kwargs):  # noqa: A003
            return self.actions[1]

    monkeypatch.setattr("estudai.ui.main_window.QMenu", _FakeMenu)
    monkeypatch.setattr(window.sidebar_folder_list, "itemAt", lambda _pos: first_item)
    monkeypatch.setattr(
        window, "_selected_folder_items", lambda: [first_item, second_item]
    )
    monkeypatch.setattr(
        window, "rename_sidebar_folder", lambda _item: called.append("rename")
    )
    monkeypatch.setattr(
        window,
        "forget_sidebar_folder_progress",
        lambda _items: called.append("forget"),
    )
    monkeypatch.setattr(
        window, "delete_sidebar_folders", lambda _items: called.append("delete")
    )

    window.open_sidebar_folder_menu(QPoint(0, 0))
    assert called == ["forget"]

    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.No,
    )
    window.forget_sidebar_folder_progress([first_item])

    assert load_folder_progress(first_folder_id) == {
        "card-1": FlashcardProgress(correct_count=2, wrong_count=1)
    }


def test_open_sidebar_menu_delete_dispatch_and_cancel_delete(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify delete dispatch from menu and cancellation keeps folders."""
    window = MainWindow()
    _add_sample_folder(window, tmp_path, "biology")
    _add_sample_folder(window, tmp_path, "chemistry")
    first_item = window.sidebar_folder_list.item(0)
    second_item = window.sidebar_folder_list.item(1)
    called: list[str] = []

    class _FakeAction:
        def __init__(self, text: str) -> None:
            self.text = text
            self.enabled = True

        def setToolTip(self, _value: str) -> None:  # noqa: N802
            pass

        def setEnabled(self, enabled: bool) -> None:  # noqa: N802
            self.enabled = enabled

    class _FakeMenu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.actions: list[_FakeAction] = []

        def addAction(self, text: str) -> _FakeAction:  # noqa: N802
            action = _FakeAction(text)
            self.actions.append(action)
            return action

        def exec(self, *_args, **_kwargs):  # noqa: A003
            return self.actions[2]

    monkeypatch.setattr("estudai.ui.main_window.QMenu", _FakeMenu)
    monkeypatch.setattr(window.sidebar_folder_list, "itemAt", lambda _pos: first_item)
    monkeypatch.setattr(
        window, "_selected_folder_items", lambda: [first_item, second_item]
    )
    monkeypatch.setattr(
        window, "rename_sidebar_folder", lambda _item: called.append("rename")
    )
    monkeypatch.setattr(
        window,
        "forget_sidebar_folder_progress",
        lambda _items: called.append("forget"),
    )
    monkeypatch.setattr(
        window, "delete_sidebar_folders", lambda _items: called.append("delete")
    )

    window.open_sidebar_folder_menu(QPoint(0, 0))
    assert called == ["delete"]

    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.No,
    )
    window.delete_sidebar_folders([first_item])
    assert len(list_persisted_folders()) == 2


def test_prompt_add_folder_cancel_and_invalid_path(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify folder picker cancellation and invalid path are handled safely."""
    window = MainWindow()
    monkeypatch.setattr(
        "estudai.ui.main_window.QFileDialog.getExistingDirectory",
        lambda *_args, **_kwargs: "",
    )
    window.prompt_and_add_folder()
    assert window.sidebar_folder_list.item(0).text() == "No saved folders yet."

    assert window.add_folder(tmp_path / "missing") is False


def test_handle_management_data_changed_skips_missing_stored_folder(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify sidebar refresh ignores persisted folders with missing storage."""
    window = MainWindow()
    fake_folder = PersistedFolder(
        id="ghost",
        name="ghost",
        source_path="",
        stored_path=str(tmp_path / "not-there"),
    )
    monkeypatch.setattr(
        "estudai.services.folder_catalog.list_persisted_folders",
        lambda: [fake_folder],
    )

    window.handle_management_data_changed()

    assert window.sidebar_folder_list.count() == 1
    assert window.sidebar_folder_list.item(0).text() == "No saved folders yet."


def test_set_navigation_visible_hides_sidebar_and_buttons(app: QApplication) -> None:
    """Verify focused mode hides navigation and sidebar."""
    window = MainWindow()
    window.toggle_sidebar()
    assert not window.sidebar.isHidden()

    window.set_navigation_visible(False)

    assert not window.sidebar_toggle_button.isVisible()
    assert not window.settings_button.isVisible()
    assert not window.sidebar.isVisible()
