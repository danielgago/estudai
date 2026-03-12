"""Sidebar folder lifecycle workflow controller."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMessageBox, QWidget

from estudai.services.csv_flashcards import Flashcard, replace_flashcards_in_folder
from estudai.services.folder_storage import (
    create_managed_folder,
    delete_persisted_folder,
    import_folder,
    list_persisted_folders,
    move_persisted_folder,
)
from estudai.services.study_progress import delete_folder_progress
from estudai.ui.application_state import StudyApplicationState
from estudai.ui.folder_context import merge_imported_flashcard_indexes

SelectedFolderItemsGetter = Callable[[], list[QListWidgetItem]]
CheckedFolderIdsGetter = Callable[[], set[str]]
HandleFolderDataChanged = Callable[[set[str] | None, str | None], None]
RefreshSidebarFolderProgressLabels = Callable[[set[str] | None], None]
RefreshActiveStudySessionAfterProgressReset = Callable[[set[str]], None]
LoadFolderFlashcards = Callable[[str, Path], tuple[list[Flashcard], str | None]]
ShowWarningMessage = Callable[[str, str], None]


class SidebarFolderOperationsController:
    """Coordinate sidebar folder lifecycle workflows and persistence."""

    def __init__(
        self,
        *,
        parent: QWidget,
        app_state: StudyApplicationState,
        sidebar_folder_list: QListWidget,
        selected_folder_items_getter: SelectedFolderItemsGetter,
        checked_folder_ids_getter: CheckedFolderIdsGetter,
        handle_folder_data_changed: HandleFolderDataChanged,
        refresh_sidebar_folder_progress_labels: RefreshSidebarFolderProgressLabels,
        refresh_active_study_session_after_progress_reset: (
            RefreshActiveStudySessionAfterProgressReset
        ),
        load_folder_flashcards: LoadFolderFlashcards,
        show_warning_message: ShowWarningMessage,
    ) -> None:
        """Initialize the controller.

        Args:
            parent: Parent widget used for dialogs.
            app_state: Shared folder-backed application state.
            sidebar_folder_list: Sidebar list widget used for folder ordering.
            selected_folder_items_getter: Returns currently selected folder items.
            checked_folder_ids_getter: Returns the current checked folder ids.
            handle_folder_data_changed: Reloads persisted folder data while
                preserving checked and selected folder ids.
            refresh_sidebar_folder_progress_labels: Refreshes sidebar labels for
                one or more folders after progress changes.
            refresh_active_study_session_after_progress_reset: Rebuilds the
                active study session when progress resets affect it.
            load_folder_flashcards: Loads the existing flashcards for one folder.
            show_warning_message: Displays a warning dialog.
        """
        self._parent = parent
        self._app_state = app_state
        self._sidebar_folder_list = sidebar_folder_list
        self._selected_folder_items_getter = selected_folder_items_getter
        self._checked_folder_ids_getter = checked_folder_ids_getter
        self._handle_folder_data_changed = handle_folder_data_changed
        self._refresh_sidebar_folder_progress_labels = (
            refresh_sidebar_folder_progress_labels
        )
        self._refresh_active_study_session_after_progress_reset = (
            refresh_active_study_session_after_progress_reset
        )
        self._load_folder_flashcards = load_folder_flashcards
        self._show_warning_message = show_warning_message

    def add_folder(self, folder_path: Path, *, show_errors: bool = False) -> bool:
        """Import one existing flashcard folder into managed storage.

        Args:
            folder_path: Selected source folder path.
            show_errors: Whether import failures should show a warning dialog.

        Returns:
            bool: True when the folder was imported successfully.
        """
        checked_ids = self._checked_folder_ids_getter()
        try:
            persisted_folder = import_folder(folder_path)
        except (FileNotFoundError, NotADirectoryError, OSError) as error:
            if show_errors:
                self._show_warning_message("Import folder", str(error))
            return False
        checked_ids.add(persisted_folder.id)
        self._handle_folder_data_changed(checked_ids, None)
        return True

    def create_folder(self, folder_name: str) -> bool:
        """Create one managed empty folder and refresh sidebar state.

        Args:
            folder_name: User-provided folder name.

        Returns:
            bool: True when the folder was created successfully.
        """
        checked_ids = self._checked_folder_ids_getter()
        try:
            persisted_folder = create_managed_folder(folder_name)
        except ValueError as error:
            self._show_warning_message("Create folder", str(error))
            return False
        checked_ids.add(persisted_folder.id)
        self._handle_folder_data_changed(checked_ids, None)
        return True

    def import_notebooklm_rows(
        self,
        target_folder_id: str,
        valid_rows: list[tuple[str, str]],
    ) -> bool:
        """Append NotebookLM CSV rows into one managed folder.

        Args:
            target_folder_id: Folder that should receive the imported rows.
            valid_rows: Valid question/answer rows returned by the import dialog.

        Returns:
            bool: True when the import was applied successfully.
        """
        persisted_folder = next(
            (
                folder
                for folder in list_persisted_folders()
                if folder.id == target_folder_id
            ),
            None,
        )
        if persisted_folder is None:
            self._show_warning_message(
                "Import NotebookLM CSV",
                "Selected folder is unavailable. Refresh and try again.",
            )
            return False

        target_folder_path = Path(persisted_folder.stored_path)
        existing_flashcards, load_error = self._load_folder_flashcards(
            persisted_folder.name,
            target_folder_path,
        )
        if load_error is not None:
            self._show_warning_message(
                "Import NotebookLM CSV",
                "Existing flashcards in the selected folder could not be read. "
                "The import will replace them.\n"
                f"{load_error}",
            )
        existing_rows = [
            (flashcard.question, flashcard.answer) for flashcard in existing_flashcards
        ]
        replace_flashcards_in_folder(target_folder_path, [*existing_rows, *valid_rows])

        selected_indexes = self._app_state.selected_indexes_for_folder(target_folder_id)
        self._app_state.selected_flashcard_indexes_by_folder[target_folder_id] = (
            merge_imported_flashcard_indexes(
                len(existing_flashcards),
                len(valid_rows),
                selected_indexes,
            )
        )
        checked_ids = self._checked_folder_ids_getter()
        checked_ids.add(target_folder_id)
        self._handle_folder_data_changed(checked_ids, None)
        return True

    def delete_folders(self, folder_items: list[QListWidgetItem]) -> None:
        """Delete one or more persisted folders after confirmation.

        Args:
            folder_items: Sidebar folder items selected for deletion.
        """
        folder_ids = self._folder_ids_from_items(folder_items)
        if not folder_ids:
            return
        confirmation = QMessageBox.question(
            self._parent,
            "Delete folder",
            f"Delete {len(folder_ids)} selected folder(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return

        checked_ids = self._checked_folder_ids_getter() - folder_ids
        for folder_id in folder_ids:
            delete_persisted_folder(folder_id)
        self._handle_folder_data_changed(checked_ids, None)

    def forget_progress_for_folders(
        self,
        folder_items: list[QListWidgetItem],
    ) -> None:
        """Reset persisted study progress for one or many folders.

        Args:
            folder_items: Sidebar folder items selected for progress reset.
        """
        folder_ids = self._folder_ids_from_items(folder_items)
        if not folder_ids:
            return
        self._reset_persisted_study_progress(
            folder_ids,
            title="Forget progress",
            message=(
                f"Forget study progress for {len(folder_ids)} selected folder(s)?\n\n"
                "This resets study statistics only. Flashcards will stay intact."
            ),
        )

    def reset_all_progress(self) -> None:
        """Reset persisted study progress across all loaded folders."""
        folder_ids = set(self._app_state.flashcards_by_folder)
        if not folder_ids:
            return
        self._reset_persisted_study_progress(
            folder_ids,
            title="Reset progress",
            message=(
                "Reset study progress for all folders?\n\n"
                "This resets study statistics only. Flashcards will stay intact."
            ),
        )

    def reset_management_folder_progress(
        self,
        editing_folder_id: str | None,
        folder_name: str,
    ) -> None:
        """Reset study progress for the folder currently open in management.

        Args:
            editing_folder_id: Folder currently open in flashcard management.
            folder_name: Display name shown in the management page title.
        """
        if editing_folder_id is None:
            self._show_warning_message(
                "Reset progress",
                "No folder is open in flashcard management.",
            )
            return
        self._reset_persisted_study_progress(
            {editing_folder_id},
            title="Reset progress",
            message=(
                f'Reset study progress for "{folder_name}"?\n\n'
                "This resets study statistics only. Flashcards will stay intact."
            ),
        )

    def move_selected_folder(self, offset: int) -> None:
        """Persist moving the selected sidebar folder by one position.

        Args:
            offset: Relative row movement to apply.
        """
        selected_items = self._selected_folder_items_getter()
        if len(selected_items) != 1:
            return
        folder_item = selected_items[0]
        folder_id = folder_item.data(Qt.UserRole)
        if folder_id is None:
            return
        current_row = self._sidebar_folder_list.row(folder_item)
        target_row = current_row + offset
        if not (0 <= target_row < self._sidebar_folder_list.count()):
            return
        checked_ids = self._checked_folder_ids_getter()
        try:
            move_persisted_folder(folder_id, target_row)
        except (KeyError, IndexError) as error:
            self._show_warning_message("Move folder", str(error))
            self._handle_folder_data_changed(checked_ids, None)
            return
        self._handle_folder_data_changed(checked_ids, folder_id)

    def _reset_persisted_study_progress(
        self,
        folder_ids: set[str],
        *,
        title: str,
        message: str,
    ) -> None:
        """Confirm and reset persisted study progress for selected folders.

        Args:
            folder_ids: Folder ids whose persisted study progress should be
                cleared.
            title: Dialog title for the confirmation prompt.
            message: Confirmation prompt body.
        """
        if not folder_ids:
            return
        confirmation = QMessageBox.question(
            self._parent,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        for folder_id in folder_ids:
            delete_folder_progress(folder_id)
        self._refresh_sidebar_folder_progress_labels(folder_ids)
        self._refresh_active_study_session_after_progress_reset(folder_ids)

    @staticmethod
    def _folder_ids_from_items(folder_items: list[QListWidgetItem]) -> set[str]:
        """Return managed folder ids represented by sidebar items.

        Args:
            folder_items: Sidebar folder items to inspect.

        Returns:
            set[str]: Folder ids found in the provided items.
        """
        folder_ids: set[str] = set()
        for item in folder_items:
            folder_id = item.data(Qt.UserRole)
            if folder_id is not None:
                folder_ids.add(folder_id)
        return folder_ids
