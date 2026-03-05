"""Timer page tests."""

import os

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QApplication

from estudai.ui.pages.timer_page import TimerPage
from estudai.ui.timer_page import TimerPage as LegacyTimerPage

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
    assert page.start_button.isEnabled()
    assert not page.pause_button.isEnabled()
    assert page.stop_button.isEnabled()

    page.start_timer()
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


def test_legacy_timer_page_import_points_to_pages_timer() -> None:
    """Verify legacy timer module re-exports the page timer class."""
    assert LegacyTimerPage is TimerPage


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
