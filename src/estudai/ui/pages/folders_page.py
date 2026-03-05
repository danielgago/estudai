"""Folders page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FoldersPage(QWidget):
    """Barebone folders page with a clear empty state."""

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
            "Pick folders from the left sidebar while studying. "
            "Use this page to manage folder setup."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)

        folder_list = QListWidget()
        folder_list.setSpacing(4)
        placeholder_item = QListWidgetItem(
            "No folders yet. Create your first folder to get started."
        )
        placeholder_item.setFlags(Qt.NoItemFlags)
        folder_list.addItem(placeholder_item)
        layout.addWidget(folder_list)

        create_button = QPushButton("Create Folder")
        create_button.setEnabled(False)
        create_button.setToolTip("Folder management is coming soon.")
        layout.addWidget(create_button, alignment=Qt.AlignLeft)
