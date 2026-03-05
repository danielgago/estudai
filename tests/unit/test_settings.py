"""Settings service and settings page tests."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from estudai.services.settings import (
    AppSettings,
    copy_notification_sound_file,
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
        question_display_duration_seconds=4,
        answer_display_duration_seconds=7,
        notification_sound_path="/tmp/sound.wav",
    )
    save_app_settings(expected)

    restored = load_app_settings()
    assert restored == expected


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
    page.question_duration_spinbox.setValue(5)
    page.answer_duration_spinbox.setValue(11)

    unchanged = load_app_settings()
    assert unchanged == AppSettings()

    page._handle_save_clicked()
    persisted = load_app_settings()
    assert persisted.timer_duration_seconds == 90
    assert persisted.flashcard_probability_percent == 80
    assert persisted.question_display_duration_seconds == 5
    assert persisted.answer_display_duration_seconds == 11


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

    monkeypatch.setattr(
        "estudai.ui.pages.settings_page.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(selected_sound), "Sound files (*.mp3 *.wav)"),
    )
    monkeypatch.setattr(
        page._sound_player,
        "setSource",
        lambda url: source_values.append(url.toLocalFile()),
    )
    monkeypatch.setattr(page._sound_player, "play", lambda: played.append("played"))

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
            question_display_duration_seconds=4,
            answer_display_duration_seconds=7,
        )
    )
    page = SettingsPage()
    page.timer_duration_spinbox.setValue(999)
    page.flashcard_probability_spinbox.setValue(1)

    page._handle_cancel_clicked()

    assert page.timer_duration_spinbox.value() == 120
    assert page.flashcard_probability_spinbox.value() == 55


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

    monkeypatch.setattr(
        page._sound_player,
        "setSource",
        lambda url: source_values.append(url.toLocalFile()),
    )
    monkeypatch.setattr(page._sound_player, "play", lambda: played.append("played"))

    page._update_sound_summary()
    assert "Selected sound: None." in page.notification_sound_label.text()
    assert "Default sound" in page.notification_sound_label.text()
    assert page.test_sound_button.isEnabled()

    page._handle_test_sound_clicked()
    assert played == ["played"]
    assert source_values == [str(default_sound)]
