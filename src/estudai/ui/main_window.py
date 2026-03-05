"""Main application window."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
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

from estudai.services.csv_flashcards import Flashcard, load_flashcards_from_folder
from estudai.services.folder_storage import (
    PersistedFolder,
    import_folder,
    list_persisted_folders,
)

from .pages import FoldersPage, SettingsPage
from .timer_page import TimerPage


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    def __init__(self):
        super().__init__()
        self.flashcards_by_folder: dict[str, list[Flashcard]] = {}
        self.loaded_flashcards: list[Flashcard] = []
        self.current_folder_id: str | None = None
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

        add_folder_button = QPushButton("Add Folder")
        add_folder_button.clicked.connect(self.prompt_and_add_folder)
        sidebar_layout.addWidget(add_folder_button)

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
        self.timer_page.set_flashcard_context(self.current_folder_name, 0)
        self._load_persisted_folders()

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
        self.current_folder_id = current_item.data(Qt.UserRole)
        if self.current_folder_id is None:
            self.loaded_flashcards = [
                flashcard
                for flashcards in self.flashcards_by_folder.values()
                for flashcard in flashcards
            ]
        else:
            self.loaded_flashcards = self.flashcards_by_folder.get(
                self.current_folder_id, []
            )
        self.timer_page.set_flashcard_context(
            self.current_folder_name, len(self.loaded_flashcards)
        )
        self.switch_to_timer()

    def handle_sidebar_folder_click(self, clicked_item: QListWidgetItem):
        """Handle explicit folder clicks, even when selection is unchanged.

        Args:
            clicked_item: The clicked folder list item.
        """
        self.select_folder_from_sidebar(clicked_item, None)

    def prompt_and_add_folder(self) -> None:
        """Prompt the user for a folder and load CSV flashcards from it."""
        selected_path = QFileDialog.getExistingDirectory(
            self,
            "Select folder with CSV flashcards",
        )
        if not selected_path:
            return
        self.add_folder(Path(selected_path))

    def add_folder(self, folder_path: Path) -> bool:
        """Copy one selected folder, persist it, and load flashcards.

        Args:
            folder_path: Selected folder path.

        Returns:
            bool: True when the folder was loaded.
        """
        try:
            persisted_folder = import_folder(folder_path)
        except (FileNotFoundError, NotADirectoryError, OSError):
            return False
        return self._load_persisted_folder(persisted_folder)

    def _load_persisted_folders(self) -> None:
        """Load previously persisted folders into memory and sidebar."""
        for persisted_folder in list_persisted_folders():
            self._load_persisted_folder(persisted_folder)

    def _load_persisted_folder(self, persisted_folder: PersistedFolder) -> bool:
        """Load one persisted folder from managed storage.

        Args:
            persisted_folder: Persisted folder metadata entry.

        Returns:
            bool: True when folder data was loaded.
        """
        stored_folder = Path(persisted_folder.stored_path)
        if not stored_folder.exists():
            return False
        self.flashcards_by_folder[persisted_folder.id] = load_flashcards_from_folder(
            stored_folder
        )

        for index in range(self.sidebar_folder_list.count()):
            item = self.sidebar_folder_list.item(index)
            if item.data(Qt.UserRole) == persisted_folder.id:
                item.setText(persisted_folder.name)
                if self.current_folder_id == persisted_folder.id:
                    self.loaded_flashcards = self.flashcards_by_folder[
                        persisted_folder.id
                    ]
                    self.timer_page.set_flashcard_context(
                        self.current_folder_name, len(self.loaded_flashcards)
                    )
                elif self.current_folder_id is None:
                    self.loaded_flashcards = [
                        flashcard
                        for flashcards in self.flashcards_by_folder.values()
                        for flashcard in flashcards
                    ]
                    self.timer_page.set_flashcard_context(
                        self.current_folder_name, len(self.loaded_flashcards)
                    )
                return True

        if self.sidebar_folder_list.count() == 2:
            placeholder_item = self.sidebar_folder_list.item(1)
            if not bool(placeholder_item.flags() & Qt.ItemIsEnabled):
                self.sidebar_folder_list.takeItem(1)

        folder_item = QListWidgetItem(persisted_folder.name)
        folder_item.setData(Qt.UserRole, persisted_folder.id)
        self.sidebar_folder_list.addItem(folder_item)
        if self.current_folder_id is None:
            self.loaded_flashcards = [
                flashcard
                for flashcards in self.flashcards_by_folder.values()
                for flashcard in flashcards
            ]
            self.timer_page.set_flashcard_context(
                self.current_folder_name, len(self.loaded_flashcards)
            )
        return True

    def set_navigation_visible(self, visible: bool):
        """Control navigation visibility for focused timer mode.

        Args:
            visible: Whether navigation controls should be visible.
        """
        self.sidebar_toggle_button.setVisible(visible)
        self.settings_button.setVisible(visible)
        if not visible:
            self.sidebar.setVisible(False)
