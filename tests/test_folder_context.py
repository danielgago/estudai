"""Folder-selection helper tests."""

from pathlib import Path

from estudai.services.csv_flashcards import Flashcard
from estudai.ui.folder_context import (
    CheckedFolderData,
    build_folder_selection_context,
    merge_imported_flashcard_indexes,
    normalize_selected_indexes,
)


def _flashcard(question: str, answer: str, line_number: int) -> Flashcard:
    """Create a flashcard fixture payload."""
    return Flashcard(
        question=question,
        answer=answer,
        source_file=Path("cards.csv"),
        source_line=line_number,
    )


def test_normalize_selected_indexes_defaults_or_filters_invalid_indexes() -> None:
    """Verify selected indexes default to all rows and drop out-of-range values."""
    assert normalize_selected_indexes(None, 3) == {0, 1, 2}
    assert normalize_selected_indexes({-1, 0, 2, 4}, 3) == {0, 2}


def test_build_folder_selection_context_merges_checked_folder_flashcards() -> None:
    """Verify checked folders compute the expected timer context."""
    context = build_folder_selection_context(
        [
            CheckedFolderData(
                folder_id="bio",
                folder_name="Biology",
                flashcards=[_flashcard("Q1?", "A1.", 1), _flashcard("Q2?", "A2.", 2)],
                selected_indexes={1},
            ),
            CheckedFolderData(
                folder_id="chem",
                folder_name="Chemistry",
                flashcards=[_flashcard("Q3?", "A3.", 1)],
                selected_indexes={0},
            ),
        ]
    )

    assert context.current_folder_id is None
    assert context.current_folder_name == "2 folders selected"
    assert context.selected_folder_ids == {"bio", "chem"}
    assert [flashcard.question for flashcard in context.loaded_flashcards] == [
        "Q2?",
        "Q3?",
    ]


def test_merge_imported_flashcard_indexes_marks_new_rows_selected() -> None:
    """Verify imported flashcards become selected without losing prior choices."""
    assert merge_imported_flashcard_indexes(2, 3, {1}) == {1, 2, 3, 4}
