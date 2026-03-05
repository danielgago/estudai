"""Settings persistence and notification sound storage helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

from .folder_storage import get_app_data_dir

SETTINGS_FILENAME = "settings.ini"
SOUNDS_FOLDER_NAME = "sounds"
SETTINGS_KEY_TIMER_DURATION_SECONDS = "timer/duration_seconds"
SETTINGS_KEY_FLASHCARD_PROBABILITY_PERCENT = "flashcard/probability_percent"
SETTINGS_KEY_FLASHCARD_RANDOM_ORDER_ENABLED = "flashcard/random_order_enabled"
SETTINGS_KEY_QUESTION_DURATION_SECONDS = "flashcard/question_duration_seconds"
SETTINGS_KEY_ANSWER_DURATION_SECONDS = "flashcard/answer_duration_seconds"
SETTINGS_KEY_NOTIFICATION_SOUND_PATH = "flashcard/notification_sound_path"
ALLOWED_SOUND_EXTENSIONS = {".mp3", ".wav"}


@dataclass(frozen=True)
class AppSettings:
    """Typed app settings payload persisted with QSettings."""

    timer_duration_seconds: int = 25 * 60
    flashcard_probability_percent: int = 30
    flashcard_random_order_enabled: bool = False
    question_display_duration_seconds: int = 8
    answer_display_duration_seconds: int = 8
    notification_sound_path: str = ""


def get_default_notification_sound_path() -> str:
    """Return the default notification sound path when available.

    Returns:
        str: Absolute path to bundled `data/alarm.mp3`, or empty string.
    """
    repository_alarm = Path(__file__).resolve().parents[3] / "data" / "alarm.mp3"
    if repository_alarm.exists() and repository_alarm.is_file():
        return str(repository_alarm)
    return ""


def _settings_path() -> Path:
    """Return the QSettings file path.

    Returns:
        Path: INI file path used by QSettings.
    """
    return get_app_data_dir() / SETTINGS_FILENAME


def _open_settings() -> QSettings:
    """Create a QSettings instance using app-local INI storage.

    Returns:
        QSettings: Configured QSettings object.
    """
    return QSettings(str(_settings_path()), QSettings.IniFormat)


def _normalize_int(
    raw_value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Normalize integer-like values into a safe bounded range.

    Args:
        raw_value: Raw value loaded from QSettings.
        default: Fallback integer when conversion fails.
        minimum: Inclusive lower bound.
        maximum: Inclusive upper bound.

    Returns:
        int: Bounded integer value.
    """
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _normalize_bool(raw_value: object, *, default: bool) -> bool:
    """Normalize truthy/falsey settings values into a boolean.

    Args:
        raw_value: Raw value loaded from QSettings.
        default: Fallback boolean when conversion is ambiguous.

    Returns:
        bool: Normalized boolean value.
    """
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(raw_value, (int, float)):
        return bool(raw_value)
    return default


def load_app_settings() -> AppSettings:
    """Load current app settings from QSettings.

    Returns:
        AppSettings: Persisted settings or default values.
    """
    qsettings = _open_settings()
    notification_sound_path = str(
        qsettings.value(
            SETTINGS_KEY_NOTIFICATION_SOUND_PATH,
            AppSettings.notification_sound_path,
        )
    )
    return AppSettings(
        timer_duration_seconds=_normalize_int(
            qsettings.value(
                SETTINGS_KEY_TIMER_DURATION_SECONDS,
                AppSettings.timer_duration_seconds,
            ),
            default=AppSettings.timer_duration_seconds,
            minimum=1,
            maximum=99 * 3600,
        ),
        flashcard_probability_percent=_normalize_int(
            qsettings.value(
                SETTINGS_KEY_FLASHCARD_PROBABILITY_PERCENT,
                AppSettings.flashcard_probability_percent,
            ),
            default=AppSettings.flashcard_probability_percent,
            minimum=0,
            maximum=100,
        ),
        flashcard_random_order_enabled=_normalize_bool(
            qsettings.value(
                SETTINGS_KEY_FLASHCARD_RANDOM_ORDER_ENABLED,
                AppSettings.flashcard_random_order_enabled,
            ),
            default=AppSettings.flashcard_random_order_enabled,
        ),
        question_display_duration_seconds=_normalize_int(
            qsettings.value(
                SETTINGS_KEY_QUESTION_DURATION_SECONDS,
                AppSettings.question_display_duration_seconds,
            ),
            default=AppSettings.question_display_duration_seconds,
            minimum=1,
            maximum=3600,
        ),
        answer_display_duration_seconds=_normalize_int(
            qsettings.value(
                SETTINGS_KEY_ANSWER_DURATION_SECONDS,
                AppSettings.answer_display_duration_seconds,
            ),
            default=AppSettings.answer_display_duration_seconds,
            minimum=1,
            maximum=3600,
        ),
        notification_sound_path=notification_sound_path,
    )


def save_app_settings(settings: AppSettings) -> None:
    """Persist all app settings into QSettings.

    Args:
        settings: Settings payload to persist.
    """
    qsettings = _open_settings()
    qsettings.setValue(
        SETTINGS_KEY_TIMER_DURATION_SECONDS,
        _normalize_int(
            settings.timer_duration_seconds,
            default=AppSettings.timer_duration_seconds,
            minimum=1,
            maximum=99 * 3600,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_FLASHCARD_PROBABILITY_PERCENT,
        _normalize_int(
            settings.flashcard_probability_percent,
            default=AppSettings.flashcard_probability_percent,
            minimum=0,
            maximum=100,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_FLASHCARD_RANDOM_ORDER_ENABLED,
        bool(settings.flashcard_random_order_enabled),
    )
    qsettings.setValue(
        SETTINGS_KEY_QUESTION_DURATION_SECONDS,
        _normalize_int(
            settings.question_display_duration_seconds,
            default=AppSettings.question_display_duration_seconds,
            minimum=1,
            maximum=3600,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_ANSWER_DURATION_SECONDS,
        _normalize_int(
            settings.answer_display_duration_seconds,
            default=AppSettings.answer_display_duration_seconds,
            minimum=1,
            maximum=3600,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_NOTIFICATION_SOUND_PATH,
        settings.notification_sound_path.strip(),
    )
    qsettings.sync()


def copy_notification_sound_file(source_path: Path) -> str:
    """Copy a selected notification sound file into app data storage.

    Args:
        source_path: User-selected source file path.

    Returns:
        str: Persisted copied sound file path.

    Raises:
        FileNotFoundError: If the source path does not exist.
        ValueError: If source extension is not supported.
    """
    resolved_source = source_path.expanduser().resolve()
    if not resolved_source.exists() or not resolved_source.is_file():
        msg = f"Sound file not found: {resolved_source}"
        raise FileNotFoundError(msg)
    extension = resolved_source.suffix.lower()
    if extension not in ALLOWED_SOUND_EXTENSIONS:
        msg = "Unsupported sound file type. Use .mp3 or .wav."
        raise ValueError(msg)

    sounds_dir = get_app_data_dir() / SOUNDS_FOLDER_NAME
    sounds_dir.mkdir(parents=True, exist_ok=True)
    copied_sound_path = sounds_dir / f"notification-sound{extension}"
    shutil.copy2(resolved_source, copied_sound_path)
    return str(copied_sound_path)
