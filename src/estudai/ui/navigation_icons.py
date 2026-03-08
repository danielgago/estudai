"""Helpers for generating navigation icons with Qt fallbacks."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

__all__ = [
    "build_menu_navigation_icon",
    "build_settings_navigation_icon",
    "load_navigation_icon",
]


def load_navigation_icon(
    theme_names: tuple[str, ...],
    fallback: QIcon,
) -> QIcon:
    """Return a themed icon when available, otherwise the provided fallback."""
    for theme_name in theme_names:
        theme_icon = QIcon.fromTheme(theme_name)
        if not theme_icon.isNull():
            return theme_icon
    return fallback


def build_menu_navigation_icon(icon_size: QSize, color: QColor) -> QIcon:
    """Build a deterministic hamburger icon used when no theme icon exists."""
    icon_extent = max(16, min(icon_size.width(), icon_size.height()))
    pixmap = QPixmap(icon_extent, icon_extent)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color)
    pen.setCapStyle(Qt.RoundCap)
    pen.setWidthF(max(1.6, icon_extent * 0.11))
    painter.setPen(pen)

    margin = icon_extent * 0.22
    for y_ratio in (0.30, 0.50, 0.70):
        y_pos = icon_extent * y_ratio
        painter.drawLine(QPointF(margin, y_pos), QPointF(icon_extent - margin, y_pos))
    painter.end()
    return QIcon(pixmap)


def build_settings_navigation_icon(icon_size: QSize, color: QColor) -> QIcon:
    """Build a deterministic cog icon used when no theme icon exists."""
    icon_extent = max(16, min(icon_size.width(), icon_size.height()))
    pixmap = QPixmap(icon_extent, icon_extent)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color)
    pen.setCapStyle(Qt.RoundCap)
    pen.setWidthF(max(1.4, icon_extent * 0.10))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    center = QPointF(icon_extent / 2.0, icon_extent / 2.0)
    outer_radius = icon_extent * 0.34
    inner_radius = icon_extent * 0.14
    tooth_inner = outer_radius * 0.73

    for angle_degrees in range(0, 360, 45):
        angle_radians = math.radians(angle_degrees)
        cos_angle = math.cos(angle_radians)
        sin_angle = math.sin(angle_radians)
        start_point = QPointF(
            center.x() + (tooth_inner * cos_angle),
            center.y() + (tooth_inner * sin_angle),
        )
        end_point = QPointF(
            center.x() + (outer_radius * cos_angle),
            center.y() + (outer_radius * sin_angle),
        )
        painter.drawLine(start_point, end_point)

    painter.drawEllipse(center, outer_radius * 0.62, outer_radius * 0.62)
    painter.drawEllipse(center, inner_radius, inner_radius)
    painter.end()
    return QIcon(pixmap)
