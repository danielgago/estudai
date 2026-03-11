"""Settings service and settings page tests."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from estudai.services.hotkeys import DEFAULT_HOTKEY_BINDINGS, HotkeyAction
from estudai.services.settings import (
    AppSettings,
    DEFAULT_IN_APP_SHORTCUT_BINDINGS,
    InAppShortcutAction,
    MAX_TIMER_DURATION_SECONDS,
    SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_DISPLAY_NAME,
    SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH,
    SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH,
    SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_DISPLAY_NAME,
    SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
    _open_settings,
    copy_notification_sound_file,
    get_default_notification_sound_path,
    load_app_settings,
    save_app_settings,
)
from estudai.ui.pages.settings_page import SOUND_PREVIEW_LIMIT_MS, SettingsPage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an isolated app data directory for each test."""
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(tmp_path / "app-data"))


class _FakePlayer:
    """Minimal sound player used to observe preview playback behavior."""

    def __init__(self) -> None:
        self.source_values: list[str] = []
        self.play_calls = 0
        self.stop_calls = 0

    def setSource(self, url) -> None:  # noqa: N802
        self.source_values.append(url.toLocalFile())

    def play(self) -> None:
        self.play_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


def test_settings_defaults_and_persistence() -> None:
    """Verify QSettings defaults load and persisted values are restored."""
    defaults = load_app_settings()
    assert defaults == AppSettings()

    expected = AppSettings(
        timer_duration_seconds=120,
        flashcard_probability_percent=55,
        flashcard_random_order_enabled=True,
        question_display_duration_seconds=4,
        answer_display_duration_seconds=7,
        question_notification_sound_path="/tmp/question-sound.wav",
        question_notification_sound_display_name="question-sound.wav",
        answer_notification_sound_path="/tmp/answer-sound.wav",
        answer_notification_sound_display_name="answer-sound.wav",
        wrong_answer_completion_mode=(
            WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG
        ),
        wrong_answer_reinsertion_mode=(WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS),
        wrong_answer_reinsert_after_count=5,
        pause_resume_hotkey="Ctrl+Alt+P",
        start_stop_hotkey="Ctrl+Alt+S",
        mark_correct_hotkey="Ctrl+Alt+Right",
        mark_wrong_hotkey="Ctrl+Alt+Left",
        copy_question_hotkey="Ctrl+Alt+C",
        in_app_pause_resume_shortcut="Ctrl+P",
        in_app_start_stop_shortcut="Ctrl+Return",
        in_app_mark_correct_shortcut="Ctrl+Up",
        in_app_mark_wrong_shortcut="Ctrl+Down",
        in_app_copy_question_shortcut="C",
    )
    save_app_settings(expected)

    restored = load_app_settings()
    assert restored == expected


def test_settings_persist_wrong_answer_reinsert_after_zero() -> None:
    """Verify the After-X setting accepts and restores zero."""
    expected = AppSettings(
        wrong_answer_reinsertion_mode=WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS,
        wrong_answer_reinsert_after_count=0,
    )

    save_app_settings(expected)

    restored = load_app_settings()
    assert restored.wrong_answer_reinsertion_mode is (
        WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS
    )
    assert restored.wrong_answer_reinsert_after_count == 0


def test_settings_persist_zero_second_timer_value() -> None:
    """Verify timer settings accept and restore an instant-study duration."""
    save_app_settings(AppSettings(timer_duration_seconds=0))

    restored = load_app_settings()

    assert restored.timer_duration_seconds == 0


def test_settings_clamp_timer_duration_to_supported_maximum() -> None:
    """Verify persisted timer duration never exceeds 59 minutes and 59 seconds."""
    save_app_settings(AppSettings(timer_duration_seconds=MAX_TIMER_DURATION_SECONDS + 1))

    restored = load_app_settings()

    assert restored.timer_duration_seconds == MAX_TIMER_DURATION_SECONDS


def test_settings_persist_empty_shortcuts() -> None:
    """Verify cleared shortcut bindings remain disabled after reload."""
    save_app_settings(
        AppSettings(
            pause_resume_hotkey="",
            start_stop_hotkey="",
            in_app_pause_resume_shortcut="",
            in_app_start_stop_shortcut="",
        )
    )

    restored = load_app_settings()

    assert restored.pause_resume_hotkey == ""
    assert restored.start_stop_hotkey == ""
    assert restored.in_app_pause_resume_shortcut == ""
    assert restored.in_app_start_stop_shortcut == ""


def test_settings_default_hotkeys_match_expected_bindings() -> None:
    """Verify new installs load the shipped global hotkey defaults."""
    restored = load_app_settings()

    assert (
        restored.pause_resume_hotkey
        == DEFAULT_HOTKEY_BINDINGS[HotkeyAction.PAUSE_RESUME]
    )
    assert (
        restored.start_stop_hotkey == DEFAULT_HOTKEY_BINDINGS[HotkeyAction.START_STOP]
    )
    assert (
        restored.mark_correct_hotkey
        == DEFAULT_HOTKEY_BINDINGS[HotkeyAction.MARK_CORRECT]
    )
    assert (
        restored.mark_wrong_hotkey == DEFAULT_HOTKEY_BINDINGS[HotkeyAction.MARK_WRONG]
    )
    assert (
        restored.copy_question_hotkey
        == DEFAULT_HOTKEY_BINDINGS[HotkeyAction.COPY_QUESTION]
    )
    assert (
        restored.in_app_pause_resume_shortcut
        == DEFAULT_IN_APP_SHORTCUT_BINDINGS[InAppShortcutAction.PAUSE_RESUME]
    )
    assert (
        restored.in_app_start_stop_shortcut
        == DEFAULT_IN_APP_SHORTCUT_BINDINGS[InAppShortcutAction.START_STOP]
    )
    assert (
        restored.in_app_mark_correct_shortcut
        == DEFAULT_IN_APP_SHORTCUT_BINDINGS[InAppShortcutAction.MARK_CORRECT]
    )
    assert (
        restored.in_app_mark_wrong_shortcut
        == DEFAULT_IN_APP_SHORTCUT_BINDINGS[InAppShortcutAction.MARK_WRONG]
    )
    assert (
        restored.in_app_copy_question_shortcut
        == DEFAULT_IN_APP_SHORTCUT_BINDINGS[InAppShortcutAction.COPY_QUESTION]
    )


def test_get_default_notification_sound_path_prefers_frozen_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify packaged installs resolve bundled default sound before repository fallback."""
    bundle_sound = tmp_path / "bundle" / "data" / "default.mp3"
    bundle_sound.parent.mkdir(parents=True)
    bundle_sound.write_bytes(b"ID3")
    fake_executable = tmp_path / "bundle" / "Estudai.exe"
    fake_executable.write_bytes(b"")
    monkeypatch.setattr("estudai.services.settings.sys.frozen", True, raising=False)
    monkeypatch.setattr(
        "estudai.services.settings.sys.executable", str(fake_executable)
    )

    assert get_default_notification_sound_path() == str(bundle_sound)


def test_copy_notification_sound_file_accepts_supported_extensions(
    tmp_path: Path,
) -> None:
    """Verify supported sound files are copied into app data storage."""
    source_sound = tmp_path / "beep.wav"
    source_sound.write_bytes(b"RIFF....WAVEfmt ")

    copied_path = Path(copy_notification_sound_file(source_sound, slot_name="question"))
    assert copied_path.exists()
    assert copied_path.suffix == ".wav"
    assert copied_path.name == "question-notification-sound.wav"


def test_copy_notification_sound_file_uses_independent_slot_filenames(
    tmp_path: Path,
) -> None:
    """Verify question and answer uploads do not overwrite each other."""
    question_sound = tmp_path / "question.mp3"
    answer_sound = tmp_path / "answer.wav"
    question_sound.write_bytes(b"ID3")
    answer_sound.write_bytes(b"RIFF....WAVEfmt ")

    question_path = Path(
        copy_notification_sound_file(question_sound, slot_name="question")
    )
    answer_path = Path(copy_notification_sound_file(answer_sound, slot_name="answer"))

    assert question_path.exists()
    assert answer_path.exists()
    assert question_path != answer_path


def test_copy_notification_sound_file_rejects_unsupported_extension(
    tmp_path: Path,
) -> None:
    """Verify unsupported sound files fail validation."""
    source_sound = tmp_path / "beep.ogg"
    source_sound.write_bytes(b"OggS")

    with pytest.raises(ValueError, match="Unsupported sound file type"):
        copy_notification_sound_file(source_sound, slot_name="question")


def test_settings_migrates_legacy_notification_sound_to_both_slots() -> None:
    """Verify the pre-split sound setting populates both new sound slots."""
    qsettings = _open_settings()
    qsettings.setValue(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH, "/tmp/legacy.wav")
    qsettings.sync()

    restored = load_app_settings()

    assert restored.question_notification_sound_path == "/tmp/legacy.wav"
    assert restored.question_notification_sound_display_name == "legacy.wav"
    assert restored.answer_notification_sound_path == "/tmp/legacy.wav"
    assert restored.answer_notification_sound_display_name == "legacy.wav"


def test_settings_save_clears_legacy_notification_sound_key() -> None:
    """Verify saving new settings removes the stale legacy sound key."""
    qsettings = _open_settings()
    qsettings.setValue(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH, "/tmp/legacy.wav")
    qsettings.sync()

    save_app_settings(
        AppSettings(
            question_notification_sound_path="/tmp/question.wav",
            answer_notification_sound_path="/tmp/answer.wav",
        )
    )

    qsettings = _open_settings()
    assert qsettings.contains(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH) is False
    assert (
        qsettings.value(SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH)
        == "/tmp/question.wav"
    )
    assert (
        qsettings.value(SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_DISPLAY_NAME)
        == "question.wav"
    )
    assert (
        qsettings.value(SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH)
        == "/tmp/answer.wav"
    )
    assert (
        qsettings.value(SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_DISPLAY_NAME)
        == "answer.wav"
    )


def test_settings_upgrade_from_1_0_preserves_legacy_sound_path_on_save() -> None:
    """Verify a 1.0-style sound setting survives the first 1.1 save."""
    qsettings = _open_settings()
    legacy_sound_path = "/tmp/notification-sound.wav"
    qsettings.setValue(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH, legacy_sound_path)
    qsettings.sync()

    upgraded = load_app_settings()
    save_app_settings(upgraded)

    reloaded = load_app_settings()
    qsettings = _open_settings()
    assert qsettings.contains(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH) is False
    assert reloaded.question_notification_sound_path == legacy_sound_path
    assert reloaded.question_notification_sound_display_name == "notification-sound.wav"
    assert reloaded.answer_notification_sound_path == legacy_sound_path
    assert reloaded.answer_notification_sound_display_name == "notification-sound.wav"


def test_settings_page_only_persists_changes_after_save(app: QApplication) -> None:
    """Verify editing spinbox values persists only when save is clicked."""
    save_app_settings(AppSettings())
    page = SettingsPage()

    page.timer_duration_spinbox.setValue(90)
    page.flashcard_probability_spinbox.setValue(80)
    page.flashcard_random_order_checkbox.setChecked(True)
    page.question_duration_spinbox.setValue(5)
    page.answer_duration_spinbox.setValue(11)
    page.wrong_answer_completion_mode_combo.setCurrentIndex(1)
    page.wrong_answer_reinsertion_mode_combo.setCurrentIndex(0)
    page.wrong_answer_reinsert_after_spinbox.setValue(6)
    page.pause_resume_hotkey_edit.setKeySequence("Ctrl+Alt+P")
    page.start_stop_hotkey_edit.setKeySequence("Ctrl+Alt+S")
    page.mark_correct_hotkey_edit.setKeySequence("Ctrl+Alt+Right")
    page.mark_wrong_hotkey_edit.setKeySequence("Ctrl+Alt+Left")
    page.copy_question_hotkey_edit.setKeySequence("Ctrl+Alt+C")
    page.in_app_pause_resume_shortcut_edit.setKeySequence("Ctrl+P")
    page.in_app_start_stop_shortcut_edit.setKeySequence("Ctrl+Return")
    page.in_app_mark_correct_shortcut_edit.setKeySequence("Ctrl+Up")
    page.in_app_mark_wrong_shortcut_edit.setKeySequence("Ctrl+Down")
    page.in_app_copy_question_shortcut_edit.setKeySequence("C")

    unchanged = load_app_settings()
    assert unchanged == AppSettings()

    page._handle_save_clicked()
    persisted = load_app_settings()
    assert persisted.timer_duration_seconds == 90
    assert persisted.flashcard_probability_percent == 80
    assert persisted.flashcard_random_order_enabled is True
    assert persisted.question_display_duration_seconds == 5
    assert persisted.answer_display_duration_seconds == 11
    assert (
        persisted.wrong_answer_completion_mode
        is WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG
    )
    assert (
        persisted.wrong_answer_reinsertion_mode
        is WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS
    )
    assert persisted.wrong_answer_reinsert_after_count == 6
    assert persisted.pause_resume_hotkey == "Ctrl+Alt+P"
    assert persisted.start_stop_hotkey == "Ctrl+Alt+S"
    assert persisted.mark_correct_hotkey == "Ctrl+Alt+Right"
    assert persisted.mark_wrong_hotkey == "Ctrl+Alt+Left"
    assert persisted.copy_question_hotkey == "Ctrl+Alt+C"
    assert persisted.in_app_pause_resume_shortcut == "Ctrl+P"
    assert persisted.in_app_start_stop_shortcut == "Ctrl+Return"
    assert persisted.in_app_mark_correct_shortcut == "Ctrl+Up"
    assert persisted.in_app_mark_wrong_shortcut == "Ctrl+Down"
    assert persisted.in_app_copy_question_shortcut == "C"


def test_settings_page_checkbox_keeps_native_indicator_styles(
    app: QApplication,
) -> None:
    """Verify random-order checkbox avoids fragile indicator stylesheet overrides."""
    page = SettingsPage()
    stylesheet = page.flashcard_random_order_checkbox.styleSheet()

    assert stylesheet == ""


def test_settings_page_uses_scrollable_tabs(app: QApplication) -> None:
    """Verify settings sections use the merged tab layout with inner scrolling."""
    page = SettingsPage()

    assert page.settings_tab_widget.count() == 3
    assert page.settings_tab_widget.tabText(0) == "Flashcards"
    assert page.settings_tab_widget.tabText(1) == "Sound"
    assert page.settings_tab_widget.tabText(2) == "Shortcuts"

    for index in range(page.settings_tab_widget.count()):
        tab = page.settings_tab_widget.widget(index)
        assert isinstance(tab, QScrollArea)
        assert tab.widgetResizable() is True
        assert tab.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_settings_page_reopens_with_zero_second_timer_value(
    app: QApplication,
) -> None:
    """Verify the settings form preserves a saved 0-second timer value."""
    save_app_settings(AppSettings(timer_duration_seconds=0))

    page = SettingsPage()

    assert page.timer_duration_spinbox.minimum() == 0
    assert page.timer_duration_spinbox.value() == 0


def test_settings_page_disables_global_hotkeys_when_unavailable(
    app: QApplication,
) -> None:
    """Verify unavailable global hotkeys are explained and not editable."""
    page = SettingsPage(
        global_hotkey_availability_error="Global hotkeys are unsupported here."
    )

    assert not page.pause_resume_hotkey_edit.isEnabled()
    assert not page.start_stop_hotkey_edit.isEnabled()
    assert "unsupported" in page.hotkey_help_label.text().lower()


def test_settings_page_enables_after_x_only_for_matching_mode(
    app: QApplication,
) -> None:
    """Verify the reinsertion X input tracks the selected reinsertion mode."""
    save_app_settings(
        AppSettings(
            wrong_answer_reinsertion_mode=WrongAnswerReinsertionMode.PUSH_TO_END
        )
    )
    page = SettingsPage()

    assert page.wrong_answer_reinsert_after_spinbox.isEnabled() is False

    page.wrong_answer_reinsertion_mode_combo.setCurrentIndex(0)

    assert page.wrong_answer_reinsert_after_spinbox.isEnabled() is True


def test_settings_page_blocks_save_when_spinbox_text_is_out_of_range(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify invalid typed numeric input raises a warning and aborts save."""
    save_app_settings(AppSettings(flashcard_probability_percent=30))
    page = SettingsPage()
    warnings: list[str] = []
    page.flashcard_probability_spinbox.lineEdit().setText("101")
    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    page._handle_save_clicked()

    assert warnings == [
        "Probability of showing flashcard must be between 0 and 100 percent."
    ]
    assert load_app_settings().flashcard_probability_percent == 30


def test_settings_page_blocks_duplicate_hotkeys(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify duplicate hotkey assignments warn and do not persist."""
    save_app_settings(AppSettings())
    page = SettingsPage()
    warnings: list[str] = []
    page.pause_resume_hotkey_edit.setKeySequence("Ctrl+Alt+Space")
    page.start_stop_hotkey_edit.setKeySequence("Ctrl+Alt+Space")
    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    page._handle_save_clicked()

    assert warnings == [
        "Hotkeys must be unique. 'Ctrl+Alt+Space' is assigned to both 'pause_resume' and 'start_stop'."
    ]
    assert load_app_settings() == AppSettings()


def test_settings_page_allows_empty_shortcuts(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify clearing shortcut editors persists disabled bindings."""
    save_app_settings(AppSettings())
    page = SettingsPage()
    warnings: list[str] = []
    page.pause_resume_hotkey_edit.setKeySequence("")
    page.start_stop_hotkey_edit.setKeySequence("")
    page.in_app_pause_resume_shortcut_edit.setKeySequence("")
    page.in_app_start_stop_shortcut_edit.setKeySequence("")
    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    page._handle_save_clicked()

    persisted = load_app_settings()
    assert warnings == []
    assert persisted.pause_resume_hotkey == ""
    assert persisted.start_stop_hotkey == ""
    assert persisted.in_app_pause_resume_shortcut == ""
    assert persisted.in_app_start_stop_shortcut == ""


def test_settings_page_blocks_duplicate_in_app_shortcuts(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify duplicate in-app shortcuts warn and do not persist."""
    save_app_settings(AppSettings())
    page = SettingsPage()
    warnings: list[str] = []
    page.in_app_pause_resume_shortcut_edit.setKeySequence("Ctrl+Space")
    page.in_app_start_stop_shortcut_edit.setKeySequence("Ctrl+Space")
    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    page._handle_save_clicked()

    assert warnings == [
        "In-app shortcuts must be unique. 'Ctrl+Space' is assigned to both 'pause_resume' and 'start_stop'."
    ]
    assert load_app_settings() == AppSettings()


def test_settings_page_uploads_sound_and_plays_test(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify question and answer uploads persist and test independently."""
    question_sound = tmp_path / "question.mp3"
    answer_sound = tmp_path / "answer.wav"
    question_sound.write_bytes(b"ID3")
    answer_sound.write_bytes(b"RIFF....WAVEfmt ")
    save_app_settings(AppSettings())
    page = SettingsPage()
    player = _FakePlayer()
    page._preview_sound_controller.set_player(player)
    page._update_sound_summary()

    selected_paths = iter(
        [
            (str(question_sound), "Sound files (*.mp3 *.wav)"),
            (str(answer_sound), "Sound files (*.mp3 *.wav)"),
        ]
    )
    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: next(selected_paths),
    )
    page._handle_upload_question_sound_clicked()
    page._handle_upload_answer_sound_clicked()
    assert page.test_question_sound_button.isEnabled()
    assert page.test_answer_sound_button.isEnabled()
    assert (
        page.question_notification_sound_label.text()
        == "Selected question sound: question.mp3"
    )
    assert (
        page.answer_notification_sound_label.text()
        == "Selected answer sound: answer.wav"
    )
    assert load_app_settings().question_notification_sound_path == ""
    assert load_app_settings().answer_notification_sound_path == ""

    page._handle_save_clicked()
    persisted_settings = load_app_settings()
    persisted_question_sound = Path(persisted_settings.question_notification_sound_path)
    persisted_answer_sound = Path(persisted_settings.answer_notification_sound_path)
    assert persisted_settings.question_notification_sound_display_name == "question.mp3"
    assert persisted_settings.answer_notification_sound_display_name == "answer.wav"
    assert page.test_question_sound_button.isEnabled()
    assert page.test_answer_sound_button.isEnabled()
    assert (
        page.question_notification_sound_label.text()
        == "Selected question sound: question.mp3"
    )
    assert (
        page.answer_notification_sound_label.text()
        == "Selected answer sound: answer.wav"
    )

    page._handle_test_question_sound_clicked()
    page._handle_test_answer_sound_clicked()
    assert player.play_calls == 2
    assert player.source_values == [
        str(persisted_question_sound),
        str(persisted_answer_sound),
    ]


def test_settings_page_cancel_restores_persisted_values(app: QApplication) -> None:
    """Verify cancel discards unsaved edits and restores persisted values."""
    save_app_settings(
        AppSettings(
            timer_duration_seconds=120,
            flashcard_probability_percent=55,
            flashcard_random_order_enabled=True,
            question_display_duration_seconds=4,
            answer_display_duration_seconds=7,
            wrong_answer_completion_mode=(
                WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG
            ),
            wrong_answer_reinsertion_mode=(
                WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS
            ),
            wrong_answer_reinsert_after_count=8,
        )
    )
    page = SettingsPage()
    page.timer_duration_spinbox.setValue(999)
    page.flashcard_probability_spinbox.setValue(1)
    page.flashcard_random_order_checkbox.setChecked(False)
    page.wrong_answer_completion_mode_combo.setCurrentIndex(0)
    page.wrong_answer_reinsertion_mode_combo.setCurrentIndex(1)
    page.wrong_answer_reinsert_after_spinbox.setValue(2)

    page._handle_cancel_clicked()

    assert page.timer_duration_spinbox.value() == 120
    assert page.flashcard_probability_spinbox.value() == 55
    assert page.flashcard_random_order_checkbox.isChecked() is True
    assert page.wrong_answer_completion_mode_combo.currentData() == (
        WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG.value
    )
    assert page.wrong_answer_reinsertion_mode_combo.currentData() == (
        WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS.value
    )
    assert page.wrong_answer_reinsert_after_spinbox.value() == 8


def test_settings_page_cancel_keeps_persisted_sound_and_name(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify cancel does not overwrite the saved sound slot or display name."""
    persisted_sound = tmp_path / "persisted.wav"
    replacement_sound = tmp_path / "replacement.mp3"
    persisted_sound.write_bytes(b"RIFF....WAVEfmt ")
    replacement_sound.write_bytes(b"ID3")
    persisted_path = copy_notification_sound_file(persisted_sound, slot_name="question")
    save_app_settings(
        AppSettings(
            question_notification_sound_path=persisted_path,
            question_notification_sound_display_name="persisted.wav",
        )
    )
    original_bytes = Path(persisted_path).read_bytes()
    page = SettingsPage()

    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (
            str(replacement_sound),
            "Sound files (*.mp3 *.wav)",
        ),
    )
    page._handle_upload_question_sound_clicked()

    assert (
        page.question_notification_sound_label.text()
        == "Selected question sound: replacement.mp3"
    )
    assert Path(persisted_path).read_bytes() == original_bytes

    page._handle_cancel_clicked()

    restored = load_app_settings()
    assert restored.question_notification_sound_path == persisted_path
    assert restored.question_notification_sound_display_name == "persisted.wav"
    assert Path(persisted_path).read_bytes() == original_bytes
    assert (
        page.question_notification_sound_label.text()
        == "Selected question sound: persisted.wav"
    )


def test_settings_page_warns_and_tests_default_sound(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify both sound slots fall back to the bundled default when unset."""
    default_sound = tmp_path / "default.wav"
    default_sound.write_bytes(b"RIFF....WAVEfmt ")
    page = SettingsPage()
    page._question_notification_sound_path = ""
    page._answer_notification_sound_path = ""
    page._default_notification_sound_path = str(default_sound)
    player = _FakePlayer()
    page._preview_sound_controller.set_player(player)

    page._update_sound_summary()
    assert (
        "Selected question sound: None."
        in page.question_notification_sound_label.text()
    )
    assert "Default sound" in page.question_notification_sound_label.text()
    assert "Selected answer sound: None." in page.answer_notification_sound_label.text()
    assert "Default sound" in page.answer_notification_sound_label.text()
    assert page.test_question_sound_button.isEnabled()
    assert page.test_answer_sound_button.isEnabled()
    assert page.stop_question_sound_button.isHidden() is True
    assert page.stop_answer_sound_button.isHidden() is True

    page._handle_test_question_sound_clicked()
    page._handle_test_answer_sound_clicked()
    assert player.play_calls == 2
    assert player.source_values == [str(default_sound), str(default_sound)]


def test_settings_page_preview_auto_stops_after_timeout(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify preview playback is trimmed by the shared 5-second limit."""
    question_sound = tmp_path / "question.wav"
    question_sound.write_bytes(b"RIFF....WAVEfmt ")
    page = SettingsPage()
    player = _FakePlayer()
    page._preview_sound_controller.set_player(player)
    page._question_notification_sound_path = str(question_sound)
    page._update_sound_summary()

    page._handle_test_question_sound_clicked()

    assert player.play_calls == 1
    assert page.stop_question_sound_button.isHidden() is False
    assert page.stop_answer_sound_button.isHidden() is True
    assert page.stop_question_sound_button.isEnabled() is True
    assert page._preview_sound_controller._stop_timer.interval() == (
        SOUND_PREVIEW_LIMIT_MS
    )
    page._preview_sound_controller._stop_timer.timeout.emit()

    assert player.stop_calls == 1
    assert page.stop_question_sound_button.isHidden() is True
    assert page.stop_question_sound_button.isEnabled() is False


def test_settings_page_stop_button_stops_active_preview(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify the Stop button ends the currently playing preview immediately."""
    answer_sound = tmp_path / "answer.wav"
    answer_sound.write_bytes(b"RIFF....WAVEfmt ")
    page = SettingsPage()
    player = _FakePlayer()
    page._preview_sound_controller.set_player(player)
    page._answer_notification_sound_path = str(answer_sound)
    page._update_sound_summary()

    page._handle_test_answer_sound_clicked()

    assert page.stop_answer_sound_button.isHidden() is False
    assert page.stop_question_sound_button.isHidden() is True
    assert page.stop_answer_sound_button.isEnabled() is True
    assert page.stop_question_sound_button.isEnabled() is False

    page.stop_answer_sound_button.click()

    assert player.stop_calls == 1
    assert page.stop_answer_sound_button.isHidden() is True
    assert page.stop_answer_sound_button.isEnabled() is False
