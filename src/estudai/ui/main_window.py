"""Main application window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .pages import FoldersPage, SettingsPage
from .timer_page import TimerPage


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Estudai!")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.sidebar = QFrame()
        self.sidebar.setFrameShape(QFrame.StyledPanel)
        self.sidebar.setFixedWidth(180)
        self.sidebar.setVisible(False)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel("Folders")
        sidebar_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        sidebar_layout.addWidget(sidebar_title)

        self.sidebar_folder_list = QListWidget()
        self.sidebar_folder_list.setSpacing(4)
        self.sidebar_folder_list.addItem("All folders")
        empty_item = QListWidgetItem("No saved folders yet.")
        empty_item.setFlags(Qt.NoItemFlags)
        self.sidebar_folder_list.addItem(empty_item)
        self.sidebar_folder_list.setCurrentRow(0)
        self.sidebar_folder_list.currentItemChanged.connect(
            self.select_folder_from_sidebar
        )
        self.sidebar_folder_list.itemClicked.connect(self.handle_sidebar_folder_click)
        sidebar_layout.addWidget(self.sidebar_folder_list)

        manage_folders_button = QPushButton("Manage Folders")
        manage_folders_button.clicked.connect(self.switch_to_folders)
        sidebar_layout.addWidget(manage_folders_button)

        sidebar_layout.addStretch()

        root_layout.addWidget(self.sidebar)

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        header_layout = QHBoxLayout()
        self.sidebar_toggle_button = QPushButton("☰")
        self.sidebar_toggle_button.setFixedWidth(36)
        self.sidebar_toggle_button.setToolTip("Show or hide folders sidebar.")
        self.sidebar_toggle_button.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.sidebar_toggle_button, alignment=Qt.AlignLeft)
        header_layout.addStretch()

        self.settings_button = QPushButton("⚙")
        self.settings_button.setFixedWidth(36)
        self.settings_button.setToolTip("Open settings.")
        self.settings_button.clicked.connect(self.switch_to_settings)
        header_layout.addWidget(self.settings_button, alignment=Qt.AlignRight)
        content_layout.addLayout(header_layout)

        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        root_layout.addWidget(content_container)

        self.timer_page = TimerPage()
        self.folders_page = FoldersPage()
        self.settings_page = SettingsPage()

        self.stacked_widget.addWidget(self.timer_page)
        self.stacked_widget.addWidget(self.folders_page)
        self.stacked_widget.addWidget(self.settings_page)

        self.stacked_widget.setCurrentWidget(self.timer_page)
        self.current_folder_name = "All folders"

    def switch_to_timer(self):
        """Switch to timer page."""
        self.stacked_widget.setCurrentWidget(self.timer_page)

    def switch_to_folders(self):
        """Switch to folders page."""
        self.stacked_widget.setCurrentWidget(self.folders_page)

    def switch_to_settings(self):
        """Switch to settings page or back to timer when already there."""
        if self.stacked_widget.currentWidget() is self.settings_page:
            self.switch_to_timer()
            return
        self.stacked_widget.setCurrentWidget(self.settings_page)

    def toggle_sidebar(self):
        """Show or hide the left sidebar."""
        self.sidebar.setHidden(not self.sidebar.isHidden())

    def select_folder_from_sidebar(
        self, current_item: QListWidgetItem | None, _: QListWidgetItem | None
    ):
        """Handle folder selection from the sidebar list.

        Args:
            current_item: The newly selected folder list item.
            _: The previously selected folder list item.
        """
        if current_item is None or not bool(current_item.flags() & Qt.ItemIsEnabled):
            return
        self.current_folder_name = current_item.text()
        self.switch_to_timer()

    def handle_sidebar_folder_click(self, clicked_item: QListWidgetItem):
        """Handle explicit folder clicks, even when selection is unchanged.

        Args:
            clicked_item: The clicked folder list item.
        """
        self.select_folder_from_sidebar(clicked_item, None)

    def set_navigation_visible(self, visible: bool):
        """Control navigation visibility for focused timer mode.

        Args:
            visible: Whether navigation controls should be visible.
        """
        self.sidebar_toggle_button.setVisible(visible)
        self.settings_button.setVisible(visible)
        if not visible:
            self.sidebar.setVisible(False)
