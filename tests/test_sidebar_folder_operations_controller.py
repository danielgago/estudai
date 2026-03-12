"""Sidebar folder operations controller tests."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)

from estudai.services.csv_flashcards import load_flashcards_from_folder
from estudai.services.folder_storage import (
    create_managed_folder,
    import_folder,
    list_persisted_folders,
)
from estudai.services.study_progress import (
    FlashcardProgress,
    FlashcardProgressEntry,
    load_folder_progress,
    save_progress_entries,
)
from estudai.ui.application_state import FolderLibraryState, StudyApplicationState
from estudai.ui.controllers.sidebar_folder_operations_controller import (
    SidebarFolderOperationsController,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for controller tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an isolated application data directory for each test."""
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(tmp_path / "app-data"))


def _build_controller(
    *,
    app_state: StudyApplicationState,
    sidebar_folder_list: QListWidget | None = None,
    selected_folder_items_getter=None,
    checked_folder_ids_getter=None,
    handle_folder_data_changed=None,
    refresh_sidebar_folder_progress_labels=None,
    refresh_active_study_session_after_progress_reset=None,
    load_folder_flashcards=None,
    show_warning_message=None,
) -> SidebarFolderOperationsController:
    """Create a sidebar operations controller with injectable test callbacks."""
    folder_list = sidebar_folder_list or QListWidget()
    return SidebarFolderOperationsController(
        parent=QWidget(),
        app_state=app_state,
        sidebar_folder_list=folder_list,
        selected_folder_items_getter=selected_folder_items_getter or (lambda: []),
        checked_folder_ids_getter=checked_folder_ids_getter or (lambda: set()),
        handle_folder_data_changed=handle_folder_data_changed
        or (lambda _checked_ids, _current_folder_id: None),
        refresh_sidebar_folder_progress_labels=(
            refresh_sidebar_folder_progress_labels or (lambda _folder_ids: None)
        ),
        refresh_active_study_session_after_progress_reset=(
            refresh_active_study_session_after_progress_reset
            or (lambda _folder_ids: None)
        ),
        load_folder_flashcards=load_folder_flashcards
        or (
            lambda _folder_name, folder_path: (
                load_flashcards_from_folder(folder_path),
                None,
            )
        ),
        show_warning_message=show_warning_message or (lambda _title, _message: None),
    )


def _create_source_folder(tmp_path: Path, name: str, csv_text: str) -> Path:
    """Create a source folder with flashcards for import tests."""
    folder = tmp_path / name
    folder.mkdir()
    (folder / "cards.csv").write_text(csv_text, encoding="utf-8")
    return folder


def _create_sidebar_item(folder_id: str, label: str) -> QListWidgetItem:
    """Create one sidebar list item for controller tests."""
    item = QListWidgetItem(label)
    item.setData(Qt.UserRole, folder_id)
    return item


def test_create_folder_refreshes_checked_ids(app: QApplication) -> None:
    """Verify creating a folder requests a sidebar refresh with the new id."""
    app_state = StudyApplicationState()
    checked_ids = {"existing-folder"}
    refresh_calls: list[tuple[set[str] | None, str | None]] = []
    controller = _build_controller(
        app_state=app_state,
        checked_folder_ids_getter=lambda: checked_ids,
        handle_folder_data_changed=lambda selected_ids, current_folder_id: (
            refresh_calls.append(
                (
                    None if selected_ids is None else set(selected_ids),
                    current_folder_id,
                )
            )
        ),
    )

    assert controller.create_folder("Biology") is True

    persisted_folders = list_persisted_folders()
    assert len(persisted_folders) == 1
    assert persisted_folders[0].name == "Biology"
    assert refresh_calls == [({"existing-folder", persisted_folders[0].id}, None)]


def test_add_folder_missing_path_surfaces_warning(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify import failures can surface a warning without refreshing sidebar data."""
    app_state = StudyApplicationState()
    warnings: list[tuple[str, str]] = []
    refresh_calls: list[tuple[set[str] | None, str | None]] = []
    controller = _build_controller(
        app_state=app_state,
        handle_folder_data_changed=lambda selected_ids, current_folder_id: (
            refresh_calls.append((selected_ids, current_folder_id))
        ),
        show_warning_message=lambda title, message: warnings.append((title, message)),
    )

    added = controller.add_folder(tmp_path / "missing", show_errors=True)

    assert added is False
    assert warnings
    assert warnings[0][0] == "Import folder"
    assert "Folder not found" in warnings[0][1]
    assert refresh_calls == []


def test_move_selected_folder_preserves_current_folder(app: QApplication) -> None:
    """Verify reordering keeps the moved folder selected after refresh."""
    first_folder = create_managed_folder("Biology")
    second_folder = create_managed_folder("Chemistry")
    folder_list = QListWidget()
    first_item = _create_sidebar_item(first_folder.id, first_folder.name)
    second_item = _create_sidebar_item(second_folder.id, second_folder.name)
    folder_list.addItem(first_item)
    folder_list.addItem(second_item)
    checked_ids = {first_folder.id, second_folder.id}
    refresh_calls: list[tuple[set[str] | None, str | None]] = []
    controller = _build_controller(
        app_state=StudyApplicationState(),
        sidebar_folder_list=folder_list,
        selected_folder_items_getter=lambda: [first_item],
        checked_folder_ids_getter=lambda: checked_ids,
        handle_folder_data_changed=lambda selected_ids, current_folder_id: (
            refresh_calls.append(
                (
                    None if selected_ids is None else set(selected_ids),
                    current_folder_id,
                )
            )
        ),
    )

    controller.move_selected_folder(1)

    persisted_folders = list_persisted_folders()
    assert [folder.id for folder in persisted_folders] == [
        second_folder.id,
        first_folder.id,
    ]
    assert refresh_calls == [({first_folder.id, second_folder.id}, first_folder.id)]


def test_forget_progress_refreshes_labels_and_session(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify resetting progress refreshes sidebar labels and active study state."""
    folder = create_managed_folder("Biology")
    save_progress_entries(
        [
            FlashcardProgressEntry(
                folder_id=folder.id,
                flashcard_id="card-1",
                progress=FlashcardProgress(correct_count=2, wrong_count=1),
            )
        ]
    )
    folder_item = _create_sidebar_item(folder.id, folder.name)
    label_refreshes: list[set[str] | None] = []
    session_refreshes: list[set[str]] = []
    controller = _build_controller(
        app_state=StudyApplicationState(),
        refresh_sidebar_folder_progress_labels=lambda folder_ids: (
            label_refreshes.append(None if folder_ids is None else set(folder_ids))
        ),
        refresh_active_study_session_after_progress_reset=lambda folder_ids: (
            session_refreshes.append(set(folder_ids))
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.controllers.sidebar_folder_operations_controller.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )

    controller.forget_progress_for_folders([folder_item])

    assert load_folder_progress(folder.id) == {}
    assert label_refreshes == [{folder.id}]
    assert session_refreshes == [{folder.id}]


def test_import_notebooklm_rows_marks_new_indexes_selected(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify imported NotebookLM rows stay selected until the next reload."""
    source_folder = _create_source_folder(tmp_path, "biology", "Q1?,A1.\n")
    persisted_folder = import_folder(source_folder)
    stored_path = Path(persisted_folder.stored_path)
    existing_flashcards = load_flashcards_from_folder(stored_path)
    app_state = StudyApplicationState()
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id=persisted_folder.id,
                folder_name=persisted_folder.name,
                folder_path=stored_path,
                flashcards=existing_flashcards,
                selected_indexes={0},
            )
        ]
    )
    refresh_calls: list[tuple[set[str] | None, str | None]] = []
    controller = _build_controller(
        app_state=app_state,
        checked_folder_ids_getter=lambda: set(),
        handle_folder_data_changed=lambda selected_ids, current_folder_id: (
            refresh_calls.append(
                (
                    None if selected_ids is None else set(selected_ids),
                    current_folder_id,
                )
            )
        ),
        load_folder_flashcards=lambda _folder_name, folder_path: (
            load_flashcards_from_folder(folder_path),
            None,
        ),
    )

    imported = controller.import_notebooklm_rows(
        persisted_folder.id,
        [("Q2?", "A2."), ("Q3?", "A3.")],
    )

    assert imported is True
    assert len(load_flashcards_from_folder(stored_path)) == 3
    assert app_state.selected_flashcard_indexes_by_folder[persisted_folder.id] == {
        0,
        1,
        2,
    }
    assert refresh_calls == [({persisted_folder.id}, None)]
