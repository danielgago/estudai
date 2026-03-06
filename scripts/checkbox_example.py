"""Minimal PySide6 checkbox demo with native rendering."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def create_checkable_table_item(checked: bool = False) -> QTableWidgetItem:
    """Create a centered checkbox-only table item.

    Args:
        checked: Initial checkbox state.

    Returns:
        QTableWidgetItem: A checkable item with empty text and centered alignment.
    """
    item = QTableWidgetItem()
    item.setData(Qt.DisplayRole, "")
    item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    item.setTextAlignment(Qt.AlignCenter)
    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    return item


class CheckboxExample(QWidget):
    """Window showing table and standalone checkbox-list patterns."""

    def __init__(self) -> None:
        """Build demo UI."""
        super().__init__()
        self.setWindowTitle("Checkbox Patterns")
        layout = QHBoxLayout(self)
        layout.addWidget(self._build_table(), 2)
        layout.addWidget(self._build_checkbox_list(), 1)

    def _build_table(self) -> QTableWidget:
        """Build a table with a dedicated checkbox column."""
        table = QTableWidget(3, 2, self)
        table.setHorizontalHeaderLabels(["", "Task"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 34)
        table.verticalHeader().setVisible(False)

        rows = [
            ("Review cards", True),
            ("Practice math", False),
            ("Read chapter", True),
        ]
        for row_index, (label, checked) in enumerate(rows):
            table.setItem(row_index, 0, create_checkable_table_item(checked=checked))
            table.setItem(row_index, 1, QTableWidgetItem(label))
        return table

    def _build_checkbox_list(self) -> QWidget:
        """Build a vertical list with real QCheckBox widgets."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel("Tags"))
        for text in ("Biology", "Physics", "History"):
            layout.addWidget(QCheckBox(text))
        layout.addStretch()
        return container


def main() -> int:
    """Run the checkbox demo app."""
    app = QApplication(sys.argv)
    window = CheckboxExample()
    window.resize(720, 360)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
