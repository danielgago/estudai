"""Timer-page controller tests."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget

from estudai.services.csv_flashcards import Flashcard
from estudai.services.settings import (
    AppSettings,
    StudyOrderMode,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
)
from estudai.services.study_time import StudyTimeTracker
from estudai.ui.application_state import FolderLibraryState, StudyApplicationState
from estudai.ui.controllers.timer_page_controller import TimerPageController
from estudai.ui.pages import TimerPage


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


class _FakeSidebarItem:
    """Minimal sidebar item used by timer controller tests."""

    def __init__(self, folder_id: str, *, checked: bool) -> None:
        """Initialize the fake item.

        Args:
            folder_id: Folder id stored in the item.
            checked: Whether the item is checked.
        """
        self._folder_id = folder_id
        self._checked = checked

    def data(self, role: int) -> str | None:
        """Return item data for the requested role."""
        if role == Qt.UserRole:
            return self._folder_id
        return None

    def checkState(self) -> Qt.CheckState:  # noqa: N802
        """Return the item's checked state."""
        return Qt.Checked if self._checked else Qt.Unchecked


def _flashcard(
    question: str,
    answer: str,
    line_number: int,
    *,
    stable_id: str,
    source_file: Path | None = None,
    origin_relative_path: str | None = None,
) -> Flashcard:
    """Create a flashcard fixture payload."""
    return Flashcard(
        question=question,
        answer=answer,
        source_file=source_file or Path("cards.csv"),
        source_line=line_number,
        stable_id=stable_id,
        origin_relative_path=origin_relative_path,
    )


def _settings() -> AppSettings:
    """Return timer settings used by controller tests."""
    return AppSettings(
        timer_duration_seconds=0,
        flashcard_probability_percent=100,
        flashcard_study_order_mode=StudyOrderMode.QUEUE,
        flashcard_queue_start_shuffled=False,
        wrong_answer_completion_mode=WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE,
        wrong_answer_reinsertion_mode=WrongAnswerReinsertionMode.PUSH_TO_END,
        wrong_answer_reinsert_after_count=0,
        question_display_duration_seconds=2,
        answer_display_duration_seconds=3,
    )


def test_start_study_session_builds_runtime_session_state(app: QApplication) -> None:
    """Verify controller startup derives session keys and runtime counters."""
    timer_page = TimerPage(default_duration_seconds=0)
    app_state = StudyApplicationState()
    flashcard = _flashcard("Q1?", "A1.", 1, stable_id="bio-1")
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
    app_state.refresh_selection({"bio"})
    controller = TimerPageController(
        parent=QWidget(),
        timer_page=timer_page,
        app_state=app_state,
        flashcard_phase_timer=QTimer(),
        flashcard_sound_player=None,
        study_time_tracker=StudyTimeTracker(),
        iter_sidebar_folder_items=lambda: [_FakeSidebarItem("bio", checked=True)],
        set_navigation_visible=lambda _visible: None,
        switch_to_timer=lambda: None,
        emit_show_flashcard=lambda _flashcard: None,
        refresh_sidebar_folder_progress_labels=lambda _folder_ids=None: None,
        start_flashcard_phase_timer=lambda _delay, _callback: None,
        handle_flashcard_phase_timeout=lambda: None,
        handle_timer_cycle_completed=lambda: None,
        load_settings=_settings,
        default_sound_path_getter=lambda: "",
    )

    assert controller.start_study_session() is True
    assert controller.study_session.active is True
    assert controller.active_study_session_keys == [("bio", "bio-1")]
    assert controller.study_session.progress().total_count == 1
    assert controller.study_session.progress().remaining_count == 1


def test_show_flashcard_popup_uses_host_timer_callback(app: QApplication) -> None:
    """Verify popup rendering goes through the injected phase-timer seam."""
    timer_page = TimerPage(default_duration_seconds=0)
    start_phase_calls: list[int] = []
    navigation_values: list[bool] = []
    switch_calls: list[str] = []
    app_state = StudyApplicationState()
    flashcard = _flashcard(
        "Question?",
        "Answer.",
        1,
        stable_id="bio-1",
        source_file=Path("/tmp/bio/_estudai_flashcards.csv"),
        origin_relative_path="cards.csv",
    )
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id="science",
                folder_name="Science",
                folder_path=Path("/tmp/science"),
                flashcards=[],
                is_flashcard_set=False,
            ),
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[flashcard],
                parent_id="science",
                selected_indexes={0},
            ),
        ]
    )
    app_state.refresh_selection({"bio"})
    controller = TimerPageController(
        parent=QWidget(),
        timer_page=timer_page,
        app_state=app_state,
        flashcard_phase_timer=QTimer(),
        flashcard_sound_player=None,
        study_time_tracker=StudyTimeTracker(),
        iter_sidebar_folder_items=lambda: [_FakeSidebarItem("bio", checked=True)],
        set_navigation_visible=lambda visible: navigation_values.append(visible),
        switch_to_timer=lambda: switch_calls.append("timer"),
        emit_show_flashcard=lambda _flashcard: None,
        refresh_sidebar_folder_progress_labels=lambda _folder_ids=None: None,
        start_flashcard_phase_timer=lambda delay, _callback: start_phase_calls.append(
            delay
        ),
        handle_flashcard_phase_timeout=lambda: None,
        handle_timer_cycle_completed=lambda: None,
        load_settings=_settings,
        default_sound_path_getter=lambda: "",
    )

    assert controller.start_study_session() is True

    controller.show_flashcard_popup(flashcard)

    assert controller.visible_flashcard == flashcard
    assert controller.visible_flashcard_folder_id == "bio"
    assert timer_page.flashcard_question_label.text() == "Question?"
    assert timer_page.current_flashcard_origin_path() == "Science / Biology"
    assert timer_page.flashcard_origin_label.text() == "Science / Biology"
    assert start_phase_calls == [2000]
    assert switch_calls == ["timer"]
    assert navigation_values == [False]
