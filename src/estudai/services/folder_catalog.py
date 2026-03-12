"""Catalog helpers for loading persisted study folders."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from estudai.services.csv_flashcards import Flashcard, load_flashcards_from_folder
from estudai.services.folder_storage import PersistedFolder, list_persisted_folders
from estudai.services.settings import WrongAnswerCompletionMode
from estudai.services.study_progress import (
    load_folder_progress,
    prune_folder_progress,
    summarize_folder_progress,
)

__all__ = [
    "FolderCatalogLoadResult",
    "LoadedPersistedFolder",
    "PersistedFolderCatalogService",
]


@dataclass(frozen=True)
class LoadedPersistedFolder:
    """Loaded folder data ready for UI state assembly.

    Args:
        persisted_folder: Persisted folder metadata from storage.
        stored_path: Folder path used for flashcard loading.
        flashcards: Flashcards currently available in the folder.
        progress_percent: Completion percentage for sidebar display.
    """

    persisted_folder: PersistedFolder
    stored_path: Path
    flashcards: list[Flashcard]
    progress_percent: int


@dataclass(frozen=True)
class FolderCatalogLoadResult:
    """Result of loading the persisted folder catalog.

    Args:
        folders: Successfully enumerated folders, including folders that loaded
            with zero flashcards after a recoverable read error.
        load_errors: Human-readable errors for folders that could not be read.
    """

    folders: list[LoadedPersistedFolder]
    load_errors: list[str]


class PersistedFolderCatalogService:
    """Load persisted folders into UI-ready records."""

    def load_catalog(
        self,
        completion_mode: WrongAnswerCompletionMode,
    ) -> FolderCatalogLoadResult:
        """Load persisted folder metadata, flashcards, and progress summaries.

        Args:
            completion_mode: Review completion rule used for progress summaries.

        Returns:
            FolderCatalogLoadResult: Catalog data and any recoverable load
            errors.
        """
        loaded_folders: list[LoadedPersistedFolder] = []
        load_errors: list[str] = []

        for persisted_folder in list_persisted_folders():
            stored_path = Path(persisted_folder.stored_path)
            if not stored_path.exists():
                continue

            flashcards, load_error = self.load_folder_flashcards(
                persisted_folder.name,
                stored_path,
            )
            if load_error is not None:
                load_errors.append(load_error)
            else:
                prune_folder_progress(
                    persisted_folder.id,
                    {
                        flashcard.stable_id
                        for flashcard in flashcards
                        if flashcard.stable_id
                    },
                )

            progress_percent = summarize_folder_progress(
                (flashcard.stable_id for flashcard in flashcards),
                load_folder_progress(persisted_folder.id),
                completion_mode,
            ).percent_done
            loaded_folders.append(
                LoadedPersistedFolder(
                    persisted_folder=persisted_folder,
                    stored_path=stored_path,
                    flashcards=flashcards,
                    progress_percent=progress_percent,
                )
            )

        return FolderCatalogLoadResult(
            folders=loaded_folders,
            load_errors=load_errors,
        )

    def load_folder_flashcards(
        self,
        folder_name: str,
        folder_path: Path,
    ) -> tuple[list[Flashcard], str | None]:
        """Load one folder without aborting the whole UI refresh.

        Args:
            folder_name: Display name used in warning messages.
            folder_path: Folder path containing flashcard CSV data.

        Returns:
            tuple[list[Flashcard], str | None]: Loaded flashcards and an
            optional formatted error message.
        """
        try:
            return load_flashcards_from_folder(folder_path), None
        except (csv.Error, OSError, UnicodeDecodeError) as error:
            return [], f"{folder_name}: {error}"
