"""Application shell controller tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from estudai.ui.controllers.app_shell_controller import AppShellController


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


class _FullscreenState:
    """Track fullscreen transitions requested by the controller."""

    def __init__(self) -> None:
        """Initialize the fullscreen state."""
        self.active = False
        self.calls: list[str] = []

    def is_fullscreen(self) -> bool:
        """Return whether fullscreen mode is active."""
        return self.active

    def show_normal(self) -> None:
        """Record returning to normal mode."""
        self.calls.append("showNormal")
        self.active = False

    def show_fullscreen(self) -> None:
        """Record entering fullscreen mode."""
        self.calls.append("showFullScreen")
        self.active = True


def _build_controller(
    *,
    window_width: int = 900,
    timer_running: bool = False,
) -> tuple[
    AppShellController,
    QWidget,
    QFrame,
    QPushButton,
    QPushButton,
    QStackedWidget,
    QWidget,
    QWidget,
    QWidget,
    list[str],
    _FullscreenState,
]:
    """Create an app-shell controller with real widgets and spy callbacks."""
    central_widget = QWidget()
    central_widget.resize(window_width, 650)
    sidebar = QFrame(central_widget)
    sidebar.setVisible(False)
    sidebar_toggle_button = QPushButton("", central_widget)
    sidebar_toggle_button.setGeometry(8, 8, 44, 44)
    settings_button = QPushButton("", central_widget)
    settings_button.setGeometry(56, 8, 44, 44)
    stats_button = QPushButton("", central_widget)
    stats_button.setGeometry(104, 8, 44, 44)
    stacked_widget = QStackedWidget(central_widget)
    timer_page = QWidget()
    management_page = QWidget()
    settings_page = QWidget()
    stats_page = QWidget()
    stacked_widget.addWidget(timer_page)
    stacked_widget.addWidget(management_page)
    stacked_widget.addWidget(settings_page)
    stacked_widget.addWidget(stats_page)
    stacked_widget.setCurrentWidget(timer_page)
    preview_calls: list[str] = []
    fullscreen_state = _FullscreenState()
    controller = AppShellController(
        stacked_widget=stacked_widget,
        timer_page=timer_page,
        management_page=management_page,
        settings_page=settings_page,
        stats_page=stats_page,
        sidebar=sidebar,
        sidebar_toggle_button=sidebar_toggle_button,
        settings_button=settings_button,
        stats_button=stats_button,
        central_widget_getter=lambda: central_widget,
        window_width_getter=lambda: window_width,
        timer_running_getter=lambda: timer_running,
        stop_settings_preview=lambda: preview_calls.append("stop"),
        is_fullscreen=fullscreen_state.is_fullscreen,
        show_normal=fullscreen_state.show_normal,
        show_fullscreen=fullscreen_state.show_fullscreen,
    )
    return (
        controller,
        central_widget,
        sidebar,
        sidebar_toggle_button,
        settings_button,
        stacked_widget,
        timer_page,
        management_page,
        settings_page,
        preview_calls,
        fullscreen_state,
    )


def test_switch_to_settings_toggles_back_to_timer(app: QApplication) -> None:
    """Verify the settings switcher toggles back to timer when repeated."""
    (
        controller,
        _central_widget,
        _sidebar,
        _toggle_button,
        _settings_button,
        stacked_widget,
        timer_page,
        _management_page,
        settings_page,
        preview_calls,
        _fullscreen_state,
    ) = _build_controller()

    controller.switch_to_settings()
    controller.switch_to_settings()

    assert stacked_widget.currentWidget() is timer_page
    assert settings_page in [stacked_widget.widget(index) for index in range(3)]
    assert preview_calls == ["stop"]


def test_switch_to_management_hides_sidebar_and_stops_preview(
    app: QApplication,
) -> None:
    """Verify switching to management closes the sidebar overlay."""
    (
        controller,
        _central_widget,
        sidebar,
        _toggle_button,
        _settings_button,
        stacked_widget,
        _timer_page,
        management_page,
        _settings_page,
        preview_calls,
        _fullscreen_state,
    ) = _build_controller()
    sidebar.setVisible(True)

    controller.switch_to_management()

    assert stacked_widget.currentWidget() is management_page
    assert sidebar.isVisible() is False
    assert preview_calls == ["stop"]


def test_toggle_sidebar_positions_on_open_and_hides_on_second_toggle(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify opening the sidebar positions it before showing the overlay."""
    (
        controller,
        _central_widget,
        sidebar,
        _toggle_button,
        _settings_button,
        _stacked_widget,
        _timer_page,
        _management_page,
        _settings_page,
        _preview_calls,
        _fullscreen_state,
    ) = _build_controller()
    position_calls: list[str] = []
    monkeypatch.setattr(
        controller,
        "position_sidebar",
        lambda: position_calls.append("position"),
    )

    controller.toggle_sidebar()
    controller.toggle_sidebar()

    assert position_calls == ["position"]
    assert sidebar.isVisible() is False


def test_handle_global_click_closes_sidebar_only_when_outside(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify outside clicks close the sidebar while inside clicks keep it open."""
    (
        controller,
        _central_widget,
        sidebar,
        toggle_button,
        _settings_button,
        _stacked_widget,
        _timer_page,
        _management_page,
        _settings_page,
        _preview_calls,
        _fullscreen_state,
    ) = _build_controller()
    sidebar.setVisible(True)
    monkeypatch.setattr(
        controller,
        "widget_contains_global_position",
        lambda widget, _global_position: widget is sidebar,
    )

    controller.handle_global_click(QPoint(0, 0))
    assert sidebar.isHidden() is False

    monkeypatch.setattr(
        controller,
        "widget_contains_global_position",
        lambda widget, _global_position: widget is toggle_button,
    )
    controller.handle_global_click(QPoint(0, 0))
    assert sidebar.isHidden() is False

    monkeypatch.setattr(
        controller,
        "widget_contains_global_position",
        lambda _widget, _global_position: False,
    )
    controller.handle_global_click(QPoint(0, 0))
    assert sidebar.isHidden() is True


def test_set_navigation_visible_hides_shell_controls(app: QApplication) -> None:
    """Verify focused mode hides both shell buttons and the sidebar."""
    (
        controller,
        _central_widget,
        sidebar,
        sidebar_toggle_button,
        settings_button,
        _stacked_widget,
        _timer_page,
        _management_page,
        _settings_page,
        _preview_calls,
        _fullscreen_state,
    ) = _build_controller()
    sidebar.setVisible(True)

    controller.set_navigation_visible(False)

    assert sidebar_toggle_button.isVisible() is False
    assert settings_button.isVisible() is False
    assert sidebar.isVisible() is False


def test_update_sidebar_width_caps_large_windows_and_repositions(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify large windows keep the sidebar width capped at the design maximum."""
    (
        controller,
        _central_widget,
        sidebar,
        _toggle_button,
        _settings_button,
        _stacked_widget,
        _timer_page,
        _management_page,
        _settings_page,
        _preview_calls,
        _fullscreen_state,
    ) = _build_controller(window_width=3000)
    position_calls: list[str] = []
    monkeypatch.setattr(
        controller,
        "position_sidebar",
        lambda: position_calls.append("position"),
    )

    controller.update_sidebar_width()

    assert sidebar.width() == 300
    assert position_calls == ["position"]


def test_set_sidebar_width_preserves_user_override_on_window_updates(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify manual sidebar width overrides survive later width refreshes."""
    (
        controller,
        _central_widget,
        sidebar,
        _toggle_button,
        _settings_button,
        _stacked_widget,
        _timer_page,
        _management_page,
        _settings_page,
        _preview_calls,
        _fullscreen_state,
    ) = _build_controller(window_width=3000)
    position_calls: list[str] = []
    monkeypatch.setattr(
        controller,
        "position_sidebar",
        lambda: position_calls.append("position"),
    )

    controller.set_sidebar_width(420)
    controller.update_sidebar_width()

    assert sidebar.width() == 420
    assert position_calls == ["position", "position"]


def test_fullscreen_helpers_toggle_and_exit_deterministically(
    app: QApplication,
) -> None:
    """Verify fullscreen helpers mirror the expected window mode transitions."""
    (
        controller,
        _central_widget,
        _sidebar,
        _toggle_button,
        _settings_button,
        _stacked_widget,
        _timer_page,
        _management_page,
        _settings_page,
        _preview_calls,
        fullscreen_state,
    ) = _build_controller()

    controller.toggle_fullscreen()
    controller.toggle_fullscreen()
    controller.exit_fullscreen()

    assert fullscreen_state.calls == ["showFullScreen", "showNormal"]
    assert fullscreen_state.active is False
