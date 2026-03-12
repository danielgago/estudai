"""Persistent study-progress helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

STUDY_PROGRESS_FILENAME = "study-progress.json"
STUDY_PROGRESS_VERSION = 1


@dataclass(frozen=True)
class FlashcardProgress:
    """Persisted progress counters for one flashcard.

    Args:
        correct_count: Total correct answers recorded for the flashcard.
        wrong_count: Total wrong answers recorded for the flashcard.
        last_reviewed_at: UTC timestamp for the latest scored review, if any.
    """

    correct_count: int = 0
    wrong_count: int = 0
    last_reviewed_at: str | None = None


@dataclass(frozen=True)
class FlashcardProgressEntry:
    """Progress payload paired with one folder/card identity.

    Args:
        folder_id: Managed folder identifier.
        flashcard_id: Stable flashcard identifier within the folder.
        progress: Persisted counter payload.
    """

    folder_id: str
    flashcard_id: str
    progress: FlashcardProgress


@dataclass(frozen=True)
class FolderProgressSummary:
    """Completion summary for one folder's persisted study progress.

    Args:
        total_flashcards: Total flashcards currently present in the folder.
        completed_flashcards: Flashcards considered completed by progress rules.
    """

    total_flashcards: int = 0
    completed_flashcards: int = 0

    @property
    def percent_done(self) -> int:
        """Return the rounded completion percentage for display."""
        if self.total_flashcards <= 0:
            return 0
        return int(
            round((self.completed_flashcards / self.total_flashcards) * 100)
        )


def get_study_progress_path() -> Path:
    """Return the study-progress JSON file path.

    Returns:
        Path: Persistent study-progress file path.
    """
    from .folder_storage import get_app_data_dir

    return get_app_data_dir() / STUDY_PROGRESS_FILENAME


def reviewed_progress(correct_count: int, wrong_count: int) -> FlashcardProgress:
    """Build a reviewed progress payload stamped with the current UTC time.

    Args:
        correct_count: Correct-answer count to persist.
        wrong_count: Wrong-answer count to persist.

    Returns:
        FlashcardProgress: Normalized progress payload.
    """
    return FlashcardProgress(
        correct_count=max(0, correct_count),
        wrong_count=max(0, wrong_count),
        last_reviewed_at=datetime.now(UTC).isoformat(),
    )


def is_review_complete(
    correct_count: int,
    wrong_count: int,
    completion_mode: WrongAnswerCompletionMode,
) -> bool:
    """Return whether counters satisfy the configured completion rule.

    Args:
        correct_count: Persisted or in-memory correct-answer count.
        wrong_count: Persisted or in-memory wrong-answer count.
        completion_mode: Completion rule configured in settings.

    Returns:
        bool: True when the counters count as completed.
    """
    from .settings import WrongAnswerCompletionMode

    if completion_mode is WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG:
        return correct_count > wrong_count
    return correct_count >= 1


def summarize_folder_progress(
    flashcard_ids: Iterable[str | None],
    folder_progress: Mapping[str, FlashcardProgress],
    completion_mode: WrongAnswerCompletionMode,
) -> FolderProgressSummary:
    """Summarize persisted completion state for one folder.

    Args:
        flashcard_ids: Stable flashcard ids currently present in the folder.
        folder_progress: Persisted progress indexed by stable flashcard id.
        completion_mode: Completion rule configured in settings.

    Returns:
        FolderProgressSummary: Folder completion summary for display.
    """
    total_flashcards = 0
    completed_flashcards = 0
    for flashcard_id in flashcard_ids:
        total_flashcards += 1
        if flashcard_id is None:
            continue
        progress = folder_progress.get(flashcard_id)
        if progress is None:
            continue
        if is_review_complete(
            progress.correct_count,
            progress.wrong_count,
            completion_mode,
        ):
            completed_flashcards += 1
    return FolderProgressSummary(
        total_flashcards=total_flashcards,
        completed_flashcards=completed_flashcards,
    )


def load_study_progress() -> dict[str, dict[str, FlashcardProgress]]:
    """Load all persisted study progress from disk.

    Returns:
        dict[str, dict[str, FlashcardProgress]]: Progress grouped by folder id.
    """
    progress_path = get_study_progress_path()
    if not progress_path.exists():
        return {}

    try:
        payload = json.loads(progress_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}

    folders_payload = payload.get("folders")
    if not isinstance(folders_payload, dict):
        return {}

    progress_by_folder: dict[str, dict[str, FlashcardProgress]] = {}
    for folder_id, folder_payload in folders_payload.items():
        if not isinstance(folder_id, str) or not isinstance(folder_payload, dict):
            continue
        folder_progress: dict[str, FlashcardProgress] = {}
        for flashcard_id, flashcard_payload in folder_payload.items():
            if not isinstance(flashcard_id, str):
                continue
            progress = _parse_flashcard_progress(flashcard_payload)
            if progress is None:
                continue
            folder_progress[flashcard_id] = progress
        if folder_progress:
            progress_by_folder[folder_id] = folder_progress
    return progress_by_folder


def load_folder_progress(folder_id: str) -> dict[str, FlashcardProgress]:
    """Load progress for one managed folder.

    Args:
        folder_id: Managed folder identifier.

    Returns:
        dict[str, FlashcardProgress]: Progress indexed by stable flashcard id.
    """
    return load_study_progress().get(folder_id, {})


def save_progress_entries(entries: list[FlashcardProgressEntry]) -> None:
    """Merge and persist progress updates for one or more flashcards.

    Args:
        entries: Folder/card progress entries to merge into persisted storage.
    """
    if not entries:
        return
    progress_by_folder = load_study_progress()
    for entry in entries:
        if not entry.folder_id or not entry.flashcard_id:
            continue
        folder_progress = progress_by_folder.setdefault(entry.folder_id, {})
        folder_progress[entry.flashcard_id] = entry.progress
    _save_study_progress(progress_by_folder)


def prune_folder_progress(folder_id: str, valid_flashcard_ids: set[str]) -> None:
    """Remove persisted progress entries for flashcards no longer present.

    Args:
        folder_id: Managed folder identifier.
        valid_flashcard_ids: Stable flashcard IDs still present in the folder.
    """
    progress_by_folder = load_study_progress()
    if folder_id not in progress_by_folder:
        return
    filtered_progress = {
        flashcard_id: progress
        for flashcard_id, progress in progress_by_folder[folder_id].items()
        if flashcard_id in valid_flashcard_ids
    }
    if filtered_progress:
        progress_by_folder[folder_id] = filtered_progress
    else:
        progress_by_folder.pop(folder_id, None)
    _save_study_progress(progress_by_folder)


def delete_folder_progress(folder_id: str) -> None:
    """Delete all persisted progress for one managed folder.

    Args:
        folder_id: Managed folder identifier.
    """
    progress_by_folder = load_study_progress()
    if progress_by_folder.pop(folder_id, None) is None:
        return
    _save_study_progress(progress_by_folder)


def _parse_flashcard_progress(payload: object) -> FlashcardProgress | None:
    """Parse one flashcard progress payload safely."""
    if not isinstance(payload, dict):
        return None
    correct_count = _parse_non_negative_int(payload.get("correct_count"))
    wrong_count = _parse_non_negative_int(payload.get("wrong_count"))
    if correct_count is None or wrong_count is None:
        return None
    last_reviewed_at = payload.get("last_reviewed_at")
    if last_reviewed_at is not None and not isinstance(last_reviewed_at, str):
        last_reviewed_at = None
    return FlashcardProgress(
        correct_count=correct_count,
        wrong_count=wrong_count,
        last_reviewed_at=last_reviewed_at,
    )


def _parse_non_negative_int(value: object) -> int | None:
    """Return a validated non-negative integer value."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _save_study_progress(
    progress_by_folder: dict[str, dict[str, FlashcardProgress]],
) -> None:
    """Persist all study progress atomically.

    Args:
        progress_by_folder: Progress grouped by folder id.
    """
    progress_path = get_study_progress_path()
    payload = {
        "version": STUDY_PROGRESS_VERSION,
        "folders": {
            folder_id: {
                flashcard_id: asdict(progress)
                for flashcard_id, progress in sorted(folder_progress.items())
            }
            for folder_id, folder_progress in sorted(progress_by_folder.items())
            if folder_progress
        },
    }
    _write_json_atomic(progress_path, payload)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    """Write JSON content atomically to avoid partial-save corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)
