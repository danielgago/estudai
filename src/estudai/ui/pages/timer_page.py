"""Timer page."""

from PySide6.QtCore import QTime, Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class TimerPage(QWidget):
    """Timer page for study sessions."""

    timer_running_changed = Signal(bool)
    timer_cycle_completed = Signal()

    def __init__(self, default_duration_seconds: int = 25 * 60):
        super().__init__()
        self._default_duration_seconds = max(1, int(default_duration_seconds))
        self.time = QTime(0, 0, 0).addSecs(self._default_duration_seconds)
        self.is_running = False
        self.init_ui()

    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        title = QLabel("Study Timer")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        self.timer_display = QLabel(self.time.toString("mm:ss"))
        self.timer_display.setStyleSheet("font-size: 48px; font-weight: bold;")
        self.timer_display.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.timer_display)

        self.flashcard_question_label = QLabel("")
        self.flashcard_question_label.setAlignment(Qt.AlignCenter)
        self.flashcard_question_label.setWordWrap(True)
        self.flashcard_question_label.setStyleSheet(
            "font-size: 28px; font-weight: bold;"
        )
        self.flashcard_question_label.setVisible(False)
        layout.addWidget(self.flashcard_question_label)

        self.flashcard_answer_label = QLabel("")
        self.flashcard_answer_label.setAlignment(Qt.AlignCenter)
        self.flashcard_answer_label.setWordWrap(True)
        self.flashcard_answer_label.setStyleSheet("font-size: 22px; color: #666;")
        self.flashcard_answer_label.setVisible(False)
        layout.addWidget(self.flashcard_answer_label)

        self.folder_context_label = QLabel("Folder: No folders selected (0 cards)")
        self.folder_context_label.setAlignment(Qt.AlignCenter)
        self.folder_context_label.setStyleSheet("color: #666;")
        layout.addWidget(self.folder_context_label)

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_timer)
        layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_timer)
        self.pause_button.setEnabled(False)
        layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_timer)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        reset_button = QPushButton("Reset")
        reset_button.clicked.connect(self.reset_timer)
        layout.addWidget(reset_button)

        layout.addStretch()

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
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.timer_running_changed.emit(True)

    def pause_timer(self):
        """Pause the timer without resetting remaining time."""
        if self.is_running:
            self.is_running = False
            self.timer.stop()
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(True)

    def stop_timer(self):
        """Stop and reset the timer to default duration."""
        if self.is_running:
            self.is_running = False
            self.timer.stop()
        self.clear_flashcard_display()
        self.time = QTime(0, 0, 0).addSecs(self._default_duration_seconds)
        self.timer_display.setText(self.time.toString("mm:ss"))
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.timer_running_changed.emit(False)

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

    def show_flashcard_question(self, question: str) -> None:
        """Show flashcard question and hide timer display.

        Args:
            question: Flashcard question text.
        """
        self.timer_display.setVisible(False)
        self.flashcard_question_label.setText(question)
        self.flashcard_question_label.setVisible(True)
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)

    def show_flashcard_answer(self, answer: str) -> None:
        """Show flashcard answer under current question.

        Args:
            answer: Flashcard answer text.
        """
        self.flashcard_answer_label.setText(answer)
        self.flashcard_answer_label.setVisible(True)

    def clear_flashcard_display(self) -> None:
        """Hide flashcard question/answer and show timer display."""
        self.flashcard_question_label.setText("")
        self.flashcard_question_label.setVisible(False)
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)
        self.timer_display.setVisible(True)

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
