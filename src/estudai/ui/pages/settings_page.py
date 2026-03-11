"""Settings page."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QKeySequenceEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:  # pragma: no cover - depends on system multimedia libraries.
    QAudioOutput = None  # type: ignore[assignment]
    QMediaPlayer = None  # type: ignore[assignment]

from estudai.services.hotkeys import (
    normalize_hotkey_binding,
    normalize_hotkey_bindings,
)
from estudai.services.settings import (
    AppSettings,
    InAppShortcutAction,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
    copy_notification_sound_file,
    get_default_notification_sound_path,
    hotkey_bindings_from_settings,
    in_app_shortcut_bindings_from_settings,
    load_app_settings,
    save_app_settings,
)
from estudai.ui.audio_playback import TimedAudioPlaybackController
from estudai.ui.utils import set_muted_label_color

SOUND_PREVIEW_LIMIT_MS = 5000


class SettingsPage(QWidget):
    """Page that edits and persists app settings."""

    cancel_requested = Signal()
    timer_duration_seconds_changed = Signal(int)
    settings_saved = Signal(object)

    def __init__(
        self,
        save_settings_callback: Callable[[AppSettings], None] | None = None,
    ) -> None:
        """Initialize the settings page."""
        super().__init__()
        self._question_notification_sound_path = ""
        self._answer_notification_sound_path = ""
        self._default_notification_sound_path = get_default_notification_sound_path()
        self._save_settings_callback = (
            save_settings_callback or self._save_settings_directly
        )
        self._audio_output: object | None = None
        self._sound_player: object | None = None
        self._active_preview_role: str | None = None
        if QAudioOutput is not None and QMediaPlayer is not None:
            self._audio_output = QAudioOutput(self)
            self._sound_player = QMediaPlayer(self)
            self._sound_player.setAudioOutput(self._audio_output)
        self._preview_sound_controller = TimedAudioPlaybackController(
            self,
            player=self._sound_player,
        )
        self._preview_sound_controller.playback_started.connect(
            self._handle_preview_playback_started
        )
        self._preview_sound_controller.playback_stopped.connect(
            self._handle_preview_playback_stopped
        )
        self._build_ui()
        self._load_persisted_settings()
        self._connect_signals()

    def _build_ui(self) -> None:
        """Build the settings UI layout."""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
            "Configure study behavior, notification audio, and both in-app and "
            "global shortcuts. Use Save to apply changes or Cancel to discard edits."
        )
        self.description_label.setWordWrap(True)
        set_muted_label_color(self.description_label)
        layout.addWidget(self.description_label)

        self.settings_tab_widget = QTabWidget()
        self.settings_tab_widget.setDocumentMode(True)
        self.settings_tab_widget.setMinimumSize(0, 0)
        self.settings_tab_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.settings_tab_widget.addTab(
            self._build_scroll_tab(self._build_flashcards_tab()),
            "Flashcards",
        )
        self.settings_tab_widget.addTab(
            self._build_scroll_tab(self._build_sound_tab()),
            "Sound",
        )
        self.settings_tab_widget.addTab(
            self._build_scroll_tab(self._build_shortcuts_tab()),
            "Shortcuts",
        )
        layout.addWidget(self.settings_tab_widget, 1)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save")
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.save_button)
        layout.addLayout(footer_layout)

        self._muted_labels = (
            self.description_label,
            self.question_notification_sound_label,
            self.answer_notification_sound_label,
            self.in_app_shortcut_help_label,
            self.hotkey_help_label,
        )

    def _build_flashcards_tab(self) -> QWidget:
        """Build the tab that contains flashcard session and retry settings."""
        content = self._create_tab_content_widget()
        content_layout = content.layout()

        timer_group = QGroupBox("Timer")
        timer_form = QFormLayout(timer_group)
        self._configure_form_layout(timer_form)

        self.timer_duration_spinbox = QSpinBox()
        self.timer_duration_spinbox.setRange(0, 99 * 3600)
        self.timer_duration_spinbox.setSuffix(" s")
        timer_form.addRow("Timer duration:", self.timer_duration_spinbox)
        content_layout.addWidget(timer_group)

        flashcard_group = QGroupBox("Flashcard Display")
        flashcard_form = QFormLayout(flashcard_group)
        self._configure_form_layout(flashcard_form)

        self.flashcard_probability_spinbox = QSpinBox()
        self.flashcard_probability_spinbox.setRange(0, 100)
        self.flashcard_probability_spinbox.setSuffix(" %")
        flashcard_form.addRow(
            "Show flashcard probability:",
            self.flashcard_probability_spinbox,
        )
        self.flashcard_random_order_checkbox = QCheckBox(
            "Show flashcards in random order"
        )
        flashcard_form.addRow("", self.flashcard_random_order_checkbox)

        self.question_duration_spinbox = QSpinBox()
        self.question_duration_spinbox.setRange(1, 3600)
        self.question_duration_spinbox.setSuffix(" s")
        flashcard_form.addRow(
            "Question display duration:",
            self.question_duration_spinbox,
        )

        self.answer_duration_spinbox = QSpinBox()
        self.answer_duration_spinbox.setRange(1, 3600)
        self.answer_duration_spinbox.setSuffix(" s")
        flashcard_form.addRow(
            "Answer display duration:",
            self.answer_duration_spinbox,
        )
        content_layout.addWidget(flashcard_group)

        retry_group = QGroupBox("Wrong-Answer Retry Rules")
        retry_form = QFormLayout(retry_group)
        self._configure_form_layout(retry_form)

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
        content_layout.addWidget(retry_group)
        content_layout.addStretch()
        return content

    def _build_sound_tab(self) -> QWidget:
        """Build the tab that contains notification sound controls."""
        content = self._create_tab_content_widget()
        content_layout = content.layout()

        question_sound_group = QGroupBox("Question Sound")
        question_sound_layout = QVBoxLayout(question_sound_group)
        self.question_notification_sound_label = QLabel("Selected question sound: None")
        self.question_notification_sound_label.setWordWrap(True)
        set_muted_label_color(self.question_notification_sound_label)
        question_sound_layout.addWidget(self.question_notification_sound_label)
        question_sound_buttons_layout = QHBoxLayout()
        self.upload_question_sound_button = QPushButton("Upload Sound (.mp3/.wav)")
        self.test_question_sound_button = QPushButton("Test Sound")
        self.stop_question_sound_button = QPushButton("Stop")
        question_sound_buttons_layout.addWidget(self.upload_question_sound_button)
        question_sound_buttons_layout.addWidget(self.test_question_sound_button)
        question_sound_buttons_layout.addWidget(self.stop_question_sound_button)
        question_sound_buttons_layout.addStretch()
        question_sound_layout.addLayout(question_sound_buttons_layout)
        content_layout.addWidget(question_sound_group)

        answer_sound_group = QGroupBox("Answer Sound")
        answer_sound_layout = QVBoxLayout(answer_sound_group)
        self.answer_notification_sound_label = QLabel("Selected answer sound: None")
        self.answer_notification_sound_label.setWordWrap(True)
        set_muted_label_color(self.answer_notification_sound_label)
        answer_sound_layout.addWidget(self.answer_notification_sound_label)
        answer_sound_buttons_layout = QHBoxLayout()
        self.upload_answer_sound_button = QPushButton("Upload Sound (.mp3/.wav)")
        self.test_answer_sound_button = QPushButton("Test Sound")
        self.stop_answer_sound_button = QPushButton("Stop")
        answer_sound_buttons_layout.addWidget(self.upload_answer_sound_button)
        answer_sound_buttons_layout.addWidget(self.test_answer_sound_button)
        answer_sound_buttons_layout.addWidget(self.stop_answer_sound_button)
        answer_sound_buttons_layout.addStretch()
        answer_sound_layout.addLayout(answer_sound_buttons_layout)
        content_layout.addWidget(answer_sound_group)
        content_layout.addStretch()
        return content

    def _build_shortcuts_tab(self) -> QWidget:
        """Build the tab that contains local and global shortcut controls."""
        content = self._create_tab_content_widget()
        content_layout = content.layout()

        in_app_group = QGroupBox("In-App Shortcuts")
        in_app_form = QFormLayout(in_app_group)
        self._configure_form_layout(in_app_form)
        self.in_app_pause_resume_shortcut_edit = self._create_shortcut_editor()
        self.in_app_start_stop_shortcut_edit = self._create_shortcut_editor()
        self.in_app_mark_correct_shortcut_edit = self._create_shortcut_editor()
        self.in_app_mark_wrong_shortcut_edit = self._create_shortcut_editor()
        self.in_app_copy_question_shortcut_edit = self._create_shortcut_editor()
        in_app_form.addRow(
            "Pause / Resume:",
            self.in_app_pause_resume_shortcut_edit,
        )
        in_app_form.addRow(
            "Start / Stop:",
            self.in_app_start_stop_shortcut_edit,
        )
        in_app_form.addRow(
            "Mark correct:",
            self.in_app_mark_correct_shortcut_edit,
        )
        in_app_form.addRow(
            "Mark wrong:",
            self.in_app_mark_wrong_shortcut_edit,
        )
        in_app_form.addRow(
            "Copy question:",
            self.in_app_copy_question_shortcut_edit,
        )
        self.in_app_shortcut_help_label = QLabel(
            "These only work while the app is focused. Start / Stop keeps "
            "Enter and Return synchronized."
        )
        self.in_app_shortcut_help_label.setWordWrap(True)
        set_muted_label_color(self.in_app_shortcut_help_label)
        in_app_form.addRow("", self.in_app_shortcut_help_label)
        content_layout.addWidget(in_app_group)

        hotkey_group = QGroupBox("Global Hotkeys")
        hotkey_form = QFormLayout(hotkey_group)
        self._configure_form_layout(hotkey_form)
        self.pause_resume_hotkey_edit = self._create_shortcut_editor()
        self.start_stop_hotkey_edit = self._create_shortcut_editor()
        self.mark_correct_hotkey_edit = self._create_shortcut_editor()
        self.mark_wrong_hotkey_edit = self._create_shortcut_editor()
        self.copy_question_hotkey_edit = self._create_shortcut_editor()
        hotkey_form.addRow("Pause / Resume:", self.pause_resume_hotkey_edit)
        hotkey_form.addRow("Start / Stop:", self.start_stop_hotkey_edit)
        hotkey_form.addRow("Mark correct:", self.mark_correct_hotkey_edit)
        hotkey_form.addRow("Mark wrong:", self.mark_wrong_hotkey_edit)
        hotkey_form.addRow("Copy question:", self.copy_question_hotkey_edit)
        self.hotkey_help_label = QLabel(
            "Bindings are system-wide. Choose single key combinations only."
        )
        self.hotkey_help_label.setWordWrap(True)
        set_muted_label_color(self.hotkey_help_label)
        hotkey_form.addRow("", self.hotkey_help_label)
        content_layout.addWidget(hotkey_group)
        content_layout.addStretch()
        return content

    def _create_tab_content_widget(self) -> QWidget:
        """Create the inner widget hosted inside one scrollable settings tab."""
        content = QWidget()
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(12)
        return content

    def _build_scroll_tab(self, content: QWidget) -> QScrollArea:
        """Wrap one tab content widget in an inner scroll area."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(content)
        scroll_area.setMinimumSize(0, 0)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        return scroll_area

    def _configure_form_layout(self, form_layout: QFormLayout) -> None:
        """Apply a responsive configuration shared by form-based groups."""
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

    def _create_shortcut_editor(self) -> QKeySequenceEdit:
        """Create a one-combination shortcut editor with a clear button."""
        editor = QKeySequenceEdit()
        editor.setClearButtonEnabled(True)
        maximum_sequence_length = getattr(editor, "setMaximumSequenceLength", None)
        if callable(maximum_sequence_length):
            maximum_sequence_length(1)
        return editor

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Refresh palette-driven colors when theme/palette changes."""
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            for label in self._muted_labels:
                set_muted_label_color(label)
        super().changeEvent(event)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.upload_question_sound_button.clicked.connect(
            self._handle_upload_question_sound_clicked
        )
        self.test_question_sound_button.clicked.connect(
            self._handle_test_question_sound_clicked
        )
        self.upload_answer_sound_button.clicked.connect(
            self._handle_upload_answer_sound_clicked
        )
        self.test_answer_sound_button.clicked.connect(
            self._handle_test_answer_sound_clicked
        )
        self.stop_question_sound_button.clicked.connect(
            self._handle_stop_question_sound_clicked
        )
        self.stop_answer_sound_button.clicked.connect(
            self._handle_stop_answer_sound_clicked
        )
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
        self._question_notification_sound_path = (
            settings.question_notification_sound_path
        )
        self._answer_notification_sound_path = settings.answer_notification_sound_path
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
        self.copy_question_hotkey_edit.setKeySequence(
            QKeySequence(settings.copy_question_hotkey)
        )
        self.in_app_pause_resume_shortcut_edit.setKeySequence(
            QKeySequence(settings.in_app_pause_resume_shortcut)
        )
        self.in_app_start_stop_shortcut_edit.setKeySequence(
            QKeySequence(settings.in_app_start_stop_shortcut)
        )
        self.in_app_mark_correct_shortcut_edit.setKeySequence(
            QKeySequence(settings.in_app_mark_correct_shortcut)
        )
        self.in_app_mark_wrong_shortcut_edit.setKeySequence(
            QKeySequence(settings.in_app_mark_wrong_shortcut)
        )
        self.in_app_copy_question_shortcut_edit.setKeySequence(
            QKeySequence(settings.in_app_copy_question_shortcut)
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
            flashcard_random_order_enabled=(
                self.flashcard_random_order_checkbox.isChecked()
            ),
            question_display_duration_seconds=self.question_duration_spinbox.value(),
            answer_display_duration_seconds=self.answer_duration_spinbox.value(),
            question_notification_sound_path=self._question_notification_sound_path,
            answer_notification_sound_path=self._answer_notification_sound_path,
            wrong_answer_completion_mode=WrongAnswerCompletionMode(
                self.wrong_answer_completion_mode_combo.currentData()
            ),
            wrong_answer_reinsertion_mode=WrongAnswerReinsertionMode(
                self.wrong_answer_reinsertion_mode_combo.currentData()
            ),
            wrong_answer_reinsert_after_count=(
                self.wrong_answer_reinsert_after_spinbox.value()
            ),
            pause_resume_hotkey=self.pause_resume_hotkey_edit.keySequence().toString(),
            start_stop_hotkey=self.start_stop_hotkey_edit.keySequence().toString(),
            mark_correct_hotkey=self.mark_correct_hotkey_edit.keySequence().toString(),
            mark_wrong_hotkey=self.mark_wrong_hotkey_edit.keySequence().toString(),
            copy_question_hotkey=self.copy_question_hotkey_edit.keySequence().toString(),
            in_app_pause_resume_shortcut=(
                self.in_app_pause_resume_shortcut_edit.keySequence().toString()
            ),
            in_app_start_stop_shortcut=(
                self.in_app_start_stop_shortcut_edit.keySequence().toString()
            ),
            in_app_mark_correct_shortcut=(
                self.in_app_mark_correct_shortcut_edit.keySequence().toString()
            ),
            in_app_mark_wrong_shortcut=(
                self.in_app_mark_wrong_shortcut_edit.keySequence().toString()
            ),
            in_app_copy_question_shortcut=(
                self.in_app_copy_question_shortcut_edit.keySequence().toString()
            ),
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
        """Refresh selected sound labels and test button states."""
        self._update_sound_control_summary(
            custom_sound_path=self._question_notification_sound_path,
            label=self.question_notification_sound_label,
            test_button=self.test_question_sound_button,
            sound_role="question",
        )
        self._update_sound_control_summary(
            custom_sound_path=self._answer_notification_sound_path,
            label=self.answer_notification_sound_label,
            test_button=self.test_answer_sound_button,
            sound_role="answer",
        )
        self._update_preview_stop_buttons()

    def _update_sound_control_summary(
        self,
        *,
        custom_sound_path: str,
        label: QLabel,
        test_button: QPushButton,
        sound_role: str,
    ) -> None:
        """Refresh one selected sound label and test button state."""
        can_play_sound = self._preview_sound_controller.is_available
        if not custom_sound_path:
            if self._default_notification_sound_path:
                default_name = Path(self._default_notification_sound_path).name
                label.setText(
                    f"Selected {sound_role} sound: None. "
                    f"Default sound ({default_name}) will be played."
                )
                test_button.setEnabled(
                    Path(self._default_notification_sound_path).exists()
                    and can_play_sound
                )
                return
            label.setText(f"Selected {sound_role} sound: None")
            test_button.setEnabled(False)
            return
        sound_path = Path(custom_sound_path)
        label.setText(f"Selected {sound_role} sound: {sound_path.name}")
        test_button.setEnabled(sound_path.exists() and can_play_sound)

    def _handle_upload_question_sound_clicked(self) -> None:
        """Open a file picker to set the question notification sound."""
        self._question_notification_sound_path = self._upload_sound(
            slot_name="question"
        )
        self._update_sound_summary()

    def _handle_upload_answer_sound_clicked(self) -> None:
        """Open a file picker to set the answer notification sound."""
        self._answer_notification_sound_path = self._upload_sound(slot_name="answer")
        self._update_sound_summary()

    def _upload_sound(self, *, slot_name: str) -> str:
        """Open a file picker and persist one selected notification sound copy."""
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select notification sound",
            "",
            "Sound files (*.mp3 *.wav)",
        )
        if not selected_path:
            return (
                self._question_notification_sound_path
                if slot_name == "question"
                else self._answer_notification_sound_path
            )

        try:
            return copy_notification_sound_file(
                Path(selected_path),
                slot_name=slot_name,
            )
        except (FileNotFoundError, ValueError) as error:
            QMessageBox.warning(self, "Upload sound", str(error))
            return (
                self._question_notification_sound_path
                if slot_name == "question"
                else self._answer_notification_sound_path
            )

    def _handle_cancel_clicked(self) -> None:
        """Discard unsaved form edits and restore persisted settings."""
        self.stop_active_preview()
        self._load_persisted_settings()
        self.cancel_requested.emit()

    def _handle_save_clicked(self) -> None:
        """Persist current form edits."""
        self.stop_active_preview()
        self._persist_settings()

    def _handle_test_question_sound_clicked(self) -> None:
        """Play the current question notification sound."""
        self._play_selected_sound(
            custom_sound_path=self._question_notification_sound_path,
            sound_role="question",
        )

    def _handle_test_answer_sound_clicked(self) -> None:
        """Play the current answer notification sound."""
        self._play_selected_sound(
            custom_sound_path=self._answer_notification_sound_path,
            sound_role="answer",
        )

    def _handle_stop_question_sound_clicked(self) -> None:
        """Stop the active question preview when one is playing."""
        self._stop_preview_sound("question")

    def _handle_stop_answer_sound_clicked(self) -> None:
        """Stop the active answer preview when one is playing."""
        self._stop_preview_sound("answer")

    def stop_active_preview(self) -> None:
        """Stop any in-progress settings sound preview."""
        self._preview_sound_controller.stop()

    def _play_selected_sound(self, *, custom_sound_path: str, sound_role: str) -> None:
        """Play one selected notification sound or the bundled default."""
        if not self._preview_sound_controller.is_available:
            QMessageBox.warning(
                self,
                "Test sound",
                "Audio playback is unavailable on this system.",
            )
            return
        sound_path_value = custom_sound_path or self._default_notification_sound_path
        if not sound_path_value:
            QMessageBox.warning(self, "Test sound", "No notification sound available.")
            return
        sound_path = Path(sound_path_value)
        if not sound_path.exists():
            QMessageBox.warning(self, "Test sound", "Saved sound file is missing.")
            self._update_sound_summary()
            return
        self._preview_sound_controller.play(
            sound_path,
            max_duration_ms=SOUND_PREVIEW_LIMIT_MS,
            context=sound_role,
        )

    def _stop_preview_sound(self, sound_role: str) -> None:
        """Stop the current preview only when it matches the requested role."""
        if self._preview_sound_controller.active_context != sound_role:
            return
        self._preview_sound_controller.stop()

    def _handle_preview_playback_started(self, context: object) -> None:
        """Update stop-action state when preview playback begins."""
        self._active_preview_role = context if isinstance(context, str) else None
        self._update_preview_stop_buttons()

    def _handle_preview_playback_stopped(self, _context: object) -> None:
        """Update stop-action state when preview playback ends."""
        self._active_preview_role = None
        self._update_preview_stop_buttons()

    def _update_preview_stop_buttons(self) -> None:
        """Show only the stop action for the currently playing preview."""
        question_preview_active = self._active_preview_role == "question"
        answer_preview_active = self._active_preview_role == "answer"
        self.stop_question_sound_button.setVisible(question_preview_active)
        self.stop_question_sound_button.setEnabled(question_preview_active)
        self.stop_answer_sound_button.setVisible(answer_preview_active)
        self.stop_answer_sound_button.setEnabled(answer_preview_active)

    def _update_wrong_answer_reinsert_after_enabled_state(self) -> None:
        """Enable X only when the matching reinsertion mode is selected."""
        reinsertion_mode = self.wrong_answer_reinsertion_mode_combo.currentData()
        self.wrong_answer_reinsert_after_spinbox.setEnabled(
            reinsertion_mode == WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS.value
        )

    def _validate_settings_form(self) -> str | None:
        """Return a validation message when the form contains invalid raw input."""
        settings = self._collect_settings()
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
            self._normalize_unique_shortcut_bindings(
                in_app_shortcut_bindings_from_settings(settings),
                group_label="In-app shortcuts",
            )
            normalize_hotkey_bindings(
                hotkey_bindings_from_settings(settings),
                allow_empty=True,
            )
        except ValueError as error:
            return str(error)

        return None

    def _normalize_unique_shortcut_bindings(
        self,
        bindings: dict[InAppShortcutAction, str],
        *,
        group_label: str,
    ) -> dict[InAppShortcutAction, str]:
        """Normalize one shortcut group and reject duplicate assignments."""
        normalized_bindings: dict[InAppShortcutAction, str] = {}
        owners_by_binding: dict[str, InAppShortcutAction] = {}
        singular_group_label = (
            group_label[:-1] if group_label.endswith("s") else group_label
        )
        for action, binding in bindings.items():
            try:
                normalized_binding = normalize_hotkey_binding(
                    binding,
                    allow_empty=True,
                )
            except ValueError as error:
                message = str(error)
                if message.startswith("Hotkeys"):
                    message = message.replace("Hotkeys", group_label, 1)
                elif message.startswith("Hotkey"):
                    message = message.replace("Hotkey", singular_group_label, 1)
                raise ValueError(message) from error
            normalized_bindings[action] = normalized_binding
            if not normalized_binding:
                continue
            owner = owners_by_binding.get(normalized_binding)
            if owner is not None:
                msg = (
                    f"{group_label} must be unique. "
                    f"'{binding}' is assigned to both '{owner.value}' and "
                    f"'{action.value}'."
                )
                raise ValueError(msg)
            owners_by_binding[normalized_binding] = action
        return normalized_bindings

    def _save_settings_directly(self, settings: AppSettings) -> None:
        """Persist settings when no external save orchestrator is provided."""
        save_app_settings(settings)
