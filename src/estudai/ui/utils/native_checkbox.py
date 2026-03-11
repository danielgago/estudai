"""Native checkbox painting helpers for Qt item views."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QStyle,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QWidget,
)

CheckboxRectResolver = Callable[[QStyleOptionViewItem, QRect], QRect]


def centered_checkbox_rect(
    option: QStyleOptionViewItem,
    indicator_rect: QRect,
) -> QRect:
    """Return a checkbox indicator rect centered inside the cell."""
    resolved_rect = QRect(indicator_rect)
    resolved_rect.moveCenter(option.rect.center())
    return resolved_rect


def left_aligned_checkbox_rect(
    option: QStyleOptionViewItem,
    indicator_rect: QRect,
    *,
    indicator_margin: int,
) -> QRect:
    """Return a checkbox indicator rect aligned to the left edge."""
    y_position = option.rect.y() + (
        (option.rect.height() - indicator_rect.height()) // 2
    )
    return QRect(
        option.rect.x() + indicator_margin,
        y_position,
        indicator_rect.width(),
        indicator_rect.height(),
    )


class NativeCheckboxDelegate(QStyledItemDelegate):
    """Paint and toggle native checkbox indicators inside item views."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        checkbox_rect_resolver: CheckboxRectResolver = centered_checkbox_rect,
        draw_item_text: bool = False,
        indicator_margin: int = 0,
        text_spacing: int = 0,
    ) -> None:
        """Initialize the delegate."""
        super().__init__(parent)
        self._checkbox_rect_resolver = checkbox_rect_resolver
        self._draw_item_text = draw_item_text
        self._indicator_margin = indicator_margin
        self._text_spacing = text_spacing

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        """Paint list/table items with a native checkbox indicator."""
        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            super().paint(painter, option, index)
            return

        style = self._style_for_option(option)
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        item_text = item_option.text
        item_option.text = ""
        item_option.features &= ~QStyleOptionViewItem.HasCheckIndicator
        style.drawControl(QStyle.CE_ItemViewItem, item_option, painter, option.widget)

        checkbox_rect = self._checkbox_rect(option)
        checkbox_option = self._checkbox_option(item_option, checkbox_rect, check_state)
        style.drawPrimitive(
            QStyle.PE_IndicatorCheckBox,
            checkbox_option,
            painter,
            option.widget,
        )

        if not self._draw_item_text:
            return
        text_rect = option.rect.adjusted(
            checkbox_rect.width() + (self._indicator_margin * 2) + self._text_spacing,
            0,
            -self._indicator_margin,
            0,
        )
        style.drawItemText(
            painter,
            text_rect,
            Qt.AlignVCenter | Qt.AlignLeft,
            item_option.palette,
            bool(item_option.state & QStyle.State_Enabled),
            item_text,
            QPalette.Text,
        )

    def editorEvent(self, event, model, option: QStyleOptionViewItem, index) -> bool:
        """Toggle checkbox state only when the indicator itself is clicked."""
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

        clicked_checkbox = self._checkbox_rect(option).contains(
            event.position().toPoint()
        )
        if event.type() == QEvent.MouseButtonPress:
            return clicked_checkbox
        if event.type() == QEvent.MouseButtonDblClick:
            return clicked_checkbox
        if not clicked_checkbox:
            return False

        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            return False
        target_state = Qt.Unchecked
        if Qt.CheckState(check_state) != Qt.Checked:
            target_state = Qt.Checked
        return model.setData(index, target_state, Qt.CheckStateRole)

    def _checkbox_rect(self, option: QStyleOptionViewItem) -> QRect:
        """Return the checkbox indicator rect for the provided item option."""
        indicator_rect = self._indicator_rect(option)
        return self._checkbox_rect_resolver(option, indicator_rect)

    def _indicator_rect(self, option: QStyleOptionViewItem) -> QRect:
        """Return the style-provided checkbox indicator geometry."""
        checkbox_option = QStyleOptionButton()
        return self._style_for_option(option).subElementRect(
            QStyle.SE_CheckBoxIndicator,
            checkbox_option,
            option.widget,
        )

    def _checkbox_option(
        self,
        item_option: QStyleOptionViewItem,
        checkbox_rect: QRect,
        check_state: Qt.CheckState,
    ) -> QStyleOptionButton:
        """Build the style option used to paint the checkbox indicator."""
        checkbox_option = QStyleOptionButton()
        checkbox_option.state = QStyle.State_Enabled
        if item_option.state & QStyle.State_MouseOver:
            checkbox_option.state |= QStyle.State_MouseOver
        if Qt.CheckState(check_state) == Qt.Checked:
            checkbox_option.state |= QStyle.State_On
        else:
            checkbox_option.state |= QStyle.State_Off
        checkbox_option.rect = checkbox_rect
        return checkbox_option

    @staticmethod
    def _style_for_option(option: QStyleOptionViewItem) -> QStyle:
        """Return the active style for the provided item option."""
        if option.widget is not None:
            return option.widget.style()
        return QApplication.style()


class NativeCheckboxHeaderView(QHeaderView):
    """Header view that paints a native checkbox in one section."""

    toggle_requested = Signal()

    def __init__(
        self,
        orientation: Qt.Orientation,
        parent: QWidget,
        *,
        checkbox_section: int = 0,
    ) -> None:
        """Initialize the custom header view."""
        super().__init__(orientation, parent)
        self._checked = False
        self._checkbox_section = checkbox_section

    def set_checked(self, checked: bool) -> None:
        """Update the painted checkbox state."""
        if self._checked == checked:
            return
        self._checked = checked
        self.viewport().update()

    def is_checked(self) -> bool:
        """Return current checkbox state."""
        return self._checked

    def paintSection(
        self, painter: QPainter, rect: QRect, logical_index: int
    ) -> None:  # noqa: N802
        """Paint the target section with a centered native checkbox."""
        super().paintSection(painter, rect, logical_index)
        if logical_index != self._checkbox_section:
            return

        option = QStyleOptionButton()
        option.initFrom(self)
        option.rect = self._checkbox_rect(rect)
        option.state = QStyle.State_Enabled
        if self._checked:
            option.state |= QStyle.State_On
        else:
            option.state |= QStyle.State_Off

        painter.save()
        self.style().drawPrimitive(QStyle.PE_IndicatorCheckBox, option, painter, self)
        painter.restore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Emit toggle request only when the checkbox indicator is clicked."""
        event_position = event.position().toPoint()
        logical_index = self.logicalIndexAt(event_position)
        if (
            event.button() == Qt.LeftButton
            and logical_index == self._checkbox_section
            and self._checkbox_rect(self._section_rect(logical_index)).contains(
                event_position
            )
        ):
            self.toggle_requested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _checkbox_rect(self, section_rect: QRect) -> QRect:
        """Return the checkbox rect centered inside the header section."""
        option = QStyleOptionButton()
        option.initFrom(self)
        checkbox_rect = self.style().subElementRect(
            QStyle.SE_CheckBoxIndicator,
            option,
            self,
        )
        checkbox_rect.moveCenter(section_rect.center())
        return checkbox_rect

    def _section_rect(self, logical_index: int) -> QRect:
        """Return the viewport rect for a header section."""
        return QRect(
            self.sectionViewportPosition(logical_index),
            0,
            self.sectionSize(logical_index),
            self.height(),
        )
