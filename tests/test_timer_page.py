"""Timer page tests."""

import os

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QApplication

from estudai.ui.pages.timer_page import TimerPage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _get_app() -> QApplication:
    """Return an active QApplication instance."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


def test_timer_start_stop_reset_and_context() -> None:
    """Verify timer controls and context label updates."""
    _get_app()
    page = TimerPage()

    page.start_timer()
    assert page.is_running is True
    assert not page.start_button.isEnabled()
    assert page.pause_button.isEnabled()
    assert page.stop_button.isEnabled()

    page.pause_timer()
    assert page.is_running is False
    assert not page.start_button.isEnabled()
    assert page.pause_button.isEnabled()
    assert page.pause_button.text() == "Resume"
    assert page.stop_button.isEnabled()

    page.pause_timer()
    assert page.is_running is True

    page.stop_timer()
    assert page.is_running is False
    assert page.start_button.isEnabled()
    assert not page.pause_button.isEnabled()
    assert not page.stop_button.isEnabled()

    page.set_flashcard_context("biology", 4)
    assert page.folder_context_label.text() == "Folder: biology (4 cards)"
    page.set_session_progress(
        completed_count=1,
        remaining_count=3,
        wrong_pending_count=1,
        total_count=4,
    )
    assert page.folder_context_label.text() == (
        "Session: 1/4 completed | 3 remaining | 1 pending review"
    )

    page.time = QTime(0, 10, 0)
    page.reset_timer()
    assert page.timer_display.text() == "25:00"


def test_timer_page_formats_single_card_context_label() -> None:
    """Verify timer context uses correct singular card label."""
    _get_app()
    page = TimerPage()

    page.set_flashcard_context("chemistry", 1)

    assert page.folder_context_label.text() == "Folder: chemistry (1 card)"


def test_timer_update_stops_when_reaches_zero() -> None:
    """Verify timer update stops the timer when countdown reaches 00:00."""
    _get_app()
    page = TimerPage()
    completions: list[bool] = []
    page.timer_cycle_completed.connect(lambda: completions.append(True))
    page.time = QTime(0, 0, 1)
    page.start_timer()

    page.update_timer()

    assert page.timer_display.text() == "00:00"
    assert page.is_running is False
    assert completions == [True]


def test_zero_second_timer_uses_ready_idle_text_and_immediate_cycle() -> None:
    """Verify 0-second mode skips countdown and returns to Ready? when idle."""
    _get_app()
    page = TimerPage(default_duration_seconds=0)
    completions: list[bool] = []
    page.timer_cycle_completed.connect(lambda: completions.append(True))

    assert page.timer_display.text() == "Ready?"

    page.start_timer()

    assert page.timer_display.text() == "Ready?"
    assert page.is_running is False
    assert not page.pause_button.isEnabled()
    assert not page.stop_button.isEnabled()
    assert completions == [True]

    page.stop_timer()
    assert page.timer_display.text() == "Ready?"


def test_flashcard_display_hides_timer_and_reveals_answer() -> None:
    """Verify flashcard question/answer rendering inside timer page."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question("What is DNA?")
    assert not page.timer_display.isVisible()
    assert not page.flashcard_question_label.isHidden()
    assert page.flashcard_question_label.text() == "What is DNA?"
    assert page.flashcard_answer_label.isHidden()
    assert page.flashcard_actions_container.isHidden()
    assert not page.correct_button.isVisible()
    assert not page.wrong_button.isVisible()
    assert not page.correct_button.isEnabled()
    assert not page.wrong_button.isEnabled()

    page.show_flashcard_answer("Genetic material.")
    assert not page.flashcard_answer_label.isHidden()
    assert page.flashcard_answer_label.text() == "Genetic material."
    assert not page.flashcard_actions_container.isHidden()
    assert page.correct_button.isEnabled()
    assert page.wrong_button.isEnabled()

    page.clear_flashcard_display()
    assert not page.timer_display.isHidden()
    assert page.flashcard_question_label.isHidden()
    assert page.flashcard_answer_label.isHidden()
    assert page.flashcard_actions_container.isHidden()
    assert not page.correct_button.isVisible()
    assert not page.wrong_button.isVisible()
    assert not page.correct_button.isEnabled()
    assert not page.wrong_button.isEnabled()


def test_flashcard_progress_bar_updates_per_phase() -> None:
    """Verify flashcard progress bar keeps its space and activates per phase."""
    _get_app()
    page = TimerPage()

    assert not page.flashcard_progress_bar.isHidden()
    assert page.is_flashcard_progress_active() is False

    page.show_flashcard_question("What is ATP?", display_duration_seconds=2)
    assert page.is_flashcard_progress_active() is True

    page.show_flashcard_answer("Cellular energy molecule.", display_duration_seconds=3)
    assert page.is_flashcard_progress_active() is True

    page.clear_flashcard_display()
    assert not page.flashcard_progress_bar.isHidden()
    assert page.is_flashcard_progress_active() is False


def test_timer_page_has_no_title_and_no_reset_button() -> None:
    """Verify timer page keeps only Start/Pause/Stop controls."""
    _get_app()
    page = TimerPage()

    assert not hasattr(page, "reset_button")
    assert page.start_button.text() == "Start"
    assert page.pause_button.text() == "Pause"
    assert page.stop_button.text() == "Stop"


def test_flashcard_phase_keeps_pause_and_stop_enabled() -> None:
    """Verify flashcard phase keeps Pause/Stop active and toggles pause state."""
    _get_app()
    page = TimerPage()
    pause_events: list[bool] = []
    page.flashcard_pause_toggled.connect(lambda paused: pause_events.append(paused))

    page.show_flashcard_question("Long question?", display_duration_seconds=10)
    assert not page.start_button.isEnabled()
    assert page.pause_button.isEnabled()
    assert page.stop_button.isEnabled()

    page.pause_timer()
    assert page.pause_button.text() == "Resume"
    assert pause_events == [True]

    page.pause_timer()
    assert page.pause_button.text() == "Pause"
    assert pause_events == [True, False]


def test_flashcard_score_buttons_stay_anchored_and_in_order() -> None:
    """Verify score controls keep a stable left-to-right layout."""
    _get_app()
    page = TimerPage()
    actions_layout = page.flashcard_actions_container.layout()

    assert page.flashcard_actions_container.isHidden()
    assert actions_layout.itemAt(1).widget() is page.correct_button
    assert actions_layout.itemAt(2).widget() is page.wrong_button


def test_flashcard_score_buttons_emit_actions() -> None:
    """Verify answer actions emit explicit events and keep a visual selection cue."""
    _get_app()
    page = TimerPage()
    events: list[str] = []
    page.flashcard_marked_correct.connect(lambda: events.append("correct"))
    page.flashcard_marked_wrong.connect(lambda: events.append("wrong"))

    page.show_flashcard_answer("A.")
    page.correct_button.click()
    assert page.selected_flashcard_score() == "correct"
    assert page.correct_button.isChecked()
    assert not page.wrong_button.isChecked()

    page.wrong_button.click()
    assert page.selected_flashcard_score() == "wrong"
    assert page.wrong_button.isChecked()
    assert not page.correct_button.isChecked()

    page.wrong_button.click()
    assert page.selected_flashcard_score() is None
    assert not page.correct_button.isChecked()
    assert not page.wrong_button.isChecked()

    assert events == ["correct", "wrong", "wrong"]


def test_flashcard_score_buttons_define_distinct_checked_and_disabled_styles() -> None:
    """Verify score buttons style checked and disabled states distinctly."""
    _get_app()
    page = TimerPage()

    stylesheet = page.correct_button.styleSheet()

    assert "QPushButton:disabled" in stylesheet
    assert "QPushButton:pressed:!disabled, QPushButton:checked" in stylesheet
    assert "border: 2px solid" in stylesheet


def test_flashcard_text_formats_inline_latex() -> None:
    """Verify inline LaTeX-like snippets are rendered as readable text."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question("Pró-opiomelanocortina ($POMC$) e $ER\\alpha$.")
    assert "$" not in page.flashcard_question_label.text()
    assert "POMC" in page.flashcard_question_label.text()
    assert "ERα" in page.flashcard_question_label.text()

    page.show_flashcard_answer("Recetores $MT_1$, $Ca^{2+}$ e $GABA_A$.")
    assert "MT<sub>1</sub>" in page.flashcard_answer_label.text()
    assert "Ca<sup>2+</sup>" in page.flashcard_answer_label.text()
    assert "GABA<sub>A</sub>" in page.flashcard_answer_label.text()
