"""Persistent study-time tracking helpers."""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

STUDY_TIME_FILENAME = "study-time.json"
STUDY_TIME_VERSION = 1


@dataclass(frozen=True)
class DailyStudyTime:
    """Active study time recorded for one calendar day.

    Args:
        date_iso: Calendar date in ISO 8601 format (YYYY-MM-DD).
        active_seconds: Total active study seconds accumulated on this date.
    """

    date_iso: str
    active_seconds: float


def get_study_time_path() -> Path:
    """Return the study-time JSON file path."""
    from .folder_storage import get_app_data_dir

    return get_app_data_dir() / STUDY_TIME_FILENAME


def _load_study_time_payload() -> dict:
    """Load the raw study-time JSON payload from disk."""
    time_path = get_study_time_path()
    if not time_path.exists():
        return {}
    try:
        payload = json.loads(time_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def load_study_time() -> dict[str, float]:
    """Load persisted daily study time from disk.

    Returns:
        dict[str, float]: Active seconds indexed by ISO date string.
    """
    payload = _load_study_time_payload()
    days_payload = payload.get("days")
    if not isinstance(days_payload, dict):
        return {}

    result: dict[str, float] = {}
    for date_key, seconds in days_payload.items():
        if not isinstance(date_key, str):
            continue
        parsed_seconds = _parse_non_negative_number(seconds)
        if parsed_seconds is not None:
            result[date_key] = parsed_seconds
    return result


def load_total_flashcards_seen() -> int:
    """Load the lifetime flashcards-seen counter from disk.

    Returns:
        int: Total number of flashcard answer reveals recorded.
    """
    payload = _load_study_time_payload()
    value = payload.get("total_flashcards_seen", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _save_study_time_payload(
    daily_times: dict[str, float],
    total_flashcards_seen: int,
) -> None:
    """Persist the full study-time payload atomically."""
    time_path = get_study_time_path()
    payload: dict[str, object] = {
        "version": STUDY_TIME_VERSION,
        "days": {
            date_key: round(seconds, 2)
            for date_key, seconds in sorted(daily_times.items())
            if seconds > 0
        },
        "total_flashcards_seen": total_flashcards_seen,
    }
    _write_json_atomic(time_path, payload)


def save_study_time(daily_times: dict[str, float]) -> None:
    """Persist daily study time atomically.

    Args:
        daily_times: Active seconds indexed by ISO date string.
    """
    seen = load_total_flashcards_seen()
    _save_study_time_payload(daily_times, seen)


def increment_flashcards_seen(count: int = 1) -> None:
    """Increment the lifetime flashcards-seen counter and persist.

    Args:
        count: Number of answer reveals to add.
    """
    if count <= 0:
        return
    daily_times = load_study_time()
    seen = load_total_flashcards_seen() + count
    _save_study_time_payload(daily_times, seen)


def add_active_study_seconds(seconds: float) -> None:
    """Add active study seconds to today's total and persist.

    Args:
        seconds: Active study seconds to add.
    """
    if seconds <= 0:
        return
    today_key = _today_iso()
    daily_times = load_study_time()
    daily_times[today_key] = daily_times.get(today_key, 0.0) + seconds
    save_study_time(daily_times)


def cumulative_active_seconds(daily_times: dict[str, float]) -> float:
    """Return total active seconds across all recorded days.

    Args:
        daily_times: Daily active seconds loaded from disk.

    Returns:
        float: Sum of all daily active seconds.
    """
    return sum(daily_times.values())


def today_active_seconds(daily_times: dict[str, float]) -> float:
    """Return active seconds recorded today.

    Args:
        daily_times: Daily active seconds loaded from disk.

    Returns:
        float: Active seconds for today, or 0.
    """
    return daily_times.get(_today_iso(), 0.0)


def recent_daily_history(
    daily_times: dict[str, float],
    days: int = 7,
) -> list[DailyStudyTime]:
    """Return the last N days of study history, most recent first.

    Args:
        daily_times: Daily active seconds loaded from disk.
        days: Number of recent days to include.

    Returns:
        list[DailyStudyTime]: Daily records sorted newest first.
    """
    sorted_dates = sorted(daily_times.keys(), reverse=True)[:days]
    return [
        DailyStudyTime(date_iso=d, active_seconds=daily_times[d]) for d in sorted_dates
    ]


def format_duration(total_seconds: float) -> str:
    """Format a duration in seconds as a human-readable string.

    Args:
        total_seconds: Duration in seconds.

    Returns:
        str: Formatted string like "2h 15m 30s" or "0s".
    """
    total = max(0, int(total_seconds))
    if total == 0:
        return "0s"
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


class StudyTimeTracker:
    """Track active study time within one session.

    The tracker accumulates time only while the study session is actively
    running (not paused or stopped).
    """

    def __init__(self, time_func: object = None) -> None:
        """Initialize an idle tracker.

        Args:
            time_func: Monotonic clock callable for testing. Defaults to
                time.monotonic.
        """
        self._time_func = time_func or time.monotonic
        self._session_start: float | None = None
        self._accumulated_seconds: float = 0.0
        self._is_active: bool = False

    @property
    def is_active(self) -> bool:
        """Return whether the tracker is currently accumulating time."""
        return self._is_active

    @property
    def session_elapsed_seconds(self) -> float:
        """Return active seconds accumulated in this app session."""
        elapsed = self._accumulated_seconds
        if self._is_active and self._session_start is not None:
            elapsed += self._time_func() - self._session_start
        return elapsed

    def start(self) -> None:
        """Start or resume active time tracking."""
        if self._is_active:
            return
        self._session_start = self._time_func()
        self._is_active = True

    def pause(self) -> None:
        """Pause active time tracking, keeping accumulated time."""
        if not self._is_active:
            return
        if self._session_start is not None:
            self._accumulated_seconds += self._time_func() - self._session_start
        self._session_start = None
        self._is_active = False

    def stop_and_persist(self) -> float:
        """Stop tracking, persist accumulated time, and reset.

        Returns:
            float: Total active seconds for the session that was stopped.
        """
        self.pause()
        total = self._accumulated_seconds
        if total > 0:
            add_active_study_seconds(total)
        self._accumulated_seconds = 0.0
        self._session_start = None
        return total

    def reset(self) -> None:
        """Discard accumulated time without persisting."""
        self._accumulated_seconds = 0.0
        self._session_start = None
        self._is_active = False


def _today_iso() -> str:
    """Return today's date as an ISO string in UTC."""
    return datetime.now(UTC).date().isoformat()


def _parse_non_negative_number(value: object) -> float | None:
    """Return a validated non-negative number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    return None


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    """Write JSON content atomically to avoid partial-save corruption."""
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        suffix=".tmp",
        prefix=path.stem,
    )
    os.close(fd)
    temporary_path = Path(tmp_name)
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
