"""Settings service and settings page tests."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from estudai.services.settings import (
    AppSettings,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
    copy_notification_sound_file,
    get_default_notification_sound_path,
    load_app_settings,
    save_app_settings,
)
from estudai.ui.pages.settings_page import SettingsPage

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
        notification_sound_path="/tmp/sound.wav",
        wrong_answer_completion_mode=(
            WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG
        ),
        wrong_answer_reinsertion_mode=(WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS),
        wrong_answer_reinsert_after_count=5,
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


def test_get_default_notification_sound_path_prefers_frozen_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify packaged installs resolve bundled alarm before repository fallback."""
    bundle_sound = tmp_path / "bundle" / "data" / "alarm.mp3"
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

    copied_path = Path(copy_notification_sound_file(source_sound))
    assert copied_path.exists()
    assert copied_path.suffix == ".wav"
    assert copied_path.name == "notification-sound.wav"


def test_copy_notification_sound_file_rejects_unsupported_extension(
    tmp_path: Path,
) -> None:
    """Verify unsupported sound files fail validation."""
    source_sound = tmp_path / "beep.ogg"
    source_sound.write_bytes(b"OggS")

    with pytest.raises(ValueError, match="Unsupported sound file type"):
        copy_notification_sound_file(source_sound)


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


def test_settings_page_checkbox_keeps_native_indicator_styles(
    app: QApplication,
) -> None:
    """Verify random-order checkbox avoids fragile indicator stylesheet overrides."""
    page = SettingsPage()
    stylesheet = page.flashcard_random_order_checkbox.styleSheet()

    assert stylesheet == ""


def test_settings_page_reopens_with_zero_second_timer_value(
    app: QApplication,
) -> None:
    """Verify the settings form preserves a saved 0-second timer value."""
    save_app_settings(AppSettings(timer_duration_seconds=0))

    page = SettingsPage()

    assert page.timer_duration_spinbox.minimum() == 0
    assert page.timer_duration_spinbox.value() == 0


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


def test_settings_page_uploads_sound_and_plays_test(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify upload sets pending sound and save persists it."""
    selected_sound = tmp_path / "notification.mp3"
    selected_sound.write_bytes(b"ID3")
    save_app_settings(AppSettings())
    page = SettingsPage()
    played: list[str] = []
    source_values: list[str] = []

    class _FakePlayer:
        def setSource(self, url) -> None:  # noqa: N802
            source_values.append(url.toLocalFile())

        def play(self) -> None:
            played.append("played")

    monkeypatch.setattr(page, "_sound_player", _FakePlayer())

    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(selected_sound), "Sound files (*.mp3 *.wav)"),
    )
    page._handle_upload_sound_clicked()
    assert page.test_sound_button.isEnabled()
    assert load_app_settings().notification_sound_path == ""

    page._handle_save_clicked()
    persisted_sound = Path(load_app_settings().notification_sound_path)
    assert page.test_sound_button.isEnabled()

    page._handle_test_sound_clicked()
    assert played == ["played"]
    assert source_values == [str(persisted_sound)]


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


def test_settings_page_warns_and_tests_default_sound(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify default sound warning is shown and test button plays default."""
    default_sound = tmp_path / "alarm-default.wav"
    default_sound.write_bytes(b"RIFF....WAVEfmt ")
    page = SettingsPage()
    page._notification_sound_path = ""
    page._default_notification_sound_path = str(default_sound)
    played: list[str] = []
    source_values: list[str] = []

    class _FakePlayer:
        def setSource(self, url) -> None:  # noqa: N802
            source_values.append(url.toLocalFile())

        def play(self) -> None:
            played.append("played")

    monkeypatch.setattr(page, "_sound_player", _FakePlayer())

    page._update_sound_summary()
    assert "Selected sound: None." in page.notification_sound_label.text()
    assert "Default sound" in page.notification_sound_label.text()
    assert page.test_sound_button.isEnabled()

    page._handle_test_sound_clicked()
    assert played == ["played"]
    assert source_values == [str(default_sound)]
