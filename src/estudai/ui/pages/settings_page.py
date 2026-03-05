"""Settings page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SettingsPage(QWidget):
    """Barebone settings page placeholder."""

    def __init__(self) -> None:
        """Initialize the settings page."""
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the settings UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            "This is a barebone settings page. App preferences and timer options will be added here."
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #666;")
        layout.addWidget(description)

        placeholder = QLabel("Nothing configurable yet.")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(
            "padding: 16px; border: 1px dashed #aaa; border-radius: 6px;"
        )
        layout.addWidget(placeholder)

        layout.addStretch()
