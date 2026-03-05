"""Timer page."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTime, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from estudai.ui.utils import render_inline_latex_html


class TimerPage(QWidget):
    """Timer page for study sessions."""

    timer_running_changed = Signal(bool)
    timer_cycle_completed = Signal()
    flashcard_pause_toggled = Signal(bool)
    stop_requested = Signal()

    def __init__(self, default_duration_seconds: int = 25 * 60):
        super().__init__()
        self._default_duration_seconds = max(1, int(default_duration_seconds))
        self.time = QTime(0, 0, 0).addSecs(self._default_duration_seconds)
        self.is_running = False
        self._flashcard_controls_active = False
        self._flashcard_paused = False
        self._flashcard_phase_animation: QPropertyAnimation | None = None
        self.init_ui()

    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.content_stack.setMinimumHeight(260)

        timer_view = QWidget()
        timer_layout = QVBoxLayout(timer_view)
        timer_layout.setContentsMargins(0, 0, 0, 0)
        timer_layout.setSpacing(0)
        timer_layout.addStretch(1)
        self.timer_display = QLabel(self.time.toString("mm:ss"))
        self.timer_display.setStyleSheet("font-size: 74px; font-weight: 800;")
        self.timer_display.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.timer_display)
        timer_layout.addStretch(1)
        self.content_stack.addWidget(timer_view)

        flashcard_view = QWidget()
        flashcard_layout = QVBoxLayout(flashcard_view)
        flashcard_layout.setContentsMargins(0, 0, 0, 0)
        flashcard_layout.setSpacing(14)
        flashcard_layout.addStretch(1)
        self.flashcard_question_label = QLabel("")
        self.flashcard_question_label.setAlignment(Qt.AlignCenter)
        self.flashcard_question_label.setWordWrap(True)
        self.flashcard_question_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.flashcard_question_label.setStyleSheet(
            "font-size: 40px; font-weight: 800;"
        )
        self.flashcard_question_label.setVisible(False)
        flashcard_layout.addWidget(self.flashcard_question_label)

        self.flashcard_answer_label = QLabel("")
        self.flashcard_answer_label.setAlignment(Qt.AlignCenter)
        self.flashcard_answer_label.setWordWrap(True)
        self.flashcard_answer_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.flashcard_answer_label.setStyleSheet("font-size: 34px; font-weight: 600;")
        self.flashcard_answer_label.setVisible(False)
        flashcard_layout.addWidget(self.flashcard_answer_label)
        flashcard_layout.addStretch(1)
        self.content_stack.addWidget(flashcard_view)
        layout.addWidget(self.content_stack)

        self.folder_context_label = QLabel("Folder: No folders selected (0 cards)")
        self.folder_context_label.setAlignment(Qt.AlignCenter)
        self.folder_context_label.setStyleSheet("font-size: 14px; color: #4b5563;")
        layout.addWidget(self.folder_context_label)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        controls_layout.addStretch(1)

        self.start_button = QPushButton("Start")
        self.start_button.setToolTip("Start countdown")
        self.start_button.clicked.connect(self.start_timer)
        self.start_button.setMinimumWidth(110)
        controls_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setToolTip("Pause countdown")
        self.pause_button.clicked.connect(self.pause_timer)
        self.pause_button.setEnabled(False)
        self.pause_button.setMinimumWidth(110)
        controls_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("Stop and reset countdown")
        self.stop_button.clicked.connect(self._handle_stop_button_clicked)
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumWidth(110)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addStretch(1)
        layout.addLayout(controls_layout)

        self.flashcard_progress_bar = QProgressBar()
        self.flashcard_progress_bar.setRange(0, 1000)
        self.flashcard_progress_bar.setValue(0)
        self.flashcard_progress_bar.setTextVisible(False)
        self.flashcard_progress_bar.setFixedHeight(6)
        self.flashcard_progress_bar.setVisible(False)
        layout.addWidget(self.flashcard_progress_bar)

        self.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 3px;
                background: #e5e7eb;
            }
            QProgressBar::chunk {
                border-radius: 3px;
                background: #6366f1;
            }
            """)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)

    def start_timer(self):
        """Start the timer."""
        if not self.is_running:
            self.clear_flashcard_display()
            if self.time.second() == 0 and self.time.minute() == 0:
                self.time = QTime(0, 0, 0).addSecs(self._default_duration_seconds)
                self.timer_display.setText(self.time.toString("mm:ss"))
            self.is_running = True
            self.timer.start(1000)
            self.start_button.setEnabled(False)
            self.pause_button.setText("Pause")
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.timer_running_changed.emit(True)

    def pause_timer(self):
        """Pause the timer without resetting remaining time."""
        if self.is_running:
            self.is_running = False
            self.timer.stop()
            self.start_button.setEnabled(True)
            self.pause_button.setText("Pause")
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            return
        if not self._flashcard_controls_active:
            return
        self._flashcard_paused = not self._flashcard_paused
        self.pause_button.setText("Resume" if self._flashcard_paused else "Pause")
        self.flashcard_pause_toggled.emit(self._flashcard_paused)

    def stop_timer(self):
        """Stop and reset the timer to default duration."""
        if self.is_running:
            self.is_running = False
            self.timer.stop()
        self.clear_flashcard_display()
        self.time = QTime(0, 0, 0).addSecs(self._default_duration_seconds)
        self.timer_display.setText(self.time.toString("mm:ss"))
        self.start_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.timer_running_changed.emit(False)

    def _handle_stop_button_clicked(self) -> None:
        """Emit stop event and stop timer from stop button interaction."""
        self.stop_requested.emit()
        self.stop_timer()

    def reset_timer(self):
        """Reset the timer."""
        self.stop_timer()

    def restart_timer_cycle(self) -> None:
        """Reset the timer and immediately start a new countdown cycle."""
        self.clear_flashcard_display()
        self.time = QTime(0, 0, 0).addSecs(self._default_duration_seconds)
        self.timer_display.setText(self.time.toString("mm:ss"))
        self.start_timer()

    def update_timer(self):
        """Update timer display."""
        if not self.is_running:
            return
        self.time = self.time.addSecs(-1)
        self.timer_display.setText(self.time.toString("mm:ss"))

        if self.time.second() == 0 and self.time.minute() == 0:
            self.timer.stop()
            self.is_running = False
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.timer_running_changed.emit(False)
            self.timer_cycle_completed.emit()

    def show_flashcard_answer(
        self, answer: str, display_duration_seconds: int = 0
    ) -> None:
        """Show flashcard answer under current question.

        Args:
            answer: Flashcard answer text.
            display_duration_seconds: Duration answer stays visible.
        """
        self.set_flashcard_controls_active(True)
        self.flashcard_answer_label.setText(render_inline_latex_html(answer))
        self.flashcard_answer_label.setVisible(True)
        self._start_flashcard_progress(display_duration_seconds)

    def show_flashcard_question(
        self, question: str, display_duration_seconds: int = 0
    ) -> None:
        """Show flashcard question and hide timer display.

        Args:
            question: Flashcard question text.
            display_duration_seconds: Duration question stays visible.
        """
        self.content_stack.setCurrentIndex(1)
        self.set_flashcard_controls_active(True)
        self.flashcard_question_label.setVisible(True)
        self.flashcard_question_label.setText(render_inline_latex_html(question))
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)
        self._start_flashcard_progress(display_duration_seconds)

    def clear_flashcard_display(self) -> None:
        """Hide flashcard question/answer and show timer display."""
        self.flashcard_question_label.setText("")
        self.flashcard_question_label.setVisible(False)
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)
        self.content_stack.setCurrentIndex(0)
        self.set_flashcard_controls_active(False)
        self._stop_flashcard_progress()

    def set_flashcard_context(self, folder_name: str, card_count: int) -> None:
        """Update selected folder summary shown on the timer page.

        Args:
            folder_name: Selected folder display name.
            card_count: Number of loaded flashcards in scope.
        """
        self.folder_context_label.setText(f"Folder: {folder_name} ({card_count} cards)")

    def set_timer_duration_seconds(self, duration_seconds: int) -> None:
        """Set the default timer duration used by reset and idle display.

        Args:
            duration_seconds: New default countdown duration in seconds.
        """
        self._default_duration_seconds = max(1, int(duration_seconds))
        if not self.is_running:
            self.time = QTime(0, 0, 0).addSecs(self._default_duration_seconds)
            self.timer_display.setText(self.time.toString("mm:ss"))

    def set_flashcard_controls_active(self, active: bool) -> None:
        """Configure control buttons for flashcard phase interactions.

        Args:
            active: Whether flashcard controls should be active.
        """
        was_paused = self._flashcard_paused
        self._flashcard_controls_active = active
        if active:
            self.start_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            if not self._flashcard_paused:
                self.pause_button.setText("Pause")
            return
        self._flashcard_paused = False
        self.pause_button.setText("Pause")
        if was_paused:
            self.flashcard_pause_toggled.emit(False)

    def _start_flashcard_progress(self, duration_seconds: int) -> None:
        """Animate progress bar for flashcard phase durations.

        Args:
            duration_seconds: Duration in seconds for the current phase.
        """
        self._stop_flashcard_progress()
        if duration_seconds <= 0:
            return
        self.flashcard_progress_bar.setValue(0)
        self.flashcard_progress_bar.setVisible(True)
        self._animate_flashcard_progress(0, duration_seconds * 1000)

    def pause_flashcard_progress(self) -> None:
        """Pause progress animation without resetting current progress."""
        if self._flashcard_phase_animation is not None:
            self._flashcard_phase_animation.stop()

    def resume_flashcard_progress(self, remaining_milliseconds: int) -> None:
        """Resume progress animation from current value.

        Args:
            remaining_milliseconds: Remaining phase duration.
        """
        if not self.flashcard_progress_bar.isVisible() or remaining_milliseconds <= 0:
            return
        self._animate_flashcard_progress(
            self.flashcard_progress_bar.value(), remaining_milliseconds
        )

    def _animate_flashcard_progress(
        self, start_value: int, duration_milliseconds: int
    ) -> None:
        """Animate progress bar between values.

        Args:
            start_value: Initial progress value.
            duration_milliseconds: Duration in milliseconds.
        """
        if self._flashcard_phase_animation is not None:
            self._flashcard_phase_animation.stop()
            self._flashcard_phase_animation.deleteLater()
            self._flashcard_phase_animation = None
        self.flashcard_progress_bar.setValue(start_value)
        animation = QPropertyAnimation(self.flashcard_progress_bar, b"value", self)
        animation.setStartValue(start_value)
        animation.setEndValue(1000)
        animation.setDuration(duration_milliseconds)
        animation.setEasingCurve(QEasingCurve.Type.Linear)
        animation.start()
        self._flashcard_phase_animation = animation

    def _stop_flashcard_progress(self) -> None:
        """Stop and reset the flashcard progress animation."""
        if self._flashcard_phase_animation is not None:
            self._flashcard_phase_animation.stop()
            self._flashcard_phase_animation.deleteLater()
            self._flashcard_phase_animation = None
        self.flashcard_progress_bar.setValue(0)
        self.flashcard_progress_bar.setVisible(False)
