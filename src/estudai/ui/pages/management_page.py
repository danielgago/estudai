"""Folders and flashcards management page."""

from __future__ import annotations

from collections.abc import Iterator

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from estudai.services.csv_flashcards import Flashcard, normalize_flashcard_fields
from estudai.ui.utils import (
    NativeCheckboxDelegate,
    NativeCheckboxHeaderView,
    centered_checkbox_rect,
    create_checkable_table_item,
    format_card_count,
    set_muted_label_color,
)


class ManagementPage(QWidget):
    """Page to edit flashcards inside one selected folder."""

    delete_requested = Signal()

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
        title_font = QFont(self.title_label.font())
        title_font.setPointSize(24)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        self.folder_context_label = QLabel("0 cards")
        set_muted_label_color(self.folder_context_label)
        layout.addWidget(self.folder_context_label)

        table_actions_layout = QHBoxLayout()
        table_actions_layout.addStretch()
        self.add_flashcard_button = QPushButton("+")
        self.add_flashcard_button.setFixedSize(34, 34)
        self.add_flashcard_button.setToolTip("Add")
        self.add_flashcard_button.setStyleSheet("font-size: 22px; font-weight: 700;")
        table_actions_layout.addWidget(self.add_flashcard_button)
        layout.addLayout(table_actions_layout)

        self.flashcards_table = QTableWidget(0, 3)
        self.flashcards_table.setHorizontalHeaderLabels(["", "Question", "Answer"])
        self.select_all_header = NativeCheckboxHeaderView(
            Qt.Horizontal,
            self.flashcards_table,
        )
        self.flashcards_table.setHorizontalHeader(self.select_all_header)
        self.flashcards_table.setItemDelegateForColumn(
            0,
            NativeCheckboxDelegate(
                self.flashcards_table,
                checkbox_rect_resolver=centered_checkbox_rect,
            ),
        )
        self.flashcards_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.flashcards_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.flashcards_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.flashcards_table.customContextMenuRequested.connect(
            self.open_flashcards_table_menu
        )
        self.select_all_header.toggle_requested.connect(self._toggle_header_selection)
        self.flashcards_table.itemChanged.connect(self.handle_table_item_changed)
        self.flashcards_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        self.flashcards_table.verticalHeader().setVisible(False)
        self.flashcards_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self.flashcards_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.Stretch,
        )
        layout.addWidget(self.flashcards_table)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save and Return to Timer")
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.save_button)
        layout.addLayout(footer_layout)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Refresh palette-driven colors when theme/palette changes."""
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            set_muted_label_color(self.folder_context_label)
        super().changeEvent(event)

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
        self.folder_context_label.setText(format_card_count(len(flashcards)))
        self.flashcards_table.blockSignals(True)
        self.flashcards_table.setRowCount(0)

        for index, flashcard in enumerate(flashcards):
            self._insert_row(
                row_index=index,
                question=flashcard.question,
                answer=flashcard.answer,
                checked=index in selected_indexes,
            )
        self.flashcards_table.blockSignals(False)
        self._sync_select_all_header()

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
        checkbox_item = create_checkable_table_item(checked=checked)
        self.flashcards_table.setItem(row_index, 0, checkbox_item)
        self.flashcards_table.setItem(row_index, 1, QTableWidgetItem(question))
        self.flashcards_table.setItem(row_index, 2, QTableWidgetItem(answer))

    def add_empty_flashcard_row(self) -> None:
        """Append an empty editable flashcard row and select it."""
        row_index = self.flashcards_table.rowCount()
        self._insert_row(row_index, "", "", True)
        self.flashcards_table.setCurrentCell(row_index, 1)
        self.flashcards_table.editItem(self.flashcards_table.item(row_index, 1))
        self._sync_select_all_header()

    def open_flashcards_table_menu(self, position: QPoint) -> None:
        """Open right-click table menu for selected flashcard rows.

        Args:
            position: Requested context-menu position.
        """
        clicked_item = self.flashcards_table.itemAt(position)
        if clicked_item is not None and not clicked_item.isSelected():
            self.flashcards_table.clearSelection()
            clicked_item.setSelected(True)
        if not self.selected_table_rows():
            return

        menu = QMenu(self)
        delete_action = menu.addAction("Delete")
        chosen_action = menu.exec(
            self.flashcards_table.viewport().mapToGlobal(position)
        )
        if chosen_action is delete_action:
            self.delete_requested.emit()

    def handle_table_header_click(self, section: int) -> None:
        """Toggle all row checkboxes when first header section is clicked.

        Args:
            section: Header section index.
        """
        if section != 0:
            return
        self._set_all_flashcards_checked(not self._are_all_flashcards_checked())

    def handle_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Refresh first-column header indicator when row checkbox changes.

        Args:
            item: Updated table item.
        """
        if item.column() == 0:
            self._sync_select_all_header()

    def _are_all_flashcards_checked(self) -> bool:
        """Return whether all flashcard rows are currently checked."""
        checkbox_items = list(self._iter_selection_items())
        if not checkbox_items:
            return False
        return all(item.checkState() == Qt.Checked for item in checkbox_items)

    def _sync_select_all_header(self) -> None:
        """Update first-column header indicator to match row checkbox state."""
        self.select_all_header.set_checked(self._are_all_flashcards_checked())

    def _toggle_header_selection(self) -> None:
        """Toggle row selection state from header checkbox interaction."""
        self._set_all_flashcards_checked(not self._are_all_flashcards_checked())

    def is_header_checkbox_checked(self) -> bool:
        """Expose header checkbox state for tests and callers."""
        return self.select_all_header.is_checked()

    def _set_all_flashcards_checked(self, checked: bool) -> None:
        """Set checkbox state for all flashcard rows.

        Args:
            checked: Target state for all rows.
        """
        self.flashcards_table.blockSignals(True)
        target_state = Qt.Checked if checked else Qt.Unchecked
        for checkbox_item in self._iter_selection_items():
            checkbox_item.setCheckState(target_state)
        self.flashcards_table.blockSignals(False)
        self._sync_select_all_header()

    def _iter_selection_items(self) -> Iterator[QTableWidgetItem]:
        """Yield first-column checkbox items for all current rows."""
        for row_index in range(self.flashcards_table.rowCount()):
            checkbox_item = self.flashcards_table.item(row_index, 0)
            if checkbox_item is not None:
                yield checkbox_item

    def select_all_flashcards(self) -> None:
        """Mark all flashcards as selected for timer usage."""
        self._set_all_flashcards_checked(True)

    def unselect_all_flashcards(self) -> None:
        """Mark all flashcards as not selected for timer usage."""
        self._set_all_flashcards_checked(False)

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
        self._sync_select_all_header()

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
            question = "" if question_item is None else question_item.text()
            answer = "" if answer_item is None else answer_item.text()
            try:
                normalized_question, normalized_answer = normalize_flashcard_fields(
                    question,
                    answer,
                )
            except ValueError as error:
                msg = f"Row {row_index + 1}: {error}"
                raise ValueError(msg)
            rows.append((normalized_question, normalized_answer))
            if selection_item is not None and selection_item.checkState() == Qt.Checked:
                selected_indexes.add(row_index)
        return rows, selected_indexes
