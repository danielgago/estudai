"""Reusable UI style-sheet helpers."""

from __future__ import annotations


def build_checkbox_indicator_styles(widget_selectors: tuple[str, ...]) -> str:
    """Return checkbox indicator styles.

    Args:
        widget_selectors: Widget selectors that expose ``::indicator`` in CSS,
            such as ``QListWidget``, ``QTableWidget``, ``QHeaderView``, and
            ``QCheckBox``.

    Returns:
        str: Empty style-sheet snippet so checkboxes render with native style.
    """
    _ = widget_selectors
    return ""
