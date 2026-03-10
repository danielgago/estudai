"""Settings page."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QUrl, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QKeySequenceEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:  # pragma: no cover - depends on system multimedia libraries.
    QAudioOutput = None  # type: ignore[assignment]
    QMediaPlayer = None  # type: ignore[assignment]

from estudai.services.hotkeys import normalize_hotkey_bindings
from estudai.services.settings import (
    AppSettings,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
    copy_notification_sound_file,
    get_default_notification_sound_path,
    hotkey_bindings_from_settings,
    load_app_settings,
    save_app_settings,
)
from estudai.ui.utils import set_muted_label_color


class SettingsPage(QWidget):
    """Page that edits and persists app settings."""

    timer_duration_seconds_changed = Signal(int)
    settings_saved = Signal(object)

    def __init__(
        self,
        save_settings_callback: Callable[[AppSettings], None] | None = None,
    ) -> None:
        """Initialize the settings page."""
        super().__init__()
        self._notification_sound_path = ""
        self._default_notification_sound_path = get_default_notification_sound_path()
        self._save_settings_callback = (
            save_settings_callback or self._save_settings_directly
        )
        self._audio_output: object | None = None
        self._sound_player: object | None = None
        if QAudioOutput is not None and QMediaPlayer is not None:
            self._audio_output = QAudioOutput(self)
            self._sound_player = QMediaPlayer(self)
            self._sound_player.setAudioOutput(self._audio_output)
        self._build_ui()
        self._load_persisted_settings()
        self._connect_signals()

    def _build_ui(self) -> None:
        """Build the settings UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title_font = QFont(title.font())
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.description_label = QLabel(
            "Configure timer behavior and flashcard popup defaults. "
            "Use Save to apply changes or Cancel to discard edits."
        )
        self.description_label.setWordWrap(True)
        set_muted_label_color(self.description_label)
        layout.addWidget(self.description_label)

        timer_group = QGroupBox("Timer and Flashcard Settings")
        timer_form = QFormLayout(timer_group)

        self.timer_duration_spinbox = QSpinBox()
        self.timer_duration_spinbox.setRange(0, 99 * 3600)
        self.timer_duration_spinbox.setSuffix(" s")
        timer_form.addRow("Timer duration:", self.timer_duration_spinbox)

        self.flashcard_probability_spinbox = QSpinBox()
        self.flashcard_probability_spinbox.setRange(0, 100)
        self.flashcard_probability_spinbox.setSuffix(" %")
        timer_form.addRow(
            "Probability of showing flashcard:",
            self.flashcard_probability_spinbox,
        )

        self.flashcard_random_order_checkbox = QCheckBox(
            "Show flashcards in random order"
        )
        timer_form.addRow("", self.flashcard_random_order_checkbox)

        self.question_duration_spinbox = QSpinBox()
        self.question_duration_spinbox.setRange(1, 3600)
        self.question_duration_spinbox.setSuffix(" s")
        timer_form.addRow(
            "Question display duration:",
            self.question_duration_spinbox,
        )

        self.answer_duration_spinbox = QSpinBox()
        self.answer_duration_spinbox.setRange(1, 3600)
        self.answer_duration_spinbox.setSuffix(" s")
        timer_form.addRow(
            "Answer display duration:",
            self.answer_duration_spinbox,
        )
        layout.addWidget(timer_group)

        retry_group = QGroupBox("Wrong-Answer Retry Rules")
        retry_form = QFormLayout(retry_group)

        self.wrong_answer_completion_mode_combo = QComboBox()
        self.wrong_answer_completion_mode_combo.addItem(
            "Retry until correct once",
            WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE.value,
        )
        self.wrong_answer_completion_mode_combo.addItem(
            "Retry until correct more times than wrong",
            WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG.value,
        )
        retry_form.addRow(
            "Completion rule:",
            self.wrong_answer_completion_mode_combo,
        )

        self.wrong_answer_reinsertion_mode_combo = QComboBox()
        self.wrong_answer_reinsertion_mode_combo.addItem(
            "After X flashcards",
            WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS.value,
        )
        self.wrong_answer_reinsertion_mode_combo.addItem(
            "Push to end of queue",
            WrongAnswerReinsertionMode.PUSH_TO_END.value,
        )
        retry_form.addRow(
            "Reinsert wrong cards:",
            self.wrong_answer_reinsertion_mode_combo,
        )

        self.wrong_answer_reinsert_after_spinbox = QSpinBox()
        self.wrong_answer_reinsert_after_spinbox.setRange(0, 999)
        retry_form.addRow(
            "After X value:",
            self.wrong_answer_reinsert_after_spinbox,
        )
        layout.addWidget(retry_group)

        sound_group = QGroupBox("Notification Sound")
        sound_layout = QVBoxLayout(sound_group)
        self.notification_sound_label = QLabel("Selected sound: None")
        self.notification_sound_label.setWordWrap(True)
        set_muted_label_color(self.notification_sound_label)
        sound_layout.addWidget(self.notification_sound_label)
        sound_buttons_layout = QHBoxLayout()
        self.upload_sound_button = QPushButton("Upload Sound (.mp3/.wav)")
        self.test_sound_button = QPushButton("Test Sound")
        sound_buttons_layout.addWidget(self.upload_sound_button)
        sound_buttons_layout.addWidget(self.test_sound_button)
        sound_buttons_layout.addStretch()
        sound_layout.addLayout(sound_buttons_layout)
        layout.addWidget(sound_group)

        hotkey_group = QGroupBox("Global Hotkeys")
        hotkey_form = QFormLayout(hotkey_group)
        self.pause_resume_hotkey_edit = QKeySequenceEdit()
        self.pause_resume_hotkey_edit.setClearButtonEnabled(True)
        self.start_stop_hotkey_edit = QKeySequenceEdit()
        self.start_stop_hotkey_edit.setClearButtonEnabled(True)
        self.mark_correct_hotkey_edit = QKeySequenceEdit()
        self.mark_correct_hotkey_edit.setClearButtonEnabled(True)
        self.mark_wrong_hotkey_edit = QKeySequenceEdit()
        self.mark_wrong_hotkey_edit.setClearButtonEnabled(True)
        for editor in (
            self.pause_resume_hotkey_edit,
            self.start_stop_hotkey_edit,
            self.mark_correct_hotkey_edit,
            self.mark_wrong_hotkey_edit,
        ):
            maximum_sequence_length = getattr(editor, "setMaximumSequenceLength", None)
            if callable(maximum_sequence_length):
                maximum_sequence_length(1)
        hotkey_form.addRow("Pause / Resume:", self.pause_resume_hotkey_edit)
        hotkey_form.addRow("Start / Stop:", self.start_stop_hotkey_edit)
        hotkey_form.addRow("Mark correct:", self.mark_correct_hotkey_edit)
        hotkey_form.addRow("Mark wrong:", self.mark_wrong_hotkey_edit)
        self.hotkey_help_label = QLabel(
            "Bindings are system-wide. "
            "Choose single key combinations only."
        )
        self.hotkey_help_label.setWordWrap(True)
        set_muted_label_color(self.hotkey_help_label)
        hotkey_form.addRow("", self.hotkey_help_label)
        layout.addWidget(hotkey_group)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save")
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.save_button)
        layout.addLayout(footer_layout)
        layout.addStretch()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Refresh palette-driven colors when theme/palette changes."""
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            set_muted_label_color(self.description_label)
            set_muted_label_color(self.notification_sound_label)
            set_muted_label_color(self.hotkey_help_label)
        super().changeEvent(event)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.upload_sound_button.clicked.connect(self._handle_upload_sound_clicked)
        self.test_sound_button.clicked.connect(self._handle_test_sound_clicked)
        self.cancel_button.clicked.connect(self._handle_cancel_clicked)
        self.save_button.clicked.connect(self._handle_save_clicked)
        self.wrong_answer_reinsertion_mode_combo.currentIndexChanged.connect(
            self._update_wrong_answer_reinsert_after_enabled_state
        )

    def _load_persisted_settings(self) -> None:
        """Load persisted settings into controls."""
        settings = load_app_settings()
        self.timer_duration_spinbox.setValue(settings.timer_duration_seconds)
        self.flashcard_probability_spinbox.setValue(
            settings.flashcard_probability_percent
        )
        self.flashcard_random_order_checkbox.setChecked(
            settings.flashcard_random_order_enabled
        )
        self.question_duration_spinbox.setValue(
            settings.question_display_duration_seconds
        )
        self.answer_duration_spinbox.setValue(settings.answer_display_duration_seconds)
        self._notification_sound_path = settings.notification_sound_path
        self._set_combo_value(
            self.wrong_answer_completion_mode_combo,
            settings.wrong_answer_completion_mode.value,
        )
        self._set_combo_value(
            self.wrong_answer_reinsertion_mode_combo,
            settings.wrong_answer_reinsertion_mode.value,
        )
        self.wrong_answer_reinsert_after_spinbox.setValue(
            settings.wrong_answer_reinsert_after_count
        )
        self.pause_resume_hotkey_edit.setKeySequence(
            QKeySequence(settings.pause_resume_hotkey)
        )
        self.start_stop_hotkey_edit.setKeySequence(
            QKeySequence(settings.start_stop_hotkey)
        )
        self.mark_correct_hotkey_edit.setKeySequence(
            QKeySequence(settings.mark_correct_hotkey)
        )
        self.mark_wrong_hotkey_edit.setKeySequence(
            QKeySequence(settings.mark_wrong_hotkey)
        )
        self._update_wrong_answer_reinsert_after_enabled_state()
        self._update_sound_summary()

    def _set_combo_value(self, combo_box: QComboBox, value: str) -> None:
        """Select the combo-box item with the provided data value."""
        index = combo_box.findData(value)
        if index >= 0:
            combo_box.setCurrentIndex(index)

    def _collect_settings(self) -> AppSettings:
        """Read current form values into a typed payload.

        Returns:
            AppSettings: Current settings represented by the form.
        """
        return AppSettings(
            timer_duration_seconds=self.timer_duration_spinbox.value(),
            flashcard_probability_percent=self.flashcard_probability_spinbox.value(),
            flashcard_random_order_enabled=self.flashcard_random_order_checkbox.isChecked(),
            question_display_duration_seconds=self.question_duration_spinbox.value(),
            answer_display_duration_seconds=self.answer_duration_spinbox.value(),
            notification_sound_path=self._notification_sound_path,
            wrong_answer_completion_mode=WrongAnswerCompletionMode(
                self.wrong_answer_completion_mode_combo.currentData()
            ),
            wrong_answer_reinsertion_mode=WrongAnswerReinsertionMode(
                self.wrong_answer_reinsertion_mode_combo.currentData()
            ),
            wrong_answer_reinsert_after_count=self.wrong_answer_reinsert_after_spinbox.value(),
            pause_resume_hotkey=self.pause_resume_hotkey_edit.keySequence().toString(),
            start_stop_hotkey=self.start_stop_hotkey_edit.keySequence().toString(),
            mark_correct_hotkey=self.mark_correct_hotkey_edit.keySequence().toString(),
            mark_wrong_hotkey=self.mark_wrong_hotkey_edit.keySequence().toString(),
        )

    def _persist_settings(self) -> None:
        """Save current form values into QSettings."""
        validation_message = self._validate_settings_form()
        if validation_message is not None:
            QMessageBox.warning(self, "Invalid settings", validation_message)
            return
        settings = self._collect_settings()
        try:
            self._save_settings_callback(settings)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid settings", str(error))
            return
        self.timer_duration_seconds_changed.emit(settings.timer_duration_seconds)
        self.settings_saved.emit(settings)

    def _update_sound_summary(self) -> None:
        """Refresh selected sound label and test button state."""
        can_play_sound = self._sound_player is not None
        if not self._notification_sound_path:
            if self._default_notification_sound_path:
                default_name = Path(self._default_notification_sound_path).name
                self.notification_sound_label.setText(
                    "Selected sound: None. "
                    f"Default sound ({default_name}) will be played."
                )
                self.test_sound_button.setEnabled(
                    Path(self._default_notification_sound_path).exists()
                    and can_play_sound
                )
                return
            self.notification_sound_label.setText("Selected sound: None")
            self.test_sound_button.setEnabled(False)
            return
        sound_path = Path(self._notification_sound_path)
        self.notification_sound_label.setText(f"Selected sound: {sound_path.name}")
        self.test_sound_button.setEnabled(sound_path.exists() and can_play_sound)

    def _handle_upload_sound_clicked(self) -> None:
        """Open a file picker to set notification sound."""
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select notification sound",
            "",
            "Sound files (*.mp3 *.wav)",
        )
        if not selected_path:
            return

        try:
            self._notification_sound_path = copy_notification_sound_file(
                Path(selected_path)
            )
        except (FileNotFoundError, ValueError) as error:
            QMessageBox.warning(self, "Upload sound", str(error))
            return

        self._update_sound_summary()

    def _handle_cancel_clicked(self) -> None:
        """Discard unsaved form edits and restore persisted settings."""
        self._load_persisted_settings()

    def _handle_save_clicked(self) -> None:
        """Persist current form edits."""
        self._persist_settings()

    def _handle_test_sound_clicked(self) -> None:
        """Play the currently selected notification sound."""
        if self._sound_player is None:
            QMessageBox.warning(
                self,
                "Test sound",
                "Audio playback is unavailable on this system.",
            )
            return
        sound_path_value = (
            self._notification_sound_path or self._default_notification_sound_path
        )
        if not sound_path_value:
            QMessageBox.warning(self, "Test sound", "No notification sound available.")
            return
        sound_path = Path(sound_path_value)
        if not sound_path.exists():
            QMessageBox.warning(self, "Test sound", "Saved sound file is missing.")
            self._update_sound_summary()
            return
        self._sound_player.setSource(QUrl.fromLocalFile(str(sound_path)))
        self._sound_player.play()

    def _update_wrong_answer_reinsert_after_enabled_state(self) -> None:
        """Enable X only when the matching reinsertion mode is selected."""
        reinsertion_mode = self.wrong_answer_reinsertion_mode_combo.currentData()
        self.wrong_answer_reinsert_after_spinbox.setEnabled(
            reinsertion_mode == WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS.value
        )

    def _validate_settings_form(self) -> str | None:
        """Return a validation message when the form contains invalid raw input."""
        spinboxes = [
            (
                self.timer_duration_spinbox,
                "Timer duration",
                "0 and 356400 seconds",
            ),
            (
                self.flashcard_probability_spinbox,
                "Probability of showing flashcard",
                "0 and 100 percent",
            ),
            (
                self.question_duration_spinbox,
                "Question display duration",
                "1 and 3600 seconds",
            ),
            (
                self.answer_duration_spinbox,
                "Answer display duration",
                "1 and 3600 seconds",
            ),
        ]
        if self.wrong_answer_reinsert_after_spinbox.isEnabled():
            spinboxes.append(
                (
                    self.wrong_answer_reinsert_after_spinbox,
                    "After X value",
                    "0 and 999 flashcards",
                )
            )

        for spinbox, label, expected_range in spinboxes:
            line_edit = spinbox.lineEdit()
            if line_edit is None:
                continue
            if not line_edit.hasAcceptableInput():
                return f"{label} must be between {expected_range}."

        try:
            normalize_hotkey_bindings(
                hotkey_bindings_from_settings(self._collect_settings())
            )
        except ValueError as error:
            return str(error)

        return None

    def _save_settings_directly(self, settings: AppSettings) -> None:
        """Persist settings when no external save orchestrator is provided."""
        save_app_settings(settings)
