"""Sidebar folder lifecycle workflow controller."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from estudai.services.csv_flashcards import (
    Flashcard,
    FlashcardRowData,
    replace_flashcards_in_folder,
)
from estudai.services.folder_storage import (
    child_folder_ids,
    create_managed_folder,
    delete_persisted_folder,
    import_folder,
    list_persisted_folders,
    move_persisted_folder,
    reparent_persisted_folder,
)
from estudai.services.study_progress import delete_folder_progress
from estudai.ui.application_state import StudyApplicationState
from estudai.ui.folder_context import merge_imported_flashcard_indexes
from estudai.ui.message_box import MessageBoxPresenter
from estudai.ui.sidebar_folders import SidebarFolderItem, SidebarFolderTreeWidget

SelectedFolderItemsGetter = Callable[[], list[SidebarFolderItem]]
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
        sidebar_folder_list: SidebarFolderTreeWidget,
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
        self._message_box = MessageBoxPresenter(parent)

    def add_folder(
        self,
        folder_path: Path,
        *,
        parent_id: str | None = None,
        show_errors: bool = False,
        split_csv_into_subfolders: bool = False,
    ) -> bool:
        """Import one existing flashcard folder into managed storage.

        Args:
            folder_path: Selected source folder path.
            parent_id: Optional parent folder id for nested imports.
            show_errors: Whether import failures should show a warning dialog.
            split_csv_into_subfolders: Whether directories with multiple CSV files
                should create one child folder per CSV during import.

        Returns:
            bool: True when the folder was imported successfully.
        """
        checked_ids = self._checked_folder_ids_getter()
        try:
            persisted_folder = import_folder(
                folder_path,
                parent_id=parent_id,
                split_csv_into_subfolders=split_csv_into_subfolders,
            )
        except (FileNotFoundError, NotADirectoryError, OSError, KeyError) as error:
            if show_errors:
                self._show_warning_message("Import folder", str(error))
            return False
        checked_ids.add(persisted_folder.id)
        checked_ids.update(child_folder_ids(persisted_folder.id))
        self._handle_folder_data_changed(checked_ids, None)
        return True

    def create_folder(
        self,
        folder_name: str,
        *,
        parent_id: str | None = None,
    ) -> bool:
        """Create one managed empty folder and refresh sidebar state.

        Args:
            folder_name: User-provided folder name.
            parent_id: Optional parent folder id for nested creation.

        Returns:
            bool: True when the folder was created successfully.
        """
        checked_ids = self._checked_folder_ids_getter()
        try:
            persisted_folder = create_managed_folder(folder_name, parent_id=parent_id)
        except (KeyError, ValueError) as error:
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
            FlashcardRowData(
                question=flashcard.question,
                answer=flashcard.answer,
                question_image_path=flashcard.question_image_path,
                answer_image_path=flashcard.answer_image_path,
            )
            for flashcard in existing_flashcards
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

    def delete_folders(self, folder_items: list[SidebarFolderItem]) -> None:
        """Delete one or more persisted folders after confirmation.

        Args:
            folder_items: Sidebar folder items selected for deletion.
        """
        folder_ids = self._folder_ids_from_items(folder_items)
        if not folder_ids:
            return
        deleting_nested = any(child_folder_ids(folder_id) for folder_id in folder_ids)
        confirmation = self._message_box.confirm_yes_no(
            "Delete folder",
            (
                f"Delete {len(folder_ids)} selected folder(s) and any nested subfolders?"
                if deleting_nested
                else f"Delete {len(folder_ids)} selected folder(s)?"
            ),
            default_button=QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return

        checked_ids = self._checked_folder_ids_getter() - folder_ids
        for folder_id in folder_ids:
            delete_persisted_folder(folder_id)
        self._handle_folder_data_changed(checked_ids, None)

    def forget_progress_for_folders(
        self,
        folder_items: list[SidebarFolderItem],
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
        parent_item = folder_item.parent()
        parent_folder_id = (
            parent_item.data(Qt.UserRole)
            if isinstance(parent_item, SidebarFolderItem)
            else None
        )
        current_row = (
            parent_item.indexOfChild(folder_item)
            if isinstance(parent_item, SidebarFolderItem)
            else self._sidebar_folder_list.indexOfTopLevelItem(folder_item)
        )
        sibling_count = (
            parent_item.childCount()
            if isinstance(parent_item, SidebarFolderItem)
            else self._sidebar_folder_list.topLevelItemCount()
        )
        target_row = current_row + offset
        if not (0 <= target_row < sibling_count):
            return
        checked_ids = self._checked_folder_ids_getter()
        try:
            move_persisted_folder(folder_id, target_row, parent_id=parent_folder_id)
        except (KeyError, IndexError, ValueError) as error:
            self._show_warning_message("Move folder", str(error))
            self._handle_folder_data_changed(checked_ids, None)
            return
        self._handle_folder_data_changed(checked_ids, folder_id)

    def move_selected_folder_in(self) -> None:
        """Nest the selected folder under its previous sibling."""
        selected_items = self._selected_folder_items_getter()
        if len(selected_items) != 1:
            return
        folder_item = selected_items[0]
        parent_item = folder_item.parent()
        current_row = (
            parent_item.indexOfChild(folder_item)
            if isinstance(parent_item, SidebarFolderItem)
            else self._sidebar_folder_list.indexOfTopLevelItem(folder_item)
        )
        if current_row <= 0:
            return
        previous_sibling = (
            parent_item.child(current_row - 1)
            if isinstance(parent_item, SidebarFolderItem)
            else self._sidebar_folder_list.topLevelItem(current_row - 1)
        )
        if not isinstance(previous_sibling, SidebarFolderItem):
            return
        folder_id = folder_item.data(Qt.UserRole)
        previous_sibling_id = previous_sibling.data(Qt.UserRole)
        if folder_id is None or previous_sibling_id is None:
            return
        checked_ids = self._checked_folder_ids_getter()
        try:
            reparent_persisted_folder(folder_id, previous_sibling_id)
        except (KeyError, IndexError, ValueError) as error:
            self._show_warning_message("Move folder", str(error))
            self._handle_folder_data_changed(checked_ids, None)
            return
        self._handle_folder_data_changed(checked_ids, folder_id)

    def move_selected_folder_out(self) -> None:
        """Promote the selected folder to its parent's level."""
        selected_items = self._selected_folder_items_getter()
        if len(selected_items) != 1:
            return
        folder_item = selected_items[0]
        parent_item = folder_item.parent()
        if not isinstance(parent_item, SidebarFolderItem):
            return
        folder_id = folder_item.data(Qt.UserRole)
        parent_folder_id = parent_item.data(Qt.UserRole)
        if folder_id is None or parent_folder_id is None:
            return
        grandparent_item = parent_item.parent()
        grandparent_folder_id = (
            grandparent_item.data(Qt.UserRole)
            if isinstance(grandparent_item, SidebarFolderItem)
            else None
        )
        parent_row = (
            grandparent_item.indexOfChild(parent_item)
            if isinstance(grandparent_item, SidebarFolderItem)
            else self._sidebar_folder_list.indexOfTopLevelItem(parent_item)
        )
        checked_ids = self._checked_folder_ids_getter()
        try:
            reparent_persisted_folder(
                folder_id,
                grandparent_folder_id,
                new_index=parent_row + 1,
            )
        except (KeyError, IndexError, ValueError) as error:
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
        confirmation = self._message_box.confirm_yes_no(
            title,
            message,
            default_button=QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        for folder_id in folder_ids:
            delete_folder_progress(folder_id)
        self._refresh_sidebar_folder_progress_labels(folder_ids)
        self._refresh_active_study_session_after_progress_reset(folder_ids)

    @staticmethod
    def _folder_ids_from_items(folder_items: list[SidebarFolderItem]) -> set[str]:
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
