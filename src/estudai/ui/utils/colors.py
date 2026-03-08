"""Color and palette helpers shared across UI widgets."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel


def blend_colors(base: QColor, overlay: QColor, overlay_ratio: float) -> QColor:
    """Return a deterministic blend between base and overlay colors."""
    clamped_ratio = max(0.0, min(1.0, overlay_ratio))
    base_ratio = 1.0 - clamped_ratio
    return QColor(
        int((base.red() * base_ratio) + (overlay.red() * clamped_ratio)),
        int((base.green() * base_ratio) + (overlay.green() * clamped_ratio)),
        int((base.blue() * base_ratio) + (overlay.blue() * clamped_ratio)),
    )


def set_muted_label_color(label: QLabel, overlay_ratio: float = 0.35) -> None:
    """Apply a readable secondary-text color derived from the active palette."""
    palette = label.palette()
    muted_color = blend_colors(
        palette.color(QPalette.WindowText),
        palette.color(QPalette.Window),
        overlay_ratio=overlay_ratio,
    )
    palette.setColor(QPalette.WindowText, muted_color)
    label.setPalette(palette)
