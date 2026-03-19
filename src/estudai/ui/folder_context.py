"""Helpers for deriving selected-folder UI state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from estudai.services.csv_flashcards import Flashcard

__all__ = [
    "CheckedFolderData",
    "FolderSelectionContext",
    "build_folder_selection_context",
    "merge_imported_flashcard_indexes",
    "normalize_selected_indexes",
]


@dataclass(frozen=True)
class CheckedFolderData:
    """Snapshot of one checked folder used to compute timer scope."""

    folder_id: str
    folder_name: str
    flashcards: list[Flashcard]
    selected_indexes: set[int]


@dataclass(frozen=True)
class FolderSelectionContext:
    """Derived selection context shown and used by the timer page."""

    selected_folder_ids: set[str]
    current_folder_id: str | None
    current_folder_name: str
    loaded_flashcards: list[Flashcard]


def normalize_selected_indexes(
    existing_indexes: set[int] | None,
    flashcard_count: int,
) -> set[int]:
    """Return selected indexes constrained to the available flashcard range."""
    if existing_indexes is None:
        return set(range(flashcard_count))
    return {
        flashcard_index
        for flashcard_index in existing_indexes
        if 0 <= flashcard_index < flashcard_count
    }


def build_folder_selection_context(
    checked_folders: Iterable[CheckedFolderData],
) -> FolderSelectionContext:
    """Build current timer context from the checked folders."""
    checked_folder_ids: list[str] = []
    checked_folder_names: list[str] = []
    loaded_flashcards: list[Flashcard] = []

    for folder in checked_folders:
        checked_folder_ids.append(folder.folder_id)
        checked_folder_names.append(folder.folder_name)
        loaded_flashcards.extend(
            flashcard
            for flashcard_index, flashcard in enumerate(folder.flashcards)
            if flashcard_index in folder.selected_indexes
        )

    count = len(checked_folder_ids)
    if count == 0:
        folder_id, folder_name = None, "No folders selected"
        loaded_flashcards = []
    elif count == 1:
        folder_id, folder_name = checked_folder_ids[0], checked_folder_names[0]
    else:
        folder_id, folder_name = None, f"{count} folders selected"

    return FolderSelectionContext(
        selected_folder_ids=set(checked_folder_ids),
        current_folder_id=folder_id,
        current_folder_name=folder_name,
        loaded_flashcards=loaded_flashcards,
    )


def merge_imported_flashcard_indexes(
    existing_flashcard_count: int,
    imported_row_count: int,
    selected_indexes: set[int],
) -> set[int]:
    """Mark imported flashcards as selected while preserving current selection."""
    imported_indexes = set(
        range(
            existing_flashcard_count,
            existing_flashcard_count + imported_row_count,
        )
    )
    return selected_indexes | imported_indexes
