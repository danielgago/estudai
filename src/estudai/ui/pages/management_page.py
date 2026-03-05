"""Folders and flashcards management page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from estudai.services.csv_flashcards import Flashcard


class ManagementPage(QWidget):
    """Page to edit flashcards inside one selected folder."""

    def __init__(self) -> None:
        """Initialize the management page."""
        super().__init__()
        self.folder_id: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the management UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        self.title_label = QLabel("No folder selected")
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(self.title_label)

        self.folder_context_label = QLabel("Folder: No folder selected")
        self.folder_context_label.setStyleSheet("color: #666;")
        layout.addWidget(self.folder_context_label)

        self.instructions_label = QLabel(
            "Double-click a folder in the sidebar to edit cards. "
            "Use the checkbox column to select cards used by the timer."
        )
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setStyleSheet("color: #666;")
        layout.addWidget(self.instructions_label)

        self.flashcards_table = QTableWidget(0, 3)
        self.flashcards_table.setHorizontalHeaderLabels(["Use", "Question", "Answer"])
        self.flashcards_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.flashcards_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.flashcards_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        self.flashcards_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self.flashcards_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.Stretch,
        )
        layout.addWidget(self.flashcards_table)

        actions_layout = QHBoxLayout()
        self.add_flashcard_button = QPushButton("Add Flashcard")
        self.delete_flashcard_button = QPushButton("Delete Selected Flashcards")
        actions_layout.addWidget(self.add_flashcard_button)
        actions_layout.addWidget(self.delete_flashcard_button)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save and Return to Timer")
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.save_button)
        layout.addLayout(footer_layout)

    def set_folder_flashcards(
        self,
        folder_id: str,
        folder_name: str,
        flashcards: list[Flashcard],
        selected_indexes: set[int],
    ) -> None:
        """Load one folder's flashcards into the editable table.

        Args:
            folder_id: Folder identifier.
            folder_name: Folder display name.
            flashcards: Flashcards currently in this folder.
            selected_indexes: Zero-based indexes selected for timer usage.
        """
        self.folder_id = folder_id
        self.title_label.setText(folder_name)
        self.folder_context_label.setText(f"Folder: {folder_name}")
        self.flashcards_table.setRowCount(0)

        for index, flashcard in enumerate(flashcards):
            self._insert_row(
                row_index=index,
                question=flashcard.question,
                answer=flashcard.answer,
                checked=index in selected_indexes,
            )

    def _insert_row(
        self,
        row_index: int,
        question: str,
        answer: str,
        checked: bool,
    ) -> None:
        """Insert one editable row into the table.

        Args:
            row_index: Target row index.
            question: Question text.
            answer: Answer text.
            checked: Whether this row is selected for timer usage.
        """
        self.flashcards_table.insertRow(row_index)
        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(
            Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        )
        checkbox_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.flashcards_table.setItem(row_index, 0, checkbox_item)
        self.flashcards_table.setItem(row_index, 1, QTableWidgetItem(question))
        self.flashcards_table.setItem(row_index, 2, QTableWidgetItem(answer))

    def add_empty_flashcard_row(self) -> None:
        """Append an empty editable flashcard row and select it."""
        row_index = self.flashcards_table.rowCount()
        self._insert_row(row_index, "", "", True)
        self.flashcards_table.setCurrentCell(row_index, 1)
        self.flashcards_table.editItem(self.flashcards_table.item(row_index, 1))

    def selected_table_rows(self) -> list[int]:
        """Return currently selected table row indexes.

        Returns:
            list[int]: Sorted row indexes.
        """
        selected_rows = self.flashcards_table.selectionModel().selectedRows()
        return sorted(index.row() for index in selected_rows)

    def remove_rows(self, row_indexes: list[int]) -> None:
        """Remove multiple rows from the table.

        Args:
            row_indexes: Zero-based indexes to remove.
        """
        for row_index in sorted(set(row_indexes), reverse=True):
            self.flashcards_table.removeRow(row_index)

    def collect_flashcards_for_save(self) -> tuple[list[tuple[str, str]], set[int]]:
        """Collect and validate table content before save.

        Returns:
            tuple[list[tuple[str, str]], set[int]]: Rows and selected row indexes.

        Raises:
            ValueError: If any row has an empty question or answer.
        """
        rows: list[tuple[str, str]] = []
        selected_indexes: set[int] = set()
        for row_index in range(self.flashcards_table.rowCount()):
            question_item = self.flashcards_table.item(row_index, 1)
            answer_item = self.flashcards_table.item(row_index, 2)
            selection_item = self.flashcards_table.item(row_index, 0)
            question = "" if question_item is None else question_item.text().strip()
            answer = "" if answer_item is None else answer_item.text().strip()
            if not question or not answer:
                msg = f"Row {row_index + 1}: Question and Answer cannot be empty."
                raise ValueError(msg)
            rows.append((question, answer))
            if selection_item is not None and selection_item.checkState() == Qt.Checked:
                selected_indexes.add(row_index)
        return rows, selected_indexes
