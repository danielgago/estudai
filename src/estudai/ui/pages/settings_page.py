"""Settings page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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

from estudai.services.settings import (
    AppSettings,
    copy_notification_sound_file,
    get_default_notification_sound_path,
    load_app_settings,
    save_app_settings,
)


class SettingsPage(QWidget):
    """Page that edits and persists app settings."""

    timer_duration_seconds_changed = Signal(int)

    def __init__(self) -> None:
        """Initialize the settings page."""
        super().__init__()
        self._notification_sound_path = ""
        self._default_notification_sound_path = get_default_notification_sound_path()
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
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            "Configure timer behavior and flashcard popup defaults. "
            "Use Save to apply changes or Cancel to discard edits."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #666;")
        layout.addWidget(description)

        timer_group = QGroupBox("Timer and Flashcard Settings")
        timer_form = QFormLayout(timer_group)

        self.timer_duration_spinbox = QSpinBox()
        self.timer_duration_spinbox.setRange(1, 99 * 3600)
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

        sound_group = QGroupBox("Notification Sound")
        sound_layout = QVBoxLayout(sound_group)
        self.notification_sound_label = QLabel("Selected sound: None")
        self.notification_sound_label.setWordWrap(True)
        self.notification_sound_label.setStyleSheet("color: #666;")
        sound_layout.addWidget(self.notification_sound_label)
        sound_buttons_layout = QHBoxLayout()
        self.upload_sound_button = QPushButton("Upload Sound (.mp3/.wav)")
        self.test_sound_button = QPushButton("Test Sound")
        sound_buttons_layout.addWidget(self.upload_sound_button)
        sound_buttons_layout.addWidget(self.test_sound_button)
        sound_buttons_layout.addStretch()
        sound_layout.addLayout(sound_buttons_layout)
        layout.addWidget(sound_group)
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save")
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.save_button)
        layout.addLayout(footer_layout)
        layout.addStretch()

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.upload_sound_button.clicked.connect(self._handle_upload_sound_clicked)
        self.test_sound_button.clicked.connect(self._handle_test_sound_clicked)
        self.cancel_button.clicked.connect(self._handle_cancel_clicked)
        self.save_button.clicked.connect(self._handle_save_clicked)

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
        self._update_sound_summary()

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
        )

    def _persist_settings(self) -> None:
        """Save current form values into QSettings."""
        settings = self._collect_settings()
        save_app_settings(settings)
        self.timer_duration_seconds_changed.emit(settings.timer_duration_seconds)

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
