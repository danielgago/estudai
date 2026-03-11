"""Settings persistence and notification sound storage helpers."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QSettings

from .folder_storage import get_app_data_dir
from .hotkeys import DEFAULT_HOTKEY_BINDINGS, HotkeyAction

SETTINGS_FILENAME = "settings.ini"
SOUNDS_FOLDER_NAME = "sounds"
SETTINGS_KEY_TIMER_DURATION_SECONDS = "timer/duration_seconds"
SETTINGS_KEY_FLASHCARD_PROBABILITY_PERCENT = "flashcard/probability_percent"
SETTINGS_KEY_FLASHCARD_RANDOM_ORDER_ENABLED = "flashcard/random_order_enabled"
SETTINGS_KEY_QUESTION_DURATION_SECONDS = "flashcard/question_duration_seconds"
SETTINGS_KEY_ANSWER_DURATION_SECONDS = "flashcard/answer_duration_seconds"
SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH = "flashcard/notification_sound_path"
SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH = (
    "flashcard/question_notification_sound_path"
)
SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH = "flashcard/answer_notification_sound_path"
SETTINGS_KEY_WRONG_ANSWER_COMPLETION_MODE = "flashcard/wrong_answer_completion_mode"
SETTINGS_KEY_WRONG_ANSWER_REINSERTION_MODE = "flashcard/wrong_answer_reinsertion_mode"
SETTINGS_KEY_WRONG_ANSWER_REINSERT_AFTER_COUNT = (
    "flashcard/wrong_answer_reinsert_after_count"
)
SETTINGS_KEY_HOTKEY_PAUSE_RESUME = "hotkeys/pause_resume"
SETTINGS_KEY_HOTKEY_START_STOP = "hotkeys/start_stop"
SETTINGS_KEY_HOTKEY_MARK_CORRECT = "hotkeys/mark_correct"
SETTINGS_KEY_HOTKEY_MARK_WRONG = "hotkeys/mark_wrong"
SETTINGS_KEY_HOTKEY_COPY_QUESTION = "hotkeys/copy_question"
SETTINGS_KEY_IN_APP_SHORTCUT_PAUSE_RESUME = "app_shortcuts/pause_resume"
SETTINGS_KEY_IN_APP_SHORTCUT_START_STOP = "app_shortcuts/start_stop"
SETTINGS_KEY_IN_APP_SHORTCUT_MARK_CORRECT = "app_shortcuts/mark_correct"
SETTINGS_KEY_IN_APP_SHORTCUT_MARK_WRONG = "app_shortcuts/mark_wrong"
SETTINGS_KEY_IN_APP_SHORTCUT_COPY_QUESTION = "app_shortcuts/copy_question"
ALLOWED_SOUND_EXTENSIONS = {".mp3", ".wav"}


class WrongAnswerCompletionMode(StrEnum):
    """Completion rule for cards answered wrong during a session."""

    UNTIL_CORRECT_ONCE = "until_correct_once"
    UNTIL_CORRECT_MORE_THAN_WRONG = "until_correct_more_than_wrong"


class WrongAnswerReinsertionMode(StrEnum):
    """Queue placement rule for cards that remain active after scoring."""

    AFTER_X_FLASHCARDS = "after_x_flashcards"
    PUSH_TO_END = "push_to_end"


class InAppShortcutAction(StrEnum):
    """Supported app-scoped shortcut actions handled inside the window."""

    PAUSE_RESUME = "pause_resume"
    START_STOP = "start_stop"
    MARK_CORRECT = "mark_correct"
    MARK_WRONG = "mark_wrong"
    COPY_QUESTION = "copy_question"


DEFAULT_IN_APP_SHORTCUT_BINDINGS: dict[InAppShortcutAction, str] = {
    InAppShortcutAction.PAUSE_RESUME: "Space",
    InAppShortcutAction.START_STOP: "Enter",
    InAppShortcutAction.MARK_CORRECT: "Up",
    InAppShortcutAction.MARK_WRONG: "Down",
    InAppShortcutAction.COPY_QUESTION: "C",
}


@dataclass(frozen=True)
class AppSettings:
    """Typed app settings payload persisted with QSettings."""

    timer_duration_seconds: int = 25 * 60
    flashcard_probability_percent: int = 30
    flashcard_random_order_enabled: bool = False
    question_display_duration_seconds: int = 8
    answer_display_duration_seconds: int = 8
    question_notification_sound_path: str = ""
    answer_notification_sound_path: str = ""
    wrong_answer_completion_mode: WrongAnswerCompletionMode = (
        WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE
    )
    wrong_answer_reinsertion_mode: WrongAnswerReinsertionMode = (
        WrongAnswerReinsertionMode.PUSH_TO_END
    )
    wrong_answer_reinsert_after_count: int = 3
    pause_resume_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.PAUSE_RESUME]
    start_stop_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.START_STOP]
    mark_correct_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.MARK_CORRECT]
    mark_wrong_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.MARK_WRONG]
    copy_question_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.COPY_QUESTION]
    in_app_pause_resume_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.PAUSE_RESUME
    ]
    in_app_start_stop_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.START_STOP
    ]
    in_app_mark_correct_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.MARK_CORRECT
    ]
    in_app_mark_wrong_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.MARK_WRONG
    ]
    in_app_copy_question_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.COPY_QUESTION
    ]


def get_default_notification_sound_path() -> str:
    """Return the default notification sound path when available.

    Returns:
        str: Absolute path to bundled `default.mp3`, or empty string.
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                executable_dir / "data" / "default.mp3",
                executable_dir / "default.mp3",
            ]
        )
    candidates.append(Path(__file__).resolve().parents[3] / "data" / "default.mp3")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
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
    except TypeError, ValueError:
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


def _normalize_enum[EnumType: StrEnum](
    raw_value: object,
    *,
    enum_type: type[EnumType],
    default: EnumType,
) -> EnumType:
    """Normalize a persisted enum-like value into the declared enum type."""
    if isinstance(raw_value, enum_type):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        try:
            return enum_type(normalized)
        except ValueError:
            return default
    return default


def _normalize_text(
    raw_value: object,
    *,
    default: str,
    allow_empty: bool = False,
) -> str:
    """Normalize a string-like value into trimmed text."""
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if normalized or allow_empty:
            return normalized
        return default
    if raw_value is None:
        return default
    normalized = str(raw_value).strip()
    if normalized or allow_empty:
        return normalized
    return default


def hotkey_bindings_from_settings(settings: AppSettings) -> dict[HotkeyAction, str]:
    """Return the persisted hotkey bindings keyed by app action."""
    return {
        HotkeyAction.PAUSE_RESUME: settings.pause_resume_hotkey,
        HotkeyAction.START_STOP: settings.start_stop_hotkey,
        HotkeyAction.MARK_CORRECT: settings.mark_correct_hotkey,
        HotkeyAction.MARK_WRONG: settings.mark_wrong_hotkey,
        HotkeyAction.COPY_QUESTION: settings.copy_question_hotkey,
    }


def in_app_shortcut_bindings_from_settings(
    settings: AppSettings,
) -> dict[InAppShortcutAction, str]:
    """Return the persisted in-app shortcut bindings keyed by action."""
    return {
        InAppShortcutAction.PAUSE_RESUME: settings.in_app_pause_resume_shortcut,
        InAppShortcutAction.START_STOP: settings.in_app_start_stop_shortcut,
        InAppShortcutAction.MARK_CORRECT: settings.in_app_mark_correct_shortcut,
        InAppShortcutAction.MARK_WRONG: settings.in_app_mark_wrong_shortcut,
        InAppShortcutAction.COPY_QUESTION: settings.in_app_copy_question_shortcut,
    }


def load_app_settings() -> AppSettings:
    """Load current app settings from QSettings.

    Returns:
        AppSettings: Persisted settings or default values.
    """
    qsettings = _open_settings()
    legacy_notification_sound_path = _normalize_text(
        qsettings.value(
            SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH,
            "",
        ),
        default="",
        allow_empty=True,
    )
    has_question_notification_sound_path = qsettings.contains(
        SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH
    )
    has_answer_notification_sound_path = qsettings.contains(
        SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH
    )
    question_notification_sound_path = _normalize_text(
        qsettings.value(
            SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH,
            AppSettings.question_notification_sound_path,
        ),
        default=AppSettings.question_notification_sound_path,
        allow_empty=True,
    )
    answer_notification_sound_path = _normalize_text(
        qsettings.value(
            SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH,
            AppSettings.answer_notification_sound_path,
        ),
        default=AppSettings.answer_notification_sound_path,
        allow_empty=True,
    )
    if (
        not has_question_notification_sound_path
        and not has_answer_notification_sound_path
        and legacy_notification_sound_path
    ):
        question_notification_sound_path = legacy_notification_sound_path
        answer_notification_sound_path = legacy_notification_sound_path
    return AppSettings(
        timer_duration_seconds=_normalize_int(
            qsettings.value(
                SETTINGS_KEY_TIMER_DURATION_SECONDS,
                AppSettings.timer_duration_seconds,
            ),
            default=AppSettings.timer_duration_seconds,
            minimum=0,
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
        question_notification_sound_path=question_notification_sound_path,
        answer_notification_sound_path=answer_notification_sound_path,
        wrong_answer_completion_mode=_normalize_enum(
            qsettings.value(
                SETTINGS_KEY_WRONG_ANSWER_COMPLETION_MODE,
                AppSettings.wrong_answer_completion_mode.value,
            ),
            enum_type=WrongAnswerCompletionMode,
            default=AppSettings.wrong_answer_completion_mode,
        ),
        wrong_answer_reinsertion_mode=_normalize_enum(
            qsettings.value(
                SETTINGS_KEY_WRONG_ANSWER_REINSERTION_MODE,
                AppSettings.wrong_answer_reinsertion_mode.value,
            ),
            enum_type=WrongAnswerReinsertionMode,
            default=AppSettings.wrong_answer_reinsertion_mode,
        ),
        wrong_answer_reinsert_after_count=_normalize_int(
            qsettings.value(
                SETTINGS_KEY_WRONG_ANSWER_REINSERT_AFTER_COUNT,
                AppSettings.wrong_answer_reinsert_after_count,
            ),
            default=AppSettings.wrong_answer_reinsert_after_count,
            minimum=0,
            maximum=999,
        ),
        pause_resume_hotkey=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_HOTKEY_PAUSE_RESUME,
                AppSettings.pause_resume_hotkey,
            ),
            default=AppSettings.pause_resume_hotkey,
            allow_empty=True,
        ),
        start_stop_hotkey=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_HOTKEY_START_STOP,
                AppSettings.start_stop_hotkey,
            ),
            default=AppSettings.start_stop_hotkey,
            allow_empty=True,
        ),
        mark_correct_hotkey=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_HOTKEY_MARK_CORRECT,
                AppSettings.mark_correct_hotkey,
            ),
            default=AppSettings.mark_correct_hotkey,
            allow_empty=True,
        ),
        mark_wrong_hotkey=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_HOTKEY_MARK_WRONG,
                AppSettings.mark_wrong_hotkey,
            ),
            default=AppSettings.mark_wrong_hotkey,
            allow_empty=True,
        ),
        copy_question_hotkey=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_HOTKEY_COPY_QUESTION,
                AppSettings.copy_question_hotkey,
            ),
            default=AppSettings.copy_question_hotkey,
            allow_empty=True,
        ),
        in_app_pause_resume_shortcut=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_IN_APP_SHORTCUT_PAUSE_RESUME,
                AppSettings.in_app_pause_resume_shortcut,
            ),
            default=AppSettings.in_app_pause_resume_shortcut,
            allow_empty=True,
        ),
        in_app_start_stop_shortcut=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_IN_APP_SHORTCUT_START_STOP,
                AppSettings.in_app_start_stop_shortcut,
            ),
            default=AppSettings.in_app_start_stop_shortcut,
            allow_empty=True,
        ),
        in_app_mark_correct_shortcut=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_IN_APP_SHORTCUT_MARK_CORRECT,
                AppSettings.in_app_mark_correct_shortcut,
            ),
            default=AppSettings.in_app_mark_correct_shortcut,
            allow_empty=True,
        ),
        in_app_mark_wrong_shortcut=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_IN_APP_SHORTCUT_MARK_WRONG,
                AppSettings.in_app_mark_wrong_shortcut,
            ),
            default=AppSettings.in_app_mark_wrong_shortcut,
            allow_empty=True,
        ),
        in_app_copy_question_shortcut=_normalize_text(
            qsettings.value(
                SETTINGS_KEY_IN_APP_SHORTCUT_COPY_QUESTION,
                AppSettings.in_app_copy_question_shortcut,
            ),
            default=AppSettings.in_app_copy_question_shortcut,
            allow_empty=True,
        ),
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
            minimum=0,
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
        SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH,
        settings.question_notification_sound_path.strip(),
    )
    qsettings.setValue(
        SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH,
        settings.answer_notification_sound_path.strip(),
    )
    qsettings.remove(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH)
    qsettings.setValue(
        SETTINGS_KEY_WRONG_ANSWER_COMPLETION_MODE,
        _normalize_enum(
            settings.wrong_answer_completion_mode,
            enum_type=WrongAnswerCompletionMode,
            default=AppSettings.wrong_answer_completion_mode,
        ).value,
    )
    qsettings.setValue(
        SETTINGS_KEY_WRONG_ANSWER_REINSERTION_MODE,
        _normalize_enum(
            settings.wrong_answer_reinsertion_mode,
            enum_type=WrongAnswerReinsertionMode,
            default=AppSettings.wrong_answer_reinsertion_mode,
        ).value,
    )
    qsettings.setValue(
        SETTINGS_KEY_WRONG_ANSWER_REINSERT_AFTER_COUNT,
        _normalize_int(
            settings.wrong_answer_reinsert_after_count,
            default=AppSettings.wrong_answer_reinsert_after_count,
            minimum=0,
            maximum=999,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_HOTKEY_PAUSE_RESUME,
        _normalize_text(
            settings.pause_resume_hotkey,
            default=AppSettings.pause_resume_hotkey,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_HOTKEY_START_STOP,
        _normalize_text(
            settings.start_stop_hotkey,
            default=AppSettings.start_stop_hotkey,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_HOTKEY_MARK_CORRECT,
        _normalize_text(
            settings.mark_correct_hotkey,
            default=AppSettings.mark_correct_hotkey,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_HOTKEY_MARK_WRONG,
        _normalize_text(
            settings.mark_wrong_hotkey,
            default=AppSettings.mark_wrong_hotkey,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_HOTKEY_COPY_QUESTION,
        _normalize_text(
            settings.copy_question_hotkey,
            default=AppSettings.copy_question_hotkey,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_IN_APP_SHORTCUT_PAUSE_RESUME,
        _normalize_text(
            settings.in_app_pause_resume_shortcut,
            default=AppSettings.in_app_pause_resume_shortcut,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_IN_APP_SHORTCUT_START_STOP,
        _normalize_text(
            settings.in_app_start_stop_shortcut,
            default=AppSettings.in_app_start_stop_shortcut,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_IN_APP_SHORTCUT_MARK_CORRECT,
        _normalize_text(
            settings.in_app_mark_correct_shortcut,
            default=AppSettings.in_app_mark_correct_shortcut,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_IN_APP_SHORTCUT_MARK_WRONG,
        _normalize_text(
            settings.in_app_mark_wrong_shortcut,
            default=AppSettings.in_app_mark_wrong_shortcut,
            allow_empty=True,
        ),
    )
    qsettings.setValue(
        SETTINGS_KEY_IN_APP_SHORTCUT_COPY_QUESTION,
        _normalize_text(
            settings.in_app_copy_question_shortcut,
            default=AppSettings.in_app_copy_question_shortcut,
            allow_empty=True,
        ),
    )
    qsettings.sync()


def copy_notification_sound_file(source_path: Path, *, slot_name: str) -> str:
    """Copy a selected notification sound file into app data storage.

    Args:
        source_path: User-selected source file path.
        slot_name: Stable identifier for the target sound slot.

    Returns:
        str: Persisted copied sound file path.

    Raises:
        FileNotFoundError: If the source path does not exist.
        ValueError: If source extension or slot name is not supported.
    """
    resolved_source = source_path.expanduser().resolve()
    if not resolved_source.exists() or not resolved_source.is_file():
        msg = f"Sound file not found: {resolved_source}"
        raise FileNotFoundError(msg)
    extension = resolved_source.suffix.lower()
    if extension not in ALLOWED_SOUND_EXTENSIONS:
        msg = "Unsupported sound file type. Use .mp3 or .wav."
        raise ValueError(msg)
    normalized_slot_name = slot_name.strip().lower().replace(" ", "-")
    if not normalized_slot_name:
        msg = "Sound slot name is required."
        raise ValueError(msg)

    sounds_dir = get_app_data_dir() / SOUNDS_FOLDER_NAME
    sounds_dir.mkdir(parents=True, exist_ok=True)
    copied_sound_path = (
        sounds_dir / f"{normalized_slot_name}-notification-sound{extension}"
    )
    shutil.copy2(resolved_source, copied_sound_path)
    return str(copied_sound_path)
