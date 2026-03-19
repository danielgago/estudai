"""Resizable sidebar overlay widgets."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QWidget


class SidebarResizeHandle(QFrame):
    """Thin drag handle used to resize the sidebar overlay horizontally."""

    drag_started = Signal(int)
    drag_moved = Signal(int)
    drag_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the resize handle."""
        super().__init__(parent)
        self.setCursor(Qt.SizeHorCursor)
        self.setToolTip("Resize sidebar")
        self.setMouseTracking(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Start a horizontal resize drag when the left button is pressed."""
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.drag_started.emit(int(event.globalPosition().x()))
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Report the current global drag position while resizing."""
        if not bool(event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        self.drag_moved.emit(int(event.globalPosition().x()))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finish a horizontal resize drag when the left button is released."""
        if event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self.drag_moved.emit(int(event.globalPosition().x()))
        self.drag_finished.emit()
        event.accept()


class SidebarOverlayFrame(QFrame):
    """Sidebar overlay with a dedicated drag handle for width changes."""

    width_resize_requested = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        resize_handle_width: int = 10,
    ) -> None:
        """Initialize the resizable overlay frame.

        Args:
            parent: Optional parent widget.
            resize_handle_width: Width of the draggable resize affordance.
        """
        super().__init__(parent)
        self.setObjectName("sidebarOverlay")
        self._resize_handle_width = resize_handle_width
        self._resize_start_global_x: int | None = None
        self._resize_start_width: int | None = None
        self.resize_handle = SidebarResizeHandle(self)
        self.resize_handle.setObjectName("sidebarResizeHandle")
        self.resize_handle.drag_started.connect(self._begin_resize)
        self.resize_handle.drag_moved.connect(self._update_resize)
        self.resize_handle.drag_finished.connect(self._finish_resize)
        self._position_resize_handle()

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Keep the resize handle anchored to the overlay's right edge."""
        super().resizeEvent(event)
        self._position_resize_handle()

    def _begin_resize(self, global_x: int) -> None:
        """Remember the starting position for one sidebar resize drag."""
        self._resize_start_global_x = global_x
        self._resize_start_width = self.width()

    def _update_resize(self, global_x: int) -> None:
        """Emit an updated sidebar width during an active drag."""
        if self._resize_start_global_x is None or self._resize_start_width is None:
            return
        self.width_resize_requested.emit(
            self._resize_start_width + (global_x - self._resize_start_global_x)
        )

    def _finish_resize(self) -> None:
        """Clear the active resize drag state."""
        self._resize_start_global_x = None
        self._resize_start_width = None

    def _position_resize_handle(self) -> None:
        """Pin the resize handle to the sidebar's right edge."""
        self.resize_handle.setGeometry(
            self.width() - self._resize_handle_width,
            0,
            self._resize_handle_width,
            self.height(),
        )
        self.resize_handle.raise_()
