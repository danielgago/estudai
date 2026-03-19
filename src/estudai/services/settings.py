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
MAX_TIMER_DURATION_SECONDS = (59 * 60) + 59
SETTINGS_KEY_TIMER_DURATION_SECONDS = "timer/duration_seconds"
SETTINGS_KEY_FLASHCARD_PROBABILITY_PERCENT = "flashcard/probability_percent"
SETTINGS_KEY_FLASHCARD_STUDY_ORDER_MODE = "flashcard/study_order_mode"
SETTINGS_KEY_FLASHCARD_QUEUE_START_SHUFFLED = "flashcard/queue_start_shuffled"
SETTINGS_KEY_FLASHCARD_RANDOM_ORDER_ENABLED = "flashcard/random_order_enabled"
SETTINGS_KEY_QUESTION_DURATION_SECONDS = "flashcard/question_duration_seconds"
SETTINGS_KEY_ANSWER_DURATION_SECONDS = "flashcard/answer_duration_seconds"
SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH = "flashcard/notification_sound_path"
SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH = (
    "flashcard/question_notification_sound_path"
)
SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH = "flashcard/answer_notification_sound_path"
SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_DISPLAY_NAME = (
    "flashcard/question_notification_sound_display_name"
)
SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_DISPLAY_NAME = (
    "flashcard/answer_notification_sound_display_name"
)
SETTINGS_KEY_WRONG_ANSWER_COMPLETION_MODE = "flashcard/wrong_answer_completion_mode"
SETTINGS_KEY_WRONG_ANSWER_REINSERTION_MODE = "flashcard/wrong_answer_reinsertion_mode"
SETTINGS_KEY_WRONG_ANSWER_REINSERT_AFTER_COUNT = (
    "flashcard/wrong_answer_reinsert_after_count"
)
SETTINGS_KEY_HOTKEY_PAUSE_RESUME = "hotkeys/pause_resume"
SETTINGS_KEY_HOTKEY_START_STOP = "hotkeys/start_stop"
SETTINGS_KEY_HOTKEY_SKIP_PHASE = "hotkeys/skip_phase"
SETTINGS_KEY_HOTKEY_MARK_CORRECT = "hotkeys/mark_correct"
SETTINGS_KEY_HOTKEY_MARK_WRONG = "hotkeys/mark_wrong"
SETTINGS_KEY_HOTKEY_COPY_QUESTION = "hotkeys/copy_question"
SETTINGS_KEY_IN_APP_SHORTCUT_PAUSE_RESUME = "app_shortcuts/pause_resume"
SETTINGS_KEY_IN_APP_SHORTCUT_START_STOP = "app_shortcuts/start_stop"
SETTINGS_KEY_IN_APP_SHORTCUT_SKIP_PHASE = "app_shortcuts/skip_phase"
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


class StudyOrderMode(StrEnum):
    """Selection strategy for choosing the next study flashcard."""

    QUEUE = "queue"
    TRUE_RANDOM = "true_random"


class InAppShortcutAction(StrEnum):
    """Supported app-scoped shortcut actions handled inside the window."""

    PAUSE_RESUME = "pause_resume"
    START_STOP = "start_stop"
    SKIP_PHASE = "skip_phase"
    MARK_CORRECT = "mark_correct"
    MARK_WRONG = "mark_wrong"
    COPY_QUESTION = "copy_question"


DEFAULT_IN_APP_SHORTCUT_BINDINGS: dict[InAppShortcutAction, str] = {
    InAppShortcutAction.PAUSE_RESUME: "Space",
    InAppShortcutAction.START_STOP: "Enter",
    InAppShortcutAction.SKIP_PHASE: "Right",
    InAppShortcutAction.MARK_CORRECT: "Up",
    InAppShortcutAction.MARK_WRONG: "Down",
    InAppShortcutAction.COPY_QUESTION: "C",
}

_IN_APP_SHORTCUT_FIELD_MAP: dict[InAppShortcutAction, str] = {
    InAppShortcutAction.PAUSE_RESUME: "in_app_pause_resume_shortcut",
    InAppShortcutAction.START_STOP: "in_app_start_stop_shortcut",
    InAppShortcutAction.SKIP_PHASE: "in_app_skip_phase_shortcut",
    InAppShortcutAction.MARK_CORRECT: "in_app_mark_correct_shortcut",
    InAppShortcutAction.MARK_WRONG: "in_app_mark_wrong_shortcut",
    InAppShortcutAction.COPY_QUESTION: "in_app_copy_question_shortcut",
}


@dataclass(frozen=True)
class AppSettings:
    """Typed app settings payload persisted with QSettings."""

    timer_duration_seconds: int = 25 * 60
    flashcard_probability_percent: int = 30
    flashcard_study_order_mode: StudyOrderMode = StudyOrderMode.QUEUE
    flashcard_queue_start_shuffled: bool = False
    question_display_duration_seconds: int = 8
    answer_display_duration_seconds: int = 8
    question_notification_sound_path: str = ""
    question_notification_sound_display_name: str = ""
    answer_notification_sound_path: str = ""
    answer_notification_sound_display_name: str = ""
    wrong_answer_completion_mode: WrongAnswerCompletionMode = (
        WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE
    )
    wrong_answer_reinsertion_mode: WrongAnswerReinsertionMode = (
        WrongAnswerReinsertionMode.PUSH_TO_END
    )
    wrong_answer_reinsert_after_count: int = 3
    pause_resume_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.PAUSE_RESUME]
    start_stop_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.START_STOP]
    skip_phase_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.SKIP_PHASE]
    mark_correct_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.MARK_CORRECT]
    mark_wrong_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.MARK_WRONG]
    copy_question_hotkey: str = DEFAULT_HOTKEY_BINDINGS[HotkeyAction.COPY_QUESTION]
    in_app_pause_resume_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.PAUSE_RESUME
    ]
    in_app_start_stop_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.START_STOP
    ]
    in_app_skip_phase_shortcut: str = DEFAULT_IN_APP_SHORTCUT_BINDINGS[
        InAppShortcutAction.SKIP_PHASE
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


# ── Data-driven field descriptors for load/save ──────────────────────────

# (field_name, settings_key, minimum, maximum)
_INT_FIELD_SPECS: list[tuple[str, str, int, int]] = [
    (
        "timer_duration_seconds",
        SETTINGS_KEY_TIMER_DURATION_SECONDS,
        0,
        MAX_TIMER_DURATION_SECONDS,
    ),
    (
        "flashcard_probability_percent",
        SETTINGS_KEY_FLASHCARD_PROBABILITY_PERCENT,
        0,
        100,
    ),
    (
        "question_display_duration_seconds",
        SETTINGS_KEY_QUESTION_DURATION_SECONDS,
        1,
        3600,
    ),
    ("answer_display_duration_seconds", SETTINGS_KEY_ANSWER_DURATION_SECONDS, 1, 3600),
    (
        "wrong_answer_reinsert_after_count",
        SETTINGS_KEY_WRONG_ANSWER_REINSERT_AFTER_COUNT,
        0,
        999,
    ),
]

# (field_name, settings_key, enum_type)
_ENUM_FIELD_SPECS: list[tuple[str, str, type[StrEnum]]] = [
    (
        "wrong_answer_completion_mode",
        SETTINGS_KEY_WRONG_ANSWER_COMPLETION_MODE,
        WrongAnswerCompletionMode,
    ),
    (
        "wrong_answer_reinsertion_mode",
        SETTINGS_KEY_WRONG_ANSWER_REINSERTION_MODE,
        WrongAnswerReinsertionMode,
    ),
]

# (field_name, settings_key) — all allow_empty=True text fields
_TEXT_FIELD_SPECS: list[tuple[str, str]] = [
    ("pause_resume_hotkey", SETTINGS_KEY_HOTKEY_PAUSE_RESUME),
    ("start_stop_hotkey", SETTINGS_KEY_HOTKEY_START_STOP),
    ("skip_phase_hotkey", SETTINGS_KEY_HOTKEY_SKIP_PHASE),
    ("mark_correct_hotkey", SETTINGS_KEY_HOTKEY_MARK_CORRECT),
    ("mark_wrong_hotkey", SETTINGS_KEY_HOTKEY_MARK_WRONG),
    ("copy_question_hotkey", SETTINGS_KEY_HOTKEY_COPY_QUESTION),
    ("in_app_pause_resume_shortcut", SETTINGS_KEY_IN_APP_SHORTCUT_PAUSE_RESUME),
    ("in_app_start_stop_shortcut", SETTINGS_KEY_IN_APP_SHORTCUT_START_STOP),
    ("in_app_skip_phase_shortcut", SETTINGS_KEY_IN_APP_SHORTCUT_SKIP_PHASE),
    ("in_app_mark_correct_shortcut", SETTINGS_KEY_IN_APP_SHORTCUT_MARK_CORRECT),
    ("in_app_mark_wrong_shortcut", SETTINGS_KEY_IN_APP_SHORTCUT_MARK_WRONG),
    ("in_app_copy_question_shortcut", SETTINGS_KEY_IN_APP_SHORTCUT_COPY_QUESTION),
]

# Action enum → AppSettings field name mappings
_HOTKEY_FIELD_MAP: dict[HotkeyAction, str] = {
    HotkeyAction.PAUSE_RESUME: "pause_resume_hotkey",
    HotkeyAction.START_STOP: "start_stop_hotkey",
    HotkeyAction.SKIP_PHASE: "skip_phase_hotkey",
    HotkeyAction.MARK_CORRECT: "mark_correct_hotkey",
    HotkeyAction.MARK_WRONG: "mark_wrong_hotkey",
    HotkeyAction.COPY_QUESTION: "copy_question_hotkey",
}


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
    """Return the QSettings file path."""
    return get_app_data_dir() / SETTINGS_FILENAME


def _open_settings() -> QSettings:
    """Create a QSettings instance using app-local INI storage."""
    return QSettings(str(_settings_path()), QSettings.IniFormat)


def _normalize_int(
    raw_value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Normalize integer-like values into a safe bounded range."""
    try:
        value = int(raw_value)
    except TypeError, ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _normalize_bool(raw_value: object, *, default: bool) -> bool:
    """Normalize truthy/falsey settings values into a boolean."""
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


def _load_study_order_settings(qsettings: QSettings) -> tuple[StudyOrderMode, bool]:
    """Load study-order settings, migrating legacy random_order_enabled boolean."""
    has_study_order_mode = qsettings.contains(SETTINGS_KEY_FLASHCARD_STUDY_ORDER_MODE)
    has_queue_start_shuffled = qsettings.contains(
        SETTINGS_KEY_FLASHCARD_QUEUE_START_SHUFFLED
    )
    if has_study_order_mode or has_queue_start_shuffled:
        return (
            _normalize_enum(
                qsettings.value(
                    SETTINGS_KEY_FLASHCARD_STUDY_ORDER_MODE,
                    AppSettings.flashcard_study_order_mode.value,
                ),
                enum_type=StudyOrderMode,
                default=AppSettings.flashcard_study_order_mode,
            ),
            _normalize_bool(
                qsettings.value(
                    SETTINGS_KEY_FLASHCARD_QUEUE_START_SHUFFLED,
                    AppSettings.flashcard_queue_start_shuffled,
                ),
                default=AppSettings.flashcard_queue_start_shuffled,
            ),
        )

    return (
        StudyOrderMode.QUEUE,
        _normalize_bool(
            qsettings.value(
                SETTINGS_KEY_FLASHCARD_RANDOM_ORDER_ENABLED,
                AppSettings.flashcard_queue_start_shuffled,
            ),
            default=AppSettings.flashcard_queue_start_shuffled,
        ),
    )


def hotkey_bindings_from_settings(settings: AppSettings) -> dict[HotkeyAction, str]:
    """Return the persisted hotkey bindings keyed by app action."""
    return {
        action: getattr(settings, field) for action, field in _HOTKEY_FIELD_MAP.items()
    }


def in_app_shortcut_bindings_from_settings(
    settings: AppSettings,
) -> dict[InAppShortcutAction, str]:
    """Return the persisted in-app shortcut bindings keyed by action."""
    return {
        action: getattr(settings, field)
        for action, field in _IN_APP_SHORTCUT_FIELD_MAP.items()
    }


def _default_notification_sound_display_name(sound_path: str) -> str:
    """Return the fallback display name for a persisted custom sound path."""
    normalized_sound_path = sound_path.strip()
    if not normalized_sound_path:
        return ""
    return Path(normalized_sound_path).name


def _normalize_notification_sound_display_name(
    display_name: str,
    *,
    sound_path: str,
) -> str:
    """Normalize persisted sound display-name metadata."""
    normalized_display_name = display_name.strip()
    if normalized_display_name:
        return normalized_display_name
    return _default_notification_sound_display_name(sound_path)


def _load_notification_sound_settings(
    qsettings: QSettings,
    kwargs: dict[str, object],
) -> None:
    """Load notification-sound settings, migrating legacy single-sound key.

    Populates question/answer sound path and display name keys in *kwargs*.
    """
    legacy_path = _normalize_text(
        qsettings.value(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH, ""),
        default="",
        allow_empty=True,
    )
    has_question = qsettings.contains(SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH)
    has_answer = qsettings.contains(SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH)

    for slot, path_key, name_key in (
        (
            "question",
            SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH,
            SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_DISPLAY_NAME,
        ),
        (
            "answer",
            SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH,
            SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_DISPLAY_NAME,
        ),
    ):
        default_path = getattr(AppSettings, f"{slot}_notification_sound_path")
        path = _normalize_text(
            qsettings.value(path_key, default_path),
            default=default_path,
            allow_empty=True,
        )
        # Migrate legacy single-sound → dual question/answer slots
        if not has_question and not has_answer and legacy_path:
            path = legacy_path
        display_name = _normalize_text(
            qsettings.value(name_key, ""),
            default="",
            allow_empty=True,
        )
        if path and not display_name:
            display_name = _default_notification_sound_display_name(path)
        kwargs[f"{slot}_notification_sound_path"] = path
        kwargs[f"{slot}_notification_sound_display_name"] = display_name


def load_app_settings() -> AppSettings:
    """Load current app settings from QSettings.

    Returns:
        AppSettings: Persisted settings or default values.
    """
    qsettings = _open_settings()
    kwargs: dict[str, object] = {}

    # Integer fields
    for field_name, key, minimum, maximum in _INT_FIELD_SPECS:
        default = getattr(AppSettings, field_name)
        kwargs[field_name] = _normalize_int(
            qsettings.value(key, default),
            default=default,
            minimum=minimum,
            maximum=maximum,
        )

    # Enum fields
    for field_name, key, enum_type in _ENUM_FIELD_SPECS:
        default = getattr(AppSettings, field_name)
        kwargs[field_name] = _normalize_enum(
            qsettings.value(key, default.value),
            enum_type=enum_type,
            default=default,
        )

    # Text fields (hotkeys + shortcuts)
    for field_name, key in _TEXT_FIELD_SPECS:
        default = getattr(AppSettings, field_name)
        kwargs[field_name] = _normalize_text(
            qsettings.value(key, default),
            default=default,
            allow_empty=True,
        )

    # Study order: migrates legacy random_order_enabled boolean
    study_order_mode, queue_start_shuffled = _load_study_order_settings(qsettings)
    kwargs["flashcard_study_order_mode"] = study_order_mode
    kwargs["flashcard_queue_start_shuffled"] = queue_start_shuffled

    # Notification sounds: migrates legacy single-sound key to dual slots
    _load_notification_sound_settings(qsettings, kwargs)

    return AppSettings(**kwargs)


def save_app_settings(settings: AppSettings) -> None:
    """Persist all app settings into QSettings.

    Args:
        settings: Settings payload to persist.
    """
    qsettings = _open_settings()

    # Integer fields
    for field_name, key, minimum, maximum in _INT_FIELD_SPECS:
        default = getattr(AppSettings, field_name)
        qsettings.setValue(
            key,
            _normalize_int(
                getattr(settings, field_name),
                default=default,
                minimum=minimum,
                maximum=maximum,
            ),
        )

    # Enum fields
    for field_name, key, enum_type in _ENUM_FIELD_SPECS:
        default = getattr(AppSettings, field_name)
        qsettings.setValue(
            key,
            _normalize_enum(
                getattr(settings, field_name),
                enum_type=enum_type,
                default=default,
            ).value,
        )

    # Text fields (hotkeys + shortcuts)
    for field_name, key in _TEXT_FIELD_SPECS:
        default = getattr(AppSettings, field_name)
        qsettings.setValue(
            key,
            _normalize_text(
                getattr(settings, field_name),
                default=default,
                allow_empty=True,
            ),
        )

    # Study order
    qsettings.setValue(
        SETTINGS_KEY_FLASHCARD_STUDY_ORDER_MODE,
        _normalize_enum(
            settings.flashcard_study_order_mode,
            enum_type=StudyOrderMode,
            default=AppSettings.flashcard_study_order_mode,
        ).value,
    )
    qsettings.setValue(
        SETTINGS_KEY_FLASHCARD_QUEUE_START_SHUFFLED,
        bool(settings.flashcard_queue_start_shuffled),
    )

    # Notification sounds (question + answer slots)
    _SOUND_SLOTS = (
        (
            "question",
            SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_PATH,
            SETTINGS_KEY_QUESTION_NOTIFICATION_SOUND_DISPLAY_NAME,
        ),
        (
            "answer",
            SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_PATH,
            SETTINGS_KEY_ANSWER_NOTIFICATION_SOUND_DISPLAY_NAME,
        ),
    )
    for slot, path_key, name_key in _SOUND_SLOTS:
        path = getattr(settings, f"{slot}_notification_sound_path").strip()
        display_name = getattr(settings, f"{slot}_notification_sound_display_name")
        qsettings.setValue(path_key, path)
        qsettings.setValue(
            name_key,
            (
                _normalize_notification_sound_display_name(
                    display_name,
                    sound_path=path,
                )
                if path
                else ""
            ),
        )

    # Remove legacy keys
    qsettings.remove(SETTINGS_KEY_LEGACY_NOTIFICATION_SOUND_PATH)
    qsettings.remove(SETTINGS_KEY_FLASHCARD_RANDOM_ORDER_ENABLED)

    qsettings.sync()


def validate_notification_sound_file(source_path: Path) -> Path:
    """Validate a user-selected notification sound file and return its path."""
    resolved_source = source_path.expanduser().resolve()
    if not resolved_source.exists() or not resolved_source.is_file():
        msg = f"Sound file not found: {resolved_source}"
        raise FileNotFoundError(msg)
    extension = resolved_source.suffix.lower()
    if extension not in ALLOWED_SOUND_EXTENSIONS:
        msg = "Unsupported sound file type. Use .mp3 or .wav."
        raise ValueError(msg)
    return resolved_source


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
    resolved_source = validate_notification_sound_file(source_path)
    extension = resolved_source.suffix.lower()
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
