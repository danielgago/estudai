"""Timer page tests."""

import os
from pathlib import Path

from PySide6.QtCore import QTime, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from estudai.ui.pages.timer_page import TimerPage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _get_app() -> QApplication:
    """Return an active QApplication instance."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


def _write_test_image(path: Path, *, width: int = 320, height: int = 180) -> str:
    """Create a simple raster image fixture and return its filesystem path."""
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0xFF3366CC)
    assert image.save(str(path))
    return str(path)
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
    assert page.current_flashcard_question_text() == "What is DNA?"

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
    assert page.current_flashcard_question_text() == ""


def test_copy_feedback_shows_only_while_flashcard_question_is_visible() -> None:
    """Verify copy feedback only appears for an active flashcard question."""
    _get_app()
    page = TimerPage()

    page.show_copy_feedback()
    assert page.copy_feedback_label.isHidden()

    page.show_flashcard_question("What is ATP?")
    page.show_copy_feedback()

    assert page.copy_feedback_label.isHidden() is False


def test_copy_feedback_does_not_move_flashcard_question() -> None:
    """Verify showing copy feedback does not shift the question layout."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question("What is ATP?")
    question_y_before = page.flashcard_question_label.y()

    page.show_copy_feedback()

    assert page.flashcard_question_label.y() == question_y_before


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
    assert page.flashcard_pause_actions_container.isHidden() is False
    assert page.skip_phase_button.isHidden() is False
    assert page.skip_phase_button.isEnabled() is True
    assert page.edit_flashcard_button.isHidden() is True
    assert page.delete_flashcard_button.isHidden() is True

    page.pause_timer()
    assert page.pause_button.text() == "Resume"
    assert pause_events == [True]
    assert not page.flashcard_pause_actions_container.isHidden()
    assert page.skip_phase_button.isHidden() is False
    assert page.shuffle_queue_button.isHidden()
    assert page.edit_flashcard_button.isHidden() is False
    assert page.edit_flashcard_button.isEnabled()
    assert page.delete_flashcard_button.isHidden() is False
    assert page.delete_flashcard_button.isEnabled()

    page.pause_timer()
    assert page.pause_button.text() == "Pause"
    assert pause_events == [True, False]
    assert page.flashcard_pause_actions_container.isHidden() is False
    assert page.skip_phase_button.isHidden() is False
    assert page.edit_flashcard_button.isHidden() is True
    assert page.delete_flashcard_button.isHidden() is True


def test_prepare_next_timer_cycle_paused_keeps_session_resume_available() -> None:
    """Verify deleting a paused card can leave the overall session paused safely."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question("Question?", display_duration_seconds=5)
    page.pause_timer()
    page.prepare_next_timer_cycle_paused()

    assert page.timer_display.text() == "25:00"
    assert page.is_running is False
    assert not page.start_button.isEnabled()
    assert page.pause_button.isEnabled()
    assert page.pause_button.text() == "Resume"
    assert page.stop_button.isEnabled()
    assert page.flashcard_question_label.isHidden()
    assert page.flashcard_answer_label.isHidden()


def test_flashcard_score_buttons_stay_anchored_and_in_order() -> None:
    """Verify score controls keep a stable left-to-right layout."""
    _get_app()
    page = TimerPage()
    actions_layout = page.flashcard_actions_container.layout()

    assert page.flashcard_actions_container.isHidden()
    assert actions_layout.itemAt(1).widget() is page.correct_button
    assert actions_layout.itemAt(2).widget() is page.wrong_button


def test_paused_flashcard_actions_are_positioned_above_question() -> None:
    """Verify paused edit/delete actions stay in the top-right flashcard header area."""
    _get_app()
    page = TimerPage()
    flashcard_layout = page.content_stack.widget(1).layout()
    flashcard_content_layout = page.flashcard_content_layout

    assert flashcard_layout.itemAt(0).widget() is page.flashcard_pause_actions_container
    assert flashcard_layout.itemAt(1).widget() is page.flashcard_content_widget
    assert flashcard_layout.itemAt(0).alignment() == (Qt.AlignTop | Qt.AlignRight)
    assert flashcard_content_layout.itemAt(1).widget() is page.flashcard_question_label
    assert flashcard_content_layout.itemAt(2).widget() is page.flashcard_question_image_label
    assert flashcard_content_layout.itemAt(3).widget() is page.flashcard_answer_label
    assert flashcard_content_layout.itemAt(4).widget() is page.flashcard_answer_image_label


def test_flashcard_content_uses_centered_container_without_scroll_area() -> None:
    """Verify flashcard text uses the available area directly without scrolling."""
    _get_app()
    page = TimerPage()

    assert hasattr(page, "flashcard_content_scroll_area") is False
    assert page.content_stack.widget(1).layout().itemAt(1).widget() is page.flashcard_content_widget
    assert page.flashcard_content_layout.itemAt(0).spacerItem() is not None
    assert page.flashcard_content_layout.itemAt(5).spacerItem() is not None


def test_small_flashcard_question_stays_near_vertical_center() -> None:
    """Verify smaller flashcards stay visually centered in the content area."""
    _get_app()
    page = TimerPage()
    page.flashcard_content_widget.setFixedSize(464, 248)
    page.show_flashcard_question("What is DNA?")

    question_center_y = page.flashcard_question_label.geometry().center().y()
    content_center_y = page.flashcard_content_widget.rect().center().y()

    assert abs(question_center_y - content_center_y) <= 30


def test_queue_shuffle_action_only_shows_when_available_and_paused() -> None:
    """Verify queue shuffle appears only for paused queue-mode sessions."""
    _get_app()
    page = TimerPage()
    shuffle_events: list[str] = []
    page.flashcard_queue_shuffle_requested.connect(
        lambda: shuffle_events.append("shuffle")
    )

    page.set_queue_shuffle_available(True)
    page.show_flashcard_question("Question?", display_duration_seconds=5)
    assert page.shuffle_queue_button.isHidden() is True

    page.pause_timer()
    assert page.shuffle_queue_button.isHidden() is False

    page.shuffle_queue_button.click()
    assert shuffle_events == ["shuffle"]

    page.set_queue_shuffle_available(False)
    assert page.shuffle_queue_button.isHidden() is True


def test_flashcard_skip_phase_button_emits_action() -> None:
    """Verify the skip button emits the dedicated phase-skip action signal."""
    _get_app()
    page = TimerPage()
    events: list[str] = []
    page.flashcard_phase_skip_requested.connect(lambda: events.append("skip"))

    page.show_flashcard_question("Question?", display_duration_seconds=5)
    page.skip_phase_button.click()

    assert events == ["skip"]


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


def test_flashcard_text_decodes_html_entities_as_plain_text() -> None:
    """Verify plain flashcard text decodes HTML entities without switching to rich text."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question("A &gt; B and it&#x27;s fine.")

    assert page.flashcard_question_label.text() == "A > B and it's fine."
    assert page.flashcard_question_label.textFormat() == Qt.PlainText


def test_short_flashcard_text_keeps_prominent_font_sizes() -> None:
    """Verify short flashcards keep the default large typography."""
    _get_app()
    page = TimerPage()
    page.flashcard_content_widget.setFixedSize(464, 248)
    page.show_flashcard_question("What is DNA?")
    page.show_flashcard_answer("Genetic material.")

    assert page.flashcard_question_label.font().pointSize() == 40
    assert page.flashcard_answer_label.font().pointSize() == 34


def test_long_flashcard_text_shrinks_to_fit_without_scrollbars() -> None:
    """Verify very long flashcards keep shrinking until they fit the content area."""
    _get_app()
    page = TimerPage()
    page.flashcard_content_widget.setFixedSize(320, 180)
    long_question = " ".join(["Long question text with enough detail to wrap heavily."] * 50)
    long_answer = " ".join(["Long answer text with additional explanation."] * 45)

    page.show_flashcard_question(long_question)
    page.show_flashcard_answer(long_answer)

    question_point_size = page.flashcard_question_label.font().pointSize()
    answer_point_size = page.flashcard_answer_label.font().pointSize()
    available_width = page._flashcard_content_available_width()
    combined_height = (
        page._measure_flashcard_text_height(
            page.flashcard_question_label,
            rendered_text=page.flashcard_question_label.text(),
            point_size=question_point_size,
            available_width=available_width,
        )
        + page._measure_flashcard_text_height(
            page.flashcard_answer_label,
            rendered_text=page.flashcard_answer_label.text(),
            point_size=answer_point_size,
            available_width=available_width,
        )
    )

    assert 1 <= question_point_size < 22
    assert 1 <= answer_point_size < 20
    assert combined_height <= page._flashcard_content_available_height(
        visible_label_count=2
    )


def test_flashcard_image_displays_with_safe_scaling(tmp_path: Path) -> None:
    """Verify attached images render within the available timer-page bounds."""
    _get_app()
    page = TimerPage()
    page.flashcard_content_widget.setFixedSize(320, 220)
    image_path = _write_test_image(tmp_path / "diagram.png", width=1600, height=900)

    page.show_flashcard_question("What structure is this?", image_path=image_path)
    page.show_flashcard_answer("It is the hippocampus.", image_path=image_path)

    question_pixmap = page.flashcard_question_image_label.pixmap()
    answer_pixmap = page.flashcard_answer_image_label.pixmap()
    assert question_pixmap is not None
    assert answer_pixmap is not None
    assert question_pixmap.width() <= page._flashcard_content_available_width()
    assert question_pixmap.height() <= page._FLASHCARD_IMAGE_MAX_HEIGHT
    assert answer_pixmap.width() <= page._flashcard_content_available_width()
    assert answer_pixmap.height() <= page._FLASHCARD_IMAGE_MAX_HEIGHT


def test_missing_flashcard_image_shows_clear_fallback_text(tmp_path: Path) -> None:
    """Verify missing image files show an explicit non-crashing fallback state."""
    _get_app()
    page = TimerPage()

    page.show_flashcard_question(
        "Which organ is shown?",
        image_path=str(tmp_path / "missing.png"),
    )
    page.show_flashcard_answer(
        "It is the liver.",
        image_path=str(tmp_path / "missing.png"),
    )

    assert page.flashcard_question_image_label.text() == "Question image unavailable."
    assert page.flashcard_answer_image_label.text() == "Answer image unavailable."
