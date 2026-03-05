"""Folders page."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class FoldersPage(QWidget):
    """Simple folders page with usage guidance."""

    def __init__(self) -> None:
        """Initialize the folders page."""
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the folders UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Folders")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Use 'Add Folder' in the left sidebar to choose CSV folders. "
            "Selected folders are copied and kept for future sessions."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)

        placeholder = QLabel("Selected folders appear in the sidebar.")
        placeholder.setStyleSheet("padding: 16px; border: 1px dashed #aaa; border-radius: 6px;")
        layout.addWidget(placeholder)
        layout.addStretch()
