"""Application-state helper tests."""

from pathlib import Path

from estudai.services.csv_flashcards import Flashcard
from estudai.ui.application_state import FolderLibraryState, StudyApplicationState


def _flashcard(question: str, answer: str, line_number: int) -> Flashcard:
    """Create a flashcard fixture payload.

    Args:
        question: Flashcard question text.
        answer: Flashcard answer text.
        line_number: Source CSV line number.

    Returns:
        Flashcard: Fixture flashcard instance.
    """
    return Flashcard(
        question=question,
        answer=answer,
        source_file=Path("cards.csv"),
        source_line=line_number,
    )


def test_replace_folders_and_refresh_selection_builds_timer_context() -> None:
    """Verify folder snapshots become the single source of timer selection."""
    state = StudyApplicationState()
    state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[_flashcard("Q1?", "A1.", 1), _flashcard("Q2?", "A2.", 2)],
                selected_indexes={1, 99},
            ),
            FolderLibraryState(
                folder_id="chem",
                folder_name="Chemistry",
                folder_path=Path("/tmp/chem"),
                flashcards=[_flashcard("Q3?", "A3.", 1)],
                selected_indexes=None,
            ),
        ]
    )

    state.refresh_selection({"bio", "chem"})

    assert state.selected_flashcard_indexes_by_folder["bio"] == {1}
    assert state.selected_flashcard_indexes_by_folder["chem"] == {0}
    assert state.current_folder_id is None
    assert state.current_folder_name == "2 sets selected"
    assert state.selected_folder_ids == {"bio", "chem"}
    assert [flashcard.question for flashcard in state.loaded_flashcards] == [
        "Q2?",
        "Q3?",
    ]


def test_update_selected_indexes_and_delete_adjustment_stay_normalized() -> None:
    """Verify per-folder selection updates stay valid after mutations."""
    state = StudyApplicationState()
    state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[
                    _flashcard("Q1?", "A1.", 1),
                    _flashcard("Q2?", "A2.", 2),
                    _flashcard("Q3?", "A3.", 3),
                ],
            )
        ]
    )

    state.update_selected_indexes("bio", {-1, 0, 2, 9})

    assert state.selected_indexes_for_folder("bio") == {0, 2}
    assert state.selected_indexes_after_deletion("bio", 0) == {1}
