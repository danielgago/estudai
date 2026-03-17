"""Main application window."""

from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:  # pragma: no cover - depends on system multimedia libraries.
    QAudioOutput = None  # type: ignore[assignment]
    QMediaPlayer = None  # type: ignore[assignment]

from estudai.services.csv_flashcards import (
    Flashcard,
    list_source_csv_files,
)
from estudai.services.folder_catalog import PersistedFolderCatalogService
from estudai.services.folder_storage import (
    move_persisted_folder,
    rename_persisted_folder,
)
from estudai.services.hotkeys import (
    GlobalHotkeyService,
    HotkeyAction,
)
from estudai.services.settings import (
    AppSettings,
    get_default_notification_sound_path,
    load_app_settings,
)
from estudai.services.study_progress import (
    load_folder_progress,
    summarize_folder_progress,
)
from estudai.ui.utils import (
    NativeCheckboxDelegate,
    blend_colors,
    left_aligned_checkbox_rect,
)
from .application_state import FolderLibraryState, StudyApplicationState
from .controllers import (
    AppShellController,
    HotkeyController,
    ManagementPageController,
    SessionMutationController,
    SidebarFolderOperationsController,
    TimerPageController,
)
from .dialog import FlashcardEditDialog, NotebookLMCsvImportDialog
from .navigation_icons import (
    build_menu_navigation_icon,
    build_settings_navigation_icon,
    load_navigation_icon,
)
from .pages import ManagementPage, SettingsPage, TimerPage
from .sidebar_folders import (
    SidebarFolderController,
    SidebarFolderItem,
    SidebarFolderTreeWidget,
)


class SidebarCheckboxDelegate(NativeCheckboxDelegate):
    """Delegate that paints native checkbox indicators for sidebar folder items."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the delegate."""
        super().__init__(
            parent,
            checkbox_rect_resolver=lambda option, indicator_rect: (
                left_aligned_checkbox_rect(
                    option,
                    indicator_rect,
                    indicator_margin=8,
                )
            ),
            draw_item_text=True,
            indicator_margin=8,
            text_spacing=8,
        )


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    show_flashcard_requested = Signal(object)
    global_hotkey_action_requested = Signal(str)
    FOLDER_NAME_ROLE = Qt.UserRole + 1

    @property
    def flashcards_by_folder(self) -> dict[str, list[Flashcard]]:
        """Return flashcards grouped by folder id."""
        return self._app_state.flashcards_by_folder

    @flashcards_by_folder.setter
    def flashcards_by_folder(self, value: dict[str, list[Flashcard]]) -> None:
        self._app_state.flashcards_by_folder = value

    @property
    def persisted_folder_paths(self) -> dict[str, Path]:
        """Return managed folder paths grouped by folder id."""
        return self._app_state.persisted_folder_paths

    @persisted_folder_paths.setter
    def persisted_folder_paths(self, value: dict[str, Path]) -> None:
        self._app_state.persisted_folder_paths = value

    @property
    def selected_flashcard_indexes_by_folder(self) -> dict[str, set[int]]:
        """Return per-folder selected flashcard indexes."""
        return self._app_state.selected_flashcard_indexes_by_folder

    @selected_flashcard_indexes_by_folder.setter
    def selected_flashcard_indexes_by_folder(
        self,
        value: dict[str, set[int]],
    ) -> None:
        self._app_state.selected_flashcard_indexes_by_folder = value

    @property
    def loaded_flashcards(self) -> list[Flashcard]:
        """Return the currently selected flashcards used by the timer."""
        return self._app_state.loaded_flashcards

    @loaded_flashcards.setter
    def loaded_flashcards(self, value: list[Flashcard]) -> None:
        self._app_state.loaded_flashcards = value

    @property
    def selected_folder_ids(self) -> set[str]:
        """Return folder ids currently selected for study."""
        return self._app_state.selected_folder_ids

    @selected_folder_ids.setter
    def selected_folder_ids(self, value: set[str]) -> None:
        self._app_state.selected_folder_ids = value

    @property
    def current_folder_id(self) -> str | None:
        """Return the current singular folder selection, when applicable."""
        return self._app_state.current_folder_id

    @current_folder_id.setter
    def current_folder_id(self, value: str | None) -> None:
        self._app_state.current_folder_id = value

    @property
    def current_folder_name(self) -> str:
        """Return the current folder label shown on the timer page."""
        return self._app_state.current_folder_name

    @current_folder_name.setter
    def current_folder_name(self, value: str) -> None:
        self._app_state.current_folder_name = value

    def __init__(
        self,
        hotkey_service: GlobalHotkeyService | None = None,
        folder_catalog_service: PersistedFolderCatalogService | None = None,
    ) -> None:
        super().__init__()
        self._app_state = StudyApplicationState()
        self._folder_catalog_service = (
            folder_catalog_service or PersistedFolderCatalogService()
        )
        self._flashcard_sound_output: object | None = None
        self._flashcard_sound_player: object | None = None
        self._hotkey_service = hotkey_service or GlobalHotkeyService()
        flashcard_phase_timer = QTimer(self)
        flashcard_phase_timer.setSingleShot(True)
        if QAudioOutput is not None and QMediaPlayer is not None:
            self._flashcard_sound_output = QAudioOutput(self)
            self._flashcard_sound_player = QMediaPlayer(self)
            self._flashcard_sound_player.setAudioOutput(self._flashcard_sound_output)
        self.setWindowTitle("Estudai!")
        self.setGeometry(100, 100, 900, 650)
        app_settings = load_app_settings()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self._build_sidebar(root_layout)
        self._build_content_area(root_layout)
        self.timer_page = TimerPage(
            default_duration_seconds=app_settings.timer_duration_seconds
        )
        self.management_page = ManagementPage()
        self.settings_page = SettingsPage(
            save_settings_callback=self._save_settings_from_page,
            global_hotkey_availability_error=self._hotkey_service.availability_error,
        )
        self._management_controller = ManagementPageController(
            parent=self,
            management_page=self.management_page,
            app_state=self._app_state,
            selected_folder_items_getter=self._selected_folder_items,
            sidebar_folder_items_iter=self._iter_sidebar_folder_items,
            folder_name_resolver=self._folder_item_name,
            checked_folder_ids_getter=self._get_checked_folder_ids,
            refresh_management_data=self._refresh_sidebar_data,
            switch_to_management=self.switch_to_management,
            switch_to_timer=self.switch_to_timer,
            edit_dialog_factory=self._create_flashcard_edit_dialog,
        )
        self._timer_controller = TimerPageController(
            parent=self,
            timer_page=self.timer_page,
            app_state=self._app_state,
            flashcard_phase_timer=flashcard_phase_timer,
            flashcard_sound_player=self._flashcard_sound_player,
            iter_sidebar_folder_items=self._iter_sidebar_folder_items,
            set_navigation_visible=self.set_navigation_visible,
            switch_to_timer=self.switch_to_timer,
            emit_show_flashcard=self._emit_show_flashcard_requested,
            refresh_sidebar_folder_progress_labels=(
                self._refresh_sidebar_folder_progress_labels
            ),
            start_flashcard_phase_timer=self._start_flashcard_phase_timer_from_controller,
            handle_flashcard_phase_timeout=(
                self._handle_flashcard_phase_timeout_from_controller
            ),
            handle_timer_cycle_completed=self.handle_timer_cycle_completed,
            load_settings=self._load_current_app_settings,
            default_sound_path_getter=self._get_default_notification_sound_path,
        )
        flashcard_phase_timer.timeout.connect(
            self._timer_controller.handle_flashcard_phase_timeout
        )
        self._session_mutation_controller = SessionMutationController(
            parent=self,
            timer_page=self.timer_page,
            app_state=self._app_state,
            runtime=self._timer_controller,
            checked_folder_ids_getter=self._get_checked_folder_ids,
            handle_folder_data_changed=self._handle_folder_data_changed_from_controller,
            edit_dialog_factory=self._create_flashcard_edit_dialog,
            show_warning_message=self._show_warning_message,
            confirm_action=self._confirm_action,
        )
        self._sidebar_folder_operations_controller = SidebarFolderOperationsController(
            parent=self,
            app_state=self._app_state,
            sidebar_folder_list=self.sidebar_folder_list,
            selected_folder_items_getter=self._selected_folder_items,
            checked_folder_ids_getter=self._get_checked_folder_ids,
            handle_folder_data_changed=self._handle_folder_data_changed_from_controller,
            refresh_sidebar_folder_progress_labels=(
                self._refresh_sidebar_folder_progress_labels
            ),
            refresh_active_study_session_after_progress_reset=(
                self._refresh_active_study_session_after_progress_reset
            ),
            load_folder_flashcards=self._load_folder_flashcards,
            show_warning_message=self._show_warning_message,
        )
        self._app_shell_controller = AppShellController(
            stacked_widget=self.stacked_widget,
            timer_page=self.timer_page,
            management_page=self.management_page,
            settings_page=self.settings_page,
            sidebar=self.sidebar,
            sidebar_toggle_button=self.sidebar_toggle_button,
            settings_button=self.settings_button,
            central_widget_getter=self.centralWidget,
            window_width_getter=self.width,
            timer_running_getter=self._timer_page_is_running,
            stop_settings_preview=self.settings_page.stop_active_preview,
            is_fullscreen=self.isFullScreen,
            show_normal=self.showNormal,
            show_fullscreen=self.showFullScreen,
        )
        self._hotkey_controller = HotkeyController(
            parent=self,
            timer_page=self.timer_page,
            current_page_getter=self.stacked_widget.currentWidget,
            hotkey_service=self._hotkey_service,
            emit_hotkey_action=self._emit_global_hotkey_action_requested,
            show_warning_message=self._show_warning_message,
            toggle_fullscreen=self.toggle_fullscreen,
            exit_fullscreen=self.exit_fullscreen,
        )
        self._configure_window_shortcuts()
        self._apply_in_app_shortcut_bindings(app_settings)
        self.stacked_widget.addWidget(self.timer_page)
        self.stacked_widget.addWidget(self.management_page)
        self.stacked_widget.addWidget(self.settings_page)
        self.timer_page.timer_running_changed.connect(self.handle_timer_running_changed)
        self.timer_page.timer_cycle_completed.connect(self.handle_timer_cycle_completed)
        self.timer_page.flashcard_pause_toggled.connect(
            self.handle_flashcard_pause_toggled
        )
        self.timer_page.flashcard_queue_shuffle_requested.connect(
            self.handle_flashcard_queue_shuffle_requested
        )
        self.timer_page.flashcard_phase_skip_requested.connect(
            self.handle_flashcard_phase_skip_requested
        )
        self.timer_page.flashcard_marked_correct.connect(
            self.handle_flashcard_marked_correct
        )
        self.timer_page.flashcard_marked_wrong.connect(
            self.handle_flashcard_marked_wrong
        )
        self.timer_page.flashcard_edit_requested.connect(
            self.handle_flashcard_edit_requested
        )
        self.timer_page.flashcard_delete_requested.connect(
            self.handle_flashcard_delete_requested
        )
        self.timer_page.stop_requested.connect(self.handle_timer_stop_requested)
        self.show_flashcard_requested.connect(self.show_flashcard_popup)
        self.global_hotkey_action_requested.connect(
            self._handle_global_hotkey_action_requested
        )
        self.management_page.add_flashcard_button.clicked.connect(
            self._management_controller.add_flashcard
        )
        self.management_page.edit_requested.connect(
            self._management_controller.edit_selected_flashcard
        )
        self.management_page.delete_requested.connect(
            self.delete_selected_flashcards_from_management
        )
        self.management_page.reset_progress_requested.connect(
            self.reset_management_folder_progress
        )
        self.management_page.save_button.clicked.connect(self.save_management_changes)
        self.management_page.cancel_button.clicked.connect(self.switch_to_timer)
        self.settings_page.cancel_requested.connect(self.switch_to_timer)
        self.settings_page.timer_duration_seconds_changed.connect(
            self.timer_page.set_timer_duration_seconds
        )
        self.settings_page.settings_saved.connect(self._handle_settings_saved)

        self.stacked_widget.setCurrentWidget(self.timer_page)
        self.timer_page.set_flashcard_context(self.current_folder_name, 0)
        self.handle_management_data_changed()
        self._update_sidebar_width()
        self._apply_initial_hotkey_bindings(app_settings)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _build_sidebar(self, root_layout: QHBoxLayout) -> None:
        """Build the sidebar area."""
        self.sidebar = QFrame(self.centralWidget())
        self.sidebar.setFrameShape(QFrame.StyledPanel)
        self.sidebar.setVisible(False)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel("Folders")
        sidebar_title_font = QFont(sidebar_title.font())
        sidebar_title_font.setPointSize(16)
        sidebar_title_font.setBold(True)
        sidebar_title.setFont(sidebar_title_font)
        sidebar_title.setStyleSheet("border: none;")
        sidebar_layout.addWidget(sidebar_title)

        self.sidebar_folder_list = SidebarFolderTreeWidget()
        self.sidebar_folder_list.setSpacing(0)
        self.sidebar_folder_list.setUniformRowHeights(True)
        self.sidebar_folder_list.setIndentation(18)
        self.sidebar_folder_list.setSelectionMode(
            SidebarFolderTreeWidget.ExtendedSelection
        )
        self.sidebar_folder_list.setEditTriggers(SidebarFolderTreeWidget.NoEditTriggers)
        self.sidebar_folder_list.setDragEnabled(True)
        self.sidebar_folder_list.viewport().setAcceptDrops(True)
        self.sidebar_folder_list.setDropIndicatorShown(True)
        self.sidebar_folder_list.setDefaultDropAction(Qt.MoveAction)
        self.sidebar_folder_list.setDragDropMode(SidebarFolderTreeWidget.InternalMove)
        self.sidebar_folder_list.setItemDelegate(
            SidebarCheckboxDelegate(self.sidebar_folder_list)
        )
        self.sidebar_folder_list.itemChanged.connect(self.handle_sidebar_item_changed)
        self.sidebar_folder_list.itemClicked.connect(self.handle_sidebar_folder_click)
        self.sidebar_folder_list.itemDoubleClicked.connect(
            self.handle_sidebar_folder_double_click
        )
        self.sidebar_folder_list.itemSelectionChanged.connect(
            self._update_sidebar_reorder_buttons
        )
        self.sidebar_folder_list.itemDelegate().closeEditor.connect(
            self.handle_sidebar_editor_closed
        )
        self.sidebar_folder_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sidebar_folder_list.customContextMenuRequested.connect(
            self.open_sidebar_folder_menu
        )
        self.sidebar_folder_list.folder_drop_completed.connect(
            self.handle_sidebar_folder_drop
        )
        self._sidebar_folders = SidebarFolderController(
            self.sidebar_folder_list,
            self.FOLDER_NAME_ROLE,
        )
        sidebar_layout.addWidget(self.sidebar_folder_list)

        reorder_button_layout = QHBoxLayout()
        self.move_folder_up_button = QPushButton("Move Up")
        self.move_folder_up_button.clicked.connect(self.move_selected_sidebar_folder_up)
        reorder_button_layout.addWidget(self.move_folder_up_button)
        self.move_folder_down_button = QPushButton("Move Down")
        self.move_folder_down_button.clicked.connect(
            self.move_selected_sidebar_folder_down
        )
        reorder_button_layout.addWidget(self.move_folder_down_button)
        sidebar_layout.addLayout(reorder_button_layout)

        self.reset_all_progress_button = QPushButton("Reset Progress")
        self.reset_all_progress_button.setToolTip("Reset progress for all folders")
        self.reset_all_progress_button.clicked.connect(self.reset_all_sidebar_progress)
        sidebar_layout.addWidget(self.reset_all_progress_button)

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
        self._apply_sidebar_palette_styles()
        self._update_sidebar_reorder_buttons()
        self.sidebar.raise_()

    def _build_content_area(self, root_layout: QHBoxLayout) -> None:
        """Build the content area with top actions and pages stack."""
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        self.header_container = QWidget()
        self.header_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.header_container.setFixedHeight(52)
        header_layout = QHBoxLayout(self.header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_toggle_button = QPushButton("")
        self.sidebar_toggle_button.setFixedSize(44, 44)
        self.sidebar_toggle_button.setToolTip("Toggle folders sidebar")
        self.sidebar_toggle_button.setIconSize(QSize(20, 20))
        self.sidebar_toggle_button.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.sidebar_toggle_button, alignment=Qt.AlignLeft)
        header_layout.addStretch()

        self.settings_button = QPushButton("")
        self.settings_button.setFixedSize(44, 44)
        self.settings_button.setToolTip("Open settings")
        self.settings_button.setIconSize(QSize(20, 20))
        self.settings_button.clicked.connect(self.switch_to_settings)
        self._apply_navigation_button_icons()
        header_layout.addWidget(self.settings_button, alignment=Qt.AlignRight)
        content_layout.addWidget(self.header_container)

        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        root_layout.addWidget(content_container)

    def _configure_window_shortcuts(self) -> None:
        """Register app-scoped shortcuts that should work regardless of focus."""
        self._hotkey_controller.configure_window_shortcuts()

    def _create_application_shortcut(self, callback: object) -> QShortcut:
        """Create one app-scoped shortcut with no binding assigned yet."""
        return self._hotkey_controller.create_application_shortcut(callback)

    def _apply_in_app_shortcut_bindings(self, settings: AppSettings) -> None:
        """Apply persisted in-app shortcut bindings to the active window."""
        self._hotkey_controller.apply_in_app_shortcut_bindings(settings)

    def _start_stop_shortcut_sequences(self, binding: str) -> list[QKeySequence]:
        """Return the start/stop shortcut list, keeping Enter and Return aligned."""
        return self._hotkey_controller.start_stop_shortcut_sequences(binding)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Resize sidebar width proportionally with window size."""
        super().resizeEvent(event)
        self._update_sidebar_width()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Refresh palette-driven sidebar visuals when theme/palette changes."""
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            self._apply_navigation_button_icons()
            self._apply_sidebar_palette_styles()
            self._refresh_sidebar_item_visual_states()
        super().changeEvent(event)

    def _apply_navigation_button_icons(self) -> None:
        """Set cross-platform navigation icons with theme/native fallback."""
        icon_color = self._navigation_icon_color()
        self.sidebar_toggle_button.setIcon(
            load_navigation_icon(
                theme_names=("open-menu-symbolic", "application-menu"),
                fallback=build_menu_navigation_icon(
                    self.sidebar_toggle_button.iconSize(),
                    icon_color,
                ),
            )
        )
        self.settings_button.setIcon(
            load_navigation_icon(
                theme_names=("preferences-system", "settings-configure", "settings"),
                fallback=build_settings_navigation_icon(
                    self.settings_button.iconSize(),
                    icon_color,
                ),
            )
        )

    def _navigation_icon_color(self) -> QColor:
        """Return icon color with contrast against the current button background."""
        return self.palette().buttonText().color()

    def _apply_sidebar_palette_styles(self) -> None:
        """Apply palette-aware sidebar frame and checkbox styles."""
        palette = self.sidebar.palette()
        border_color = blend_colors(
            palette.color(QPalette.Window),
            palette.color(QPalette.WindowText),
            overlay_ratio=0.28,
        ).name(QColor.HexRgb)
        self.sidebar.setStyleSheet(
            "QFrame {"
            " background-color: palette(window);"
            f" border: 1px solid {border_color};"
            "}"
        )
        self.sidebar_folder_list.setStyleSheet(
            "QTreeWidget {" " show-decoration-selected: 0;" "}"
        )

    def _update_sidebar_width(self) -> None:
        """Keep sidebar wide enough to read folder names."""
        controller = getattr(self, "_app_shell_controller", None)
        if controller is None:
            return
        controller.update_sidebar_width()

    def _position_sidebar(self) -> None:
        """Place sidebar as an overlay anchored below the sidebar toggle button."""
        controller = getattr(self, "_app_shell_controller", None)
        if controller is None:
            return
        controller.position_sidebar()

    def switch_to_timer(self) -> None:
        """Switch to timer page."""
        if not self._confirm_discard_management_changes():
            return
        self._app_shell_controller.switch_to_timer()

    def switch_to_management(self) -> None:
        """Switch to flashcard management page."""
        self._app_shell_controller.switch_to_management()

    def switch_to_settings(self) -> None:
        """Switch to settings page or back to timer when already there."""
        if not self._confirm_discard_management_changes():
            return
        self._app_shell_controller.switch_to_settings()

    def _confirm_discard_management_changes(self) -> bool:
        """Confirm leaving management when there are unsaved flashcard edits."""
        if self.stacked_widget.currentWidget() is not self.management_page:
            return True
        if not self.management_page.is_dirty():
            return True
        confirmation = QMessageBox.warning(
            self,
            "Unsaved changes",
            "You have unsaved flashcard changes. Discard them and leave this page?",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return confirmation == QMessageBox.Discard

    def _refresh_sidebar_data(self, checked_ids: set[str]) -> None:
        """Refresh sidebar items while preserving the provided checked ids."""
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

    def _handle_folder_data_changed_from_controller(
        self,
        preferred_checked_ids: set[str] | None,
        preferred_current_folder_id: str | None,
    ) -> None:
        """Reload folder data while preserving controller-provided selections.

        Args:
            preferred_checked_ids: Checked folder ids to preserve after reload.
            preferred_current_folder_id: Current folder id to keep selected.
        """
        self.handle_management_data_changed(
            preferred_checked_ids=preferred_checked_ids,
            preferred_current_folder_id=preferred_current_folder_id,
        )

    def _create_flashcard_edit_dialog(
        self,
        question: str,
        answer: str,
        question_image_path: str | None,
        answer_image_path: str | None,
        folder_path: Path,
    ) -> FlashcardEditDialog:
        """Create the shared flashcard edit dialog used across controllers.

        Args:
            question: Initial flashcard question text.
            answer: Initial flashcard answer text.
            question_image_path: Optional question image path.
            answer_image_path: Optional answer image path.
            folder_path: Base folder used to resolve relative image paths.

        Returns:
            FlashcardEditDialog: Configured edit dialog parented to the window.
        """
        return FlashcardEditDialog(
            question,
            answer,
            question_image_path=question_image_path,
            answer_image_path=answer_image_path,
            base_folder_path=folder_path,
            parent=self,
        )

    def _confirm_action(self, title: str, message: str) -> bool:
        """Ask the user to confirm a destructive action.

        Args:
            title: Dialog title.
            message: Confirmation prompt text.

        Returns:
            bool: True when the user confirms the action.
        """
        return (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _show_warning_message(self, title: str, message: str) -> None:
        """Show a warning dialog using the main window as parent."""
        QMessageBox.warning(self, title, message)

    def _emit_show_flashcard_requested(self, flashcard: Flashcard) -> None:
        """Forward a flashcard request through the window signal seam.

        Args:
            flashcard: Flashcard selected for display.
        """
        self.show_flashcard_requested.emit(flashcard)

    def _start_flashcard_phase_timer_from_controller(
        self,
        duration_ms: int,
        callback: object,
    ) -> None:
        """Route phase-timer starts back through the timer controller.

        Args:
            duration_ms: Phase duration in milliseconds.
            callback: Pending phase callback scheduled for timer completion.
        """
        self._timer_controller.start_flashcard_phase_timer(duration_ms, callback)

    def _handle_flashcard_phase_timeout_from_controller(self) -> None:
        """Route flashcard phase completion back through the timer controller."""
        self._timer_controller.handle_flashcard_phase_timeout()

    def _load_current_app_settings(self) -> AppSettings:
        """Load application settings using the latest module-level implementation."""
        return load_app_settings()

    def _get_default_notification_sound_path(self) -> str:
        """Resolve the default notification sound using the latest helper."""
        return get_default_notification_sound_path()

    def _handle_settings_saved(self, _settings: AppSettings) -> None:
        """Return to the timer page after a successful settings save."""
        self._refresh_sidebar_folder_progress_labels()
        self._timer_controller.refresh_queue_shuffle_action()
        self.switch_to_timer()

    def handle_timer_running_changed(self, is_running: bool) -> None:
        """Hide editing/navigation controls while timer is active."""
        self._timer_controller.handle_timer_running_changed(is_running)

    def handle_flashcard_pause_toggled(self, paused: bool) -> None:
        """Pause or resume flashcard phase timing."""
        self._timer_controller.handle_flashcard_pause_toggled(paused)

    def handle_flashcard_queue_shuffle_requested(self) -> None:
        """Shuffle the remaining queue for the active queue-based session."""
        self._timer_controller.handle_flashcard_queue_shuffle_requested()

    def handle_timer_stop_requested(self) -> None:
        """Abort the current study session when user clicks Stop."""
        self._timer_controller.handle_timer_stop_requested()

    def _hotkey_action_callbacks(self) -> dict[HotkeyAction, object]:
        """Return thread-safe callbacks that marshal hotkeys into the UI thread."""
        return self._hotkey_controller.hotkey_action_callbacks()

    def _apply_initial_hotkey_bindings(self, settings: AppSettings) -> None:
        """Apply persisted hotkeys on startup and fall back to defaults on failure."""
        self._hotkey_controller.apply_initial_hotkey_bindings(settings)

    def _save_settings_from_page(self, settings: AppSettings) -> None:
        """Apply live hotkeys before persisting settings to disk."""
        self._hotkey_controller.save_settings_from_page(settings)

    def _emit_global_hotkey_action_requested(self, action_value: str) -> None:
        """Forward a global hotkey action back onto the main-thread signal.

        Args:
            action_value: Serialized hotkey action enum value.
        """
        self.global_hotkey_action_requested.emit(action_value)

    def _handle_global_hotkey_action_requested(self, action_value: str) -> None:
        """Dispatch a hotkey action onto the same UI paths as button clicks."""
        self._hotkey_controller.handle_global_hotkey_action_requested(action_value)

    def _timer_page_is_running(self) -> bool:
        """Return whether the timer page countdown is currently active."""
        return self.timer_page.is_running

    def _timer_page_is_active(self) -> bool:
        """Return whether timer hotkeys should be active for the current page."""
        return self._hotkey_controller.timer_page_is_active()

    def _trigger_timer_page_pause_resume(self) -> None:
        """Mirror the pause/resume button path for local and global shortcuts."""
        self._hotkey_controller.trigger_timer_page_pause_resume()

    def _trigger_timer_page_start_stop(self) -> None:
        """Mirror the start/stop button path for local and global shortcuts."""
        self._hotkey_controller.trigger_timer_page_start_stop()

    def _trigger_timer_page_mark_correct(self) -> None:
        """Mirror the correct button path for local and global shortcuts."""
        self._hotkey_controller.trigger_timer_page_mark_correct()

    def _trigger_timer_page_skip_phase(self) -> None:
        """Mirror the skip-phase action path for local and global shortcuts."""
        self._hotkey_controller.trigger_timer_page_skip_phase()

    def _trigger_timer_page_mark_wrong(self) -> None:
        """Mirror the wrong button path for local and global shortcuts."""
        self._hotkey_controller.trigger_timer_page_mark_wrong()

    def _trigger_timer_page_copy_question(self) -> None:
        """Copy the current flashcard question and show transient feedback."""
        self._hotkey_controller.trigger_timer_page_copy_question()

    def handle_flashcard_phase_skip_requested(self) -> None:
        """Advance the current flashcard phase immediately when one is pending."""
        self._timer_controller.handle_flashcard_phase_skip_requested()

    def handle_timer_cycle_completed(self) -> None:
        """Advance the current study session when a timer cycle finishes."""
        self._timer_controller.handle_timer_cycle_completed()

    def show_flashcard_popup(self, flashcard: object) -> None:
        """Show flashcard question/answer inside timer page.

        Args:
            flashcard: Flashcard payload emitted from timer completion.
        """
        self._timer_controller.show_flashcard_popup(flashcard)

    def handle_flashcard_marked_correct(self) -> None:
        """Queue the selected Correct state until answer timeout."""
        self._timer_controller.handle_flashcard_marked_correct()

    def handle_flashcard_marked_wrong(self) -> None:
        """Queue the selected Wrong state until answer timeout."""
        self._timer_controller.handle_flashcard_marked_wrong()

    def handle_flashcard_edit_requested(self) -> None:
        """Edit the paused flashcard and update the active session immediately."""
        self._session_mutation_controller.handle_flashcard_edit_requested()

    def handle_flashcard_delete_requested(self) -> None:
        """Delete the paused flashcard and remove it from the active session."""
        self._session_mutation_controller.handle_flashcard_delete_requested()

    def toggle_sidebar(self) -> None:
        """Show or hide the left sidebar."""
        self._app_shell_controller.toggle_sidebar()

    def toggle_fullscreen(self) -> None:
        """Toggle between fullscreen and normal window modes."""
        self._app_shell_controller.toggle_fullscreen()

    def exit_fullscreen(self) -> None:
        """Leave fullscreen mode when currently active."""
        self._app_shell_controller.exit_fullscreen()

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
        return self._app_shell_controller.widget_contains_global_position(
            widget,
            global_position,
        )

    def _handle_global_click(self, global_position: QPoint) -> None:
        """Hide sidebar when user clicks outside the sidebar and toggle button.

        Args:
            global_position: Click position in global coordinates.
        """
        self._app_shell_controller.handle_global_click(global_position)

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

    def closeEvent(self, event) -> None:  # noqa: N802
        """Release global hotkeys and app-wide filters when closing the window."""
        self.settings_page.stop_active_preview()
        self._timer_controller.flashcard_sound_controller.stop()
        self._hotkey_service.clear()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def _is_folder_item(self, item: SidebarFolderItem | None) -> bool:
        """Return whether a sidebar item maps to a persisted folder.

        Args:
            item: Sidebar item.

        Returns:
            bool: True when item represents a folder.
        """
        return self._sidebar_folders.is_folder_item(item)

    def _selected_folder_items(self) -> list[SidebarFolderItem]:
        """Return selected list items that map to persisted folders.

        Returns:
            list[SidebarFolderItem]: Selected folder items.
        """
        return self._sidebar_folders.selected_folder_items()

    def _iter_sidebar_folder_items(self):
        """Yield sidebar items that map to persisted folders."""
        yield from self._sidebar_folders.iter_folder_items()

    def _clear_rename_tracking(self) -> None:
        """Clear inline-rename tracking state."""
        self._sidebar_folders.clear_rename_tracking()

    def _get_checked_folder_ids(self) -> set[str]:
        """Return ids for currently checked folders.

        Returns:
            set[str]: Checked folder ids.
        """
        return self._sidebar_folders.checked_folder_ids()

    def _sidebar_progress_percent(self, folder_id: str) -> int:
        """Return the current completion percentage for one folder."""
        completion_mode = load_app_settings().wrong_answer_completion_mode
        folder_flashcards = self.flashcards_by_folder.get(folder_id, [])
        summary = summarize_folder_progress(
            (flashcard.stable_id for flashcard in folder_flashcards),
            load_folder_progress(folder_id),
            completion_mode,
        )
        return summary.percent_done

    def _refresh_sidebar_folder_progress_labels(
        self,
        folder_ids: set[str] | None = None,
    ) -> None:
        """Refresh sidebar labels for one or many folders without rebuilding the list.

        Args:
            folder_ids: Optional subset of folder ids to refresh.
        """
        were_signals_blocked = self.sidebar_folder_list.blockSignals(True)
        try:
            for item in self._iter_sidebar_folder_items():
                folder_id = item.data(Qt.UserRole)
                if folder_id is None:
                    continue
                if folder_ids is not None and folder_id not in folder_ids:
                    continue
                if folder_id == self._sidebar_folders.renaming_folder_id:
                    continue
                folder_flashcards = self.flashcards_by_folder.get(folder_id, [])
                item.setText(
                    self._format_sidebar_folder_label(
                        self._folder_item_name(item),
                        len(folder_flashcards),
                        self._sidebar_progress_percent(folder_id),
                    )
                )
        finally:
            self.sidebar_folder_list.blockSignals(were_signals_blocked)

    def _refresh_loaded_flashcards(self) -> None:
        """Refresh selected flashcards from checked folders."""
        self._app_state.refresh_selection(self._get_checked_folder_ids())
        self._timer_controller.reset_flashcard_sequence_order()
        self.timer_page.set_flashcard_context(
            self.current_folder_name,
            len(self.loaded_flashcards),
        )
        if not self._timer_controller.study_session.active:
            self.timer_page.clear_session_progress()

    def handle_sidebar_item_changed(
        self,
        item: SidebarFolderItem,
        column: int = 0,
    ) -> None:
        """Handle sidebar item updates (checkbox and inline rename).

        Args:
            item: Updated sidebar item.
            column: Updated tree column.
        """
        if column != 0 or not self._is_folder_item(item):
            return
        were_signals_blocked = self.sidebar_folder_list.blockSignals(True)
        try:
            self._apply_sidebar_item_visual_state(item)
            self._sidebar_folders.cascade_check_state(item)
        finally:
            self.sidebar_folder_list.blockSignals(were_signals_blocked)
        self._handle_inline_rename(item)
        folder_id = item.data(Qt.UserRole)
        if folder_id is not None:
            is_checked = item.checkState() == Qt.Checked
            was_checked = folder_id in self.selected_folder_ids
            if is_checked and not was_checked:
                folder_flashcards = self.flashcards_by_folder.get(folder_id, [])
                self._app_state.update_selected_indexes(
                    folder_id,
                    set(range(len(folder_flashcards))),
                )
            elif not is_checked and was_checked:
                self._app_state.update_selected_indexes(folder_id, set())
        self._refresh_loaded_flashcards()

    def _handle_inline_rename(self, item: SidebarFolderItem) -> None:
        """Persist folder rename when inline editing changes item text.

        Args:
            item: Updated folder list item.
        """
        self._sidebar_folders.handle_inline_rename(
            item,
            checked_ids=self._get_checked_folder_ids(),
            rename_folder=rename_persisted_folder,
            refresh_data=self._refresh_sidebar_data,
            show_warning=self._show_warning_message,
        )

    def handle_sidebar_editor_closed(self, *_: object) -> None:
        """Clear inline rename tracking when editor closes."""
        self._sidebar_folders.handle_editor_closed(
            checked_ids=self._get_checked_folder_ids(),
            refresh_data=self._refresh_sidebar_data,
        )

    def handle_sidebar_folder_click(
        self,
        clicked_item: SidebarFolderItem,
        _column: int = 0,
    ) -> None:
        """Handle folder clicks without forcing page navigation.

        Args:
            clicked_item: The clicked folder list item.
        """
        if not self._is_folder_item(clicked_item):
            return

    def handle_sidebar_folder_double_click(
        self,
        clicked_item: SidebarFolderItem,
        _column: int = 0,
    ) -> None:
        """Open folder management when a folder is double-clicked.

        Args:
            clicked_item: The double-clicked folder list item.
        """
        if not self._is_folder_item(clicked_item):
            return
        folder_id = clicked_item.data(Qt.UserRole)
        if folder_id is None:
            return
        self.open_management_for_folder(folder_id, self._folder_item_name(clicked_item))

    def open_sidebar_folder_menu(self, position: QPoint) -> None:
        """Open the right-click folder menu.

        Args:
            position: Position where the menu is requested.
        """
        clicked_item = self.sidebar_folder_list.itemAt(position)
        selected_folder_items = self._sidebar_folders.normalize_menu_selection(
            clicked_item
        )
        if not selected_folder_items:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        rename_action.setToolTip("Rename")
        create_subfolder_action = menu.addAction("Create Subfolder")
        create_subfolder_action.setToolTip("Create a child folder")
        forget_progress_action = menu.addAction("Forget progress")
        forget_progress_action.setToolTip("Reset folder progress")
        delete_action = menu.addAction("Delete")
        delete_action.setToolTip("Delete")
        rename_action.setEnabled(len(selected_folder_items) == 1)
        create_subfolder_action.setEnabled(len(selected_folder_items) == 1)
        chosen_action = menu.exec(
            self.sidebar_folder_list.viewport().mapToGlobal(position)
        )
        if chosen_action is rename_action and len(selected_folder_items) == 1:
            self.rename_sidebar_folder(selected_folder_items[0])
        if chosen_action is create_subfolder_action and len(selected_folder_items) == 1:
            self.prompt_and_create_subfolder(selected_folder_items[0])
        if chosen_action is forget_progress_action:
            self.forget_sidebar_folder_progress(selected_folder_items)
        if chosen_action is delete_action:
            self.delete_sidebar_folders(selected_folder_items)

    def rename_sidebar_folder(self, folder_item: SidebarFolderItem) -> None:
        """Start inline rename for one folder from sidebar action.

        Args:
            folder_item: Folder item selected from sidebar.
        """
        self._sidebar_folders.begin_rename(folder_item)

    def delete_sidebar_folders(self, folder_items: list[SidebarFolderItem]) -> None:
        """Delete one or many folders from sidebar action.

        Args:
            folder_items: Folder items selected for deletion.
        """
        self._sidebar_folder_operations_controller.delete_folders(folder_items)

    def forget_sidebar_folder_progress(
        self,
        folder_items: list[SidebarFolderItem],
    ) -> None:
        """Reset persisted study progress for one or many folders.

        Args:
            folder_items: Folder items selected for progress reset.
        """
        self._sidebar_folder_operations_controller.forget_progress_for_folders(
            folder_items
        )

    def reset_all_sidebar_progress(self) -> None:
        """Reset persisted study progress across all currently loaded folders."""
        self._sidebar_folder_operations_controller.reset_all_progress()

    def reset_management_folder_progress(self) -> None:
        """Reset persisted study progress for the folder open in management."""
        self._sidebar_folder_operations_controller.reset_management_folder_progress(
            self._management_controller.editing_folder_id,
            self.management_page.title_label.text(),
        )

    def _refresh_active_study_session_after_progress_reset(
        self,
        folder_ids: set[str],
    ) -> None:
        """Rebuild the active study session when reset affects selected folders.

        Args:
            folder_ids: Folder ids whose persisted progress was reset.
        """
        self._timer_controller.refresh_active_study_session_after_progress_reset(
            folder_ids
        )

    def move_selected_sidebar_folder_up(self) -> None:
        """Move the selected sidebar folder one position upward."""
        self._sidebar_folder_operations_controller.move_selected_folder(-1)

    def move_selected_sidebar_folder_down(self) -> None:
        """Move the selected sidebar folder one position downward."""
        self._sidebar_folder_operations_controller.move_selected_folder(1)

    def move_selected_sidebar_folder_in(self) -> None:
        """Nest the selected sidebar folder under its previous sibling."""
        self._sidebar_folder_operations_controller.move_selected_folder_in()

    def move_selected_sidebar_folder_out(self) -> None:
        """Promote the selected sidebar folder to the parent level."""
        self._sidebar_folder_operations_controller.move_selected_folder_out()

    def handle_sidebar_folder_drop(
        self,
        folder_id: str,
        parent_id: object,
        new_index: int,
    ) -> None:
        """Persist one sidebar drag-and-drop move.

        Args:
            folder_id: Moved folder identifier.
            parent_id: New parent folder identifier, or None at the root.
            new_index: Zero-based sibling index after the drop.
        """
        target_parent_id = parent_id if isinstance(parent_id, str) else None
        if new_index < 0:
            self.handle_management_data_changed(
                preferred_checked_ids=self._get_checked_folder_ids(),
                preferred_current_folder_id=folder_id,
            )
            return
        checked_ids = self._get_checked_folder_ids()
        try:
            move_persisted_folder(folder_id, new_index, parent_id=target_parent_id)
        except (KeyError, IndexError, ValueError) as error:
            self._show_warning_message("Move folder", str(error))
            self.handle_management_data_changed(
                preferred_checked_ids=checked_ids,
                preferred_current_folder_id=folder_id,
            )
            return
        self.handle_management_data_changed(
            preferred_checked_ids=checked_ids,
            preferred_current_folder_id=folder_id,
        )

    def prompt_and_add_folder(self) -> None:
        """Prompt the user for a folder and load CSV flashcards from it."""
        selected_path = QFileDialog.getExistingDirectory(
            self,
            "Select folder with CSV flashcards",
        )
        if not selected_path:
            return
        folder_path = Path(selected_path)
        split_csv_into_subfolders = self._prompt_for_split_csv_import(folder_path)
        if split_csv_into_subfolders is None:
            return
        self.add_folder(
            folder_path,
            show_errors=True,
            split_csv_into_subfolders=split_csv_into_subfolders,
        )

    def prompt_and_create_folder(self) -> None:
        """Prompt for a folder name and create a managed empty folder."""
        self._prompt_and_create_folder()

    def prompt_and_create_subfolder(self, folder_item: SidebarFolderItem) -> None:
        """Prompt for a subfolder name and create it under the selected folder.

        Args:
            folder_item: Parent folder item.
        """
        parent_folder_id = folder_item.data(Qt.UserRole)
        if not isinstance(parent_folder_id, str):
            return
        self._prompt_and_create_folder(parent_id=parent_folder_id)

    def _prompt_and_create_folder(self, parent_id: str | None = None) -> None:
        """Prompt for a folder name and create it at the requested level.

        Args:
            parent_id: Optional parent folder id.
        """
        folder_name, accepted = QInputDialog.getText(
            self,
            "Create subfolder" if parent_id is not None else "Create folder",
            "Subfolder name:" if parent_id is not None else "Folder name:",
        )
        if not accepted:
            return
        self._sidebar_folder_operations_controller.create_folder(
            folder_name,
            parent_id=parent_id,
        )

    def prompt_and_import_notebooklm_csv(self) -> None:
        """Open NotebookLM CSV import dialog and import valid rows."""
        dialog = NotebookLMCsvImportDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        target_folder_id = dialog.selected_folder_id()
        valid_rows = dialog.import_rows()
        if target_folder_id is None or not valid_rows:
            return
        self._sidebar_folder_operations_controller.import_notebooklm_rows(
            target_folder_id,
            valid_rows,
        )

    def open_management_from_selection(self) -> None:
        """Open management for one selected/checked folder."""
        self._management_controller.open_from_selection()

    def open_management_for_folder(self, folder_id: str, folder_name: str) -> None:
        """Load one folder into management page and switch to it.

        Args:
            folder_id: Folder identifier.
            folder_name: Display name used in the sidebar.
        """
        self._management_controller.open_for_folder(folder_id, folder_name)

    def delete_selected_flashcards_from_management(self) -> None:
        """Delete selected rows from management table with confirmation."""
        self._management_controller.delete_selected_flashcards()

    def save_management_changes(self) -> None:
        """Persist flashcard table edits and return to timer page."""
        self._management_controller.save_changes()

    def add_folder(
        self,
        folder_path: Path,
        *,
        show_errors: bool = False,
        split_csv_into_subfolders: bool = False,
    ) -> bool:
        """Copy one selected folder, persist it, and load flashcards.

        Args:
            folder_path: Selected folder path.
            show_errors: Whether import failures should show a warning dialog.
            split_csv_into_subfolders: Whether directories with multiple CSV files
                should create one child folder per CSV during import.

        Returns:
            bool: True when the folder was loaded.
        """
        return self._sidebar_folder_operations_controller.add_folder(
            folder_path,
            show_errors=show_errors,
            split_csv_into_subfolders=split_csv_into_subfolders,
        )

    def _prompt_for_split_csv_import(self, folder_path: Path) -> bool | None:
        """Return how a selected import should handle directories with many CSVs.

        Args:
            folder_path: Folder selected for import.

        Returns:
            bool | None: `True` to split CSV files into child folders, `False` to
            keep the current consolidated behavior, or `None` when the user
            cancels the import.
        """
        if not folder_path.exists() or not folder_path.is_dir():
            return False
        if not self._folder_tree_contains_multi_csv_directory(folder_path):
            return False

        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Question)
        message_box.setWindowTitle("Import Existing Folder")
        message_box.setText(
            "One or more folders in this import contain multiple CSV files."
        )
        message_box.setInformativeText(
            "Would you like Estudai to create a separate folder for each CSV "
            "file instead of keeping those CSVs together inside the same folder?"
        )
        separate_button = message_box.addButton(
            "Separate Each CSV",
            QMessageBox.AcceptRole,
        )
        keep_together_button = message_box.addButton(
            "Keep Together",
            QMessageBox.NoRole,
        )
        cancel_button = message_box.addButton(QMessageBox.Cancel)
        message_box.setDefaultButton(keep_together_button)
        message_box.exec()
        clicked_button = message_box.clickedButton()
        if clicked_button is cancel_button:
            return None
        return clicked_button is separate_button

    def _folder_tree_contains_multi_csv_directory(self, folder_path: Path) -> bool:
        """Return whether any directory in a folder tree contains many CSV files.

        Args:
            folder_path: Root folder selected for import.

        Returns:
            bool: True when at least one directory contains multiple source CSV
            files that could be split into child folders.
        """
        pending_directories = [folder_path]
        while pending_directories:
            current_directory = pending_directories.pop()
            if len(list_source_csv_files(current_directory)) > 1:
                return True
            pending_directories.extend(
                sorted(
                    child_directory
                    for child_directory in current_directory.iterdir()
                    if child_directory.is_dir()
                )
            )
        return False

    def _create_sidebar_folder_item(
        self,
        folder_id: str,
        folder_name: str,
        flashcard_count: int,
        progress_percent: int,
        checked: bool,
    ) -> SidebarFolderItem:
        """Create one folder item for the sidebar list.

        Args:
            folder_id: Folder identifier.
            folder_name: Display name.
            flashcard_count: Number of flashcards in folder.
            progress_percent: Percent of flashcards completed for the folder.
            checked: Whether the item starts checked.

        Returns:
            SidebarFolderItem: Configured tree item.
        """
        return self._sidebar_folders.create_folder_item(
            folder_id,
            folder_name,
            flashcard_count,
            progress_percent,
            checked,
        )

    def _apply_sidebar_item_visual_state(self, item: SidebarFolderItem) -> None:
        """Apply visual cues that keep checked folders easy to identify."""
        self._sidebar_folders.apply_item_visual_state(item)

    def _refresh_sidebar_item_visual_states(self) -> None:
        """Recompute item visuals for current palette/theme values."""
        self._sidebar_folders.refresh_item_visual_states()

    def _folder_item_name(self, item: SidebarFolderItem) -> str:
        """Return folder name without flashcard count suffix."""
        return self._sidebar_folders.folder_item_name(item)

    def _load_folder_flashcards(
        self,
        folder_name: str,
        folder_path: Path,
    ) -> tuple[list[Flashcard], str | None]:
        """Load one folder's flashcards without aborting the whole refresh."""
        return self._folder_catalog_service.load_folder_flashcards(
            folder_name,
            folder_path,
        )

    def _show_folder_load_warning(self, errors: list[str]) -> None:
        """Warn when one or more persisted folders could not be read."""
        if not errors:
            return
        details = "\n".join(f"- {error}" for error in errors)
        QMessageBox.warning(
            self,
            "Load flashcards",
            "Some folders could not be read and were loaded with 0 flashcards:\n"
            f"{details}",
        )

    def _format_sidebar_folder_label(
        self,
        folder_name: str,
        flashcard_count: int,
        progress_percent: int,
    ) -> str:
        """Build sidebar folder label with card count."""
        return self._sidebar_folders.format_folder_label(
            folder_name,
            flashcard_count,
            progress_percent,
        )

    def handle_management_data_changed(
        self,
        preferred_checked_ids: set[str] | None = None,
        preferred_current_folder_id: str | None = None,
    ) -> None:
        """Reload sidebar and current context after folder data changes.

        Args:
            preferred_checked_ids: Folder ids that should remain checked.
            preferred_current_folder_id: Folder id that should remain selected.
        """
        preferred_current_item: SidebarFolderItem | None = None
        expanded_folder_ids = self._sidebar_folders.expanded_folder_ids()
        completion_mode = load_app_settings().wrong_answer_completion_mode
        catalog_result = self._folder_catalog_service.load_catalog(completion_mode)
        self._app_state.replace_folders(
            [
                FolderLibraryState(
                    folder_id=loaded_folder.persisted_folder.id,
                    folder_name=loaded_folder.persisted_folder.name,
                    folder_path=loaded_folder.stored_path,
                    flashcards=loaded_folder.flashcards,
                    selected_indexes=self._app_state.normalized_selected_indexes(
                        loaded_folder.persisted_folder.id,
                        len(loaded_folder.flashcards),
                    ),
                )
                for loaded_folder in catalog_result.folders
            ]
        )
        self.sidebar_folder_list.blockSignals(True)
        self.sidebar_folder_list.clear()
        folder_items_by_id: dict[str, SidebarFolderItem] = {}

        for loaded_folder in catalog_result.folders:
            persisted_folder = loaded_folder.persisted_folder
            parent_item = folder_items_by_id.get(persisted_folder.parent_id)
            is_checked = (
                True
                if preferred_checked_ids is None
                else persisted_folder.id in preferred_checked_ids
                or (parent_item is not None and parent_item.checkState() == Qt.Checked)
            )
            folder_item = self._create_sidebar_folder_item(
                persisted_folder.id,
                persisted_folder.name,
                flashcard_count=len(loaded_folder.flashcards),
                progress_percent=loaded_folder.progress_percent,
                checked=is_checked,
            )
            if parent_item is None:
                self.sidebar_folder_list.addItem(folder_item)
            else:
                parent_item.addChild(folder_item)
                parent_item.setExpanded(
                    parent_item.data(Qt.UserRole) in expanded_folder_ids
                    or preferred_checked_ids is None
                )
            folder_items_by_id[persisted_folder.id] = folder_item
            if persisted_folder.id in expanded_folder_ids or (
                preferred_checked_ids is None
                and folder_item.childCount() > 0
                and persisted_folder.parent_id is None
            ):
                folder_item.setExpanded(True)
            if persisted_folder.id == preferred_current_folder_id:
                preferred_current_item = folder_item

        if self.sidebar_folder_list.count() == 0:
            self.sidebar_folder_list.addItem(
                self._sidebar_folders.create_placeholder_item("No saved folders yet.")
            )
        else:
            if preferred_current_item is None:
                self.sidebar_folder_list.setCurrentRow(0)
            else:
                self.sidebar_folder_list.setCurrentItem(preferred_current_item)
        self.sidebar_folder_list.blockSignals(False)
        self._refresh_loaded_flashcards()
        if self.stacked_widget.currentWidget() is self.management_page:
            editing_folder_id = self._management_controller.editing_folder_id
            if editing_folder_id is not None and self._app_state.has_folder(
                editing_folder_id
            ):
                self.management_page.set_folder_flashcards(
                    editing_folder_id,
                    self._app_state.folder_names_by_id[editing_folder_id],
                    self._app_state.flashcards_by_folder[editing_folder_id],
                    self._app_state.selected_indexes_for_folder(editing_folder_id),
                )
        self.reset_all_progress_button.setEnabled(bool(self.flashcards_by_folder))
        self._update_sidebar_reorder_buttons()
        self._show_folder_load_warning(catalog_result.load_errors)

    def _update_sidebar_reorder_buttons(self) -> None:
        """Enable sidebar reorder buttons when a single folder can move."""
        selected_items = self._selected_folder_items()
        if len(selected_items) != 1:
            self.move_folder_up_button.setEnabled(False)
            self.move_folder_down_button.setEnabled(False)
            return
        selected_item = selected_items[0]
        parent_item = selected_item.parent()
        current_row = (
            parent_item.indexOfChild(selected_item)
            if isinstance(parent_item, SidebarFolderItem)
            else self.sidebar_folder_list.indexOfTopLevelItem(selected_item)
        )
        last_row = (
            parent_item.childCount() - 1
            if isinstance(parent_item, SidebarFolderItem)
            else self.sidebar_folder_list.topLevelItemCount() - 1
        )
        self.move_folder_up_button.setEnabled(current_row > 0)
        self.move_folder_down_button.setEnabled(current_row < last_row)

    def set_navigation_visible(self, visible: bool) -> None:
        """Control navigation visibility for focused timer mode.

        Args:
            visible: Whether navigation controls should be visible.
        """
        self._app_shell_controller.set_navigation_visible(visible)
