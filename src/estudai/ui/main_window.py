"""Main application window."""

from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from estudai.services.csv_flashcards import Flashcard, load_flashcards_from_folder
from estudai.services.folder_storage import (
    delete_persisted_folder,
    import_folder,
    list_persisted_folders,
    rename_persisted_folder,
)

from .pages import SettingsPage, TimerPage


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    def __init__(self):
        super().__init__()
        self.flashcards_by_folder: dict[str, list[Flashcard]] = {}
        self.loaded_flashcards: list[Flashcard] = []
        self.selected_folder_ids: set[str] = set()
        self.current_folder_id: str | None = None
        self.current_folder_name = "No folders selected"
        self.setWindowTitle("Estudai!")
        self.setGeometry(100, 100, 900, 650)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.sidebar = QFrame()
        self.sidebar.setFrameShape(QFrame.StyledPanel)
        self.sidebar.setVisible(False)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel("Folders")
        sidebar_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        sidebar_layout.addWidget(sidebar_title)

        self.sidebar_folder_list = QListWidget()
        self.sidebar_folder_list.setSpacing(4)
        self.sidebar_folder_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.sidebar_folder_list.itemChanged.connect(
            self.handle_folder_check_state_changed
        )
        self.sidebar_folder_list.itemClicked.connect(self.handle_sidebar_folder_click)
        self.sidebar_folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sidebar_folder_list.customContextMenuRequested.connect(
            self.open_sidebar_folder_menu
        )
        sidebar_layout.addWidget(self.sidebar_folder_list)

        add_folder_button = QPushButton("Add Folder")
        add_folder_button.clicked.connect(self.prompt_and_add_folder)
        sidebar_layout.addWidget(add_folder_button)
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
        self.settings_page = SettingsPage()
        self.stacked_widget.addWidget(self.timer_page)
        self.stacked_widget.addWidget(self.settings_page)

        self.stacked_widget.setCurrentWidget(self.timer_page)
        self.timer_page.set_flashcard_context(self.current_folder_name, 0)
        self.handle_management_data_changed()
        self._update_sidebar_width()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Resize sidebar width proportionally with window size."""
        super().resizeEvent(event)
        self._update_sidebar_width()

    def _update_sidebar_width(self) -> None:
        """Keep sidebar wide enough to read folder names."""
        responsive_width = max(280, min(500, int(self.width() * 0.30)))
        self.sidebar.setFixedWidth(responsive_width)

    def switch_to_timer(self):
        """Switch to timer page."""
        self.stacked_widget.setCurrentWidget(self.timer_page)

    def switch_to_settings(self):
        """Switch to settings page or back to timer when already there."""
        if self.stacked_widget.currentWidget() is self.settings_page:
            self.switch_to_timer()
            return
        self.stacked_widget.setCurrentWidget(self.settings_page)

    def toggle_sidebar(self):
        """Show or hide the left sidebar."""
        self.sidebar.setHidden(not self.sidebar.isHidden())

    def _is_folder_item(self, item: QListWidgetItem | None) -> bool:
        """Return whether a sidebar item maps to a persisted folder.

        Args:
            item: Sidebar item.

        Returns:
            bool: True when item represents a folder.
        """
        return item is not None and item.data(Qt.UserRole) is not None

    def _get_checked_folder_ids(self) -> set[str]:
        """Return ids for currently checked folders.

        Returns:
            set[str]: Checked folder ids.
        """
        checked_ids: set[str] = set()
        for index in range(self.sidebar_folder_list.count()):
            item = self.sidebar_folder_list.item(index)
            folder_id = item.data(Qt.UserRole)
            if folder_id is None:
                continue
            if item.checkState() == Qt.Checked:
                checked_ids.add(folder_id)
        return checked_ids

    def _refresh_loaded_flashcards(self) -> None:
        """Refresh selected flashcards from checked folders."""
        checked_folder_ids: list[str] = []
        checked_folder_names: list[str] = []
        for index in range(self.sidebar_folder_list.count()):
            item = self.sidebar_folder_list.item(index)
            folder_id = item.data(Qt.UserRole)
            if folder_id is None or item.checkState() != Qt.Checked:
                continue
            checked_folder_ids.append(folder_id)
            checked_folder_names.append(item.text())

        self.selected_folder_ids = set(checked_folder_ids)
        if not checked_folder_ids:
            self.current_folder_id = None
            self.current_folder_name = "No folders selected"
            self.loaded_flashcards = []
        elif len(checked_folder_ids) == 1:
            self.current_folder_id = checked_folder_ids[0]
            self.current_folder_name = checked_folder_names[0]
            self.loaded_flashcards = self.flashcards_by_folder.get(
                self.current_folder_id, []
            )
        else:
            self.current_folder_id = None
            self.current_folder_name = f"{len(checked_folder_ids)} folders selected"
            self.loaded_flashcards = [
                flashcard
                for folder_id in checked_folder_ids
                for flashcard in self.flashcards_by_folder.get(folder_id, [])
            ]
        self.timer_page.set_flashcard_context(
            self.current_folder_name,
            len(self.loaded_flashcards),
        )

    def handle_folder_check_state_changed(self, item: QListWidgetItem) -> None:
        """Handle checkbox updates from sidebar folder items.

        Args:
            item: Updated sidebar item.
        """
        if not self._is_folder_item(item):
            return
        self._refresh_loaded_flashcards()

    def handle_sidebar_folder_click(self, clicked_item: QListWidgetItem):
        """Handle folder clicks and switch back to timer.

        Args:
            clicked_item: The clicked folder list item.
        """
        if not self._is_folder_item(clicked_item):
            return
        self.switch_to_timer()

    def open_sidebar_folder_menu(self, position: QPoint) -> None:
        """Open the right-click folder menu.

        Args:
            position: Position where the menu is requested.
        """
        clicked_item = self.sidebar_folder_list.itemAt(position)
        if not self._is_folder_item(clicked_item):
            return

        if not clicked_item.isSelected():
            self.sidebar_folder_list.clearSelection()
            clicked_item.setSelected(True)
        selected_folder_items = [
            item
            for item in self.sidebar_folder_list.selectedItems()
            if self._is_folder_item(item)
        ]
        if not selected_folder_items:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename folder")
        delete_action = menu.addAction("Delete folder(s)")
        rename_action.setEnabled(len(selected_folder_items) == 1)
        chosen_action = menu.exec(
            self.sidebar_folder_list.viewport().mapToGlobal(position)
        )
        if chosen_action is rename_action and len(selected_folder_items) == 1:
            self.rename_sidebar_folder(selected_folder_items[0])
        if chosen_action is delete_action:
            self.delete_sidebar_folders(selected_folder_items)

    def rename_sidebar_folder(self, folder_item: QListWidgetItem) -> None:
        """Rename one folder from sidebar action.

        Args:
            folder_item: Folder item selected from sidebar.
        """
        folder_id = folder_item.data(Qt.UserRole)
        if folder_id is None:
            return
        new_name, accepted = QInputDialog.getText(
            self,
            "Rename folder",
            "Folder name:",
            text=folder_item.text(),
        )
        if not accepted:
            return
        checked_ids = self._get_checked_folder_ids()
        try:
            rename_persisted_folder(folder_id, new_name)
        except (KeyError, ValueError) as error:
            QMessageBox.warning(self, "Rename folder", str(error))
            return
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

    def delete_sidebar_folders(self, folder_items: list[QListWidgetItem]) -> None:
        """Delete one or many folders from sidebar action.

        Args:
            folder_items: Folder items selected for deletion.
        """
        folder_ids = {
            item.data(Qt.UserRole)
            for item in folder_items
            if item.data(Qt.UserRole) is not None
        }
        if not folder_ids:
            return
        confirmation = QMessageBox.question(
            self,
            "Delete folder",
            f"Delete {len(folder_ids)} selected folder(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return

        checked_ids = self._get_checked_folder_ids() - folder_ids
        for folder_id in folder_ids:
            delete_persisted_folder(folder_id)
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

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
        checked_ids = self._get_checked_folder_ids()
        try:
            persisted_folder = import_folder(folder_path)
        except (FileNotFoundError, NotADirectoryError, OSError):
            return False
        checked_ids.add(persisted_folder.id)
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)
        return True

    def handle_management_data_changed(
        self, preferred_checked_ids: set[str] | None = None
    ) -> None:
        """Reload sidebar and current context after folder data changes.

        Args:
            preferred_checked_ids: Folder ids that should remain checked.
        """
        self.flashcards_by_folder = {}
        self.sidebar_folder_list.blockSignals(True)
        self.sidebar_folder_list.clear()

        for persisted_folder in list_persisted_folders():
            stored_folder = Path(persisted_folder.stored_path)
            if not stored_folder.exists():
                continue
            self.flashcards_by_folder[persisted_folder.id] = (
                load_flashcards_from_folder(stored_folder)
            )
            folder_item = QListWidgetItem(persisted_folder.name)
            folder_item.setData(Qt.UserRole, persisted_folder.id)
            folder_item.setFlags(
                folder_item.flags()
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
            )
            if preferred_checked_ids is None:
                folder_item.setCheckState(Qt.Checked)
            else:
                folder_item.setCheckState(
                    Qt.Checked
                    if persisted_folder.id in preferred_checked_ids
                    else Qt.Unchecked
                )
            self.sidebar_folder_list.addItem(folder_item)

        if self.sidebar_folder_list.count() == 0:
            empty_item = QListWidgetItem("No saved folders yet.")
            empty_item.setFlags(Qt.NoItemFlags)
            self.sidebar_folder_list.addItem(empty_item)
        else:
            self.sidebar_folder_list.setCurrentRow(0)
        self.sidebar_folder_list.blockSignals(False)
        self._refresh_loaded_flashcards()

    def set_navigation_visible(self, visible: bool):
        """Control navigation visibility for focused timer mode.

        Args:
            visible: Whether navigation controls should be visible.
        """
        self.sidebar_toggle_button.setVisible(visible)
        self.settings_button.setVisible(visible)
        if not visible:
            self.sidebar.setVisible(False)
