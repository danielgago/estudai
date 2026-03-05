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

    page.time = QTime(0, 10, 0)
    page.reset_timer()
    assert page.timer_display.text() == "25:00"


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


def test_flashcard_display_hides_timer_and_reveals_answer() -> None:
    """Verify flashcard question/answer rendering inside timer page."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question("What is DNA?")
    assert not page.timer_display.isVisible()
    assert not page.flashcard_question_label.isHidden()
    assert page.flashcard_question_label.text() == "What is DNA?"
    assert page.flashcard_answer_label.isHidden()

    page.show_flashcard_answer("Genetic material.")
    assert not page.flashcard_answer_label.isHidden()
    assert page.flashcard_answer_label.text() == "Genetic material."

    page.clear_flashcard_display()
    assert not page.timer_display.isHidden()
    assert page.flashcard_question_label.isHidden()
    assert page.flashcard_answer_label.isHidden()


def test_flashcard_progress_bar_updates_per_phase() -> None:
    """Verify flashcard progress bar appears for question/answer phases."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question("What is ATP?", display_duration_seconds=2)
    assert not page.flashcard_progress_bar.isHidden()

    page.show_flashcard_answer("Cellular energy molecule.", display_duration_seconds=3)
    assert not page.flashcard_progress_bar.isHidden()

    page.clear_flashcard_display()
    assert page.flashcard_progress_bar.isHidden()


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
