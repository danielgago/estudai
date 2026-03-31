"""Helpers for generating navigation icons with Qt fallbacks."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

__all__ = [
    "build_menu_navigation_icon",
    "build_settings_navigation_icon",
    "build_stats_navigation_icon",
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


def build_stats_navigation_icon(icon_size: QSize, color: QColor) -> QIcon:
    """Build a deterministic bar-chart icon used when no theme icon exists."""
    icon_extent = max(16, min(icon_size.width(), icon_size.height()))
    pixmap = QPixmap(icon_extent, icon_extent)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)

    margin = icon_extent * 0.20
    usable_width = icon_extent - 2 * margin
    bottom_y = icon_extent * 0.82
    bar_count = 3
    gap_ratio = 0.25
    total_gaps = gap_ratio * (bar_count - 1)
    bar_width = usable_width / (bar_count + total_gaps)
    gap_width = bar_width * gap_ratio

    bar_heights = [0.30, 0.55, 0.80]
    for i, height_ratio in enumerate(bar_heights):
        x = margin + i * (bar_width + gap_width)
        bar_height = usable_width * height_ratio
        y = bottom_y - bar_height
        painter.drawRoundedRect(
            QRectF(x, y, bar_width, bar_height),
            bar_width * 0.15,
            bar_width * 0.15,
        )
    painter.end()
    return QIcon(pixmap)
