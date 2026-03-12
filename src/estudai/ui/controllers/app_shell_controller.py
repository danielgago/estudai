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

    def __init__(
        self,
        *,
        stacked_widget: QStackedWidget,
        timer_page: QWidget,
        management_page: QWidget,
        settings_page: QWidget,
        sidebar: QFrame,
        sidebar_toggle_button: QPushButton,
        settings_button: QPushButton,
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
            sidebar: Sidebar overlay widget.
            sidebar_toggle_button: Button that toggles sidebar visibility.
            settings_button: Button that opens the settings page.
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
        self._sidebar = sidebar
        self._sidebar_toggle_button = sidebar_toggle_button
        self._settings_button = settings_button
        self._central_widget_getter = central_widget_getter
        self._window_width_getter = window_width_getter
        self._timer_running_getter = timer_running_getter
        self._stop_settings_preview = stop_settings_preview
        self._is_fullscreen = is_fullscreen
        self._show_normal = show_normal
        self._show_fullscreen = show_fullscreen

    def update_sidebar_width(self) -> None:
        """Keep the sidebar width responsive within a readable range."""
        responsive_width = max(220, min(300, int(self._window_width_getter() * 0.18)))
        self._sidebar.setFixedWidth(responsive_width)
        self.position_sidebar()

    def position_sidebar(self) -> None:
        """Place the sidebar as an overlay below the toggle button."""
        central_widget = self._central_widget_getter()
        if central_widget is None:
            return
        anchor_point = self._sidebar_toggle_button.mapTo(
            central_widget,
            QPoint(0, self._sidebar_toggle_button.height() + 8),
        )
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
