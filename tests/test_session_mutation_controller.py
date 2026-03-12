"""Session mutation controller tests."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from estudai.services.csv_flashcards import Flashcard
from estudai.ui.application_state import FolderLibraryState, StudyApplicationState
from estudai.ui.controllers.session_mutation_controller import (
    SessionMutationController,
)


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


class _FakeDialog:
    """Minimal accepted edit dialog used by mutation-controller tests."""

    def __init__(self, question: str, answer: str) -> None:
        """Initialize the dialog with replacement values."""
        self._question = question
        self._answer = answer

    def exec(self) -> int:
        """Return an accepted dialog result."""
        return QDialog.Accepted

    def question_text(self) -> str:
        """Return the edited question text."""
        return self._question

    def answer_text(self) -> str:
        """Return the edited answer text."""
        return self._answer


class _FakeTimerPage:
    """Minimal timer page spy used by mutation-controller tests."""

    def __init__(self) -> None:
        """Initialize the fake timer page."""
        self.updated_display: tuple[str, str] | None = None
        self.prepared_next_cycle = False

    def update_displayed_flashcard(self, question: str, answer: str) -> None:
        """Record the flashcard text updated in place."""
        self.updated_display = (question, answer)

    def prepare_next_timer_cycle_paused(self) -> None:
        """Record preparing the next timer cycle in paused mode."""
        self.prepared_next_cycle = True


class _FakeStudySession:
    """Minimal study-session spy used by mutation-controller tests."""

    def __init__(self, flashcards: list[Flashcard]) -> None:
        """Initialize the fake session.

        Args:
            flashcards: Session flashcards currently active.
        """
        self.flashcards = list(flashcards)
        self.current_flashcard_index: int | None = 0 if flashcards else None
        self.replace_current_return_value = True
        self.remove_current_return_value = True

    def current_flashcard(self) -> Flashcard | None:
        """Return the active flashcard."""
        if self.current_flashcard_index is None:
            return None
        if not (0 <= self.current_flashcard_index < len(self.flashcards)):
            return None
        return self.flashcards[self.current_flashcard_index]

    def replace_current_flashcard(self, flashcard: Flashcard) -> bool:
        """Replace the current flashcard payload."""
        if (
            not self.replace_current_return_value
            or self.current_flashcard_index is None
        ):
            return False
        self.flashcards[self.current_flashcard_index] = flashcard
        return True

    def remove_current_flashcard(self) -> bool:
        """Remove the current flashcard payload."""
        if not self.remove_current_return_value or self.current_flashcard_index is None:
            return False
        self.flashcards.pop(self.current_flashcard_index)
        self.current_flashcard_index = None
        return True

    def replace_flashcards(self, replacements: dict[Flashcard, Flashcard]) -> None:
        """Apply session flashcard replacements."""
        self.flashcards = [
            replacements.get(flashcard, flashcard) for flashcard in self.flashcards
        ]

    def progress(self) -> SimpleNamespace:
        """Return a progress object with the remaining count."""
        return SimpleNamespace(remaining_count=len(self.flashcards))


class _FakeRuntime:
    """Minimal runtime state adapter used by mutation-controller tests."""

    def __init__(
        self,
        flashcards: list[Flashcard],
        active_keys: list[tuple[str, str]],
    ) -> None:
        """Initialize the runtime wrapper."""
        self.study_session = _FakeStudySession(flashcards)
        self.active_study_session_keys = list(active_keys)
        self.pending_flashcard_score: str | None = "wrong"
        self.visible_flashcard: Flashcard | None = flashcards[0] if flashcards else None
        self.flashcard_sequence = SimpleNamespace(sequence_paused=True)
        self.cancel_count = 0
        self.progress_update_count = 0
        self.complete_count = 0

    def cancel_flashcard_phase_timer(self) -> None:
        """Record cancelling the active flashcard phase timer."""
        self.cancel_count += 1

    def update_study_session_progress(self) -> None:
        """Record refreshing visible study progress."""
        self.progress_update_count += 1

    def complete_study_session(self) -> None:
        """Record completing the active study session."""
        self.complete_count += 1


def _flashcard(question: str, answer: str, stable_id: str) -> Flashcard:
    """Create a flashcard fixture payload."""
    return Flashcard(
        question=question,
        answer=answer,
        source_file=Path("cards.csv"),
        source_line=1,
        stable_id=stable_id,
    )


def _build_controller(
    *,
    app_state: StudyApplicationState,
    runtime: _FakeRuntime,
    timer_page: _FakeTimerPage | None = None,
    handle_folder_data_changed=None,
    show_warning_message=None,
    confirm_action=None,
    edit_dialog_factory=None,
) -> SessionMutationController:
    """Create a mutation controller with injectable test seams."""
    return SessionMutationController(
        parent=QWidget(),
        timer_page=(timer_page or _FakeTimerPage()),  # type: ignore[arg-type]
        app_state=app_state,
        runtime=runtime,
        checked_folder_ids_getter=lambda: {"bio"},
        handle_folder_data_changed=handle_folder_data_changed
        or (lambda _checked_ids, _current_folder_id: None),
        edit_dialog_factory=edit_dialog_factory
        or (lambda _question, _answer: _FakeDialog("Edited Q?", "Edited A.")),
        show_warning_message=show_warning_message or (lambda _title, _message: None),
        confirm_action=confirm_action or (lambda _title, _message: True),
    )


def test_edit_requested_updates_session_flashcard_and_timer_display(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify editing the paused flashcard updates runtime and display state."""
    flashcard = _flashcard("Q1?", "A1.", "bio-1")
    updated_flashcard = _flashcard("Edited Q1?", "Edited A1.", "bio-1")
    app_state = StudyApplicationState()
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[flashcard],
                selected_indexes={0},
            )
        ]
    )
    runtime = _FakeRuntime([flashcard], [("bio", "bio-1")])
    timer_page = _FakeTimerPage()
    refresh_calls: list[tuple[set[str] | None, str | None]] = []
    controller = _build_controller(
        app_state=app_state,
        runtime=runtime,
        timer_page=timer_page,
        handle_folder_data_changed=lambda checked_ids, current_folder_id: (
            refresh_calls.append(
                (
                    None if checked_ids is None else set(checked_ids),
                    current_folder_id,
                )
            )
        ),
        edit_dialog_factory=lambda _question, _answer: _FakeDialog(
            "Edited Q1?",
            "Edited A1.",
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.controllers.session_mutation_controller.update_flashcard_in_folder",
        lambda *_args, **_kwargs: [updated_flashcard],
    )

    controller.handle_flashcard_edit_requested()

    assert runtime.study_session.flashcards == [updated_flashcard]
    assert runtime.visible_flashcard == updated_flashcard
    assert timer_page.updated_display == ("Edited Q1?", "Edited A1.")
    assert refresh_calls == [({"bio"}, None)]


def test_delete_requested_removes_current_card_and_prepares_next_cycle(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify deleting the active flashcard refreshes session state and timer UI."""
    first_flashcard = _flashcard("Q1?", "A1.", "bio-1")
    second_flashcard = _flashcard("Q2?", "A2.", "bio-2")
    app_state = StudyApplicationState()
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[first_flashcard, second_flashcard],
                selected_indexes={0, 1},
            )
        ]
    )
    runtime = _FakeRuntime(
        [first_flashcard, second_flashcard],
        [("bio", "bio-1"), ("bio", "bio-2")],
    )
    timer_page = _FakeTimerPage()
    refresh_calls: list[tuple[set[str] | None, str | None]] = []
    controller = _build_controller(
        app_state=app_state,
        runtime=runtime,
        timer_page=timer_page,
        handle_folder_data_changed=lambda checked_ids, current_folder_id: (
            refresh_calls.append(
                (
                    None if checked_ids is None else set(checked_ids),
                    current_folder_id,
                )
            )
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.controllers.session_mutation_controller.delete_flashcards_from_folder",
        lambda *_args, **_kwargs: [second_flashcard],
    )

    controller.handle_flashcard_delete_requested()

    assert runtime.cancel_count == 1
    assert runtime.flashcard_sequence.sequence_paused is False
    assert runtime.pending_flashcard_score is None
    assert runtime.visible_flashcard is None
    assert runtime.active_study_session_keys == [("bio", "bio-2")]
    assert runtime.study_session.flashcards == [second_flashcard]
    assert app_state.selected_indexes_for_folder("bio") == {0}
    assert refresh_calls == [({"bio"}, None)]
    assert runtime.progress_update_count == 1
    assert runtime.complete_count == 0
    assert timer_page.prepared_next_cycle is True


def test_edit_requested_warns_when_current_flashcard_is_unavailable(
    app: QApplication,
) -> None:
    """Verify editing warns when the runtime session no longer exposes a current card."""
    app_state = StudyApplicationState()
    runtime = _FakeRuntime([], [])
    runtime.study_session.current_flashcard_index = None
    warnings: list[tuple[str, str]] = []
    controller = _build_controller(
        app_state=app_state,
        runtime=runtime,
        show_warning_message=lambda title, message: warnings.append((title, message)),
    )

    controller.handle_flashcard_edit_requested()

    assert warnings == [
        (
            "Edit flashcard",
            "The current flashcard is unavailable. Refresh and try again.",
        )
    ]
