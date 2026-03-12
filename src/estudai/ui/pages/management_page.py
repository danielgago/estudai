"""Folders and flashcards management page."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QItemSelectionModel, Qt, Signal
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

from estudai.services.csv_flashcards import (
    Flashcard,
    FlashcardRowData,
    flashcard_question_sort_key,
    normalize_flashcard_fields,
)
from estudai.ui.utils import (
    NativeCheckboxDelegate,
    NativeCheckboxHeaderView,
    centered_checkbox_rect,
    create_checkable_table_item,
    format_card_count,
    set_muted_label_color,
)

_QUESTION_IMAGE_ROLE = int(Qt.UserRole) + 1
_ANSWER_IMAGE_ROLE = int(Qt.UserRole) + 2


@dataclass(frozen=True)
class FlashcardTableRowState:
    """Editable flashcard row state including selection and checked status."""

    question: str
    answer: str
    question_image_path: str | None
    answer_image_path: str | None
    checked: bool
    selected: bool


class ManagementPage(QWidget):
    """Page to edit flashcards inside one selected folder."""

    edit_requested = Signal()
    delete_requested = Signal()
    reset_progress_requested = Signal()

    def __init__(self) -> None:
        """Initialize the management page."""
        super().__init__()
        self.folder_id: str | None = None
        self._loaded_table_row_states: list[FlashcardTableRowState] = []
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
        self.move_up_button = QPushButton("Move Up")
        self.move_up_button.clicked.connect(self.move_selected_rows_up)
        table_actions_layout.addWidget(self.move_up_button)
        self.move_down_button = QPushButton("Move Down")
        self.move_down_button.clicked.connect(self.move_selected_rows_down)
        table_actions_layout.addWidget(self.move_down_button)
        self.sort_flashcards_button = QPushButton("Sort by Question A-Z")
        self.sort_flashcards_button.clicked.connect(self.sort_flashcards_by_question)
        table_actions_layout.addWidget(self.sort_flashcards_button)
        self.edit_flashcard_button = QPushButton("Edit")
        self.edit_flashcard_button.setEnabled(False)
        self.edit_flashcard_button.clicked.connect(self.edit_requested.emit)
        table_actions_layout.addWidget(self.edit_flashcard_button)
        self.reset_progress_button = QPushButton("Reset Progress")
        self.reset_progress_button.setToolTip("Reset folder progress")
        self.reset_progress_button.clicked.connect(self.reset_progress_requested.emit)
        table_actions_layout.addWidget(self.reset_progress_button)
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
        self.flashcards_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.flashcards_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.flashcards_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.flashcards_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.flashcards_table.customContextMenuRequested.connect(
            self.open_flashcards_table_menu
        )
        self.flashcards_table.itemDoubleClicked.connect(
            lambda _item: self.edit_requested.emit()
        )
        self.flashcards_table.itemSelectionChanged.connect(
            self._update_row_action_buttons
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
                question_image_path=flashcard.question_image_path,
                answer_image_path=flashcard.answer_image_path,
                checked=index in selected_indexes,
            )
        self.flashcards_table.blockSignals(False)
        self._sync_select_all_header()
        self._update_row_action_buttons()
        self._loaded_table_row_states = self._collect_table_row_states(
            include_selection=False
        )

    def _insert_row(
        self,
        row_index: int,
        question: str,
        answer: str,
        question_image_path: str | None,
        answer_image_path: str | None,
        checked: bool,
    ) -> None:
        """Insert one editable row into the table.

        Args:
            row_index: Target row index.
            question: Question text.
            answer: Answer text.
            question_image_path: Optional question-side image path.
            answer_image_path: Optional answer-side image path.
            checked: Whether this row is selected for timer usage.
        """
        self.flashcards_table.insertRow(row_index)
        checkbox_item = create_checkable_table_item(checked=checked)
        self.flashcards_table.setItem(row_index, 0, checkbox_item)
        question_item = QTableWidgetItem(question)
        answer_item = QTableWidgetItem(answer)
        question_item.setFlags(question_item.flags() & ~Qt.ItemIsEditable)
        answer_item.setFlags(answer_item.flags() & ~Qt.ItemIsEditable)
        question_item.setData(_QUESTION_IMAGE_ROLE, question_image_path)
        answer_item.setData(_ANSWER_IMAGE_ROLE, answer_image_path)
        self._apply_row_image_tooltips(
            question_item,
            answer_item,
            question_image_path=question_image_path,
            answer_image_path=answer_image_path,
        )
        self.flashcards_table.setItem(row_index, 1, question_item)
        self.flashcards_table.setItem(row_index, 2, answer_item)

    def _apply_row_image_tooltips(
        self,
        question_item: QTableWidgetItem,
        answer_item: QTableWidgetItem,
        *,
        question_image_path: str | None,
        answer_image_path: str | None,
    ) -> None:
        """Expose whether each side currently has an attached image."""
        question_item.setToolTip(
            "Question image attached."
            if question_image_path is not None
            else "No question image attached."
        )
        answer_item.setToolTip(
            "Answer image attached."
            if answer_image_path is not None
            else "No answer image attached."
        )

    def add_flashcard_row(
        self,
        question: str,
        answer: str,
        *,
        question_image_path: str | None = None,
        answer_image_path: str | None = None,
        checked: bool = True,
    ) -> None:
        """Append one editable flashcard row and select it."""
        row_index = self.flashcards_table.rowCount()
        self._insert_row(
            row_index,
            question,
            answer,
            question_image_path,
            answer_image_path,
            checked,
        )
        self.flashcards_table.setCurrentCell(row_index, 1)
        self._sync_select_all_header()
        self._update_row_action_buttons()

    def update_flashcard_row(
        self,
        row_index: int,
        question: str,
        answer: str,
        *,
        question_image_path: str | None = None,
        answer_image_path: str | None = None,
    ) -> None:
        """Replace the editable payload for one table row."""
        if not (0 <= row_index < self.flashcards_table.rowCount()):
            msg = f"Flashcard row out of range: {row_index}"
            raise IndexError(msg)
        question_item = self.flashcards_table.item(row_index, 1)
        answer_item = self.flashcards_table.item(row_index, 2)
        if question_item is None or answer_item is None:
            msg = f"Flashcard row is incomplete: {row_index}"
            raise ValueError(msg)
        question_item.setText(question)
        answer_item.setText(answer)
        question_item.setData(_QUESTION_IMAGE_ROLE, question_image_path)
        answer_item.setData(_ANSWER_IMAGE_ROLE, answer_image_path)
        self._apply_row_image_tooltips(
            question_item,
            answer_item,
            question_image_path=question_image_path,
            answer_image_path=answer_image_path,
        )

    def selected_flashcard_row(self) -> tuple[int, FlashcardRowData] | None:
        """Return the selected row payload when exactly one row is selected."""
        selected_rows = self.selected_table_rows()
        if len(selected_rows) != 1:
            return None
        row_index = selected_rows[0]
        return row_index, self.flashcard_row_data(row_index)

    def flashcard_row_data(self, row_index: int) -> FlashcardRowData:
        """Return one table row as editable flashcard data."""
        question_item = self.flashcards_table.item(row_index, 1)
        answer_item = self.flashcards_table.item(row_index, 2)
        question = "" if question_item is None else question_item.text()
        answer = "" if answer_item is None else answer_item.text()
        return FlashcardRowData(
            question=question,
            answer=answer,
            question_image_path=(
                None
                if question_item is None
                else question_item.data(_QUESTION_IMAGE_ROLE)
            ),
            answer_image_path=(
                None if answer_item is None else answer_item.data(_ANSWER_IMAGE_ROLE)
            ),
        )

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
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")
        edit_action.setEnabled(len(self.selected_table_rows()) == 1)
        chosen_action = menu.exec(
            self.flashcards_table.viewport().mapToGlobal(position)
        )
        if chosen_action is edit_action:
            self.edit_requested.emit()
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
        self._update_row_action_buttons()

    def move_selected_rows_up(self) -> None:
        """Move the current selected flashcard rows one step upward."""
        rows = self._collect_table_row_states()
        moved = False
        for row_index in range(1, len(rows)):
            if rows[row_index].selected and not rows[row_index - 1].selected:
                rows[row_index - 1], rows[row_index] = (
                    rows[row_index],
                    rows[row_index - 1],
                )
                moved = True
        if moved:
            self._set_table_row_states(rows)

    def move_selected_rows_down(self) -> None:
        """Move the current selected flashcard rows one step downward."""
        rows = self._collect_table_row_states()
        moved = False
        for row_index in range(len(rows) - 2, -1, -1):
            if rows[row_index].selected and not rows[row_index + 1].selected:
                rows[row_index], rows[row_index + 1] = (
                    rows[row_index + 1],
                    rows[row_index],
                )
                moved = True
        if moved:
            self._set_table_row_states(rows)

    def sort_flashcards_by_question(self) -> None:
        """Sort all flashcards alphabetically by normalized question text."""
        rows = self._collect_table_row_states()
        sorted_rows = sorted(
            rows,
            key=lambda row: flashcard_question_sort_key(row.question, row.answer),
        )
        if sorted_rows != rows:
            self._set_table_row_states(sorted_rows)

    def _collect_table_row_states(
        self,
        *,
        include_selection: bool = True,
    ) -> list[FlashcardTableRowState]:
        """Return current table rows including persisted and optional UI state.

        Args:
            include_selection: Whether transient table-row selection should be
                included in the collected state.
        """
        selected_rows = set(self.selected_table_rows()) if include_selection else set()
        rows: list[FlashcardTableRowState] = []
        for row_index in range(self.flashcards_table.rowCount()):
            question_item = self.flashcards_table.item(row_index, 1)
            answer_item = self.flashcards_table.item(row_index, 2)
            selection_item = self.flashcards_table.item(row_index, 0)
            rows.append(
                FlashcardTableRowState(
                    question="" if question_item is None else question_item.text(),
                    answer="" if answer_item is None else answer_item.text(),
                    question_image_path=(
                        None
                        if question_item is None
                        else question_item.data(_QUESTION_IMAGE_ROLE)
                    ),
                    answer_image_path=(
                        None
                        if answer_item is None
                        else answer_item.data(_ANSWER_IMAGE_ROLE)
                    ),
                    checked=(
                        selection_item is not None
                        and selection_item.checkState() == Qt.Checked
                    ),
                    selected=row_index in selected_rows,
                )
            )
        return rows

    def _set_table_row_states(self, rows: list[FlashcardTableRowState]) -> None:
        """Replace the table content while preserving row selection state."""
        self.flashcards_table.blockSignals(True)
        self.flashcards_table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self._insert_row(
                row_index,
                row.question,
                row.answer,
                row.question_image_path,
                row.answer_image_path,
                checked=row.checked,
            )
        selection_model = self.flashcards_table.selectionModel()
        if selection_model is not None:
            selection_model.clearSelection()
            model = self.flashcards_table.model()
            for row_index, row in enumerate(rows):
                if not row.selected:
                    continue
                selection_model.select(
                    model.index(row_index, 0),
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )
        self.flashcards_table.blockSignals(False)
        self._sync_select_all_header()
        self._update_row_action_buttons()

    def is_dirty(self) -> bool:
        """Return whether persisted flashcard data differs from the loaded state."""
        return self._loaded_table_row_states != self._collect_table_row_states(
            include_selection=False
        )

    def _update_row_action_buttons(self) -> None:
        """Enable reorder actions only when the current selection can move."""
        row_count = self.flashcards_table.rowCount()
        selected_rows = self.selected_table_rows()
        has_selection = bool(selected_rows)
        self.move_up_button.setEnabled(has_selection and min(selected_rows) > 0)
        self.move_down_button.setEnabled(
            has_selection and max(selected_rows) < row_count - 1
        )
        self.edit_flashcard_button.setEnabled(len(selected_rows) == 1)
        self.sort_flashcards_button.setEnabled(row_count > 1)

    def collect_flashcards_for_save(
        self,
    ) -> tuple[list[FlashcardRowData], set[int]]:
        """Collect and validate table content before save.

        Returns:
            tuple[list[FlashcardRowData], set[int]]: Rows and selected row indexes.

        Raises:
            ValueError: If any row has an empty question or answer.
        """
        rows: list[FlashcardRowData] = []
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
                    question_image_path=(
                        None
                        if question_item is None
                        else question_item.data(_QUESTION_IMAGE_ROLE)
                    ),
                    answer_image_path=(
                        None
                        if answer_item is None
                        else answer_item.data(_ANSWER_IMAGE_ROLE)
                    ),
                )
            except ValueError as error:
                msg = f"Row {row_index + 1}: {error}"
                raise ValueError(msg)
            rows.append(
                FlashcardRowData(
                    question=normalized_question,
                    answer=normalized_answer,
                    question_image_path=(
                        None
                        if question_item is None
                        else question_item.data(_QUESTION_IMAGE_ROLE)
                    ),
                    answer_image_path=(
                        None
                        if answer_item is None
                        else answer_item.data(_ANSWER_IMAGE_ROLE)
                    ),
                )
            )
            if selection_item is not None and selection_item.checkState() == Qt.Checked:
                selected_indexes.add(row_index)
        return rows, selected_indexes
