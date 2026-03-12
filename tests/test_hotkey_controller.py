"""Hotkey controller tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from estudai.services.hotkeys import (
    DEFAULT_HOTKEY_BINDINGS,
    HotkeyAction,
    HotkeyRegistrationError,
)
from estudai.services.settings import AppSettings
from estudai.ui.controllers.hotkey_controller import HotkeyController


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


class _FakeHotkeyService:
    """Minimal hotkey service used to capture controller interactions."""

    def __init__(self, *, availability_error: str | None = None) -> None:
        """Initialize the fake service.

        Args:
            availability_error: Optional availability failure to expose.
        """
        self.availability_error = availability_error
        self.apply_calls: list[dict[HotkeyAction, str]] = []
        self._queued_errors: list[HotkeyRegistrationError] = []

    def queue_error(self, error: HotkeyRegistrationError) -> None:
        """Queue one error for the next apply attempt."""
        self._queued_errors.append(error)

    def apply_bindings(
        self,
        bindings: dict[HotkeyAction, str],
        _callbacks: dict[HotkeyAction, object],
    ) -> dict[HotkeyAction, str]:
        """Record one apply call and optionally raise a queued error."""
        self.apply_calls.append(dict(bindings))
        if self._queued_errors:
            raise self._queued_errors.pop(0)
        return dict(bindings)


class _FakeTimerPage(QWidget):
    """Minimal timer page spy used by hotkey controller tests."""

    def __init__(self) -> None:
        """Initialize the fake timer page."""
        super().__init__()
        self.start_button = QPushButton(self)
        self.pause_button = QPushButton(self)
        self.stop_button = QPushButton(self)
        self.correct_button = QPushButton(self)
        self.wrong_button = QPushButton(self)
        self.skip_phase_button = QPushButton(self)
        self.flashcard_question_label = QLabel(self)
        self.flashcard_question_label.hide()
        self.start_click_count = 0
        self.pause_click_count = 0
        self.stop_click_count = 0
        self.correct_click_count = 0
        self.wrong_click_count = 0
        self.skip_click_count = 0
        self.copy_feedback_count = 0
        self.start_button.clicked.connect(self._handle_start_clicked)
        self.pause_button.clicked.connect(self._handle_pause_clicked)
        self.stop_button.clicked.connect(self._handle_stop_clicked)
        self.correct_button.clicked.connect(self._handle_correct_clicked)
        self.wrong_button.clicked.connect(self._handle_wrong_clicked)
        self.skip_phase_button.clicked.connect(self._handle_skip_clicked)

    def current_flashcard_question_text(self) -> str:
        """Return the current question label text."""
        return self.flashcard_question_label.text()

    def show_copy_feedback(self) -> None:
        """Record showing copy feedback."""
        self.copy_feedback_count += 1

    def _handle_start_clicked(self) -> None:
        """Record a start-button click."""
        self.start_click_count += 1

    def _handle_pause_clicked(self) -> None:
        """Record a pause-button click."""
        self.pause_click_count += 1

    def _handle_stop_clicked(self) -> None:
        """Record a stop-button click."""
        self.stop_click_count += 1

    def _handle_correct_clicked(self) -> None:
        """Record a correct-button click."""
        self.correct_click_count += 1

    def _handle_wrong_clicked(self) -> None:
        """Record a wrong-button click."""
        self.wrong_click_count += 1

    def _handle_skip_clicked(self) -> None:
        """Record a skip-button click."""
        self.skip_click_count += 1


def _build_controller(
    *,
    current_page: QWidget | None = None,
    hotkey_service: _FakeHotkeyService | None = None,
    save_settings_calls: list[AppSettings] | None = None,
    warnings: list[tuple[str, str]] | None = None,
) -> tuple[HotkeyController, _FakeTimerPage, QWidget]:
    """Create a configured hotkey controller for tests."""
    parent = QWidget()
    timer_page = _FakeTimerPage()
    active_page = {"widget": current_page or timer_page}
    controller = HotkeyController(
        parent=parent,
        timer_page=timer_page,  # type: ignore[arg-type]
        current_page_getter=lambda: active_page["widget"],
        hotkey_service=hotkey_service or _FakeHotkeyService(),  # type: ignore[arg-type]
        emit_hotkey_action=lambda _action_value: None,
        show_warning_message=lambda title, message: (
            warnings.append((title, message)) if warnings is not None else None
        ),
        toggle_fullscreen=lambda: None,
        exit_fullscreen=lambda: None,
        save_settings_callback=lambda settings: (
            save_settings_calls.append(settings)
            if save_settings_calls is not None
            else None
        ),
    )
    controller.configure_window_shortcuts()
    return controller, timer_page, parent


def test_configure_window_shortcuts_creates_application_scoped_shortcuts(
    app: QApplication,
) -> None:
    """Verify configured shortcuts use application scope and fullscreen defaults."""
    controller, _timer_page, _parent = _build_controller()

    assert controller.timer_page_start_stop_shortcut.context() == Qt.ApplicationShortcut
    assert controller.toggle_fullscreen_shortcut.key().toString() == "F11"
    assert controller.exit_fullscreen_shortcut.key().toString() == "Esc"


def test_apply_in_app_shortcut_bindings_keeps_enter_and_return_in_sync(
    app: QApplication,
) -> None:
    """Verify start/stop bindings keep Enter and Return aliases aligned."""
    controller, _timer_page, _parent = _build_controller()

    controller.apply_in_app_shortcut_bindings(
        AppSettings(in_app_start_stop_shortcut="Ctrl+Enter")
    )

    assert {
        shortcut.toString()
        for shortcut in controller.timer_page_start_stop_shortcut.keys()
    } == {"Ctrl+Enter", "Ctrl+Return"}


def test_apply_initial_hotkey_bindings_falls_back_after_registration_error(
    app: QApplication,
) -> None:
    """Verify failed startup registration retries with default global bindings."""
    warnings: list[tuple[str, str]] = []
    hotkey_service = _FakeHotkeyService()
    hotkey_service.queue_error(HotkeyRegistrationError("Could not register"))
    controller, _timer_page, _parent = _build_controller(
        hotkey_service=hotkey_service,
        warnings=warnings,
    )

    controller.apply_initial_hotkey_bindings(
        AppSettings(start_stop_hotkey="Ctrl+Alt+S")
    )

    assert warnings == [("Global hotkeys", "Could not register")]
    assert hotkey_service.apply_calls[0][HotkeyAction.START_STOP] == "Ctrl+Alt+S"
    assert hotkey_service.apply_calls[1] == DEFAULT_HOTKEY_BINDINGS


def test_handle_global_hotkey_action_requested_dispatches_timer_actions(
    app: QApplication,
) -> None:
    """Verify hotkey dispatch mirrors timer-page actions when timer is active."""
    controller, timer_page, _parent = _build_controller()
    timer_page.flashcard_question_label.setText("Question?")
    timer_page.flashcard_question_label.show()
    QApplication.clipboard().clear()

    controller.handle_global_hotkey_action_requested(HotkeyAction.START_STOP.value)
    controller.handle_global_hotkey_action_requested(HotkeyAction.PAUSE_RESUME.value)
    controller.handle_global_hotkey_action_requested(HotkeyAction.SKIP_PHASE.value)
    controller.handle_global_hotkey_action_requested(HotkeyAction.MARK_CORRECT.value)
    controller.handle_global_hotkey_action_requested(HotkeyAction.MARK_WRONG.value)
    controller.handle_global_hotkey_action_requested(HotkeyAction.COPY_QUESTION.value)

    assert timer_page.start_click_count == 1
    assert timer_page.pause_click_count == 1
    assert timer_page.skip_click_count == 1
    assert timer_page.correct_click_count == 1
    assert timer_page.wrong_click_count == 1
    assert QApplication.clipboard().text() == "Question?"
    assert timer_page.copy_feedback_count == 1


def test_handle_global_hotkey_action_requested_ignores_non_timer_pages(
    app: QApplication,
) -> None:
    """Verify timer actions are ignored when another page is active."""
    other_page = QWidget()
    controller, timer_page, _parent = _build_controller(current_page=other_page)
    timer_page.flashcard_question_label.setText("Question?")
    timer_page.flashcard_question_label.show()
    QApplication.clipboard().clear()

    controller.handle_global_hotkey_action_requested(HotkeyAction.START_STOP.value)
    controller.handle_global_hotkey_action_requested(HotkeyAction.COPY_QUESTION.value)

    assert timer_page.start_click_count == 0
    assert QApplication.clipboard().text() == ""
    assert timer_page.copy_feedback_count == 0


def test_save_settings_from_page_applies_live_bindings_before_persisting(
    app: QApplication,
) -> None:
    """Verify save applies hotkey and shortcut changes before persisting settings."""
    save_settings_calls: list[AppSettings] = []
    hotkey_service = _FakeHotkeyService()
    controller, _timer_page, _parent = _build_controller(
        hotkey_service=hotkey_service,
        save_settings_calls=save_settings_calls,
    )
    settings = AppSettings(
        start_stop_hotkey="Ctrl+Alt+S",
        in_app_pause_resume_shortcut="Ctrl+P",
    )

    controller.save_settings_from_page(settings)

    assert hotkey_service.apply_calls == [
        {
            HotkeyAction.PAUSE_RESUME: settings.pause_resume_hotkey,
            HotkeyAction.START_STOP: "Ctrl+Alt+S",
            HotkeyAction.SKIP_PHASE: settings.skip_phase_hotkey,
            HotkeyAction.MARK_CORRECT: settings.mark_correct_hotkey,
            HotkeyAction.MARK_WRONG: settings.mark_wrong_hotkey,
            HotkeyAction.COPY_QUESTION: settings.copy_question_hotkey,
        }
    ]
    assert controller.timer_page_pause_resume_shortcut.key().toString() == "Ctrl+P"
    assert save_settings_calls == [settings]
