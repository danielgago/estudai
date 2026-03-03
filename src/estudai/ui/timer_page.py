from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer, QTime


class TimerPage(QWidget):
    """Timer page for study sessions."""

    def __init__(self):
        super().__init__()
        self.time = QTime(0, 25, 0)
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

        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_timer)
        layout.addWidget(self.start_button)

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
            self.is_running = True
            self.timer.start(1000)
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)

    def stop_timer(self):
        """Stop the timer."""
        if self.is_running:
            self.is_running = False
            self.timer.stop()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def reset_timer(self):
        """Reset the timer."""
        self.stop_timer()
        self.time = QTime(0, 25, 0)
        self.timer_display.setText(self.time.toString("mm:ss"))

    def update_timer(self):
        """Update timer display."""
        self.time = self.time.addSecs(-1)
        self.timer_display.setText(self.time.toString("mm:ss"))

        if self.time.second() == 0 and self.time.minute() == 0:
            self.stop_timer()
