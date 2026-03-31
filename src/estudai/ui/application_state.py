"""Application state helpers for folder-backed study selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from estudai.services.csv_flashcards import Flashcard

from .folder_context import (
    CheckedFolderData,
    build_folder_selection_context,
    normalize_selected_indexes,
)

__all__ = [
    "FolderLibraryState",
    "StudyApplicationState",
]

_NO_FOLDERS_SELECTED = "No sets selected"


@dataclass(frozen=True)
class FolderLibraryState:
    """Normalized folder state tracked by the main window.

    Args:
        folder_id: Persistent folder identifier.
        folder_name: Display name shown in the sidebar.
        folder_path: Managed folder storage path.
        parent_id: Optional parent folder identifier for hierarchy metadata.
        is_flashcard_set: Whether the node is an editable flashcard set.
        flashcards: Flashcards currently loaded for the folder.
        selected_indexes: Optional selected flashcard indexes for timer scope.
    """

    folder_id: str
    folder_name: str
    folder_path: Path
    flashcards: list[Flashcard]
    parent_id: str | None = None
    is_flashcard_set: bool = True
    selected_indexes: set[int] | None = None


class StudyApplicationState:
    """Own folder caches plus derived timer selection state."""

    def __init__(self) -> None:
        """Initialize empty application state."""
        self.flashcards_by_folder: dict[str, list[Flashcard]] = {}
        self.persisted_folder_paths: dict[str, Path] = {}
        self.folder_names_by_id: dict[str, str] = {}
        self.parent_folder_ids_by_id: dict[str, str | None] = {}
        self.flashcard_set_flags_by_id: dict[str, bool] = {}
        self.selected_flashcard_indexes_by_folder: dict[str, set[int]] = {}
        self.selected_folder_ids: set[str] = set()
        self.current_folder_id: str | None = None
        self.current_folder_name = _NO_FOLDERS_SELECTED
        self.loaded_flashcards: list[Flashcard] = []

    def replace_folders(self, folders: list[FolderLibraryState]) -> None:
        """Replace the tracked folder library with normalized snapshots.

        Args:
            folders: Folder states that should become the new source of truth.
        """
        self.flashcards_by_folder = {
            folder.folder_id: folder.flashcards for folder in folders
        }
        self.persisted_folder_paths = {
            folder.folder_id: folder.folder_path for folder in folders
        }
        self.folder_names_by_id = {
            folder.folder_id: folder.folder_name for folder in folders
        }
        self.parent_folder_ids_by_id = {
            folder.folder_id: folder.parent_id for folder in folders
        }
        self.flashcard_set_flags_by_id = {
            folder.folder_id: folder.is_flashcard_set for folder in folders
        }
        self.selected_flashcard_indexes_by_folder = {
            folder.folder_id: normalize_selected_indexes(
                folder.selected_indexes,
                len(folder.flashcards),
            )
            for folder in folders
        }

    def normalized_selected_indexes(
        self,
        folder_id: str,
        flashcard_count: int,
    ) -> set[int]:
        """Return selected indexes normalized to the current flashcard count.

        Args:
            folder_id: Folder identifier to read previous selection from.
            flashcard_count: Number of flashcards currently available.

        Returns:
            set[int]: Valid selected indexes for the folder.
        """
        return normalize_selected_indexes(
            self.selected_flashcard_indexes_by_folder.get(folder_id),
            flashcard_count,
        )

    def selected_indexes_for_folder(self, folder_id: str) -> set[int]:
        """Return the normalized selected indexes for one folder.

        Args:
            folder_id: Folder identifier to inspect.

        Returns:
            set[int]: Selected indexes for the folder, or an empty set when the
            folder is unavailable.
        """
        folder_flashcards = self.flashcards_by_folder.get(folder_id)
        if folder_flashcards is None:
            return set()
        return set(
            self.selected_flashcard_indexes_by_folder.get(
                folder_id,
                set(range(len(folder_flashcards))),
            )
        )

    def update_selected_indexes(
        self,
        folder_id: str,
        selected_indexes: set[int],
        *,
        flashcard_count: int | None = None,
    ) -> None:
        """Persist normalized timer selection indexes for one folder.

        Args:
            folder_id: Folder identifier to update.
            selected_indexes: Candidate selected indexes.
            flashcard_count: Optional flashcard count used to normalize the
                selection when the persisted folder data has changed but the
                in-memory cache has not been refreshed yet.
        """
        if flashcard_count is None:
            folder_flashcards = self.flashcards_by_folder.get(folder_id)
            if folder_flashcards is None:
                return
            flashcard_count = len(folder_flashcards)
        if flashcard_count < 0:
            return
        self.selected_flashcard_indexes_by_folder[folder_id] = (
            normalize_selected_indexes(selected_indexes, flashcard_count)
        )

    def selected_indexes_after_deletion(
        self,
        folder_id: str,
        deleted_flashcard_index: int,
    ) -> set[int]:
        """Return selected indexes after removing one flashcard from a folder.

        Args:
            folder_id: Folder identifier whose selection is being updated.
            deleted_flashcard_index: Deleted flashcard row index.

        Returns:
            set[int]: Adjusted selected indexes after deletion.
        """
        return {
            (
                flashcard_index - 1
                if flashcard_index > deleted_flashcard_index
                else flashcard_index
            )
            for flashcard_index in self.selected_indexes_for_folder(folder_id)
            if flashcard_index != deleted_flashcard_index
        }

    def refresh_selection(self, checked_folder_ids: set[str]) -> None:
        """Rebuild the timer selection context from checked folders.

        Args:
            checked_folder_ids: Folder ids currently checked in the sidebar.
        """
        checked_folders = [
            CheckedFolderData(
                folder_id=folder_id,
                folder_name=self.folder_names_by_id[folder_id],
                flashcards=self.flashcards_by_folder[folder_id],
                selected_indexes=self.selected_indexes_for_folder(folder_id),
            )
            for folder_id in self.flashcards_by_folder
            if folder_id in checked_folder_ids and self.is_flashcard_set(folder_id)
        ]
        selection_context = build_folder_selection_context(checked_folders)
        self.selected_folder_ids = selection_context.selected_folder_ids
        self.current_folder_id = selection_context.current_folder_id
        self.current_folder_name = selection_context.current_folder_name
        self.loaded_flashcards = selection_context.loaded_flashcards

    def has_folder(self, folder_id: str) -> bool:
        """Return whether one folder id is currently loaded.

        Args:
            folder_id: Folder identifier to check.

        Returns:
            bool: True when the folder exists in current state.
        """
        return folder_id in self.flashcards_by_folder

    def is_flashcard_set(self, folder_id: str) -> bool:
        """Return whether one loaded folder id maps to a flashcard set."""
        return self.flashcard_set_flags_by_id.get(folder_id, True)

    def child_folder_ids(self, folder_id: str) -> list[str]:
        """Return direct child folder ids for one loaded folder."""
        return [
            child_id
            for child_id, parent_id in self.parent_folder_ids_by_id.items()
            if parent_id == folder_id
        ]

    def folder_display_path(self, folder_id: str) -> str | None:
        """Return one folder path using the sidebar hierarchy labels.

        Args:
            folder_id: Folder identifier to resolve.

        Returns:
            str | None: Slash-delimited folder path as shown in the sidebar, or
            None when the folder is unavailable.
        """
        if folder_id not in self.folder_names_by_id:
            return None
        path_parts: list[str] = []
        current_folder_id: str | None = folder_id
        visited_folder_ids: set[str] = set()
        while current_folder_id is not None:
            if current_folder_id in visited_folder_ids:
                break
            visited_folder_ids.add(current_folder_id)
            folder_name = self.folder_names_by_id.get(current_folder_id)
            if folder_name is None:
                break
            path_parts.append(folder_name)
            current_folder_id = self.parent_folder_ids_by_id.get(current_folder_id)
        path_parts.reverse()
        return " / ".join(path_parts)
