"""Reusable UI style-sheet helpers."""

from __future__ import annotations


def build_checkbox_indicator_styles(widget_selectors: tuple[str, ...]) -> str:
    """Build palette-aware checkbox indicator rules for selectors.

    Args:
        widget_selectors: Widget selectors that expose ``::indicator`` in CSS,
            such as ``QListWidget``, ``QTableWidget``, ``QHeaderView``, and
            ``QCheckBox``.

    Returns:
        str: Concatenated style-sheet rules for unchecked/checked/indeterminate
            indicator states.
    """
    style_rules: list[str] = []
    for selector in widget_selectors:
        style_rules.extend(
            [
                f"{selector}::indicator:unchecked {{"
                " border: 1px solid palette(mid);"
                " background: palette(base);"
                "}",
                f"{selector}::indicator:checked {{"
                " border: 1px solid palette(dark);"
                " background: palette(highlight);"
                "}",
                f"{selector}::indicator:indeterminate {{"
                " border: 1px solid palette(dark);"
                " background: palette(midlight);"
                "}",
            ]
        )
    return "".join(style_rules)

