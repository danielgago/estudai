"""Stats overview page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from estudai.services.study_progress import load_study_progress
from estudai.services.study_time import (
    StudyTimeTracker,
    cumulative_active_seconds,
    format_duration,
    load_study_time,
    recent_daily_history,
    today_active_seconds,
)
from estudai.ui.utils import set_muted_label_color


class StatsPage(QWidget):
    """Page that displays study statistics overview."""

    back_requested = Signal()

    def __init__(
        self,
        study_time_tracker: StudyTimeTracker | None = None,
    ) -> None:
        """Initialize the stats page.

        Args:
            study_time_tracker: Shared tracker for current session active time.
        """
        super().__init__()
        self._study_time_tracker = study_time_tracker
        self._build_ui()

    def refresh_stats(self) -> None:
        """Reload all stats from disk and update the UI."""
        self._refresh_time_stats()
        self._refresh_flashcard_stats()
        self._refresh_daily_history()

    def _build_ui(self) -> None:
        """Build the stats page layout."""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Stats")
        title_font = QFont(title.font())
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.description_label = QLabel(
            "Overview of your study activity and daily progress."
        )
        self.description_label.setWordWrap(True)
        set_muted_label_color(self.description_label)
        layout.addWidget(self.description_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(16)

        self._build_time_section()
        self._build_daily_history_section()
        self._scroll_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, 1)

    def _build_time_section(self) -> None:
        """Build the study time and flashcard statistics section."""
        group = QGroupBox("Study Time")
        form = QFormLayout(group)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        self.current_session_label = QLabel("—")
        form.addRow("Current session:", self.current_session_label)

        self.today_label = QLabel("—")
        form.addRow("Today:", self.today_label)

        self.all_time_label = QLabel("—")
        form.addRow("All time:", self.all_time_label)

        self.total_reviews_label = QLabel("—")
        form.addRow("Lifetime flashcards seen:", self.total_reviews_label)

        self._scroll_layout.addWidget(group)

    def _build_daily_history_section(self) -> None:
        """Build the daily study history section."""
        self._history_group = QGroupBox("Recent Study History")
        self._history_layout = QVBoxLayout(self._history_group)
        self._history_layout.setSpacing(6)

        self._no_history_label = QLabel("No study sessions recorded yet.")
        set_muted_label_color(self._no_history_label)
        self._history_layout.addWidget(self._no_history_label)

        self._scroll_layout.addWidget(self._history_group)

    def _refresh_time_stats(self) -> None:
        """Reload time stats from disk and the active tracker."""
        daily_times = load_study_time()
        session_seconds = 0.0
        if self._study_time_tracker is not None:
            session_seconds = self._study_time_tracker.session_elapsed_seconds

        today_seconds = today_active_seconds(daily_times) + session_seconds
        all_time_seconds = cumulative_active_seconds(daily_times) + session_seconds

        self.current_session_label.setText(format_duration(session_seconds))
        self.today_label.setText(format_duration(today_seconds))
        self.all_time_label.setText(format_duration(all_time_seconds))

    def _refresh_flashcard_stats(self) -> None:
        """Reload flashcard stats from persisted progress."""
        progress_by_folder = load_study_progress()
        total_reviews = 0
        for folder_progress in progress_by_folder.values():
            for card_progress in folder_progress.values():
                total_reviews += card_progress.correct_count + card_progress.wrong_count
        self.total_reviews_label.setText(f"{total_reviews:,}")

    def _refresh_daily_history(self) -> None:
        """Rebuild daily study history widgets."""
        _clear_layout_widgets(self._history_layout)

        daily_times = load_study_time()
        history = recent_daily_history(daily_times, days=7)

        if not history:
            label = QLabel("No study sessions recorded yet.")
            set_muted_label_color(label)
            self._history_layout.addWidget(label)
            return

        max_seconds = max(d.active_seconds for d in history)

        for entry in history:
            row = QHBoxLayout()
            date_label = QLabel(entry.date_iso)
            date_label.setFixedWidth(90)
            row.addWidget(date_label)

            bar = QProgressBar()
            bar.setRange(0, max(1, int(max_seconds)))
            bar.setValue(int(entry.active_seconds))
            bar.setTextVisible(True)
            bar.setFormat(format_duration(entry.active_seconds))
            bar.setFixedHeight(18)
            row.addWidget(bar, 1)

            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(4, 2, 4, 2)
            container_layout.addLayout(row)
            self._history_layout.addWidget(container)


def _clear_layout_widgets(layout: QVBoxLayout) -> None:
    """Remove all widgets from a layout."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
