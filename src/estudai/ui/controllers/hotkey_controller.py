"""Application hotkey and shortcut controller."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QWidget

from estudai.services.hotkeys import (
    DEFAULT_HOTKEY_BINDINGS,
    GlobalHotkeyService,
    HotkeyAction,
    HotkeyRegistrationError,
    normalize_hotkey_binding,
)
from estudai.services.settings import (
    AppSettings,
    InAppShortcutAction,
    hotkey_bindings_from_settings,
    in_app_shortcut_bindings_from_settings,
    save_app_settings,
)
from estudai.ui.pages import TimerPage

CurrentPageGetter = Callable[[], QWidget | None]
EmitHotkeyAction = Callable[[str], None]
ShowWarningMessage = Callable[[str, str], None]
WindowAction = Callable[[], None]
SaveSettingsCallback = Callable[[AppSettings], None]


class HotkeyController:
    """Coordinate application shortcuts and global hotkey dispatch."""

    def __init__(
        self,
        *,
        parent: QWidget,
        timer_page: TimerPage,
        current_page_getter: CurrentPageGetter,
        hotkey_service: GlobalHotkeyService,
        emit_hotkey_action: EmitHotkeyAction,
        show_warning_message: ShowWarningMessage,
        toggle_fullscreen: WindowAction,
        exit_fullscreen: WindowAction,
        save_settings_callback: SaveSettingsCallback = save_app_settings,
    ) -> None:
        """Initialize the controller.

        Args:
            parent: Parent widget used for application-scoped shortcuts.
            timer_page: Timer page whose actions are mirrored by shortcuts.
            current_page_getter: Returns the current visible page widget.
            hotkey_service: Service used to register global hotkeys.
            emit_hotkey_action: Emits global-hotkey actions back onto the UI
                thread.
            show_warning_message: Displays hotkey registration warnings.
            toggle_fullscreen: Toggles fullscreen mode.
            exit_fullscreen: Leaves fullscreen mode.
            save_settings_callback: Persists application settings after live
                bindings are updated.
        """
        self._parent = parent
        self._timer_page = timer_page
        self._current_page_getter = current_page_getter
        self._hotkey_service = hotkey_service
        self._emit_hotkey_action = emit_hotkey_action
        self._show_warning_message = show_warning_message
        self._toggle_fullscreen = toggle_fullscreen
        self._exit_fullscreen = exit_fullscreen
        self._save_settings_callback = save_settings_callback
        self._timer_page_pause_resume_shortcut: QShortcut | None = None
        self._timer_page_start_stop_shortcut: QShortcut | None = None
        self._timer_page_skip_phase_shortcut: QShortcut | None = None
        self._timer_page_mark_correct_shortcut: QShortcut | None = None
        self._timer_page_mark_wrong_shortcut: QShortcut | None = None
        self._timer_page_copy_question_shortcut: QShortcut | None = None
        self._toggle_fullscreen_shortcut: QShortcut | None = None
        self._exit_fullscreen_shortcut: QShortcut | None = None

    @property
    def timer_page_pause_resume_shortcut(self) -> QShortcut:
        """Return the application-scoped pause/resume shortcut."""
        return self._require_shortcut(self._timer_page_pause_resume_shortcut)

    @property
    def timer_page_start_stop_shortcut(self) -> QShortcut:
        """Return the application-scoped start/stop shortcut."""
        return self._require_shortcut(self._timer_page_start_stop_shortcut)

    @property
    def timer_page_skip_phase_shortcut(self) -> QShortcut:
        """Return the application-scoped skip-phase shortcut."""
        return self._require_shortcut(self._timer_page_skip_phase_shortcut)

    @property
    def timer_page_mark_correct_shortcut(self) -> QShortcut:
        """Return the application-scoped mark-correct shortcut."""
        return self._require_shortcut(self._timer_page_mark_correct_shortcut)

    @property
    def timer_page_mark_wrong_shortcut(self) -> QShortcut:
        """Return the application-scoped mark-wrong shortcut."""
        return self._require_shortcut(self._timer_page_mark_wrong_shortcut)

    @property
    def timer_page_copy_question_shortcut(self) -> QShortcut:
        """Return the application-scoped copy-question shortcut."""
        return self._require_shortcut(self._timer_page_copy_question_shortcut)

    @property
    def toggle_fullscreen_shortcut(self) -> QShortcut:
        """Return the application-scoped fullscreen-toggle shortcut."""
        return self._require_shortcut(self._toggle_fullscreen_shortcut)

    @property
    def exit_fullscreen_shortcut(self) -> QShortcut:
        """Return the application-scoped fullscreen-exit shortcut."""
        return self._require_shortcut(self._exit_fullscreen_shortcut)

    def configure_window_shortcuts(self) -> None:
        """Create application-scoped shortcuts used throughout the window."""
        self._timer_page_pause_resume_shortcut = self.create_application_shortcut(
            self._trigger_timer_page_pause_resume
        )
        self._timer_page_start_stop_shortcut = self.create_application_shortcut(
            self._trigger_timer_page_start_stop
        )
        self._timer_page_skip_phase_shortcut = self.create_application_shortcut(
            self._trigger_timer_page_skip_phase
        )
        self._timer_page_mark_correct_shortcut = self.create_application_shortcut(
            self._trigger_timer_page_mark_correct
        )
        self._timer_page_mark_wrong_shortcut = self.create_application_shortcut(
            self._trigger_timer_page_mark_wrong
        )
        self._timer_page_copy_question_shortcut = self.create_application_shortcut(
            self._trigger_timer_page_copy_question
        )
        self._toggle_fullscreen_shortcut = self.create_application_shortcut(
            self._toggle_fullscreen
        )
        self.toggle_fullscreen_shortcut.setKey(QKeySequence("F11"))
        self._exit_fullscreen_shortcut = self.create_application_shortcut(
            self._exit_fullscreen
        )
        self.exit_fullscreen_shortcut.setKey(QKeySequence("Escape"))

    def apply_in_app_shortcut_bindings(self, settings: AppSettings) -> None:
        """Apply persisted in-app shortcut bindings to the current window."""
        bindings = in_app_shortcut_bindings_from_settings(settings)
        self.timer_page_pause_resume_shortcut.setKey(
            QKeySequence(bindings[InAppShortcutAction.PAUSE_RESUME])
        )
        self.timer_page_start_stop_shortcut.setKeys(
            self.start_stop_shortcut_sequences(bindings[InAppShortcutAction.START_STOP])
        )
        self.timer_page_skip_phase_shortcut.setKey(
            QKeySequence(bindings[InAppShortcutAction.SKIP_PHASE])
        )
        self.timer_page_mark_correct_shortcut.setKey(
            QKeySequence(bindings[InAppShortcutAction.MARK_CORRECT])
        )
        self.timer_page_mark_wrong_shortcut.setKey(
            QKeySequence(bindings[InAppShortcutAction.MARK_WRONG])
        )
        self.timer_page_copy_question_shortcut.setKey(
            QKeySequence(bindings[InAppShortcutAction.COPY_QUESTION])
        )

    def apply_initial_hotkey_bindings(self, settings: AppSettings) -> None:
        """Apply persisted global hotkeys and fall back to defaults on failure."""
        if self._hotkey_service.availability_error is not None:
            return
        try:
            self._hotkey_service.apply_bindings(
                hotkey_bindings_from_settings(settings),
                self.hotkey_action_callbacks(),
            )
            return
        except HotkeyRegistrationError as error:
            self._show_warning_message("Global hotkeys", str(error))

        try:
            self._hotkey_service.apply_bindings(
                DEFAULT_HOTKEY_BINDINGS,
                self.hotkey_action_callbacks(),
            )
        except HotkeyRegistrationError:
            return

    def save_settings_from_page(self, settings: AppSettings) -> None:
        """Apply live bindings and persist settings changes."""
        if self._hotkey_service.availability_error is None:
            self._hotkey_service.apply_bindings(
                hotkey_bindings_from_settings(settings),
                self.hotkey_action_callbacks(),
            )
        self.apply_in_app_shortcut_bindings(settings)
        self._save_settings_callback(settings)

    def hotkey_action_callbacks(self) -> dict[HotkeyAction, object]:
        """Return thread-safe callbacks that marshal actions to the UI thread."""
        return {
            action: (
                lambda action_value=action.value: self._emit_hotkey_action(action_value)
            )
            for action in HotkeyAction
        }

    def handle_global_hotkey_action_requested(self, action_value: str) -> None:
        """Dispatch one global hotkey action onto the timer-page UI path."""
        try:
            action = HotkeyAction(action_value)
        except ValueError:
            return

        if action is HotkeyAction.PAUSE_RESUME:
            self._trigger_timer_page_pause_resume()
            return
        if action is HotkeyAction.START_STOP:
            self._trigger_timer_page_start_stop()
            return
        if action is HotkeyAction.SKIP_PHASE:
            self._trigger_timer_page_skip_phase()
            return
        if action is HotkeyAction.MARK_CORRECT:
            self._trigger_timer_page_mark_correct()
            return
        if action is HotkeyAction.MARK_WRONG:
            self._trigger_timer_page_mark_wrong()
            return
        if action is HotkeyAction.COPY_QUESTION:
            self._trigger_timer_page_copy_question()

    def timer_page_is_active(self) -> bool:
        """Return whether timer shortcuts should affect the current page."""
        return self._current_page_getter() is self._timer_page

    def trigger_timer_page_pause_resume(self) -> None:
        """Mirror the pause/resume button path for external callers."""
        self._trigger_timer_page_pause_resume()

    def trigger_timer_page_start_stop(self) -> None:
        """Mirror the start/stop button path for external callers."""
        self._trigger_timer_page_start_stop()

    def trigger_timer_page_mark_correct(self) -> None:
        """Mirror the mark-correct button path for external callers."""
        self._trigger_timer_page_mark_correct()

    def trigger_timer_page_skip_phase(self) -> None:
        """Mirror the skip-phase button path for external callers."""
        self._trigger_timer_page_skip_phase()

    def trigger_timer_page_mark_wrong(self) -> None:
        """Mirror the mark-wrong button path for external callers."""
        self._trigger_timer_page_mark_wrong()

    def trigger_timer_page_copy_question(self) -> None:
        """Mirror the copy-question action path for external callers."""
        self._trigger_timer_page_copy_question()

    @staticmethod
    def start_stop_shortcut_sequences(binding: str) -> list[QKeySequence]:
        """Return the start/stop shortcut list with Enter/Return aliases kept aligned."""
        normalized_binding = normalize_hotkey_binding(binding, allow_empty=True)
        if not normalized_binding:
            return [QKeySequence()]
        primary_sequence = QKeySequence(binding)
        primary_binding = primary_sequence.toString()
        sequences = [primary_sequence]
        if normalized_binding.endswith("enter"):
            if "+" in primary_binding:
                prefix, _separator, key_name = primary_binding.rpartition("+")
                alias_key_name = "Return" if key_name == "Enter" else "Enter"
                alias_binding = f"{prefix}+{alias_key_name}"
            else:
                alias_binding = "Return" if primary_binding == "Enter" else "Enter"
            sequences.append(QKeySequence(alias_binding))
        return sequences

    def create_application_shortcut(self, callback: object) -> QShortcut:
        """Create one app-scoped shortcut with no binding assigned yet."""
        shortcut = QShortcut(QKeySequence(), self._parent)
        shortcut.setContext(Qt.ApplicationShortcut)
        shortcut.activated.connect(callback)
        return shortcut

    def _trigger_timer_page_pause_resume(self) -> None:
        """Mirror the pause/resume button path for local and global shortcuts."""
        if not self.timer_page_is_active():
            return
        if self._timer_page.pause_button.isEnabled():
            self._timer_page.pause_button.click()

    def _trigger_timer_page_start_stop(self) -> None:
        """Mirror the start/stop button path for local and global shortcuts."""
        if not self.timer_page_is_active():
            return
        if self._timer_page.start_button.isEnabled():
            self._timer_page.start_button.click()
        elif self._timer_page.stop_button.isEnabled():
            self._timer_page.stop_button.click()

    def _trigger_timer_page_mark_correct(self) -> None:
        """Mirror the correct button path for local and global shortcuts."""
        if not self.timer_page_is_active():
            return
        if self._timer_page.correct_button.isEnabled():
            self._timer_page.correct_button.click()

    def _trigger_timer_page_skip_phase(self) -> None:
        """Mirror the skip-phase action path for local and global shortcuts."""
        if not self.timer_page_is_active():
            return
        if self._timer_page.skip_phase_button.isEnabled():
            self._timer_page.skip_phase_button.click()

    def _trigger_timer_page_mark_wrong(self) -> None:
        """Mirror the wrong button path for local and global shortcuts."""
        if not self.timer_page_is_active():
            return
        if self._timer_page.wrong_button.isEnabled():
            self._timer_page.wrong_button.click()

    def _trigger_timer_page_copy_question(self) -> None:
        """Copy the current flashcard question and show transient feedback."""
        if not self.timer_page_is_active():
            return
        if self._timer_page.flashcard_question_label.isHidden():
            return
        question = self._timer_page.current_flashcard_question_text().strip()
        if not question:
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(question)
        self._timer_page.show_copy_feedback()

    @staticmethod
    def _require_shortcut(shortcut: QShortcut | None) -> QShortcut:
        """Return one configured shortcut or raise when shortcuts are missing."""
        if shortcut is None:
            msg = "Window shortcuts have not been configured yet."
            raise RuntimeError(msg)
        return shortcut
