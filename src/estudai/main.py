import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from estudai.ui.main_window import MainWindow


def get_app_icon_path() -> str:
    """Return the best available app icon path.

    Returns:
        str: Absolute path to the bundled SVG icon, or empty string.
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                executable_dir / "data" / "estudai.svg",
                executable_dir / "estudai.svg",
            ]
        )
    candidates.append(Path(__file__).resolve().parents[2] / "data" / "estudai.svg")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return ""


def main():
    """Run the application."""
    app = QApplication(sys.argv)
    icon_path = get_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
