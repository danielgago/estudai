"""Management-page controller tests."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from estudai.services.csv_flashcards import Flashcard
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
        self.collect_result: tuple[list[tuple[str, str]], set[int]] = ([], set())

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

    def collect_flashcards_for_save(self) -> tuple[list[tuple[str, str]], set[int]]:
        """Return the preconfigured save payload."""
        return self.collect_result


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
    page.collect_result = ([("Edited Q1?", "Edited A1.")], {0})
    refresh_calls: list[set[str]] = []
    switch_calls: list[str] = []
    replace_calls: list[tuple[Path, list[tuple[str, str]]]] = []
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
    )
    controller.open_for_folder("bio", "Biology")

    monkeypatch.setattr(
        "estudai.ui.controllers.management_page_controller.replace_flashcards_in_folder",
        lambda folder_path, rows: replace_calls.append((folder_path, list(rows))),
    )

    controller.save_changes()

    assert replace_calls == [(Path("/tmp/bio"), [("Edited Q1?", "Edited A1.")])]
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
    )
    monkeypatch.setattr(
        "estudai.ui.controllers.management_page_controller.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )

    controller.delete_selected_flashcards()

    assert page.removed_rows == [1, 3]
