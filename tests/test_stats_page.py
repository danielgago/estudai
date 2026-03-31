"""Stats page tests."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from estudai.services.study_time import StudyTimeTracker
from estudai.ui.pages.stats_page import StatsPage


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


@pytest.fixture(autouse=True)
def _isolate_persistence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect all persistence to temporary directories."""
    monkeypatch.setattr(
        "estudai.services.study_time.get_study_time_path",
        lambda: tmp_path / "study-time.json",
    )


def test_stats_page_creates_without_error(app: QApplication) -> None:
    """Verify the stats page initializes and renders without errors."""
    page = StatsPage()
    assert page.current_session_label.text() == "—"
    assert page.total_reviews_label.text() == "—"


def test_stats_page_refresh_with_no_data(app: QApplication) -> None:
    """Verify refresh produces default values with no persisted data."""
    page = StatsPage()
    page.refresh_stats()

    assert page.current_session_label.text() == "0s"
    assert page.today_label.text() == "0s"
    assert page.all_time_label.text() == "0s"
    assert page.total_reviews_label.text() == "0"


def test_stats_page_shows_active_session_time(app: QApplication) -> None:
    """Verify the stats page reflects the tracker's current session time."""
    clock = [0.0]
    tracker = StudyTimeTracker(time_func=lambda: clock[0])
    tracker.start()
    clock[0] = 90.0

    page = StatsPage(study_time_tracker=tracker)
    page.refresh_stats()

    assert page.current_session_label.text() == "1m 30s"


def test_stats_page_has_back_signal(app: QApplication) -> None:
    """Verify the back_requested signal exists."""
    page = StatsPage()
    assert hasattr(page, "back_requested")
