"""Focused flashcard editor dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
)

from estudai.services.csv_flashcards import normalize_flashcard_fields


class FlashcardEditDialog(QDialog):
    """Dialog used to edit one flashcard without opening full management."""

    def __init__(
        self,
        question: str,
        answer: str,
        parent=None,
    ) -> None:
        """Initialize dialog widgets with the current flashcard text."""
        super().__init__(parent)
        self._build_ui(question, answer)

    def _build_ui(self, question: str, answer: str) -> None:
        """Create and connect the dialog widgets."""
        self.setWindowTitle("Edit Flashcard")
        self.resize(640, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Question"))
        self.question_edit = QPlainTextEdit(question)
        self.question_edit.setTabChangesFocus(True)
        layout.addWidget(self.question_edit)

        layout.addWidget(QLabel("Answer"))
        self.answer_edit = QPlainTextEdit(answer)
        self.answer_edit.setTabChangesFocus(True)
        layout.addWidget(self.answer_edit)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_row.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._handle_save_clicked)
        buttons_row.addWidget(self.save_button)

        layout.addLayout(buttons_row)

    def _handle_save_clicked(self) -> None:
        """Validate current fields and accept when the inputs are valid."""
        try:
            question, answer = normalize_flashcard_fields(
                self.question_edit.toPlainText(),
                self.answer_edit.toPlainText(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Edit flashcard", str(error))
            return
        self.question_edit.setPlainText(question)
        self.answer_edit.setPlainText(answer)
        self.accept()

    def question_text(self) -> str:
        """Return the normalized question text."""
        return self.question_edit.toPlainText()

    def answer_text(self) -> str:
        """Return the normalized answer text."""
        return self.answer_edit.toPlainText()
