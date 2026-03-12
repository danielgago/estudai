"""Management-page workflow controller."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QWidget

from estudai.services.csv_flashcards import replace_flashcards_in_folder
from estudai.ui.application_state import StudyApplicationState
from estudai.ui.pages import ManagementPage

SelectedFolderItemsGetter = Callable[[], list[QListWidgetItem]]
SidebarFolderItemsIter = Callable[[], Iterable[QListWidgetItem]]
FolderNameResolver = Callable[[QListWidgetItem], str]
CheckedFolderIdsGetter = Callable[[], set[str]]
RefreshManagementData = Callable[[set[str]], None]
PageSwitchCallback = Callable[[], None]


class ManagementPageController:
    """Coordinate management-page navigation and persistence workflows."""

    def __init__(
        self,
        *,
        parent: QWidget,
        management_page: ManagementPage,
        app_state: StudyApplicationState,
        selected_folder_items_getter: SelectedFolderItemsGetter,
        sidebar_folder_items_iter: SidebarFolderItemsIter,
        folder_name_resolver: FolderNameResolver,
        checked_folder_ids_getter: CheckedFolderIdsGetter,
        refresh_management_data: RefreshManagementData,
        switch_to_management: PageSwitchCallback,
        switch_to_timer: PageSwitchCallback,
    ) -> None:
        """Initialize the controller.

        Args:
            parent: Parent widget used for modal dialogs.
            management_page: Managed flashcard editor page.
            app_state: Shared folder/selection application state.
            selected_folder_items_getter: Returns currently selected sidebar
                folder items.
            sidebar_folder_items_iter: Iterates sidebar folder items.
            folder_name_resolver: Resolves a folder display name from a sidebar
                item.
            checked_folder_ids_getter: Returns currently checked folder ids.
            refresh_management_data: Reloads persisted folders while preserving
                the provided checked ids.
            switch_to_management: Navigates to the management page.
            switch_to_timer: Navigates back to the timer page.
        """
        self._parent = parent
        self._management_page = management_page
        self._app_state = app_state
        self._selected_folder_items_getter = selected_folder_items_getter
        self._sidebar_folder_items_iter = sidebar_folder_items_iter
        self._folder_name_resolver = folder_name_resolver
        self._checked_folder_ids_getter = checked_folder_ids_getter
        self._refresh_management_data = refresh_management_data
        self._switch_to_management = switch_to_management
        self._switch_to_timer = switch_to_timer
        self._editing_folder_id: str | None = None

    @property
    def editing_folder_id(self) -> str | None:
        """Return the folder currently open in management."""
        return self._editing_folder_id

    def open_from_selection(self) -> None:
        """Open management for one selected or checked sidebar folder."""
        selected_items = self._selected_folder_items_getter()
        if len(selected_items) == 1:
            self._open_for_sidebar_item(selected_items[0])
            return

        checked_items = [
            item
            for item in self._sidebar_folder_items_iter()
            if item.checkState() == Qt.Checked
        ]
        if len(checked_items) == 1:
            self._open_for_sidebar_item(checked_items[0])
            return

        QMessageBox.information(
            self._parent,
            "Manage flashcards",
            "Select one folder (or double-click one) to edit its flashcards.",
        )

    def open_for_folder(self, folder_id: str, folder_name: str) -> None:
        """Open one folder inside the management page.

        Args:
            folder_id: Folder identifier to open.
            folder_name: Display name shown by the management page.
        """
        if not self._app_state.has_folder(folder_id):
            self._refresh_management_data(self._checked_folder_ids_getter())
        if not self._app_state.has_folder(folder_id):
            QMessageBox.warning(
                self._parent,
                "Manage flashcards",
                "This folder is unavailable. Try re-importing it.",
            )
            return

        self._editing_folder_id = folder_id
        self._management_page.set_folder_flashcards(
            folder_id,
            folder_name,
            self._app_state.flashcards_by_folder.get(folder_id, []),
            self._app_state.selected_indexes_for_folder(folder_id),
        )
        self._switch_to_management()

    def delete_selected_flashcards(self) -> None:
        """Delete selected management rows after confirmation."""
        selected_rows = self._management_page.selected_table_rows()
        if not selected_rows:
            QMessageBox.information(
                self._parent,
                "Delete flashcards",
                "Select one or more flashcards first.",
            )
            return

        confirmation = QMessageBox.question(
            self._parent,
            "Delete flashcards",
            f"Delete {len(selected_rows)} selected flashcard(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        self._management_page.remove_rows(selected_rows)

    def save_changes(self) -> None:
        """Persist management-page edits and return to the timer page."""
        if self._editing_folder_id is None:
            QMessageBox.warning(
                self._parent,
                "Save flashcards",
                "No folder selected for editing.",
            )
            return

        folder_path = self._app_state.persisted_folder_paths.get(
            self._editing_folder_id
        )
        if folder_path is None:
            QMessageBox.warning(
                self._parent,
                "Save flashcards",
                "Folder storage is unavailable. Please refresh and try again.",
            )
            return

        try:
            flashcard_rows, selected_indexes = (
                self._management_page.collect_flashcards_for_save()
            )
            replace_flashcards_in_folder(folder_path, flashcard_rows)
        except ValueError as error:
            QMessageBox.warning(self._parent, "Save flashcards", str(error))
            return

        checked_ids = self._checked_folder_ids_getter()
        if selected_indexes:
            checked_ids.add(self._editing_folder_id)
        else:
            checked_ids.discard(self._editing_folder_id)
        self._app_state.update_selected_indexes(
            self._editing_folder_id, selected_indexes
        )
        self._refresh_management_data(checked_ids)
        self._switch_to_timer()

    def _open_for_sidebar_item(self, folder_item: QListWidgetItem) -> None:
        """Open management using one sidebar item.

        Args:
            folder_item: Sidebar item representing the folder to manage.
        """
        folder_id = folder_item.data(Qt.UserRole)
        if folder_id is None:
            return
        self.open_for_folder(folder_id, self._folder_name_resolver(folder_item))
