"""Sidebar folder tree behavior helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from estudai.ui.utils import format_card_count

RenameFolder = Callable[[str, str], None]
RefreshSidebarData = Callable[[set[str]], None]
ShowWarning = Callable[[str, str], None]

__all__ = [
    "SidebarFolderController",
    "SidebarFolderItem",
    "SidebarFolderTreeWidget",
]


class SidebarFolderItem(QTreeWidgetItem):
    """Tree item that preserves the sidebar's previous list-style API."""

    def text(self, column: int = 0) -> str:  # type: ignore[override]
        """Return item text for the provided column.

        Args:
            column: Tree column index.

        Returns:
            str: Item text.
        """
        return super().text(column)

    def setText(self, column_or_text: int | str, text: str | None = None) -> None:  # type: ignore[override]
        """Set item text using either tree-style or list-style calling.

        Args:
            column_or_text: Column index or text when using the default column.
            text: Optional text used with the explicit column overload.
        """
        if text is None:
            super().setText(0, str(column_or_text))
            return
        super().setText(int(column_or_text), text)

    def data(self, column_or_role: int, role: int | None = None):  # type: ignore[override]
        """Return item data using either tree-style or list-style calling.

        Args:
            column_or_role: Column index or item-data role.
            role: Optional explicit item-data role.

        Returns:
            object: Stored item data.
        """
        if role is None:
            return super().data(0, column_or_role)
        return super().data(column_or_role, role)

    def setData(  # type: ignore[override]
        self,
        column_or_role: int,
        role_or_value: int | object,
        value: object | None = None,
    ) -> None:
        """Set item data using either tree-style or list-style calling.

        Args:
            column_or_role: Column index or item-data role.
            role_or_value: Explicit role or the value for the default column.
            value: Optional explicit value for the explicit-column overload.
        """
        if value is None:
            super().setData(0, column_or_role, role_or_value)
            return
        super().setData(column_or_role, int(role_or_value), value)

    def font(self, column: int = 0) -> QFont:  # type: ignore[override]
        """Return item font for the provided column.

        Args:
            column: Tree column index.

        Returns:
            QFont: Item font.
        """
        return super().font(column)

    def setFont(self, column_or_font: int | QFont, font: QFont | None = None) -> None:  # type: ignore[override]
        """Set item font using either tree-style or list-style calling.

        Args:
            column_or_font: Column index or font for the default column.
            font: Optional explicit font when a column index is provided.
        """
        if font is None:
            super().setFont(0, column_or_font)
            return
        super().setFont(int(column_or_font), font)

    def checkState(self, column: int = 0) -> Qt.CheckState:  # type: ignore[override]
        """Return item check state for the provided column.

        Args:
            column: Tree column index.

        Returns:
            Qt.CheckState: Item check state.
        """
        return super().checkState(column)

    def setCheckState(
        self,
        column_or_state: int | Qt.CheckState,
        state: Qt.CheckState | None = None,
    ) -> None:  # type: ignore[override]
        """Set check state using either tree-style or list-style calling.

        Args:
            column_or_state: Column index or check state for the default column.
            state: Optional explicit state when a column index is provided.
        """
        if state is None:
            super().setCheckState(0, Qt.CheckState(column_or_state))
            return
        super().setCheckState(int(column_or_state), state)


class SidebarFolderTreeWidget(QTreeWidget):
    """Tree widget that preserves key list-style helpers for existing callers."""

    folder_drop_completed = Signal(str, object, int)

    def __init__(self) -> None:
        """Initialize a one-column tree widget for the sidebar."""
        super().__init__()
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self._spacing = 0
        self._dragged_folder_id: str | None = None

    def setSpacing(self, spacing: int) -> None:
        """Store list-style spacing requests for compatibility.

        Args:
            spacing: Requested row spacing.
        """
        self._spacing = spacing

    def iter_items(self) -> Iterator[SidebarFolderItem]:
        """Yield tree items in pre-order traversal.

        Yields:
            SidebarFolderItem: Sidebar items in visible tree order.
        """
        for top_level_index in range(self.topLevelItemCount()):
            top_level_item = self.topLevelItem(top_level_index)
            if isinstance(top_level_item, SidebarFolderItem):
                yield from self._iter_subtree_items(top_level_item)

    def _iter_subtree_items(
        self,
        item: SidebarFolderItem,
    ) -> Iterator[SidebarFolderItem]:
        """Yield one item followed by all descendants.

        Args:
            item: Root item of the subtree.

        Yields:
            SidebarFolderItem: Items in subtree pre-order.
        """
        yield item
        for child_index in range(item.childCount()):
            child_item = item.child(child_index)
            if isinstance(child_item, SidebarFolderItem):
                yield from self._iter_subtree_items(child_item)

    def count(self) -> int:
        """Return the total number of items in the tree.

        Returns:
            int: Pre-order item count.
        """
        return sum(1 for _ in self.iter_items())

    def item(self, index: int) -> SidebarFolderItem | None:
        """Return one item by its pre-order index.

        Args:
            index: Zero-based pre-order position.

        Returns:
            SidebarFolderItem | None: Matching item when present.
        """
        if index < 0:
            return None
        for current_index, item in enumerate(self.iter_items()):
            if current_index == index:
                return item
        return None

    def row(self, item: SidebarFolderItem) -> int:
        """Return the pre-order row for one item.

        Args:
            item: Item to locate.

        Returns:
            int: Pre-order row, or -1 when not present.
        """
        for current_index, current_item in enumerate(self.iter_items()):
            if current_item is item:
                return current_index
        return -1

    def addItem(self, item: SidebarFolderItem) -> None:
        """Add one item as a top-level entry.

        Args:
            item: Item to add.
        """
        self.addTopLevelItem(item)

    def setCurrentRow(self, row: int) -> None:
        """Select the item at the provided pre-order row.

        Args:
            row: Zero-based pre-order row.
        """
        item = self.item(row)
        if item is not None:
            self.setCurrentItem(item)

    def folder_item_by_id(self, folder_id: str) -> SidebarFolderItem | None:
        """Return one folder item by id.

        Args:
            folder_id: Folder identifier to locate.

        Returns:
            SidebarFolderItem | None: Matching folder item when present.
        """
        for item in self.iter_items():
            if item.data(Qt.UserRole) == folder_id:
                return item
        return None

    def startDrag(self, supported_actions) -> None:  # noqa: N802
        """Start a drag operation only when one folder item is selected."""
        selected_items = [
            item
            for item in self.selectedItems()
            if isinstance(item, SidebarFolderItem)
            and item.data(Qt.UserRole) is not None
        ]
        if len(selected_items) != 1:
            self._dragged_folder_id = None
            return
        dragged_item = selected_items[0]
        dragged_folder_id = dragged_item.data(Qt.UserRole)
        if not isinstance(dragged_folder_id, str):
            self._dragged_folder_id = None
            return
        self._dragged_folder_id = dragged_folder_id
        super().startDrag(supported_actions)
        self._dragged_folder_id = None

    def dropEvent(self, event) -> None:  # noqa: N802
        """Emit persisted drop coordinates after an internal move completes."""
        dragged_folder_id = self._dragged_folder_id
        super().dropEvent(event)
        if dragged_folder_id is None:
            return
        dropped_item = self.folder_item_by_id(dragged_folder_id)
        if dropped_item is None:
            return
        parent_item = dropped_item.parent()
        parent_folder_id = (
            parent_item.data(Qt.UserRole)
            if isinstance(parent_item, SidebarFolderItem)
            else None
        )
        sibling_index = (
            parent_item.indexOfChild(dropped_item)
            if isinstance(parent_item, SidebarFolderItem)
            else self.indexOfTopLevelItem(dropped_item)
        )
        self.folder_drop_completed.emit(
            dragged_folder_id,
            parent_folder_id,
            sibling_index,
        )


class SidebarFolderController:
    """Encapsulate sidebar folder-item behavior and rename state."""

    def __init__(
        self,
        folder_list: SidebarFolderTreeWidget,
        folder_name_role: int,
    ) -> None:
        """Initialize the controller.

        Args:
            folder_list: Sidebar tree widget.
            folder_name_role: Custom item-data role used to store folder names.
        """
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

    def is_folder_item(self, item: SidebarFolderItem | None) -> bool:
        """Return whether a sidebar item maps to a persisted folder."""
        return item is not None and item.data(Qt.UserRole) is not None

    def selected_folder_items(self) -> list[SidebarFolderItem]:
        """Return selected tree items that map to persisted folders."""
        return [
            item
            for item in self._folder_list.selectedItems()
            if isinstance(item, SidebarFolderItem) and self.is_folder_item(item)
        ]

    def iter_folder_items(self) -> Iterator[SidebarFolderItem]:
        """Yield sidebar items that map to persisted folders."""
        for item in self._folder_list.iter_items():
            if self.is_folder_item(item):
                yield item

    def iter_descendant_folder_items(
        self,
        folder_item: SidebarFolderItem,
    ) -> Iterator[SidebarFolderItem]:
        """Yield descendant folder items for one tree item.

        Args:
            folder_item: Root folder item.

        Yields:
            SidebarFolderItem: Descendant folder items.
        """
        for child_index in range(folder_item.childCount()):
            child_item = folder_item.child(child_index)
            if not isinstance(child_item, SidebarFolderItem):
                continue
            if self.is_folder_item(child_item):
                yield child_item
            yield from self.iter_descendant_folder_items(child_item)

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

    def expanded_folder_ids(self) -> set[str]:
        """Return ids for folders that are currently expanded."""
        return {
            folder_id
            for item in self.iter_folder_items()
            if item.isExpanded()
            for folder_id in [item.data(Qt.UserRole)]
            if folder_id is not None
        }

    def folder_item_name(self, item: SidebarFolderItem) -> str:
        """Return folder name without flashcard count suffix."""
        folder_name = item.data(self._folder_name_role)
        return folder_name if isinstance(folder_name, str) else item.text()

    def format_folder_label(
        self,
        folder_name: str,
        flashcard_count: int,
        progress_percent: int,
    ) -> str:
        """Build sidebar folder label with card count and completion progress."""
        return (
            f"{folder_name} "
            f"({format_card_count(flashcard_count)} | {progress_percent}% done)"
        )

    def create_folder_item(
        self,
        folder_id: str,
        folder_name: str,
        flashcard_count: int,
        progress_percent: int,
        checked: bool,
    ) -> SidebarFolderItem:
        """Create one folder item for the sidebar tree.

        Args:
            folder_id: Folder identifier.
            folder_name: Display name.
            flashcard_count: Number of flashcards in folder.
            progress_percent: Percent of flashcards completed for the folder.
            checked: Whether the item starts checked.

        Returns:
            SidebarFolderItem: Configured tree item.
        """
        folder_item = SidebarFolderItem(
            [
                self.format_folder_label(
                    folder_name,
                    flashcard_count,
                    progress_percent,
                )
            ]
        )
        folder_item.setData(Qt.UserRole, folder_id)
        folder_item.setData(self._folder_name_role, folder_name)
        folder_item.setFlags(
            folder_item.flags()
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )
        folder_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.apply_item_visual_state(folder_item)
        return folder_item

    def create_placeholder_item(self, text: str) -> SidebarFolderItem:
        """Create one non-interactive placeholder item.

        Args:
            text: Placeholder text to display.

        Returns:
            SidebarFolderItem: Non-selectable placeholder item.
        """
        placeholder_item = SidebarFolderItem([text])
        placeholder_item.setFlags(Qt.NoItemFlags)
        return placeholder_item

    def apply_item_visual_state(self, item: SidebarFolderItem) -> None:
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

    def cascade_check_state(self, folder_item: SidebarFolderItem) -> None:
        """Apply a folder's checked state to all descendants.

        Args:
            folder_item: Folder item whose descendants should match its state.
        """
        if not self.is_folder_item(folder_item):
            return
        descendant_state = folder_item.checkState()
        for descendant_item in self.iter_descendant_folder_items(folder_item):
            descendant_item.setCheckState(descendant_state)
            self.apply_item_visual_state(descendant_item)

    def begin_rename(self, folder_item: SidebarFolderItem) -> None:
        """Start inline rename for one folder."""
        folder_id = folder_item.data(Qt.UserRole)
        if folder_id is None:
            return
        self._renaming_folder_id = folder_id
        self._renaming_original_name = self.folder_item_name(folder_item)
        folder_item.setText(self._renaming_original_name)
        self._folder_list.setCurrentItem(folder_item)
        QTimer.singleShot(0, lambda: self._folder_list.editItem(folder_item, 0))

    def normalize_menu_selection(
        self,
        clicked_item: SidebarFolderItem | None,
    ) -> list[SidebarFolderItem]:
        """Normalize sidebar selection for a context-menu action."""
        if not self.is_folder_item(clicked_item):
            return []
        if clicked_item is not None and not clicked_item.isSelected():
            self._folder_list.clearSelection()
            clicked_item.setSelected(True)
        return self.selected_folder_items()

    def handle_inline_rename(
        self,
        item: SidebarFolderItem,
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
