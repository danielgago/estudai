"""Sidebar folder list behavior helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from estudai.ui.utils import format_card_count

RenameFolder = Callable[[str, str], None]
RefreshSidebarData = Callable[[set[str]], None]
ShowWarning = Callable[[str, str], None]

__all__ = ["SidebarFolderController"]


class SidebarFolderController:
    """Encapsulate sidebar folder-item behavior and rename state."""

    def __init__(self, folder_list: QListWidget, folder_name_role: int) -> None:
        """Initialize the controller."""
        self._folder_list = folder_list
        self._folder_name_role = folder_name_role
        self._renaming_folder_id: str | None = None
        self._renaming_original_name: str | None = None

    @property
    def renaming_folder_id(self) -> str | None:
        """Return the id currently being renamed inline."""
        return self._renaming_folder_id

    @renaming_folder_id.setter
    def renaming_folder_id(self, value: str | None) -> None:
        self._renaming_folder_id = value

    @property
    def renaming_original_name(self) -> str | None:
        """Return the original name of the item being renamed."""
        return self._renaming_original_name

    @renaming_original_name.setter
    def renaming_original_name(self, value: str | None) -> None:
        self._renaming_original_name = value

    def is_folder_item(self, item: QListWidgetItem | None) -> bool:
        """Return whether a sidebar item maps to a persisted folder."""
        return item is not None and item.data(Qt.UserRole) is not None

    def selected_folder_items(self) -> list[QListWidgetItem]:
        """Return selected list items that map to persisted folders."""
        return [
            item
            for item in self._folder_list.selectedItems()
            if self.is_folder_item(item)
        ]

    def iter_folder_items(self) -> Iterator[QListWidgetItem]:
        """Yield sidebar items that map to persisted folders."""
        for index in range(self._folder_list.count()):
            item = self._folder_list.item(index)
            if self.is_folder_item(item):
                yield item

    def clear_rename_tracking(self) -> None:
        """Clear inline-rename tracking state."""
        self._renaming_folder_id = None
        self._renaming_original_name = None

    def checked_folder_ids(self) -> set[str]:
        """Return ids for currently checked folders."""
        return {
            folder_id
            for item in self.iter_folder_items()
            if item.checkState() == Qt.Checked
            for folder_id in [item.data(Qt.UserRole)]
            if folder_id is not None
        }

    def folder_item_name(self, item: QListWidgetItem) -> str:
        """Return folder name without flashcard count suffix."""
        folder_name = item.data(self._folder_name_role)
        return folder_name if isinstance(folder_name, str) else item.text()

    def format_folder_label(self, folder_name: str, flashcard_count: int) -> str:
        """Build sidebar folder label with card count."""
        return f"{folder_name} ({format_card_count(flashcard_count)})"

    def create_folder_item(
        self,
        folder_id: str,
        folder_name: str,
        flashcard_count: int,
        checked: bool,
    ) -> QListWidgetItem:
        """Create one folder item for the sidebar list."""
        folder_item = QListWidgetItem(
            self.format_folder_label(folder_name, flashcard_count)
        )
        folder_item.setData(Qt.UserRole, folder_id)
        folder_item.setData(self._folder_name_role, folder_name)
        folder_item.setFlags(
            folder_item.flags()
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
        )
        folder_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.apply_item_visual_state(folder_item)
        return folder_item

    def apply_item_visual_state(self, item: QListWidgetItem) -> None:
        """Apply visual cues that keep checked folders easy to identify."""
        if not self.is_folder_item(item):
            return
        is_checked = item.checkState() == Qt.Checked
        item_font = item.font()
        item_font.setBold(is_checked)
        item.setFont(item_font)
        item.setData(Qt.ForegroundRole, None)
        item.setData(Qt.BackgroundRole, None)

    def refresh_item_visual_states(self) -> None:
        """Recompute item visuals for current sidebar items."""
        for item in self.iter_folder_items():
            self.apply_item_visual_state(item)

    def begin_rename(self, folder_item: QListWidgetItem) -> None:
        """Start inline rename for one folder."""
        folder_id = folder_item.data(Qt.UserRole)
        if folder_id is None:
            return
        self._renaming_folder_id = folder_id
        self._renaming_original_name = self.folder_item_name(folder_item)
        folder_item.setText(self._renaming_original_name)
        self._folder_list.setCurrentItem(folder_item)
        QTimer.singleShot(0, lambda: self._folder_list.editItem(folder_item))

    def normalize_menu_selection(
        self, clicked_item: QListWidgetItem | None
    ) -> list[QListWidgetItem]:
        """Normalize sidebar selection for a context-menu action."""
        if not self.is_folder_item(clicked_item):
            return []
        if clicked_item is not None and not clicked_item.isSelected():
            self._folder_list.clearSelection()
            clicked_item.setSelected(True)
        return self.selected_folder_items()

    def handle_inline_rename(
        self,
        item: QListWidgetItem,
        *,
        checked_ids: set[str],
        rename_folder: RenameFolder,
        refresh_data: RefreshSidebarData,
        show_warning: ShowWarning,
    ) -> None:
        """Persist folder rename when inline editing changes item text."""
        folder_id = item.data(Qt.UserRole)
        if folder_id is None or folder_id != self._renaming_folder_id:
            return

        new_name = item.text()
        if self._renaming_original_name == new_name:
            return

        self.clear_rename_tracking()
        try:
            rename_folder(folder_id, new_name)
        except (KeyError, ValueError) as error:
            show_warning("Rename folder", str(error))
            refresh_data(checked_ids)
            return
        refresh_data(checked_ids)

    def handle_editor_closed(
        self,
        *,
        checked_ids: set[str],
        refresh_data: RefreshSidebarData,
    ) -> None:
        """Clear inline rename tracking when editor closes."""
        if self._renaming_folder_id is not None:
            refresh_data(checked_ids)
        self.clear_rename_tracking()
