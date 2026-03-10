"""Main application window."""

import random
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QSize,
    QTimer,
    Qt,
    QUrl,
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
    QListWidget,
    QListWidgetItem,
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
    delete_flashcards_from_folder,
    load_flashcards_from_folder,
    replace_flashcards_in_folder,
    update_flashcard_in_folder,
)
from estudai.services.folder_storage import (
    create_managed_folder,
    delete_persisted_folder,
    import_folder,
    list_persisted_folders,
    move_persisted_folder,
    rename_persisted_folder,
)
from estudai.services.hotkeys import (
    DEFAULT_HOTKEY_BINDINGS,
    GlobalHotkeyService,
    HotkeyAction,
    HotkeyRegistrationError,
)
from estudai.services.settings import (
    AppSettings,
    get_default_notification_sound_path,
    hotkey_bindings_from_settings,
    load_app_settings,
    save_app_settings,
)
from estudai.ui.utils import (
    NativeCheckboxDelegate,
    blend_colors,
    left_aligned_checkbox_rect,
)

from .dialog import FlashcardEditDialog, NotebookLMCsvImportDialog
from .flashcard_sequence import FlashcardSequenceController
from .folder_context import (
    CheckedFolderData,
    build_folder_selection_context,
    merge_imported_flashcard_indexes,
    normalize_selected_indexes,
)
from .navigation_icons import (
    build_menu_navigation_icon,
    build_settings_navigation_icon,
    load_navigation_icon,
)
from .pages import ManagementPage, SettingsPage, TimerPage
from .sidebar_folders import SidebarFolderController
from .study_session import StudySessionController


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


@dataclass(frozen=True)
class CurrentFlashcardLocation:
    """Location metadata for the active flashcard across UI and storage."""

    session_flashcard_index: int
    folder_id: str
    folder_flashcard_index: int
    folder_path: Path
    flashcard: Flashcard


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    show_flashcard_requested = Signal(object)
    global_hotkey_action_requested = Signal(str)
    FOLDER_NAME_ROLE = Qt.UserRole + 1

    def __init__(self, hotkey_service: GlobalHotkeyService | None = None) -> None:
        super().__init__()
        self.flashcards_by_folder: dict[str, list[Flashcard]] = {}
        self.persisted_folder_paths: dict[str, Path] = {}
        self.selected_flashcard_indexes_by_folder: dict[str, set[int]] = {}
        self.loaded_flashcards: list[Flashcard] = []
        self.selected_folder_ids: set[str] = set()
        self.current_folder_id: str | None = None
        self.current_folder_name = "No folders selected"
        self._editing_folder_id: str | None = None
        self._study_session = StudySessionController()
        self._pending_flashcard_score: str | None = None
        self._visible_flashcard: Flashcard | None = None
        self._flashcard_sound_output: object | None = None
        self._flashcard_sound_player: object | None = None
        self._hotkey_service = hotkey_service or GlobalHotkeyService()
        flashcard_phase_timer = QTimer(self)
        flashcard_phase_timer.setSingleShot(True)
        flashcard_phase_timer.timeout.connect(self._handle_flashcard_phase_timeout)
        self._flashcard_sequence = FlashcardSequenceController(flashcard_phase_timer)
        if QAudioOutput is not None and QMediaPlayer is not None:
            self._flashcard_sound_output = QAudioOutput(self)
            self._flashcard_sound_player = QMediaPlayer(self)
            self._flashcard_sound_player.setAudioOutput(self._flashcard_sound_output)
        self.setWindowTitle("Estudai!")
        self.setGeometry(100, 100, 900, 650)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self._build_sidebar(root_layout)
        self._build_content_area(root_layout)
        self._configure_window_shortcuts()

        app_settings = load_app_settings()
        self.timer_page = TimerPage(
            default_duration_seconds=app_settings.timer_duration_seconds
        )
        self.management_page = ManagementPage()
        self.settings_page = SettingsPage(
            save_settings_callback=self._save_settings_from_page
        )
        self.stacked_widget.addWidget(self.timer_page)
        self.stacked_widget.addWidget(self.management_page)
        self.stacked_widget.addWidget(self.settings_page)
        self.timer_page.timer_running_changed.connect(self.handle_timer_running_changed)
        self.timer_page.timer_cycle_completed.connect(self.handle_timer_cycle_completed)
        self.timer_page.flashcard_pause_toggled.connect(
            self.handle_flashcard_pause_toggled
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
            self.management_page.add_empty_flashcard_row
        )
        self.management_page.delete_requested.connect(
            self.delete_selected_flashcards_from_management
        )
        self.management_page.save_button.clicked.connect(self.save_management_changes)
        self.management_page.cancel_button.clicked.connect(self.switch_to_timer)
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

        self.sidebar_folder_list = QListWidget()
        self.sidebar_folder_list.setSpacing(0)
        self.sidebar_folder_list.setUniformItemSizes(True)
        self.sidebar_folder_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.sidebar_folder_list.setEditTriggers(QListWidget.NoEditTriggers)
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
        self._timer_page_pause_resume_shortcut = QShortcut(
            QKeySequence("Space"), self
        )
        self._timer_page_pause_resume_shortcut.setContext(Qt.ApplicationShortcut)
        self._timer_page_pause_resume_shortcut.activated.connect(
            self._trigger_timer_page_pause_resume
        )

        self._timer_page_start_stop_shortcuts = [
            QShortcut(QKeySequence("Return"), self),
            QShortcut(QKeySequence("Enter"), self),
        ]
        for shortcut in self._timer_page_start_stop_shortcuts:
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(self._trigger_timer_page_start_stop)

        self._timer_page_mark_correct_shortcut = QShortcut(QKeySequence("Up"), self)
        self._timer_page_mark_correct_shortcut.setContext(Qt.ApplicationShortcut)
        self._timer_page_mark_correct_shortcut.activated.connect(
            self._trigger_timer_page_mark_correct
        )

        self._timer_page_mark_wrong_shortcut = QShortcut(QKeySequence("Down"), self)
        self._timer_page_mark_wrong_shortcut.setContext(Qt.ApplicationShortcut)
        self._timer_page_mark_wrong_shortcut.activated.connect(
            self._trigger_timer_page_mark_wrong
        )

        self._toggle_fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self._toggle_fullscreen_shortcut.setContext(Qt.ApplicationShortcut)
        self._toggle_fullscreen_shortcut.activated.connect(self.toggle_fullscreen)

        self._exit_fullscreen_shortcut = QShortcut(QKeySequence("Escape"), self)
        self._exit_fullscreen_shortcut.setContext(Qt.ApplicationShortcut)
        self._exit_fullscreen_shortcut.activated.connect(self.exit_fullscreen)

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
            "QListWidget {" " show-decoration-selected: 0;" "}"
        )

    def _update_sidebar_width(self) -> None:
        """Keep sidebar wide enough to read folder names."""
        responsive_width = max(220, min(300, int(self.width() * 0.18)))
        self.sidebar.setFixedWidth(responsive_width)
        self._position_sidebar()

    def _position_sidebar(self) -> None:
        """Place sidebar as an overlay anchored below the sidebar toggle button."""
        central_widget = self.centralWidget()
        if central_widget is None:
            return
        anchor_point = self.sidebar_toggle_button.mapTo(
            central_widget,
            QPoint(0, self.sidebar_toggle_button.height() + 8),
        )
        bottom_margin = 12
        available_height = max(
            120, central_widget.height() - anchor_point.y() - bottom_margin
        )
        self.sidebar.setFixedHeight(available_height)
        self.sidebar.move(anchor_point.x(), anchor_point.y())
        self.sidebar.raise_()

    def switch_to_timer(self) -> None:
        """Switch to timer page."""
        self.stacked_widget.setCurrentWidget(self.timer_page)
        if not self.timer_page.is_running:
            self.sidebar_toggle_button.setVisible(True)

    def switch_to_management(self) -> None:
        """Switch to flashcard management page."""
        self.stacked_widget.setCurrentWidget(self.management_page)
        self.sidebar.setVisible(False)

    def switch_to_settings(self) -> None:
        """Switch to settings page or back to timer when already there."""
        if self.stacked_widget.currentWidget() is self.settings_page:
            self.switch_to_timer()
            return
        self.stacked_widget.setCurrentWidget(self.settings_page)

    def _refresh_sidebar_data(self, checked_ids: set[str]) -> None:
        """Refresh sidebar items while preserving the provided checked ids."""
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

    def _show_warning_message(self, title: str, message: str) -> None:
        """Show a warning dialog using the main window as parent."""
        QMessageBox.warning(self, title, message)

    def _handle_settings_saved(self, _settings: AppSettings) -> None:
        """Return to the timer page after a successful settings save."""
        self.switch_to_timer()

    def handle_timer_running_changed(self, is_running: bool) -> None:
        """Hide editing/navigation controls while timer is active.

        Args:
            is_running: Whether timer is currently running.
        """
        if is_running and not self._study_session.active:
            if not self._start_study_session():
                self.timer_page.stop_timer()
                return
        self.set_navigation_visible(not is_running)
        if (
            not is_running
            and self.timer_page.flashcard_question_label.isHidden()
            and self.timer_page.flashcard_answer_label.isHidden()
        ):
            self._cancel_flashcard_phase_timer()
            self._flashcard_sequence.sequence_paused = False

    def handle_flashcard_pause_toggled(self, paused: bool) -> None:
        """Pause or resume flashcard phase timing.

        Args:
            paused: Whether flashcard progression should be paused.
        """
        if (
            self.timer_page.flashcard_question_label.isHidden()
            and self.timer_page.flashcard_answer_label.isHidden()
        ):
            return
        self._flashcard_sequence.handle_pause_toggle(
            paused,
            flashcard_visible=True,
            pause_progress=self.timer_page.pause_flashcard_progress,
            resume_progress=self.timer_page.resume_flashcard_progress,
            on_timeout=self._handle_flashcard_phase_timeout,
        )

    def handle_timer_stop_requested(self) -> None:
        """Abort the current study session when user clicks Stop."""
        self._reset_study_session_state()

    def _hotkey_action_callbacks(self) -> dict[HotkeyAction, object]:
        """Return thread-safe callbacks that marshal hotkeys into the UI thread."""
        return {
            action: (
                lambda action_value=action.value: self.global_hotkey_action_requested.emit(
                    action_value
                )
            )
            for action in HotkeyAction
        }

    def _apply_initial_hotkey_bindings(self, settings: AppSettings) -> None:
        """Apply persisted hotkeys on startup and fall back to defaults on failure."""
        if self._hotkey_service.availability_error is not None:
            return
        try:
            self._hotkey_service.apply_bindings(
                hotkey_bindings_from_settings(settings),
                self._hotkey_action_callbacks(),
            )
            return
        except HotkeyRegistrationError as error:
            self._show_warning_message("Global hotkeys", str(error))

        fallback_bindings = DEFAULT_HOTKEY_BINDINGS
        try:
            self._hotkey_service.apply_bindings(
                fallback_bindings,
                self._hotkey_action_callbacks(),
            )
        except HotkeyRegistrationError:
            return

    def _save_settings_from_page(self, settings: AppSettings) -> None:
        """Apply live hotkeys before persisting settings to disk."""
        if self._hotkey_service.availability_error is None:
            self._hotkey_service.apply_bindings(
                hotkey_bindings_from_settings(settings),
                self._hotkey_action_callbacks(),
            )
        save_app_settings(settings)

    def _handle_global_hotkey_action_requested(self, action_value: str) -> None:
        """Dispatch a hotkey action onto the same UI paths as button clicks."""
        try:
            action = HotkeyAction(action_value)
        except ValueError:
            return

        if action is HotkeyAction.PAUSE_RESUME:
            self._trigger_timer_page_pause_resume()
            return
        if action is HotkeyAction.START_STOP:
            self._trigger_timer_page_start_stop()
            return
        if action is HotkeyAction.MARK_CORRECT:
            self._trigger_timer_page_mark_correct()
            return
        if action is HotkeyAction.MARK_WRONG:
            self._trigger_timer_page_mark_wrong()

    def _timer_page_is_active(self) -> bool:
        """Return whether timer hotkeys should be active for the current page."""
        return self.stacked_widget.currentWidget() is self.timer_page

    def _trigger_timer_page_pause_resume(self) -> None:
        """Mirror the pause/resume button path for local and global shortcuts."""
        if not self._timer_page_is_active():
            return
        if self.timer_page.pause_button.isEnabled():
            self.timer_page.pause_button.click()

    def _trigger_timer_page_start_stop(self) -> None:
        """Mirror the start/stop button path for local and global shortcuts."""
        if not self._timer_page_is_active():
            return
        if self.timer_page.start_button.isEnabled():
            self.timer_page.start_button.click()
        elif self.timer_page.stop_button.isEnabled():
            self.timer_page.stop_button.click()

    def _trigger_timer_page_mark_correct(self) -> None:
        """Mirror the correct button path for local and global shortcuts."""
        if not self._timer_page_is_active():
            return
        if self.timer_page.correct_button.isEnabled():
            self.timer_page.correct_button.click()

    def _trigger_timer_page_mark_wrong(self) -> None:
        """Mirror the wrong button path for local and global shortcuts."""
        if not self._timer_page_is_active():
            return
        if self.timer_page.wrong_button.isEnabled():
            self.timer_page.wrong_button.click()

    def _start_flashcard_phase_timer(
        self, duration_milliseconds: int, callback
    ) -> None:
        """Start single-shot phase timer used by flashcard question/answer flow.

        Args:
            duration_milliseconds: Delay before callback runs.
            callback: Action to run when delay completes.
        """
        if not self._flashcard_sequence.start_phase_timer(
            duration_milliseconds,
            callback,
        ):
            self._handle_flashcard_phase_timeout()

    def _handle_flashcard_phase_timeout(self) -> None:
        """Run pending flashcard phase callback when phase timer finishes."""
        callback = self._flashcard_sequence.handle_phase_timeout()
        if callback is not None:
            callback()

    def _cancel_flashcard_phase_timer(self) -> None:
        """Stop and clear pending flashcard phase callbacks."""
        self._flashcard_sequence.cancel_phase_timer()

    def _reset_flashcard_sequence_order(self) -> None:
        """Reset sequential flashcard pointer to the first card."""
        self._flashcard_sequence.reset_order()

    def handle_timer_cycle_completed(self) -> None:
        """Advance the current study session when a timer cycle finishes."""
        flashcard = self._next_flashcard_for_display()
        if flashcard is None:
            self._complete_study_session()
            return
        self.show_flashcard_requested.emit(flashcard)

    def _next_flashcard_for_display(self) -> Flashcard | None:
        """Return the next active flashcard for the current study session.

        Returns:
            Flashcard | None: Selected flashcard if available.
        """
        return self._study_session.next_flashcard()

    def _start_study_session(self) -> bool:
        """Create a runtime-only study session for the current flashcard scope."""
        if not self.selected_folder_ids:
            QMessageBox.warning(
                self,
                "Timer",
                "No folders selected. Select at least one folder to start a study session.",
            )
            return False
        if not self.loaded_flashcards:
            QMessageBox.warning(
                self,
                "Timer",
                "No flashcards are available in selected folders. Study session not started.",
            )
            return False
        self._cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self._reset_flashcard_sequence_order()
        self._pending_flashcard_score = None
        app_settings = load_app_settings()
        if not self._study_session.start(
            self.loaded_flashcards,
            wrong_answer_completion_mode=app_settings.wrong_answer_completion_mode,
            wrong_answer_reinsertion_mode=app_settings.wrong_answer_reinsertion_mode,
            wrong_answer_reinsert_after_count=app_settings.wrong_answer_reinsert_after_count,
            random_order=app_settings.flashcard_random_order_enabled,
            choice_func=random.choice,
        ):
            return False
        self._update_study_session_progress()
        return True

    def _update_study_session_progress(self) -> None:
        """Refresh visible study progress for the timer page."""
        progress = self._study_session.progress()
        self.timer_page.set_session_progress(
            completed_count=progress.completed_count,
            remaining_count=progress.remaining_count,
            wrong_pending_count=progress.wrong_pending_count,
            total_count=progress.total_count,
        )

    def _reset_study_session_state(self) -> None:
        """Clear all runtime-only study session state."""
        self._cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self._reset_flashcard_sequence_order()
        self._study_session.reset()
        self._pending_flashcard_score = None
        self._visible_flashcard = None
        self.timer_page.clear_session_progress()

    def _complete_study_session(self) -> None:
        """Stop the timer UI after the active session is fully completed."""
        self._reset_study_session_state()
        self.timer_page.stop_timer()

    def _resolve_current_flashcard_location(self) -> CurrentFlashcardLocation | None:
        """Return folder/storage metadata for the flashcard active in the session."""
        current_flashcard = self._study_session.current_flashcard()
        session_flashcard_index = self._study_session.current_flashcard_index
        if current_flashcard is None or session_flashcard_index is None:
            return None

        for folder_id, folder_flashcards in self.flashcards_by_folder.items():
            try:
                folder_flashcard_index = folder_flashcards.index(current_flashcard)
            except ValueError:
                continue
            folder_path = self.persisted_folder_paths.get(folder_id)
            if folder_path is None:
                continue
            return CurrentFlashcardLocation(
                session_flashcard_index=session_flashcard_index,
                folder_id=folder_id,
                folder_flashcard_index=folder_flashcard_index,
                folder_path=folder_path,
                flashcard=current_flashcard,
            )
        return None

    def _selected_indexes_after_deletion(
        self,
        folder_id: str,
        deleted_flashcard_index: int,
    ) -> set[int]:
        """Return selected indexes after removing one flashcard from a folder."""
        existing_indexes = self.selected_flashcard_indexes_by_folder.get(
            folder_id, set()
        )
        return {
            (
                flashcard_index - 1
                if flashcard_index > deleted_flashcard_index
                else flashcard_index
            )
            for flashcard_index in existing_indexes
            if flashcard_index != deleted_flashcard_index
        }

    def _refresh_flashcard_data_after_mutation(
        self,
        folder_id: str,
        *,
        selected_indexes: set[int] | None = None,
    ) -> None:
        """Reload persisted flashcard data after one folder mutation."""
        checked_ids = self._get_checked_folder_ids()
        if selected_indexes is not None:
            self.selected_flashcard_indexes_by_folder[folder_id] = selected_indexes
            if selected_indexes:
                checked_ids.add(folder_id)
            else:
                checked_ids.discard(folder_id)
        self.handle_management_data_changed(preferred_checked_ids=checked_ids)

    def _sync_session_flashcards_for_folder(
        self,
        previous_folder_flashcards: list[Flashcard],
        updated_folder_flashcards: list[Flashcard],
        *,
        removed_flashcard_index: int | None = None,
    ) -> None:
        """Refresh remaining in-session cards for one mutated folder."""
        replacements: dict[Flashcard, Flashcard] = {}
        for flashcard_index, previous_flashcard in enumerate(
            previous_folder_flashcards
        ):
            if (
                removed_flashcard_index is not None
                and flashcard_index == removed_flashcard_index
            ):
                continue
            updated_index = flashcard_index
            if (
                removed_flashcard_index is not None
                and flashcard_index > removed_flashcard_index
            ):
                updated_index -= 1
            if not (0 <= updated_index < len(updated_folder_flashcards)):
                continue
            replacements[previous_flashcard] = updated_folder_flashcards[updated_index]
        self._study_session.replace_flashcards(replacements)

    def _play_flashcard_notification_sound(self) -> None:
        """Play notification sound configured in settings when available."""
        if self._flashcard_sound_player is None:
            return
        settings = load_app_settings()
        sound_path_value = (
            settings.notification_sound_path or get_default_notification_sound_path()
        )
        if not sound_path_value:
            return
        sound_path = Path(sound_path_value)
        if not sound_path.exists():
            return
        self._flashcard_sound_player.setSource(QUrl.fromLocalFile(str(sound_path)))
        self._flashcard_sound_player.play()

    def _show_current_flashcard_answer(
        self,
        sequence_id: int,
        answer_display_duration_seconds: int,
    ) -> None:
        """Show the current session flashcard answer using live session data."""
        current_flashcard = self._study_session.current_flashcard()
        if current_flashcard is None:
            current_flashcard = self._visible_flashcard
        if current_flashcard is None:
            return
        self._show_flashcard_answer(
            sequence_id,
            current_flashcard.answer,
            answer_display_duration_seconds,
        )

    def _show_flashcard_answer(
        self,
        sequence_id: int,
        answer: str,
        answer_display_duration_seconds: int,
    ) -> None:
        """Show answer phase for active flashcard sequence."""
        if (
            sequence_id != self._active_flashcard_sequence_id
            or self.timer_page.is_running
            or self.timer_page.flashcard_question_label.isHidden()
        ):
            return
        self.timer_page.show_flashcard_answer(answer, answer_display_duration_seconds)
        self._play_flashcard_notification_sound()
        self._start_flashcard_phase_timer(
            answer_display_duration_seconds * 1000,
            lambda: self._finish_flashcard_answer_phase(sequence_id),
        )

    def _finish_flashcard_answer_phase(self, sequence_id: int) -> None:
        """Apply the queued answer choice only after the answer timer finishes."""
        if (
            sequence_id != self._active_flashcard_sequence_id
            or self.timer_page.is_running
            or (
                self.timer_page.flashcard_question_label.isHidden()
                and self.timer_page.flashcard_answer_label.isHidden()
            )
        ):
            return
        self._study_session.apply_current_score(self._pending_flashcard_score)
        self._advance_after_flashcard_score()

    def show_flashcard_popup(self, flashcard: object) -> None:
        """Show flashcard question/answer inside timer page.

        Args:
            flashcard: Flashcard payload emitted from timer completion.
        """
        if not isinstance(flashcard, Flashcard):
            return
        app_settings = load_app_settings()
        self._cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self._pending_flashcard_score = None
        self._visible_flashcard = flashcard
        sequence_id = self._flashcard_sequence.begin_sequence()
        self.switch_to_timer()
        self.set_navigation_visible(False)
        self.timer_page.show_flashcard_question(
            flashcard.question,
            app_settings.question_display_duration_seconds,
        )
        self._play_flashcard_notification_sound()
        self._start_flashcard_phase_timer(
            app_settings.question_display_duration_seconds * 1000,
            lambda: self._show_current_flashcard_answer(
                sequence_id,
                app_settings.answer_display_duration_seconds,
            ),
        )

    def _advance_after_flashcard_score(self) -> None:
        """Continue or finish the session after scoring the current flashcard."""
        self._cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self._pending_flashcard_score = None
        self._visible_flashcard = None
        self._update_study_session_progress()
        if self._study_session.is_complete():
            self._complete_study_session()
            return
        self.timer_page.clear_flashcard_display()
        self.timer_page.restart_timer_cycle()

    def handle_flashcard_marked_correct(self) -> None:
        """Queue the selected Correct state until answer timeout."""
        if self._study_session.current_flashcard() is None:
            return
        self._pending_flashcard_score = self.timer_page.selected_flashcard_score()

    def handle_flashcard_marked_wrong(self) -> None:
        """Queue the selected Wrong state until answer timeout."""
        if self._study_session.current_flashcard() is None:
            return
        self._pending_flashcard_score = self.timer_page.selected_flashcard_score()

    def handle_flashcard_edit_requested(self) -> None:
        """Edit the paused flashcard and update the active session immediately."""
        location = self._resolve_current_flashcard_location()
        if location is None:
            QMessageBox.warning(
                self,
                "Edit flashcard",
                "The current flashcard is unavailable. Refresh and try again.",
            )
            return

        dialog = FlashcardEditDialog(
            location.flashcard.question,
            location.flashcard.answer,
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        previous_folder_flashcards = list(
            self.flashcards_by_folder.get(location.folder_id, [])
        )
        try:
            updated_flashcards = update_flashcard_in_folder(
                location.folder_path,
                location.folder_flashcard_index,
                dialog.question_text(),
                dialog.answer_text(),
            )
        except (IndexError, ValueError) as error:
            QMessageBox.warning(self, "Edit flashcard", str(error))
            self._refresh_flashcard_data_after_mutation(location.folder_id)
            return

        updated_flashcard = updated_flashcards[location.folder_flashcard_index]
        if not self._study_session.replace_current_flashcard(updated_flashcard):
            QMessageBox.warning(
                self,
                "Edit flashcard",
                "The current study session is no longer active.",
            )
            return
        self._sync_session_flashcards_for_folder(
            previous_folder_flashcards,
            updated_flashcards,
        )
        self._refresh_flashcard_data_after_mutation(location.folder_id)
        self._visible_flashcard = updated_flashcard
        self.timer_page.update_displayed_flashcard(
            updated_flashcard.question,
            updated_flashcard.answer,
        )

    def handle_flashcard_delete_requested(self) -> None:
        """Delete the paused flashcard and remove it from the active session."""
        location = self._resolve_current_flashcard_location()
        if location is None:
            QMessageBox.warning(
                self,
                "Delete flashcard",
                "The current flashcard is unavailable. Refresh and try again.",
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Delete flashcard",
            "Delete the current flashcard?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return

        previous_folder_flashcards = list(
            self.flashcards_by_folder.get(location.folder_id, [])
        )
        try:
            updated_flashcards = delete_flashcards_from_folder(
                location.folder_path,
                [location.folder_flashcard_index],
            )
        except IndexError as error:
            QMessageBox.warning(self, "Delete flashcard", str(error))
            self._refresh_flashcard_data_after_mutation(location.folder_id)
            return

        selected_indexes = self._selected_indexes_after_deletion(
            location.folder_id,
            location.folder_flashcard_index,
        )
        self._cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self._pending_flashcard_score = None
        self._visible_flashcard = None
        if not self._study_session.remove_current_flashcard():
            QMessageBox.warning(
                self,
                "Delete flashcard",
                "The current study session is no longer active.",
            )
            self._refresh_flashcard_data_after_mutation(
                location.folder_id,
                selected_indexes=selected_indexes,
            )
            return
        self._sync_session_flashcards_for_folder(
            previous_folder_flashcards,
            updated_flashcards,
            removed_flashcard_index=location.folder_flashcard_index,
        )
        self._refresh_flashcard_data_after_mutation(
            location.folder_id,
            selected_indexes=selected_indexes,
        )
        self._update_study_session_progress()
        if self._study_session.progress().remaining_count <= 0:
            self._complete_study_session()
            return
        self.timer_page.prepare_next_timer_cycle_paused()

    def toggle_sidebar(self) -> None:
        """Show or hide the left sidebar."""
        if self.sidebar.isHidden():
            self._position_sidebar()
            self.sidebar.setVisible(True)
            return
        self.sidebar.setVisible(False)

    def toggle_fullscreen(self) -> None:
        """Toggle between fullscreen and normal window modes."""
        if self.isFullScreen():
            self.showNormal()
            return
        self.showFullScreen()

    def exit_fullscreen(self) -> None:
        """Leave fullscreen mode when currently active."""
        if self.isFullScreen():
            self.showNormal()

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

    def closeEvent(self, event) -> None:  # noqa: N802
        """Release global hotkeys and app-wide filters when closing the window."""
        self._hotkey_service.clear()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def _is_folder_item(self, item: QListWidgetItem | None) -> bool:
        """Return whether a sidebar item maps to a persisted folder.

        Args:
            item: Sidebar item.

        Returns:
            bool: True when item represents a folder.
        """
        return self._sidebar_folders.is_folder_item(item)

    def _selected_folder_items(self) -> list[QListWidgetItem]:
        """Return selected list items that map to persisted folders.

        Returns:
            list[QListWidgetItem]: Selected folder items.
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

    def _refresh_loaded_flashcards(self) -> None:
        """Refresh selected flashcards from checked folders."""
        checked_folders: list[CheckedFolderData] = []
        for item in self._iter_sidebar_folder_items():
            folder_id = item.data(Qt.UserRole)
            if folder_id is None or item.checkState() != Qt.Checked:
                continue
            folder_flashcards = self.flashcards_by_folder.get(folder_id, [])
            checked_folders.append(
                CheckedFolderData(
                    folder_id=folder_id,
                    folder_name=self._folder_item_name(item),
                    flashcards=folder_flashcards,
                    selected_indexes=self.selected_flashcard_indexes_by_folder.get(
                        folder_id,
                        set(range(len(folder_flashcards))),
                    ),
                )
            )

        selection_context = build_folder_selection_context(checked_folders)
        self.selected_folder_ids = selection_context.selected_folder_ids
        self.current_folder_id = selection_context.current_folder_id
        self.current_folder_name = selection_context.current_folder_name
        self.loaded_flashcards = selection_context.loaded_flashcards
        self._reset_flashcard_sequence_order()
        self.timer_page.set_flashcard_context(
            self.current_folder_name,
            len(self.loaded_flashcards),
        )
        if not self._study_session.active:
            self.timer_page.clear_session_progress()

    def handle_sidebar_item_changed(self, item: QListWidgetItem) -> None:
        """Handle sidebar item updates (checkbox and inline rename).

        Args:
            item: Updated sidebar item.
        """
        if not self._is_folder_item(item):
            return
        self._apply_sidebar_item_visual_state(item)
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

    def handle_sidebar_folder_click(self, clicked_item: QListWidgetItem) -> None:
        """Handle folder clicks without forcing page navigation.

        Args:
            clicked_item: The clicked folder list item.
        """
        if not self._is_folder_item(clicked_item):
            return

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
        self._sidebar_folders.begin_rename(folder_item)

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

    def move_selected_sidebar_folder_up(self) -> None:
        """Move the selected sidebar folder one position upward."""
        self._move_selected_sidebar_folder(-1)

    def move_selected_sidebar_folder_down(self) -> None:
        """Move the selected sidebar folder one position downward."""
        self._move_selected_sidebar_folder(1)

    def _move_selected_sidebar_folder(self, offset: int) -> None:
        """Persist moving the selected sidebar folder by one position."""
        selected_items = self._selected_folder_items()
        if len(selected_items) != 1:
            return
        folder_item = selected_items[0]
        folder_id = folder_item.data(Qt.UserRole)
        if folder_id is None:
            return
        current_row = self.sidebar_folder_list.row(folder_item)
        target_row = current_row + offset
        if not (0 <= target_row < self.sidebar_folder_list.count()):
            return
        checked_ids = self._get_checked_folder_ids()
        try:
            move_persisted_folder(folder_id, target_row)
        except (KeyError, IndexError) as error:
            QMessageBox.warning(self, "Move folder", str(error))
            self.handle_management_data_changed(preferred_checked_ids=checked_ids)
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
        self.selected_flashcard_indexes_by_folder[target_folder_id] = (
            merge_imported_flashcard_indexes(
                len(existing_flashcards),
                len(valid_rows),
                selected_indexes,
            )
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
                self.open_management_for_folder(
                    folder_id, self._folder_item_name(folder_item)
                )
                return
        checked_items = [
            item
            for item in self._iter_sidebar_folder_items()
            if item.checkState() == Qt.Checked
        ]
        if len(checked_items) == 1:
            folder_item = checked_items[0]
            folder_id = folder_item.data(Qt.UserRole)
            if folder_id is not None:
                self.open_management_for_folder(
                    folder_id, self._folder_item_name(folder_item)
                )
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
        if selected_indexes:
            checked_ids.add(self._editing_folder_id)
        else:
            checked_ids.discard(self._editing_folder_id)
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
        self, folder_id: str, folder_name: str, flashcard_count: int, checked: bool
    ) -> QListWidgetItem:
        """Create one folder item for the sidebar list.

        Args:
            folder_id: Folder identifier.
            folder_name: Display name.
            flashcard_count: Number of flashcards in folder.
            checked: Whether the item starts checked.

        Returns:
            QListWidgetItem: Configured list item.
        """
        return self._sidebar_folders.create_folder_item(
            folder_id,
            folder_name,
            flashcard_count,
            checked,
        )

    def _apply_sidebar_item_visual_state(self, item: QListWidgetItem) -> None:
        """Apply visual cues that keep checked folders easy to identify."""
        self._sidebar_folders.apply_item_visual_state(item)

    def _refresh_sidebar_item_visual_states(self) -> None:
        """Recompute item visuals for current palette/theme values."""
        self._sidebar_folders.refresh_item_visual_states()

    def _folder_item_name(self, item: QListWidgetItem) -> str:
        """Return folder name without flashcard count suffix."""
        return self._sidebar_folders.folder_item_name(item)

    def _format_sidebar_folder_label(
        self, folder_name: str, flashcard_count: int
    ) -> str:
        """Build sidebar folder label with card count."""
        return self._sidebar_folders.format_folder_label(folder_name, flashcard_count)

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
        self.flashcards_by_folder = {}
        self.persisted_folder_paths = {}
        remaining_folder_ids: set[str] = set()
        preferred_current_row: int | None = None
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
            self.selected_flashcard_indexes_by_folder[persisted_folder.id] = (
                normalize_selected_indexes(
                    self.selected_flashcard_indexes_by_folder.get(persisted_folder.id),
                    len(folder_flashcards),
                )
            )
            is_checked = (
                True
                if preferred_checked_ids is None
                else persisted_folder.id in preferred_checked_ids
            )
            folder_item = self._create_sidebar_folder_item(
                persisted_folder.id,
                persisted_folder.name,
                flashcard_count=len(folder_flashcards),
                checked=is_checked,
            )
            self.sidebar_folder_list.addItem(folder_item)
            if persisted_folder.id == preferred_current_folder_id:
                preferred_current_row = self.sidebar_folder_list.count() - 1

        if self.sidebar_folder_list.count() == 0:
            empty_item = QListWidgetItem("No saved folders yet.")
            empty_item.setFlags(Qt.NoItemFlags)
            self.sidebar_folder_list.addItem(empty_item)
        else:
            self.sidebar_folder_list.setCurrentRow(
                0 if preferred_current_row is None else preferred_current_row
            )
        self.sidebar_folder_list.blockSignals(False)
        self.selected_flashcard_indexes_by_folder = {
            folder_id: indexes
            for folder_id, indexes in self.selected_flashcard_indexes_by_folder.items()
            if folder_id in remaining_folder_ids
        }
        self._refresh_loaded_flashcards()
        self._update_sidebar_reorder_buttons()

    def _update_sidebar_reorder_buttons(self) -> None:
        """Enable sidebar reorder buttons when a single folder can move."""
        selected_items = self._selected_folder_items()
        if len(selected_items) != 1:
            self.move_folder_up_button.setEnabled(False)
            self.move_folder_down_button.setEnabled(False)
            return
        current_row = self.sidebar_folder_list.row(selected_items[0])
        last_row = self.sidebar_folder_list.count() - 1
        self.move_folder_up_button.setEnabled(current_row > 0)
        self.move_folder_down_button.setEnabled(current_row < last_row)

    def set_navigation_visible(self, visible: bool) -> None:
        """Control navigation visibility for focused timer mode.

        Args:
            visible: Whether navigation controls should be visible.
        """
        self.sidebar_toggle_button.setVisible(visible)
        self.settings_button.setVisible(visible)
        if not visible:
            self.sidebar.setVisible(False)

    @property
    def _renaming_folder_id(self) -> str | None:
        """Compatibility proxy for sidebar inline rename id."""
        return self._sidebar_folders.renaming_folder_id

    @_renaming_folder_id.setter
    def _renaming_folder_id(self, value: str | None) -> None:
        self._sidebar_folders.renaming_folder_id = value

    @property
    def _renaming_original_name(self) -> str | None:
        """Compatibility proxy for sidebar inline rename original name."""
        return self._sidebar_folders.renaming_original_name

    @_renaming_original_name.setter
    def _renaming_original_name(self, value: str | None) -> None:
        self._sidebar_folders.renaming_original_name = value

    @property
    def _active_flashcard_sequence_id(self) -> int:
        """Compatibility proxy for flashcard sequence id."""
        return self._flashcard_sequence.active_sequence_id

    @_active_flashcard_sequence_id.setter
    def _active_flashcard_sequence_id(self, value: int) -> None:
        self._flashcard_sequence.active_sequence_id = value

    @property
    def _next_flashcard_index(self) -> int:
        """Compatibility proxy for sequential flashcard index."""
        return self._flashcard_sequence.next_flashcard_index

    @_next_flashcard_index.setter
    def _next_flashcard_index(self, value: int) -> None:
        self._flashcard_sequence.next_flashcard_index = value

    @property
    def _pending_flashcard_phase_callback(self):
        """Compatibility proxy for pending flashcard callback."""
        return self._flashcard_sequence.pending_phase_callback

    @_pending_flashcard_phase_callback.setter
    def _pending_flashcard_phase_callback(self, callback) -> None:
        self._flashcard_sequence.pending_phase_callback = callback

    @property
    def _flashcard_phase_remaining_ms(self) -> int:
        """Compatibility proxy for remaining flashcard phase time."""
        return self._flashcard_sequence.phase_remaining_ms

    @_flashcard_phase_remaining_ms.setter
    def _flashcard_phase_remaining_ms(self, value: int) -> None:
        self._flashcard_sequence.phase_remaining_ms = value

    @property
    def _flashcard_sequence_paused(self) -> bool:
        """Compatibility proxy for paused flashcard state."""
        return self._flashcard_sequence.sequence_paused

    @_flashcard_sequence_paused.setter
    def _flashcard_sequence_paused(self, value: bool) -> None:
        self._flashcard_sequence.sequence_paused = value

    @property
    def _flashcard_phase_timer(self):
        """Compatibility proxy for the underlying phase timer."""
        return self._flashcard_sequence.phase_timer

    @_flashcard_phase_timer.setter
    def _flashcard_phase_timer(self, value) -> None:
        self._flashcard_sequence.phase_timer = value
