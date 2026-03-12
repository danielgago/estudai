"""Flashcard edit dialog tests."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from estudai.ui.dialog.flashcard_edit_dialog import FlashcardEditDialog

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


def test_dialog_accepts_image_only_flashcard_sides(
    app: QApplication,
    tmp_path: Path,
) -> None:
    """Verify image attachments allow saving empty question and answer text."""
    accepted: list[bool] = []
    dialog = FlashcardEditDialog("", "", base_folder_path=tmp_path)
    dialog._question_image_path = str(tmp_path / "question.png")
    dialog._answer_image_path = str(tmp_path / "answer.png")
    dialog.accept = lambda: accepted.append(True)

    dialog._handle_save_clicked()

    assert dialog.question_text() == ""
    assert dialog.answer_text() == ""
    assert accepted == [True]


def test_dialog_rejects_side_without_text_or_image(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the dialog still warns when a side has neither text nor image."""
    warnings: list[str] = []
    dialog = FlashcardEditDialog("", "")
    monkeypatch.setattr(
        "estudai.ui.dialog.flashcard_edit_dialog.QMessageBox.warning",
        lambda *_args: warnings.append("warning"),
    )

    dialog._handle_save_clicked()

    assert warnings == ["warning"]
