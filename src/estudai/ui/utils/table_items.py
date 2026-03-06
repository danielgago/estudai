"""Table item utility helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem


def create_checkable_table_item(checked: bool = False) -> QTableWidgetItem:
    """Create a checkbox-only table item with consistent defaults.

    Args:
        checked: Initial checked state.

    Returns:
        QTableWidgetItem: A centered, user-checkable table item with no text.
    """
    table_item = QTableWidgetItem()
    table_item.setData(Qt.DisplayRole, "")
    table_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    table_item.setTextAlignment(Qt.AlignCenter)
    table_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    return table_item
