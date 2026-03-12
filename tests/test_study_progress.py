"""Study-progress persistence tests."""

import json
import os
from pathlib import Path

import pytest

from estudai.services.csv_flashcards import load_flashcards_from_folder
from estudai.services.folder_storage import import_folder
from estudai.services.study_progress import (
    FlashcardProgress,
    FlashcardProgressEntry,
    get_study_progress_path,
    load_folder_progress,
    prune_folder_progress,
    save_progress_entries,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an isolated app data directory for each test."""
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(tmp_path / "app-data"))


def test_reimport_preserves_flashcard_ids_when_source_rows_reorder(
    tmp_path: Path,
) -> None:
    """Verify re-importing the same folder keeps IDs for reordered source rows."""
    source_folder = tmp_path / "biology"
    source_folder.mkdir()
    source_csv = source_folder / "cards.csv"
    source_csv.write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")

    persisted_folder = import_folder(source_folder)
    initial_ids = {
        flashcard.question: flashcard.stable_id
        for flashcard in load_flashcards_from_folder(Path(persisted_folder.stored_path))
    }

    source_csv.write_text("Q2?,A2.\nQ1?,A1.\n", encoding="utf-8")
    reimported_folder = import_folder(source_folder)
    updated_ids = {
        flashcard.question: flashcard.stable_id
        for flashcard in load_flashcards_from_folder(
            Path(reimported_folder.stored_path)
        )
    }

    assert reimported_folder.id == persisted_folder.id
    assert updated_ids == initial_ids


def test_reimport_preserves_flashcard_id_for_same_source_line_edits(
    tmp_path: Path,
) -> None:
    """Verify editing a source row in place keeps the existing flashcard ID."""
    source_folder = tmp_path / "biology"
    source_folder.mkdir()
    source_csv = source_folder / "cards.csv"
    source_csv.write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")

    persisted_folder = import_folder(source_folder)
    initial_flashcards = load_flashcards_from_folder(Path(persisted_folder.stored_path))
    first_flashcard_id = initial_flashcards[0].stable_id
    second_flashcard_id = initial_flashcards[1].stable_id

    source_csv.write_text("Q1 updated?,A1 updated.\nQ2?,A2.\n", encoding="utf-8")
    reimported_folder = import_folder(source_folder)
    updated_flashcards = load_flashcards_from_folder(
        Path(reimported_folder.stored_path)
    )

    assert updated_flashcards[0].question == "Q1 updated?"
    assert updated_flashcards[0].stable_id == first_flashcard_id
    assert updated_flashcards[1].stable_id == second_flashcard_id


def test_load_folder_progress_ignores_corrupt_and_invalid_payloads() -> None:
    """Verify corrupt or partially invalid progress data fails safely."""
    progress_path = get_study_progress_path()
    progress_path.write_text("{invalid json", encoding="utf-8")

    assert load_folder_progress("biology") == {}

    progress_path.write_text(
        json.dumps(
            {
                "version": 1,
                "folders": {
                    "biology": {
                        "valid-card": {
                            "correct_count": 2,
                            "wrong_count": 1,
                            "last_reviewed_at": "2026-03-12T10:00:00+00:00",
                        },
                        "bad-count-type": {
                            "correct_count": "2",
                            "wrong_count": 1,
                        },
                        "bad-structure": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert load_folder_progress("biology") == {
        "valid-card": FlashcardProgress(
            correct_count=2,
            wrong_count=1,
            last_reviewed_at="2026-03-12T10:00:00+00:00",
        )
    }


def test_prune_folder_progress_removes_deleted_flashcards_only() -> None:
    """Verify pruning removes stale entries without affecting other folders."""
    save_progress_entries(
        [
            FlashcardProgressEntry(
                folder_id="biology",
                flashcard_id="card-1",
                progress=FlashcardProgress(correct_count=1, wrong_count=0),
            ),
            FlashcardProgressEntry(
                folder_id="biology",
                flashcard_id="card-2",
                progress=FlashcardProgress(correct_count=0, wrong_count=2),
            ),
            FlashcardProgressEntry(
                folder_id="chemistry",
                flashcard_id="card-3",
                progress=FlashcardProgress(correct_count=3, wrong_count=1),
            ),
        ]
    )

    prune_folder_progress("biology", {"card-2"})

    assert load_folder_progress("biology") == {
        "card-2": FlashcardProgress(correct_count=0, wrong_count=2)
    }
    assert load_folder_progress("chemistry") == {
        "card-3": FlashcardProgress(correct_count=3, wrong_count=1)
    }
