"""Folders and flashcards management page."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from estudai.services.csv_flashcards import Flashcard
from estudai.ui.utils import build_checkbox_indicator_styles


class SelectAllHeaderView(QHeaderView):
    """Header view that paints a native checkbox in the first column."""

    toggle_requested = Signal()

    def __init__(self, orientation: Qt.Orientation, parent: QWidget) -> None:
        """Initialize the custom header view.

        Args:
            orientation: Header orientation.
            parent: Parent widget.
        """
        super().__init__(orientation, parent)
        self._checked = False

    def set_checked(self, checked: bool) -> None:
        """Update the painted checkbox state.

        Args:
            checked: Checkbox state.
        """
        if self._checked == checked:
            return
        self._checked = checked
        self.viewport().update()

    def is_checked(self) -> bool:
        """Return current checkbox state."""
        return self._checked

    def paintSection(
        self, painter: QPainter, rect, logical_index: int
    ) -> None:  # noqa: N802
        """Paint the first section with a native checkbox indicator."""
        if logical_index != 0:
            super().paintSection(painter, rect, logical_index)
            return

        super().paintSection(painter, rect, logical_index)
        style = self.style()
        option = QStyleOptionButton()
        option.initFrom(self)
        checkbox_rect = style.subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        checkbox_rect.moveCenter(rect.center())

        option.rect = checkbox_rect
        option.state = QStyle.State_Enabled
        if self._checked:
            option.state |= QStyle.State_On
        else:
            option.state |= QStyle.State_Off

        painter.save()
        style.drawPrimitive(QStyle.PE_IndicatorCheckBox, option, painter, self)
        painter.restore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Emit toggle request when clicking inside first header section."""
        if event.button() == Qt.LeftButton and self.logicalIndexAt(event.pos()) == 0:
            self.toggle_requested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CenteredCheckboxDelegate(QStyledItemDelegate):
    """Delegate that paints checkboxes centered inside their table cell."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        """Paint first-column checkboxes centered to match header indicator."""
        if index.column() != 0:
            super().paint(painter, option, index)
            return

        style = (
            option.widget.style() if option.widget is not None else QApplication.style()
        )
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        item_option.text = ""
        style.drawControl(QStyle.CE_ItemViewItem, item_option, painter, option.widget)

        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            return
        checkbox_option = QStyleOptionButton()
        checkbox_option.state = QStyle.State_Enabled
        if Qt.CheckState(check_state) == Qt.Checked:
            checkbox_option.state |= QStyle.State_On
        else:
            checkbox_option.state |= QStyle.State_Off
        checkbox_option.rect = self._checkbox_rect(option)
        style.drawPrimitive(
            QStyle.PE_IndicatorCheckBox,
            checkbox_option,
            painter,
            option.widget,
        )

    def editorEvent(self, event, model, option: QStyleOptionViewItem, index) -> bool:
        """Toggle first-column checkboxes only when centered indicator is clicked."""
        if index.column() != 0:
            return super().editorEvent(event, model, option, index)

        flags = model.flags(index)
        if not (flags & Qt.ItemIsUserCheckable and flags & Qt.ItemIsEnabled):
            return False

        if event.type() not in (
            QEvent.MouseButtonRelease,
            QEvent.MouseButtonPress,
            QEvent.MouseButtonDblClick,
        ):
            return super().editorEvent(event, model, option, index)
        if not isinstance(event, QMouseEvent) or event.button() != Qt.LeftButton:
            return False

        if event.type() == QEvent.MouseButtonPress:
            return True
        if not self._checkbox_rect(option).contains(event.position().toPoint()):
            return False

        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            return False
        target_state = Qt.Unchecked
        if Qt.CheckState(check_state) != Qt.Checked:
            target_state = Qt.Checked
        return model.setData(index, target_state, Qt.CheckStateRole)

    def _checkbox_rect(self, option: QStyleOptionViewItem):
        """Return centered checkbox indicator rect for the given item option."""
        style = (
            option.widget.style() if option.widget is not None else QApplication.style()
        )
        checkbox_option = QStyleOptionButton()
        indicator_rect = style.subElementRect(
            QStyle.SE_CheckBoxIndicator,
            checkbox_option,
            option.widget,
        )
        indicator_rect.moveCenter(option.rect.center())
        return indicator_rect


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
        self._set_muted_label_color(self.folder_context_label)
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
        self.flashcards_table.setStyleSheet(
            build_checkbox_indicator_styles(("QTableWidget", "QHeaderView"))
        )
        self.select_all_header = SelectAllHeaderView(
            Qt.Horizontal,
            self.flashcards_table,
        )
        self.flashcards_table.setHorizontalHeader(self.select_all_header)
        self.flashcards_table.setItemDelegateForColumn(
            0,
            CenteredCheckboxDelegate(self.flashcards_table),
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
            self._set_muted_label_color(self.folder_context_label)
        super().changeEvent(event)

    def _set_muted_label_color(self, label: QLabel) -> None:
        """Apply a readable secondary-text color derived from the active palette."""
        palette = label.palette()
        muted_color = self._blend_colors(
            palette.color(QPalette.WindowText),
            palette.color(QPalette.Window),
            overlay_ratio=0.35,
        )
        palette.setColor(QPalette.WindowText, muted_color)
        label.setPalette(palette)

    @staticmethod
    def _blend_colors(base: QColor, overlay: QColor, overlay_ratio: float) -> QColor:
        """Return a deterministic blend between base and overlay colors."""
        clamped_ratio = max(0.0, min(1.0, overlay_ratio))
        base_ratio = 1.0 - clamped_ratio
        return QColor(
            int((base.red() * base_ratio) + (overlay.red() * clamped_ratio)),
            int((base.green() * base_ratio) + (overlay.green() * clamped_ratio)),
            int((base.blue() * base_ratio) + (overlay.blue() * clamped_ratio)),
        )

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
        card_word = "card" if len(flashcards) == 1 else "cards"
        self.folder_context_label.setText(f"{len(flashcards)} {card_word}")
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
        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(
            Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        )
        checkbox_item.setTextAlignment(Qt.AlignCenter)
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
        row_count = self.flashcards_table.rowCount()
        if row_count == 0:
            return False
        for row_index in range(row_count):
            checkbox_item = self.flashcards_table.item(row_index, 0)
            if checkbox_item is None or checkbox_item.checkState() != Qt.Checked:
                return False
        return True

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
        for row_index in range(self.flashcards_table.rowCount()):
            checkbox_item = self.flashcards_table.item(row_index, 0)
            if checkbox_item is not None:
                checkbox_item.setCheckState(target_state)
        self.flashcards_table.blockSignals(False)
        self._sync_select_all_header()

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
            question = "" if question_item is None else question_item.text().strip()
            answer = "" if answer_item is None else answer_item.text().strip()
            if not question or not answer:
                msg = f"Row {row_index + 1}: Question and Answer cannot be empty."
                raise ValueError(msg)
            rows.append((question, answer))
            if selection_item is not None and selection_item.checkState() == Qt.Checked:
                selected_indexes.add(row_index)
        return rows, selected_indexes
