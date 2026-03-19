"""Management-page controller tests."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from estudai.services.csv_flashcards import Flashcard, FlashcardRowData
from estudai.ui.application_state import FolderLibraryState, StudyApplicationState
from estudai.ui.controllers.management_page_controller import ManagementPageController


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


class _FakeSidebarItem:
    """Minimal sidebar item used by controller tests."""

    def __init__(self, folder_id: str | None, *, checked: bool) -> None:
        """Initialize the fake sidebar item.

        Args:
            folder_id: Folder id stored in the item.
            checked: Whether the item is checked.
        """
        self._folder_id = folder_id
        self._checked = checked

    def data(self, role: int) -> str | None:
        """Return stored folder data for the requested role.

        Args:
            role: Requested data role.

        Returns:
            str | None: Stored folder id for `Qt.UserRole`.
        """
        if role == Qt.UserRole:
            return self._folder_id
        return None

    def checkState(self) -> Qt.CheckState:  # noqa: N802
        """Return the item's checked state."""
        return Qt.Checked if self._checked else Qt.Unchecked


class _FakeManagementPage:
    """Minimal management page spy used by controller tests."""

    def __init__(self) -> None:
        """Initialize the fake page."""
        self.loaded_folder_call: tuple[str, str, list[Flashcard], set[int]] | None = (
            None
        )
        self.selected_rows: list[int] = []
        self.removed_rows: list[int] | None = None
        self.collect_result: tuple[list[FlashcardRowData], set[int]] = ([], set())
        self.added_rows: list[FlashcardRowData] = []
        self.updated_rows: list[tuple[int, FlashcardRowData]] = []
        self.selected_row_payload: tuple[int, FlashcardRowData] | None = None

    def set_folder_flashcards(
        self,
        folder_id: str,
        folder_name: str,
        flashcards: list[Flashcard],
        selected_indexes: set[int],
    ) -> None:
        """Record the folder payload loaded into the page."""
        self.loaded_folder_call = (
            folder_id,
            folder_name,
            list(flashcards),
            set(selected_indexes),
        )

    def selected_table_rows(self) -> list[int]:
        """Return selected table rows."""
        return list(self.selected_rows)

    def remove_rows(self, row_indexes: list[int]) -> None:
        """Record row removals requested by the controller."""
        self.removed_rows = list(row_indexes)

    def collect_flashcards_for_save(self) -> tuple[list[FlashcardRowData], set[int]]:
        """Return the preconfigured save payload."""
        return self.collect_result

    def add_flashcard_row(
        self,
        question: str,
        answer: str,
        *,
        question_image_path: str | None = None,
        answer_image_path: str | None = None,
        checked: bool = True,
    ) -> None:
        """Record rows added through the management controller."""
        self.added_rows.append(
            FlashcardRowData(
                question=question,
                answer=answer,
                question_image_path=question_image_path,
                answer_image_path=answer_image_path,
            )
        )

    def selected_flashcard_row(self) -> tuple[int, FlashcardRowData] | None:
        """Return the preconfigured selected row payload."""
        return self.selected_row_payload

    def update_flashcard_row(
        self,
        row_index: int,
        question: str,
        answer: str,
        *,
        question_image_path: str | None = None,
        answer_image_path: str | None = None,
    ) -> None:
        """Record row updates requested by the controller."""
        self.updated_rows.append(
            (
                row_index,
                FlashcardRowData(
                    question=question,
                    answer=answer,
                    question_image_path=question_image_path,
                    answer_image_path=answer_image_path,
                ),
            )
        )


class _FakeEditDialog:
    """Simple accepted dialog used by management-controller tests."""

    def __init__(
        self,
        question: str,
        answer: str,
        question_image_path: str | None,
        answer_image_path: str | None,
        folder_path: Path,
    ) -> None:
        """Initialize the fake dialog with the values it should expose."""
        self._question = question
        self._answer = answer
        self._question_image_path = question_image_path
        self._answer_image_path = answer_image_path

    def exec(self) -> int:
        """Accept the fake dialog."""
        return QDialog.Accepted

    def question_text(self) -> str:
        """Return the edited question text."""
        return self._question

    def answer_text(self) -> str:
        """Return the edited answer text."""
        return self._answer

    def question_image_path(self) -> str | None:
        """Return the edited question image path."""
        return self._question_image_path

    def answer_image_path(self) -> str | None:
        """Return the edited answer image path."""
        return self._answer_image_path


def _flashcard(question: str, answer: str, line_number: int) -> Flashcard:
    """Create a flashcard fixture payload."""
    return Flashcard(
        question=question,
        answer=answer,
        source_file=Path("cards.csv"),
        source_line=line_number,
    )


def test_open_from_selection_falls_back_to_single_checked_folder(
    app: QApplication,
) -> None:
    """Verify the controller opens the only checked folder when none is selected."""
    app_state = StudyApplicationState()
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[_flashcard("Q1?", "A1.", 1)],
                selected_indexes={0},
            )
        ]
    )
    page = _FakeManagementPage()
    checked_item = _FakeSidebarItem("bio", checked=True)
    switch_calls: list[str] = []
    controller = ManagementPageController(
        parent=QWidget(),
        management_page=page,  # type: ignore[arg-type]
        app_state=app_state,
        selected_folder_items_getter=lambda: [],
        sidebar_folder_items_iter=lambda: [checked_item],
        folder_name_resolver=lambda _item: "Biology",
        checked_folder_ids_getter=lambda: {"bio"},
        refresh_management_data=lambda _checked_ids: None,
        switch_to_management=lambda: switch_calls.append("management"),
        switch_to_timer=lambda: switch_calls.append("timer"),
        edit_dialog_factory=lambda question, answer, question_image_path, answer_image_path, folder_path: _FakeEditDialog(
            question,
            answer,
            question_image_path,
            answer_image_path,
            folder_path,
        ),
    )

    controller.open_from_selection()

    assert controller.editing_folder_id == "bio"
    assert page.loaded_folder_call is not None
    assert page.loaded_folder_call[0] == "bio"
    assert page.loaded_folder_call[1] == "Biology"
    assert [card.question for card in page.loaded_folder_call[2]] == ["Q1?"]
    assert page.loaded_folder_call[3] == {0}
    assert switch_calls == ["management"]


def test_save_changes_persists_rows_refreshes_state_and_returns_to_timer(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify save delegates persistence and refreshes checked-folder selection."""
    app_state = StudyApplicationState()
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[_flashcard("Q1?", "A1.", 1), _flashcard("Q2?", "A2.", 2)],
                selected_indexes={0, 1},
            )
        ]
    )
    page = _FakeManagementPage()
    page.collect_result = (
        [FlashcardRowData(question="Edited Q1?", answer="Edited A1.")],
        {0},
    )
    refresh_calls: list[set[str]] = []
    switch_calls: list[str] = []
    replace_calls: list[tuple[Path, list[FlashcardRowData]]] = []
    controller = ManagementPageController(
        parent=QWidget(),
        management_page=page,  # type: ignore[arg-type]
        app_state=app_state,
        selected_folder_items_getter=lambda: [],
        sidebar_folder_items_iter=lambda: [],
        folder_name_resolver=lambda _item: "Biology",
        checked_folder_ids_getter=lambda: {"bio"},
        refresh_management_data=lambda checked_ids: refresh_calls.append(
            set(checked_ids)
        ),
        switch_to_management=lambda: switch_calls.append("management"),
        switch_to_timer=lambda: switch_calls.append("timer"),
        edit_dialog_factory=lambda question, answer, question_image_path, answer_image_path, folder_path: _FakeEditDialog(
            question,
            answer,
            question_image_path,
            answer_image_path,
            folder_path,
        ),
    )
    controller.open_for_folder("bio", "Biology")

    monkeypatch.setattr(
        "estudai.ui.controllers.management_page_controller.replace_flashcards_in_folder",
        lambda folder_path, rows: replace_calls.append((folder_path, list(rows))),
    )

    controller.save_changes()

    assert replace_calls == [
        (
            Path("/tmp/bio"),
            [FlashcardRowData(question="Edited Q1?", answer="Edited A1.")],
        )
    ]
    assert app_state.selected_indexes_for_folder("bio") == {0}
    assert refresh_calls == [{"bio"}]
    assert switch_calls == ["management", "timer"]


def test_delete_selected_flashcards_removes_rows_after_confirmation(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify delete removes selected rows only after user confirmation."""
    page = _FakeManagementPage()
    page.selected_rows = [1, 3]
    controller = ManagementPageController(
        parent=QWidget(),
        management_page=page,  # type: ignore[arg-type]
        app_state=StudyApplicationState(),
        selected_folder_items_getter=lambda: [],
        sidebar_folder_items_iter=lambda: [],
        folder_name_resolver=lambda _item: "Biology",
        checked_folder_ids_getter=lambda: set(),
        refresh_management_data=lambda _checked_ids: None,
        switch_to_management=lambda: None,
        switch_to_timer=lambda: None,
        edit_dialog_factory=lambda question, answer, question_image_path, answer_image_path, folder_path: _FakeEditDialog(
            question,
            answer,
            question_image_path,
            answer_image_path,
            folder_path,
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.message_box.MessageBoxPresenter.confirm_yes_no",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )

    controller.delete_selected_flashcards()

    assert page.removed_rows == [1, 3]


def test_add_flashcard_uses_dialog_result_to_append_row(
    app: QApplication,
) -> None:
    """Verify add opens the editor dialog and appends the accepted row."""
    app_state = StudyApplicationState()
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[],
                selected_indexes=set(),
            )
        ]
    )
    page = _FakeManagementPage()
    controller = ManagementPageController(
        parent=QWidget(),
        management_page=page,  # type: ignore[arg-type]
        app_state=app_state,
        selected_folder_items_getter=lambda: [],
        sidebar_folder_items_iter=lambda: [],
        folder_name_resolver=lambda _item: "Biology",
        checked_folder_ids_getter=lambda: {"bio"},
        refresh_management_data=lambda _checked_ids: None,
        switch_to_management=lambda: None,
        switch_to_timer=lambda: None,
        edit_dialog_factory=lambda _question, _answer, _question_image_path, _answer_image_path, _folder_path: _FakeEditDialog(
            "New Q?",
            "New A.",
            "question.png",
            "answer.png",
            Path("/tmp/bio"),
        ),
    )
    controller.open_for_folder("bio", "Biology")

    controller.add_flashcard()

    assert page.added_rows == [
        FlashcardRowData(
            question="New Q?",
            answer="New A.",
            question_image_path="question.png",
            answer_image_path="answer.png",
        )
    ]


def test_edit_selected_flashcard_uses_dialog_result_to_update_row(
    app: QApplication,
) -> None:
    """Verify edit opens the editor dialog for the selected management row."""
    app_state = StudyApplicationState()
    app_state.replace_folders(
        [
            FolderLibraryState(
                folder_id="bio",
                folder_name="Biology",
                folder_path=Path("/tmp/bio"),
                flashcards=[_flashcard("Q1?", "A1.", 1)],
                selected_indexes={0},
            )
        ]
    )
    page = _FakeManagementPage()
    page.selected_row_payload = (
        0,
        FlashcardRowData(
            question="Q1?",
            answer="A1.",
            question_image_path="old-question.png",
            answer_image_path=None,
        ),
    )
    controller = ManagementPageController(
        parent=QWidget(),
        management_page=page,  # type: ignore[arg-type]
        app_state=app_state,
        selected_folder_items_getter=lambda: [],
        sidebar_folder_items_iter=lambda: [],
        folder_name_resolver=lambda _item: "Biology",
        checked_folder_ids_getter=lambda: {"bio"},
        refresh_management_data=lambda _checked_ids: None,
        switch_to_management=lambda: None,
        switch_to_timer=lambda: None,
        edit_dialog_factory=lambda _question, _answer, _question_image_path, _answer_image_path, _folder_path: _FakeEditDialog(
            "Edited Q1?",
            "Edited A1.",
            "new-question.png",
            "new-answer.png",
            Path("/tmp/bio"),
        ),
    )
    controller.open_for_folder("bio", "Biology")

    controller.edit_selected_flashcard()

    assert page.updated_rows == [
        (
            0,
            FlashcardRowData(
                question="Edited Q1?",
                answer="Edited A1.",
                question_image_path="new-question.png",
                answer_image_path="new-answer.png",
            ),
        )
    ]
