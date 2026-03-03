"""Tests for the main application."""


def test_app_initialization(qapplication):
    """Test that the application can be initialized."""
    assert qapplication is not None


def test_imports():
    """Test that all modules can be imported."""
    from estudai.ui.main_window import MainWindow
    from estudai.ui.timer_page import TimerPage

    assert MainWindow is not None
    assert TimerPage is not None
