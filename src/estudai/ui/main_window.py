"""Main application window."""

from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
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

from estudai.services.csv_flashcards import (
    Flashcard,
    load_flashcards_from_folder,
    replace_flashcards_in_folder,
)
from estudai.services.folder_storage import (
    create_managed_folder,
    delete_persisted_folder,
    import_folder,
    list_persisted_folders,
    rename_persisted_folder,
)
from estudai.services.settings import load_app_settings

from .notebooklm_import_dialog import NotebookLMCsvImportDialog
from .pages import ManagementPage, SettingsPage, TimerPage


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    def __init__(self):
        super().__init__()
        self.flashcards_by_folder: dict[str, list[Flashcard]] = {}
        self.persisted_folder_paths: dict[str, Path] = {}
        self.selected_flashcard_indexes_by_folder: dict[str, set[int]] = {}
        self.loaded_flashcards: list[Flashcard] = []
        self.selected_folder_ids: set[str] = set()
        self.current_folder_id: str | None = None
        self.current_folder_name = "No folders selected"
        self._editing_folder_id: str | None = None
        self._renaming_folder_id: str | None = None
        self._renaming_original_name: str | None = None
        self.setWindowTitle("Estudai!")
        self.setGeometry(100, 100, 900, 650)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self._build_sidebar(root_layout)
        self._build_content_area(root_layout)

        app_settings = load_app_settings()
        self.timer_page = TimerPage(
            default_duration_seconds=app_settings.timer_duration_seconds
        )
        self.management_page = ManagementPage()
        self.settings_page = SettingsPage()
        self.stacked_widget.addWidget(self.timer_page)
        self.stacked_widget.addWidget(self.management_page)
        self.stacked_widget.addWidget(self.settings_page)
        self.timer_page.timer_running_changed.connect(self.handle_timer_running_changed)
        self.management_page.add_flashcard_button.clicked.connect(
            self.management_page.add_empty_flashcard_row
        )
        self.management_page.delete_flashcard_button.clicked.connect(
            self.delete_selected_flashcards_from_management
        )
        self.management_page.save_button.clicked.connect(self.save_management_changes)
        self.management_page.cancel_button.clicked.connect(self.switch_to_timer)
        self.settings_page.timer_duration_seconds_changed.connect(
            self.timer_page.set_timer_duration_seconds
        )

        self.stacked_widget.setCurrentWidget(self.timer_page)
        self.timer_page.set_flashcard_context(self.current_folder_name, 0)
        self.handle_management_data_changed()
        self._update_sidebar_width()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _build_sidebar(self, root_layout: QHBoxLayout) -> None:
        """Build the sidebar area."""
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
        self.sidebar_folder_list.setEditTriggers(QListWidget.NoEditTriggers)
        self.sidebar_folder_list.itemChanged.connect(self.handle_sidebar_item_changed)
        self.sidebar_folder_list.itemClicked.connect(self.handle_sidebar_folder_click)
        self.sidebar_folder_list.itemDoubleClicked.connect(
            self.handle_sidebar_folder_double_click
        )
        self.sidebar_folder_list.itemDelegate().closeEditor.connect(
            self.handle_sidebar_editor_closed
        )
        self.sidebar_folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sidebar_folder_list.customContextMenuRequested.connect(
            self.open_sidebar_folder_menu
        )
        sidebar_layout.addWidget(self.sidebar_folder_list)

        create_folder_button = QPushButton("Create Folder")
        create_folder_button.clicked.connect(self.prompt_and_create_folder)
        sidebar_layout.addWidget(create_folder_button)

        import_notebooklm_csv_button = QPushButton("Import NotebookLM CSV")
        import_notebooklm_csv_button.clicked.connect(
            self.prompt_and_import_notebooklm_csv
        )
        sidebar_layout.addWidget(import_notebooklm_csv_button)

        import_folder_button = QPushButton("Import Existing Folder")
        import_folder_button.clicked.connect(self.prompt_and_add_folder)
        sidebar_layout.addWidget(import_folder_button)
        sidebar_layout.addStretch()

        root_layout.addWidget(self.sidebar)

    def _build_content_area(self, root_layout: QHBoxLayout) -> None:
        """Build the content area with top actions and pages stack."""
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

    def switch_to_management(self) -> None:
        """Switch to flashcard management page."""
        self.stacked_widget.setCurrentWidget(self.management_page)

    def switch_to_settings(self):
        """Switch to settings page or back to timer when already there."""
        if self.stacked_widget.currentWidget() is self.settings_page:
            self.switch_to_timer()
            return
        self.stacked_widget.setCurrentWidget(self.settings_page)

    def handle_timer_running_changed(self, is_running: bool) -> None:
        """Hide editing/navigation controls while timer is active.

        Args:
            is_running: Whether timer is currently running.
        """
        self.set_navigation_visible(not is_running)

    def toggle_sidebar(self):
        """Show or hide the left sidebar."""
        self.sidebar.setHidden(not self.sidebar.isHidden())

    def _widget_contains_global_position(
        self, widget: QWidget, global_position: QPoint
    ) -> bool:
        """Return whether a global click position is inside a widget.

        Args:
            widget: Widget to evaluate.
            global_position: Click position in global coordinates.

        Returns:
            bool: True when the click is inside the widget.
        """
        if widget.isHidden():
            return False
        return widget.rect().contains(widget.mapFromGlobal(global_position))

    def _handle_global_click(self, global_position: QPoint) -> None:
        """Hide sidebar when user clicks outside the sidebar and toggle button.

        Args:
            global_position: Click position in global coordinates.
        """
        if self.sidebar.isHidden():
            return
        if self._widget_contains_global_position(self.sidebar, global_position):
            return
        if self._widget_contains_global_position(
            self.sidebar_toggle_button, global_position
        ):
            return
        self.sidebar.setVisible(False)

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        """Close sidebar when clicks happen outside it.

        Args:
            watched: Object receiving the event.
            event: Qt event to inspect.

        Returns:
            bool: False to continue normal event processing.
        """
        if (
            event.type() == QEvent.MouseButtonPress
            and isinstance(watched, QWidget)
            and watched.window() is self
        ):
            global_position_getter = getattr(event, "globalPosition", None)
            if callable(global_position_getter):
                self._handle_global_click(event.globalPosition().toPoint())
        return super().eventFilter(watched, event)

    def _is_folder_item(self, item: QListWidgetItem | None) -> bool:
        """Return whether a sidebar item maps to a persisted folder.

        Args:
            item: Sidebar item.

        Returns:
            bool: True when item represents a folder.
        """
        return item is not None and item.data(Qt.UserRole) is not None

    def _selected_folder_items(self) -> list[QListWidgetItem]:
        """Return selected list items that map to persisted folders.

        Returns:
            list[QListWidgetItem]: Selected folder items.
        """
        return [
            item
            for item in self.sidebar_folder_list.selectedItems()
            if self._is_folder_item(item)
        ]

    def _clear_rename_tracking(self) -> None:
        """Clear inline-rename tracking state."""
        self._renaming_folder_id = None
        self._renaming_original_name = None

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
        selected_flashcards: list[Flashcard] = []
        for index in range(self.sidebar_folder_list.count()):
            item = self.sidebar_folder_list.item(index)
            folder_id = item.data(Qt.UserRole)
            if folder_id is None or item.checkState() != Qt.Checked:
                continue
            checked_folder_ids.append(folder_id)
            checked_folder_names.append(item.text())
            folder_flashcards = self.flashcards_by_folder.get(folder_id, [])
            selected_indexes = self.selected_flashcard_indexes_by_folder.get(
                folder_id,
                set(range(len(folder_flashcards))),
            )
            selected_flashcards.extend(
                flashcard
                for flashcard_index, flashcard in enumerate(folder_flashcards)
                if flashcard_index in selected_indexes
            )

        self.selected_folder_ids = set(checked_folder_ids)
        if not checked_folder_ids:
            self.current_folder_id = None
            self.current_folder_name = "No folders selected"
            self.loaded_flashcards = []
        elif len(checked_folder_ids) == 1:
            self.current_folder_id = checked_folder_ids[0]
            self.current_folder_name = checked_folder_names[0]
            self.loaded_flashcards = selected_flashcards
        else:
            self.current_folder_id = None
            self.current_folder_name = f"{len(checked_folder_ids)} folders selected"
            self.loaded_flashcards = selected_flashcards
        self.timer_page.set_flashcard_context(
            self.current_folder_name,
            len(self.loaded_flashcards),
        )

    def handle_sidebar_item_changed(self, item: QListWidgetItem) -> None:
        """Handle sidebar item updates (checkbox and inline rename).

        Args:
            item: Updated sidebar item.
        """
        if not self._is_folder_item(item):
            return
        self._handle_inline_rename(item)
        folder_id = item.data(Qt.UserRole)
        if folder_id is not None:
            is_checked = item.checkState() == Qt.Checked
            was_checked = folder_id in self.selected_folder_ids
            if is_checked and not was_checked:
                folder_flashcards = self.flashcards_by_folder.get(folder_id, [])
                self.selected_flashcard_indexes_by_folder[folder_id] = set(
                    range(len(folder_flashcards))
                )
            elif not is_checked and was_checked:
                self.selected_flashcard_indexes_by_folder[folder_id] = set()
        self._refresh_loaded_flashcards()

    def _handle_inline_rename(self, item: QListWidgetItem) -> None:
        """Persist folder rename when inline editing changes item text.

        Args:
            item: Updated folder list item.
        """
        folder_id = item.data(Qt.UserRole)
        if folder_id is None or folder_id != self._renaming_folder_id:
            return

        new_name = item.text()
        if self._renaming_original_name == new_name:
            return

        checked_ids = self._get_checked_folder_ids()
        self._clear_rename_tracking()
        try:
            rename_persisted_folder(folder_id, new_name)
        except (KeyError, ValueError) as error:
            QMessageBox.warning(self, "Rename folder", str(error))
            self.handle_management_data_changed(preferred_checked_ids=checked_ids)
            return
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

    def handle_sidebar_editor_closed(self, *_: object) -> None:
        """Clear inline rename tracking when editor closes."""
        self._clear_rename_tracking()

    def handle_sidebar_folder_click(self, clicked_item: QListWidgetItem):
        """Handle folder clicks and switch back to timer.

        Args:
            clicked_item: The clicked folder list item.
        """
        if not self._is_folder_item(clicked_item):
            return
        self.switch_to_timer()

    def handle_sidebar_folder_double_click(self, clicked_item: QListWidgetItem) -> None:
        """Open folder management when a folder is double-clicked.

        Args:
            clicked_item: The double-clicked folder list item.
        """
        if not self._is_folder_item(clicked_item):
            return
        folder_id = clicked_item.data(Qt.UserRole)
        if folder_id is None:
            return
        self.open_management_for_folder(folder_id, clicked_item.text())

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
        selected_folder_items = self._selected_folder_items()
        if not selected_folder_items:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        rename_action.setToolTip("Rename")
        delete_action = menu.addAction("Delete")
        delete_action.setToolTip("Delete")
        rename_action.setEnabled(len(selected_folder_items) == 1)
        chosen_action = menu.exec(
            self.sidebar_folder_list.viewport().mapToGlobal(position)
        )
        if chosen_action is rename_action and len(selected_folder_items) == 1:
            self.rename_sidebar_folder(selected_folder_items[0])
        if chosen_action is delete_action:
            self.delete_sidebar_folders(selected_folder_items)

    def rename_sidebar_folder(self, folder_item: QListWidgetItem) -> None:
        """Start inline rename for one folder from sidebar action.

        Args:
            folder_item: Folder item selected from sidebar.
        """
        folder_id = folder_item.data(Qt.UserRole)
        if folder_id is None:
            return
        self._renaming_folder_id = folder_id
        self._renaming_original_name = folder_item.text()
        self.sidebar_folder_list.setCurrentItem(folder_item)
        QTimer.singleShot(0, lambda: self.sidebar_folder_list.editItem(folder_item))

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

    def prompt_and_create_folder(self) -> None:
        """Prompt for a folder name and create a managed empty folder."""
        folder_name, accepted = QInputDialog.getText(
            self,
            "Create folder",
            "Folder name:",
        )
        if not accepted:
            return
        checked_ids = self._get_checked_folder_ids()
        try:
            persisted_folder = create_managed_folder(folder_name)
        except ValueError as error:
            QMessageBox.warning(self, "Create folder", str(error))
            return
        checked_ids.add(persisted_folder.id)
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

    def prompt_and_import_notebooklm_csv(self) -> None:
        """Open NotebookLM CSV import dialog and import valid rows."""
        dialog = NotebookLMCsvImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        target_folder_id = dialog.selected_folder_id()
        valid_rows = dialog.import_rows()
        if target_folder_id is None or not valid_rows:
            return

        persisted_folder = next(
            (
                folder
                for folder in list_persisted_folders()
                if folder.id == target_folder_id
            ),
            None,
        )
        if persisted_folder is None:
            QMessageBox.warning(
                self,
                "Import NotebookLM CSV",
                "Selected folder is unavailable. Refresh and try again.",
            )
            return

        target_folder_path = Path(persisted_folder.stored_path)
        existing_flashcards = load_flashcards_from_folder(target_folder_path)
        existing_rows = [
            (flashcard.question, flashcard.answer) for flashcard in existing_flashcards
        ]
        replace_flashcards_in_folder(target_folder_path, [*existing_rows, *valid_rows])

        selected_indexes = self.selected_flashcard_indexes_by_folder.get(
            target_folder_id,
            set(range(len(existing_flashcards))),
        )
        imported_indexes = set(
            range(len(existing_flashcards), len(existing_flashcards) + len(valid_rows))
        )
        self.selected_flashcard_indexes_by_folder[target_folder_id] = (
            selected_indexes | imported_indexes
        )
        checked_ids = self._get_checked_folder_ids()
        checked_ids.add(target_folder_id)
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

    def open_management_from_selection(self) -> None:
        """Open management for one selected/checked folder."""
        selected_items = self._selected_folder_items()
        if len(selected_items) == 1:
            folder_item = selected_items[0]
            folder_id = folder_item.data(Qt.UserRole)
            if folder_id is not None:
                self.open_management_for_folder(folder_id, folder_item.text())
                return
        checked_items = [
            self.sidebar_folder_list.item(index)
            for index in range(self.sidebar_folder_list.count())
            if self._is_folder_item(self.sidebar_folder_list.item(index))
            and self.sidebar_folder_list.item(index).checkState() == Qt.Checked
        ]
        if len(checked_items) == 1:
            folder_item = checked_items[0]
            folder_id = folder_item.data(Qt.UserRole)
            if folder_id is not None:
                self.open_management_for_folder(folder_id, folder_item.text())
                return
        QMessageBox.information(
            self,
            "Manage flashcards",
            "Select one folder (or double-click one) to edit its flashcards.",
        )

    def open_management_for_folder(self, folder_id: str, folder_name: str) -> None:
        """Load one folder into management page and switch to it.

        Args:
            folder_id: Folder identifier.
            folder_name: Display name used in the sidebar.
        """
        if folder_id not in self.flashcards_by_folder:
            self.handle_management_data_changed(
                preferred_checked_ids=self._get_checked_folder_ids()
            )
        if folder_id not in self.flashcards_by_folder:
            QMessageBox.warning(
                self,
                "Manage flashcards",
                "This folder is unavailable. Try re-importing it.",
            )
            return
        folder_flashcards = self.flashcards_by_folder.get(folder_id, [])
        selected_indexes = self.selected_flashcard_indexes_by_folder.get(
            folder_id,
            set(range(len(folder_flashcards))),
        )
        self._editing_folder_id = folder_id
        self.management_page.set_folder_flashcards(
            folder_id,
            folder_name,
            folder_flashcards,
            selected_indexes,
        )
        self.switch_to_management()

    def delete_selected_flashcards_from_management(self) -> None:
        """Delete selected rows from management table with confirmation."""
        selected_rows = self.management_page.selected_table_rows()
        if not selected_rows:
            QMessageBox.information(
                self,
                "Delete flashcards",
                "Select one or more flashcards first.",
            )
            return
        confirmation = QMessageBox.question(
            self,
            "Delete flashcards",
            f"Delete {len(selected_rows)} selected flashcard(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        self.management_page.remove_rows(selected_rows)

    def save_management_changes(self) -> None:
        """Persist flashcard table edits and return to timer page."""
        if self._editing_folder_id is None:
            QMessageBox.warning(
                self,
                "Save flashcards",
                "No folder selected for editing.",
            )
            return
        folder_path = self.persisted_folder_paths.get(self._editing_folder_id)
        if folder_path is None:
            QMessageBox.warning(
                self,
                "Save flashcards",
                "Folder storage is unavailable. Please refresh and try again.",
            )
            return
        try:
            flashcard_rows, selected_indexes = (
                self.management_page.collect_flashcards_for_save()
            )
            replace_flashcards_in_folder(folder_path, flashcard_rows)
        except ValueError as error:
            QMessageBox.warning(self, "Save flashcards", str(error))
            return
        checked_ids = self._get_checked_folder_ids()
        self.selected_flashcard_indexes_by_folder[self._editing_folder_id] = (
            selected_indexes
        )
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)
        self.switch_to_timer()

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

    def _create_sidebar_folder_item(
        self, folder_id: str, folder_name: str, checked: bool
    ) -> QListWidgetItem:
        """Create one folder item for the sidebar list.

        Args:
            folder_id: Folder identifier.
            folder_name: Display name.
            checked: Whether the item starts checked.

        Returns:
            QListWidgetItem: Configured list item.
        """
        folder_item = QListWidgetItem(folder_name)
        folder_item.setData(Qt.UserRole, folder_id)
        folder_item.setFlags(
            folder_item.flags()
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
        )
        folder_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        return folder_item

    def handle_management_data_changed(
        self, preferred_checked_ids: set[str] | None = None
    ) -> None:
        """Reload sidebar and current context after folder data changes.

        Args:
            preferred_checked_ids: Folder ids that should remain checked.
        """
        self.flashcards_by_folder = {}
        self.persisted_folder_paths = {}
        remaining_folder_ids: set[str] = set()
        self.sidebar_folder_list.blockSignals(True)
        self.sidebar_folder_list.clear()

        for persisted_folder in list_persisted_folders():
            stored_folder = Path(persisted_folder.stored_path)
            if not stored_folder.exists():
                continue
            remaining_folder_ids.add(persisted_folder.id)
            self.persisted_folder_paths[persisted_folder.id] = stored_folder
            self.flashcards_by_folder[persisted_folder.id] = (
                load_flashcards_from_folder(stored_folder)
            )
            folder_flashcards = self.flashcards_by_folder[persisted_folder.id]
            existing_indexes = self.selected_flashcard_indexes_by_folder.get(
                persisted_folder.id
            )
            if existing_indexes is None:
                self.selected_flashcard_indexes_by_folder[persisted_folder.id] = set(
                    range(len(folder_flashcards))
                )
            else:
                self.selected_flashcard_indexes_by_folder[persisted_folder.id] = {
                    flashcard_index
                    for flashcard_index in existing_indexes
                    if 0 <= flashcard_index < len(folder_flashcards)
                }
            is_checked = (
                True
                if preferred_checked_ids is None
                else persisted_folder.id in preferred_checked_ids
            )
            folder_item = self._create_sidebar_folder_item(
                persisted_folder.id,
                persisted_folder.name,
                checked=is_checked,
            )
            self.sidebar_folder_list.addItem(folder_item)

        if self.sidebar_folder_list.count() == 0:
            empty_item = QListWidgetItem("No saved folders yet.")
            empty_item.setFlags(Qt.NoItemFlags)
            self.sidebar_folder_list.addItem(empty_item)
        else:
            self.sidebar_folder_list.setCurrentRow(0)
        self.sidebar_folder_list.blockSignals(False)
        self.selected_flashcard_indexes_by_folder = {
            folder_id: indexes
            for folder_id, indexes in self.selected_flashcard_indexes_by_folder.items()
            if folder_id in remaining_folder_ids
        }
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
