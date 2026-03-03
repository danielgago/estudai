"""Main application window."""

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget, QVBoxLayout

from .timer_page import TimerPage


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Estudai!")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.stacked_widget = QStackedWidget()
        layout.addWidget(self.stacked_widget)

        self.timer_page = TimerPage()

        self.stacked_widget.addWidget(self.timer_page)

        self.stacked_widget.setCurrentWidget(self.timer_page)

    def switch_to_timer(self):
        """Switch to timer page."""
        self.stacked_widget.setCurrentWidget(self.timer_page)
