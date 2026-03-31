"""Study time service tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from estudai.services.study_time import (
    StudyTimeTracker,
    add_active_study_seconds,
    cumulative_active_seconds,
    format_duration,
    increment_flashcards_seen,
    load_study_time,
    load_total_flashcards_seen,
    recent_daily_history,
    save_study_time,
    today_active_seconds,
)


@pytest.fixture(autouse=True)
def _isolate_study_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect study time persistence to a temporary directory."""
    monkeypatch.setattr(
        "estudai.services.study_time.get_study_time_path",
        lambda: tmp_path / "study-time.json",
    )


class TestLoadAndSaveStudyTime:
    """Test load_study_time and save_study_time round-trip."""

    def test_empty_on_missing_file(self) -> None:
        """Return empty dict when the file does not exist."""
        assert load_study_time() == {}

    def test_round_trip(self) -> None:
        """Data survives save then load."""
        data = {"2025-01-15": 3600.0, "2025-01-16": 1800.5}
        save_study_time(data)
        loaded = load_study_time()
        assert loaded["2025-01-15"] == 3600.0
        assert loaded["2025-01-16"] == 1800.5

    def test_zero_seconds_are_dropped(self) -> None:
        """Days with zero seconds are excluded from the persisted file."""
        save_study_time({"2025-01-15": 0.0, "2025-01-16": 120.0})
        loaded = load_study_time()
        assert "2025-01-15" not in loaded
        assert loaded["2025-01-16"] == 120.0

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        """Corrupt JSON gracefully returns empty dict."""
        path = tmp_path / "study-time.json"
        path.write_text("not valid json", encoding="utf-8")
        assert load_study_time() == {}


class TestAddActiveStudySeconds:
    """Test add_active_study_seconds merges into today's total."""

    def test_adds_to_today(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Adds seconds under today's date key."""
        monkeypatch.setattr(
            "estudai.services.study_time._today_iso",
            lambda: "2025-03-01",
        )
        add_active_study_seconds(60.0)
        add_active_study_seconds(30.0)
        loaded = load_study_time()
        assert loaded["2025-03-01"] == 90.0

    def test_non_positive_seconds_ignored(self) -> None:
        """Zero or negative seconds do not write anything."""
        add_active_study_seconds(0)
        add_active_study_seconds(-5)
        assert load_study_time() == {}


class TestAggregationHelpers:
    """Test cumulative_active_seconds and today_active_seconds."""

    def test_cumulative(self) -> None:
        """Sum all daily values."""
        data = {"2025-01-01": 100.0, "2025-01-02": 200.0}
        assert cumulative_active_seconds(data) == 300.0

    def test_today(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return today's value or zero."""
        monkeypatch.setattr(
            "estudai.services.study_time._today_iso",
            lambda: "2025-03-01",
        )
        data = {"2025-03-01": 120.0, "2025-02-28": 60.0}
        assert today_active_seconds(data) == 120.0

    def test_today_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return zero when today has no entry."""
        monkeypatch.setattr(
            "estudai.services.study_time._today_iso",
            lambda: "2099-01-01",
        )
        assert today_active_seconds({"2025-01-01": 100.0}) == 0.0


class TestRecentDailyHistory:
    """Test recent_daily_history ordering and limit."""

    def test_returns_most_recent_first(self) -> None:
        """Most recent dates come first."""
        data = {"2025-01-01": 10.0, "2025-01-03": 30.0, "2025-01-02": 20.0}
        result = recent_daily_history(data, days=3)
        assert [r.date_iso for r in result] == [
            "2025-01-03",
            "2025-01-02",
            "2025-01-01",
        ]

    def test_limits_to_n_days(self) -> None:
        """Only return up to N days."""
        data = {f"2025-01-{d:02d}": float(d) for d in range(1, 11)}
        result = recent_daily_history(data, days=3)
        assert len(result) == 3

    def test_empty_data(self) -> None:
        """Return empty list for empty data."""
        assert recent_daily_history({}, days=7) == []


class TestFormatDuration:
    """Test format_duration output."""

    def test_zero(self) -> None:
        assert format_duration(0) == "0s"

    def test_seconds_only(self) -> None:
        assert format_duration(45) == "45s"

    def test_minutes_and_seconds(self) -> None:
        assert format_duration(130) == "2m 10s"

    def test_hours_minutes_seconds(self) -> None:
        assert format_duration(3661) == "1h 1m 1s"

    def test_exact_hour(self) -> None:
        assert format_duration(3600) == "1h"

    def test_exact_minute(self) -> None:
        assert format_duration(60) == "1m"

    def test_negative_returns_zero(self) -> None:
        assert format_duration(-100) == "0s"


class TestStudyTimeTracker:
    """Test the in-memory StudyTimeTracker lifecycle."""

    def test_start_pause_accumulates(self) -> None:
        """Pause captures elapsed active time."""
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        tracker.start()
        clock[0] = 10.0
        tracker.pause()
        assert tracker.session_elapsed_seconds == pytest.approx(10.0)
        assert tracker.is_active is False

    def test_resume_continues(self) -> None:
        """Resume after pause continues accumulating."""
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        tracker.start()
        clock[0] = 5.0
        tracker.pause()
        clock[0] = 10.0
        tracker.start()
        clock[0] = 15.0
        assert tracker.session_elapsed_seconds == pytest.approx(10.0)

    def test_stop_and_persist_resets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stop persists and returns total, then resets."""
        monkeypatch.setattr(
            "estudai.services.study_time._today_iso",
            lambda: "2025-06-01",
        )
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        tracker.start()
        clock[0] = 120.0
        total = tracker.stop_and_persist()
        assert total == pytest.approx(120.0)
        assert tracker.session_elapsed_seconds == 0.0
        assert tracker.is_active is False
        loaded = load_study_time()
        assert loaded["2025-06-01"] == pytest.approx(120.0, abs=1)

    def test_double_start_is_idempotent(self) -> None:
        """Starting while already active does not reset the clock."""
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        tracker.start()
        clock[0] = 5.0
        tracker.start()
        clock[0] = 10.0
        tracker.pause()
        assert tracker.session_elapsed_seconds == pytest.approx(10.0)

    def test_double_pause_is_idempotent(self) -> None:
        """Pausing while already paused does not lose time."""
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        tracker.start()
        clock[0] = 5.0
        tracker.pause()
        tracker.pause()
        assert tracker.session_elapsed_seconds == pytest.approx(5.0)

    def test_reset_discards_without_persisting(self) -> None:
        """Reset clears state without writing to disk."""
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        tracker.start()
        clock[0] = 100.0
        tracker.reset()
        assert tracker.session_elapsed_seconds == 0.0
        assert load_study_time() == {}

    def test_elapsed_during_active(self) -> None:
        """Elapsed includes live ticking time when active."""
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        tracker.start()
        clock[0] = 7.5
        assert tracker.session_elapsed_seconds == pytest.approx(7.5)
        assert tracker.is_active is True

    def test_pause_preserves_accumulated_across_resumes(self) -> None:
        """Multiple start/pause cycles accumulate within one tracker."""
        clock = [0.0]
        tracker = StudyTimeTracker(time_func=lambda: clock[0])
        # First study session: 10s
        tracker.start()
        clock[0] = 10.0
        tracker.pause()
        # Gap (user not studying)
        clock[0] = 50.0
        # Second study session: 5s
        tracker.start()
        clock[0] = 55.0
        tracker.pause()
        assert tracker.session_elapsed_seconds == pytest.approx(15.0)


class TestFlashcardsSeenCounter:
    """Test the global lifetime flashcards-seen counter."""

    def test_default_is_zero(self) -> None:
        """Counter returns 0 when no data is persisted."""
        assert load_total_flashcards_seen() == 0

    def test_increment_and_load(self) -> None:
        """Incrementing persists and is readable."""
        increment_flashcards_seen()
        assert load_total_flashcards_seen() == 1
        increment_flashcards_seen(3)
        assert load_total_flashcards_seen() == 4

    def test_increment_preserves_daily_times(self) -> None:
        """Incrementing the counter does not lose daily study time data."""
        save_study_time({"2025-06-01": 100.0})
        increment_flashcards_seen(2)
        daily = load_study_time()
        assert daily["2025-06-01"] == pytest.approx(100.0)
        assert load_total_flashcards_seen() == 2

    def test_save_study_time_preserves_counter(self) -> None:
        """Saving daily study times preserves the flashcards-seen counter."""
        increment_flashcards_seen(5)
        save_study_time({"2025-07-01": 200.0})
        assert load_total_flashcards_seen() == 5

    def test_zero_increment_is_noop(self) -> None:
        """Incrementing by 0 does not write to disk."""
        increment_flashcards_seen(0)
        assert load_total_flashcards_seen() == 0
