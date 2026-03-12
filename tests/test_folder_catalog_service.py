"""Persisted folder catalog service tests."""

from pathlib import Path

import pytest

from estudai.services.csv_flashcards import replace_flashcards_in_folder
from estudai.services.folder_catalog import PersistedFolderCatalogService
from estudai.services.folder_storage import create_managed_folder
from estudai.services.settings import WrongAnswerCompletionMode
from estudai.services.study_progress import (
    FlashcardProgressEntry,
    load_folder_progress,
    reviewed_progress,
    save_progress_entries,
)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an isolated app data directory for each test.

    Args:
        tmp_path: Temporary path provided by pytest.
        monkeypatch: Pytest monkeypatch helper.
    """
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(tmp_path / "app-data"))


def test_load_catalog_returns_flashcards_and_progress_percent() -> None:
    """Verify catalog loading aggregates folder flashcards and progress."""
    persisted_folder = create_managed_folder("Biology")
    folder_path = Path(persisted_folder.stored_path)
    loaded_flashcards = replace_flashcards_in_folder(
        folder_path,
        [("What is DNA?", "Genetic material.")],
    )
    save_progress_entries(
        [
            FlashcardProgressEntry(
                folder_id=persisted_folder.id,
                flashcard_id=loaded_flashcards[0].stable_id,
                progress=reviewed_progress(correct_count=1, wrong_count=0),
            )
        ]
    )

    service = PersistedFolderCatalogService()
    result = service.load_catalog(WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE)

    assert result.load_errors == []
    assert len(result.folders) == 1
    assert result.folders[0].persisted_folder.id == persisted_folder.id
    assert result.folders[0].stored_path == folder_path
    assert [flashcard.question for flashcard in result.folders[0].flashcards] == [
        "What is DNA?"
    ]
    assert result.folders[0].progress_percent == 100


def test_load_catalog_prunes_progress_for_removed_flashcards() -> None:
    """Verify catalog loading drops orphaned progress entries after reload."""
    persisted_folder = create_managed_folder("Biology")
    folder_path = Path(persisted_folder.stored_path)
    first_flashcards = replace_flashcards_in_folder(
        folder_path,
        [("Q1?", "A1."), ("Q2?", "A2.")],
    )
    save_progress_entries(
        [
            FlashcardProgressEntry(
                folder_id=persisted_folder.id,
                flashcard_id=first_flashcards[0].stable_id,
                progress=reviewed_progress(correct_count=1, wrong_count=0),
            ),
            FlashcardProgressEntry(
                folder_id=persisted_folder.id,
                flashcard_id=first_flashcards[1].stable_id,
                progress=reviewed_progress(correct_count=1, wrong_count=0),
            ),
        ]
    )
    updated_flashcards = replace_flashcards_in_folder(folder_path, [("Q2?", "A2.")])

    service = PersistedFolderCatalogService()
    result = service.load_catalog(WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE)
    remaining_progress = load_folder_progress(persisted_folder.id)

    assert result.load_errors == []
    assert [flashcard.question for flashcard in result.folders[0].flashcards] == ["Q2?"]
    assert set(remaining_progress) == {updated_flashcards[0].stable_id}
