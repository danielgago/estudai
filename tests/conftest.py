"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture(scope="session")
def qapplication():
    """Create a QApplication instance for the test session.

    This prevents "QApplication has already been created" errors
    when running multiple GUI tests.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def main_window(qapplication):
    """Provide a MainWindow instance for tests."""
    from estudai.ui.main_window import MainWindow

    window = MainWindow()
    yield window
    window.close()
