"""Focused flashcard editor dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
)

from estudai.services.csv_flashcards import (
    FLASHCARD_IMAGE_FILE_DIALOG_FILTER,
    normalize_flashcard_fields,
)


class FlashcardEditDialog(QDialog):
    """Dialog used to edit one flashcard without opening full management."""

    def __init__(
        self,
        question: str,
        answer: str,
        question_image_path: str | None = None,
        answer_image_path: str | None = None,
        base_folder_path: Path | None = None,
        parent=None,
    ) -> None:
        """Initialize dialog widgets with the current flashcard text."""
        super().__init__(parent)
        self._base_folder_path = base_folder_path
        self._question_image_path = question_image_path
        self._answer_image_path = answer_image_path
        self._build_ui(question, answer)

    def _build_ui(self, question: str, answer: str) -> None:
        """Create and connect the dialog widgets."""
        self.setWindowTitle("Edit Flashcard")
        self.resize(700, 520)

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

        layout.addWidget(QLabel("Question image"))
        self.question_image_summary_label = QLabel()
        self.question_image_summary_label.setWordWrap(True)
        layout.addWidget(self.question_image_summary_label)
        question_image_buttons = QHBoxLayout()
        self.choose_question_image_button = QPushButton("Choose Question Image")
        self.choose_question_image_button.clicked.connect(
            lambda: self._choose_image("question")
        )
        question_image_buttons.addWidget(self.choose_question_image_button)
        self.remove_question_image_button = QPushButton("Remove")
        self.remove_question_image_button.clicked.connect(
            lambda: self._remove_image("question")
        )
        question_image_buttons.addWidget(self.remove_question_image_button)
        question_image_buttons.addStretch()
        layout.addLayout(question_image_buttons)

        layout.addWidget(QLabel("Answer image"))
        self.answer_image_summary_label = QLabel()
        self.answer_image_summary_label.setWordWrap(True)
        layout.addWidget(self.answer_image_summary_label)
        answer_image_buttons = QHBoxLayout()
        self.choose_answer_image_button = QPushButton("Choose Answer Image")
        self.choose_answer_image_button.clicked.connect(
            lambda: self._choose_image("answer")
        )
        answer_image_buttons.addWidget(self.choose_answer_image_button)
        self.remove_answer_image_button = QPushButton("Remove")
        self.remove_answer_image_button.clicked.connect(
            lambda: self._remove_image("answer")
        )
        answer_image_buttons.addWidget(self.remove_answer_image_button)
        answer_image_buttons.addStretch()
        layout.addLayout(answer_image_buttons)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_row.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._handle_save_clicked)
        buttons_row.addWidget(self.save_button)

        layout.addLayout(buttons_row)
        self._refresh_image_summary_labels()

    def _handle_save_clicked(self) -> None:
        """Validate current fields and accept when the inputs are valid."""
        try:
            question, answer = normalize_flashcard_fields(
                self.question_edit.toPlainText(),
                self.answer_edit.toPlainText(),
                question_image_path=self._question_image_path,
                answer_image_path=self._answer_image_path,
            )
        except ValueError as error:
            QMessageBox.warning(self, "Edit flashcard", str(error))
            return
        self.question_edit.setPlainText(question)
        self.answer_edit.setPlainText(answer)
        self.accept()

    def _choose_image(self, side: str) -> None:
        """Prompt the user for one image and store its path for the given side."""
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {side} image",
            "",
            FLASHCARD_IMAGE_FILE_DIALOG_FILTER,
        )
        if not selected_path:
            return
        if side == "question":
            self._question_image_path = selected_path
        else:
            self._answer_image_path = selected_path
        self._refresh_image_summary_labels()

    def _remove_image(self, side: str) -> None:
        """Clear the currently attached image for the given flashcard side."""
        if side == "question":
            self._question_image_path = None
        else:
            self._answer_image_path = None
        self._refresh_image_summary_labels()

    def _refresh_image_summary_labels(self) -> None:
        """Update the visible image summaries and remove-button availability."""
        self.question_image_summary_label.setText(
            self._image_summary_text(self._question_image_path)
        )
        self.answer_image_summary_label.setText(
            self._image_summary_text(self._answer_image_path)
        )
        self.remove_question_image_button.setEnabled(
            self._question_image_path is not None
        )
        self.remove_answer_image_button.setEnabled(self._answer_image_path is not None)

    def _image_summary_text(self, image_path: str | None) -> str:
        """Return user-facing summary text for one optional image path."""
        if image_path is None:
            return "No image attached."
        display_path = image_path
        resolved_path = self._resolved_image_path(image_path)
        if resolved_path is not None and self._base_folder_path is not None:
            try:
                display_path = resolved_path.relative_to(
                    self._base_folder_path
                ).as_posix()
            except ValueError:
                display_path = str(resolved_path)
        status_suffix = ""
        if resolved_path is not None and not resolved_path.exists():
            status_suffix = " (unavailable)"
        return f"Attached: {display_path}{status_suffix}"

    def _resolved_image_path(self, image_path: str) -> Path | None:
        """Resolve one image path against the current managed folder, when known."""
        candidate_path = Path(image_path).expanduser()
        if candidate_path.is_absolute():
            return candidate_path
        if self._base_folder_path is None:
            return None
        return self._base_folder_path / candidate_path

    def question_text(self) -> str:
        """Return the normalized question text."""
        return self.question_edit.toPlainText()

    def answer_text(self) -> str:
        """Return the normalized answer text."""
        return self.answer_edit.toPlainText()

    def question_image_path(self) -> str | None:
        """Return the currently selected question-side image path."""
        return self._question_image_path

    def answer_image_path(self) -> str | None:
        """Return the currently selected answer-side image path."""
        return self._answer_image_path
