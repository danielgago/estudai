"""Application shell and sidebar visibility controller."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QFrame, QPushButton, QStackedWidget, QWidget

CentralWidgetGetter = Callable[[], QWidget | None]
WindowWidthGetter = Callable[[], int]
TimerRunningGetter = Callable[[], bool]
StopSettingsPreview = Callable[[], None]
IsFullscreenGetter = Callable[[], bool]
WindowModeCallback = Callable[[], None]


class AppShellController:
    """Coordinate page switching and shell-level sidebar behavior."""

    _MINIMUM_SIDEBAR_WIDTH = 220
    _RESPONSIVE_MAXIMUM_SIDEBAR_WIDTH = 300
    _MANUAL_MAXIMUM_SIDEBAR_WIDTH = 520

    def __init__(
        self,
        *,
        stacked_widget: QStackedWidget,
        timer_page: QWidget,
        management_page: QWidget,
        settings_page: QWidget,
        stats_page: QWidget,
        sidebar: QFrame,
        sidebar_toggle_button: QPushButton,
        settings_button: QPushButton,
        stats_button: QPushButton,
        central_widget_getter: CentralWidgetGetter,
        window_width_getter: WindowWidthGetter,
        timer_running_getter: TimerRunningGetter,
        stop_settings_preview: StopSettingsPreview,
        is_fullscreen: IsFullscreenGetter,
        show_normal: WindowModeCallback,
        show_fullscreen: WindowModeCallback,
    ) -> None:
        """Initialize the controller.

        Args:
            stacked_widget: Central page stack for the main window.
            timer_page: Timer page widget.
            management_page: Flashcard management page widget.
            settings_page: Settings page widget.
            stats_page: Stats overview page widget.
            sidebar: Sidebar overlay widget.
            sidebar_toggle_button: Button that toggles sidebar visibility.
            settings_button: Button that opens the settings page.
            stats_button: Button that opens the stats page.
            central_widget_getter: Returns the central widget used to anchor the
                sidebar overlay.
            window_width_getter: Returns the current window width.
            timer_running_getter: Returns whether the timer page is currently
                running a study timer.
            stop_settings_preview: Stops any active preview sound in settings.
            is_fullscreen: Returns whether the host window is fullscreen.
            show_normal: Restores the host window to normal mode.
            show_fullscreen: Switches the host window into fullscreen mode.
        """
        self._stacked_widget = stacked_widget
        self._timer_page = timer_page
        self._management_page = management_page
        self._settings_page = settings_page
        self._stats_page = stats_page
        self._sidebar = sidebar
        self._sidebar_toggle_button = sidebar_toggle_button
        self._settings_button = settings_button
        self._stats_button = stats_button
        self._central_widget_getter = central_widget_getter
        self._window_width_getter = window_width_getter
        self._timer_running_getter = timer_running_getter
        self._stop_settings_preview = stop_settings_preview
        self._is_fullscreen = is_fullscreen
        self._show_normal = show_normal
        self._show_fullscreen = show_fullscreen
        self._sidebar_width_override: int | None = None

    def update_sidebar_width(self) -> None:
        """Apply either the responsive width or the current user override."""
        preferred_width = (
            self._responsive_sidebar_width()
            if self._sidebar_width_override is None
            else self._sidebar_width_override
        )
        self._apply_sidebar_width(preferred_width)

    def set_sidebar_width(self, width: int) -> None:
        """Persist a user-selected sidebar width and apply it immediately."""
        self._sidebar_width_override = max(self._MINIMUM_SIDEBAR_WIDTH, width)
        self._apply_sidebar_width(self._sidebar_width_override)

    def position_sidebar(self) -> None:
        """Place the sidebar as an overlay below the toggle button."""
        central_widget = self._central_widget_getter()
        if central_widget is None:
            return
        anchor_point = self._sidebar_anchor_point(central_widget)
        bottom_margin = 12
        available_height = max(
            120,
            central_widget.height() - anchor_point.y() - bottom_margin,
        )
        self._sidebar.setFixedHeight(available_height)
        self._sidebar.move(anchor_point.x(), anchor_point.y())
        self._sidebar.raise_()

    def switch_to_timer(self) -> None:
        """Switch to the timer page and restore navigation when allowed."""
        self._stop_settings_preview()
        self._stacked_widget.setCurrentWidget(self._timer_page)
        if not self._timer_running_getter():
            self._sidebar_toggle_button.setVisible(True)

    def switch_to_management(self) -> None:
        """Switch to the management page and close the sidebar overlay."""
        self._stop_settings_preview()
        self._stacked_widget.setCurrentWidget(self._management_page)
        self._sidebar.setVisible(False)

    def switch_to_settings(self) -> None:
        """Switch to settings or back to timer when already on settings."""
        if self._stacked_widget.currentWidget() is self._settings_page:
            self.switch_to_timer()
            return
        self._stacked_widget.setCurrentWidget(self._settings_page)

    def switch_to_stats(self) -> None:
        """Switch to stats or back to timer when already on stats."""
        if self._stacked_widget.currentWidget() is self._stats_page:
            self.switch_to_timer()
            return
        self._stop_settings_preview()
        self._stacked_widget.setCurrentWidget(self._stats_page)

    def toggle_sidebar(self) -> None:
        """Show or hide the sidebar overlay."""
        if self._sidebar.isHidden():
            self.position_sidebar()
            self._sidebar.setVisible(True)
            return
        self._sidebar.setVisible(False)

    def set_navigation_visible(self, visible: bool) -> None:
        """Show or hide the shell navigation controls."""
        self._sidebar_toggle_button.setVisible(visible)
        self._settings_button.setVisible(visible)
        self._stats_button.setVisible(visible)
        if not visible:
            self._sidebar.setVisible(False)

    def toggle_fullscreen(self) -> None:
        """Toggle between fullscreen and normal modes."""
        if self._is_fullscreen():
            self._show_normal()
            return
        self._show_fullscreen()

    def exit_fullscreen(self) -> None:
        """Leave fullscreen mode when currently active."""
        if self._is_fullscreen():
            self._show_normal()

    def _apply_sidebar_width(self, width: int) -> None:
        """Clamp and apply one sidebar width, then reposition the overlay."""
        self._sidebar.setFixedWidth(self._clamped_sidebar_width(width))
        self.position_sidebar()

    def _responsive_sidebar_width(self) -> int:
        """Return the default responsive width for the current window size."""
        return max(
            self._MINIMUM_SIDEBAR_WIDTH,
            min(
                self._RESPONSIVE_MAXIMUM_SIDEBAR_WIDTH,
                int(self._window_width_getter() * 0.18),
            ),
        )

    def _clamped_sidebar_width(self, width: int) -> int:
        """Clamp one sidebar width to the available overlay space."""
        return max(
            self._MINIMUM_SIDEBAR_WIDTH,
            min(self._maximum_sidebar_width(), width),
        )

    def _maximum_sidebar_width(self) -> int:
        """Return the maximum sidebar width allowed in the current window."""
        central_widget = self._central_widget_getter()
        if central_widget is None:
            return self._MANUAL_MAXIMUM_SIDEBAR_WIDTH
        anchor_point = self._sidebar_anchor_point(central_widget)
        available_width = max(
            self._MINIMUM_SIDEBAR_WIDTH,
            central_widget.width() - anchor_point.x() - 12,
        )
        return min(self._MANUAL_MAXIMUM_SIDEBAR_WIDTH, available_width)

    def _sidebar_anchor_point(self, central_widget: QWidget) -> QPoint:
        """Return the sidebar overlay anchor point within the central widget."""
        return self._sidebar_toggle_button.mapTo(
            central_widget,
            QPoint(0, self._sidebar_toggle_button.height() + 8),
        )

    def widget_contains_global_position(
        self,
        widget: QWidget,
        global_position: QPoint,
    ) -> bool:
        """Return whether a global click position lands inside a widget."""
        if widget.isHidden():
            return False
        return widget.rect().contains(widget.mapFromGlobal(global_position))

    def handle_global_click(self, global_position: QPoint) -> None:
        """Hide the sidebar when a click lands outside shell controls."""
        if self._sidebar.isHidden():
            return
        if self.widget_contains_global_position(self._sidebar, global_position):
            return
        if self.widget_contains_global_position(
            self._sidebar_toggle_button,
            global_position,
        ):
            return
        self._sidebar.setVisible(False)
