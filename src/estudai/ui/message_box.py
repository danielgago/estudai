"""Shared presenter for simple modal message boxes."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


class MessageBoxPresenter:
    """Present shared QMessageBox dialogs for one parent widget.

    Args:
        parent: Parent widget used for modal dialogs.
    """

    def __init__(self, parent: QWidget | None) -> None:
        """Store the parent widget used for message boxes.

        Args:
            parent: Parent widget used for modal dialogs.
        """
        self._parent = parent

    def show_information(self, title: str, message: str) -> None:
        """Show an informational message dialog.

        Args:
            title: Dialog title.
            message: Dialog body text.
        """
        QMessageBox.information(self._parent, title, message)

    def show_warning(self, title: str, message: str) -> None:
        """Show a warning message dialog.

        Args:
            title: Dialog title.
            message: Dialog body text.
        """
        QMessageBox.warning(self._parent, title, message)

    def confirm_yes_no(
        self,
        title: str,
        message: str,
        *,
        default_button: QMessageBox.StandardButton = QMessageBox.No,
    ) -> QMessageBox.StandardButton:
        """Ask a Yes/No confirmation question and return the chosen button.

        Args:
            title: Dialog title.
            message: Dialog body text.
            default_button: Default selected standard button.

        Returns:
            QMessageBox.StandardButton: Button chosen by the user.
        """
        return QMessageBox.question(
            self._parent,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            default_button,
        )
