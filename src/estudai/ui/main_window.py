"""Main application window."""

import math
import random
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap
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
from estudai.services.settings import (
    get_default_notification_sound_path,
    load_app_settings,
)

from .dialog.notebooklm_import_dialog import NotebookLMCsvImportDialog
from .pages import ManagementPage, SettingsPage, TimerPage


class MainWindow(QMainWindow):
    """Main application window with page navigation."""

    show_flashcard_requested = Signal(object)
    FOLDER_NAME_ROLE = Qt.UserRole + 1

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
        self._active_flashcard_sequence_id = 0
        self._next_flashcard_index = 0
        self._pending_flashcard_phase_callback: Callable[[], None] | None = None
        self._flashcard_phase_remaining_ms = 0
        self._flashcard_sequence_paused = False
        self._flashcard_sound_output: object | None = None
        self._flashcard_sound_player: object | None = None
        self._flashcard_phase_timer = QTimer(self)
        self._flashcard_phase_timer.setSingleShot(True)
        self._flashcard_phase_timer.timeout.connect(
            self._handle_flashcard_phase_timeout
        )
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
        self.timer_page.timer_cycle_completed.connect(self.handle_timer_cycle_completed)
        self.timer_page.flashcard_pause_toggled.connect(
            self.handle_flashcard_pause_toggled
        )
        self.timer_page.stop_requested.connect(self.handle_timer_stop_requested)
        self.show_flashcard_requested.connect(self.show_flashcard_popup)
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
        self.settings_page.save_button.clicked.connect(self.switch_to_timer)

        self.stacked_widget.setCurrentWidget(self.timer_page)
        self.timer_page.set_flashcard_context(self.current_folder_name, 0)
        self.handle_management_data_changed()
        self._update_sidebar_width()
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
        self._apply_sidebar_palette_styles()
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
        self.sidebar_toggle_button.setIcon(
            self._load_navigation_icon(
                theme_names=("open-menu-symbolic", "application-menu"),
                fallback=self._build_menu_navigation_icon(
                    self.sidebar_toggle_button.iconSize()
                ),
            )
        )
        self.settings_button.setIcon(
            self._load_navigation_icon(
                theme_names=("preferences-system", "settings-configure", "settings"),
                fallback=self._build_settings_navigation_icon(
                    self.settings_button.iconSize()
                ),
            )
        )

    def _load_navigation_icon(
        self,
        theme_names: tuple[str, ...],
        fallback: QIcon,
    ) -> QIcon:
        """Return a theme icon when available, else the provided fallback icon."""
        for theme_name in theme_names:
            theme_icon = QIcon.fromTheme(theme_name)
            if not theme_icon.isNull():
                return theme_icon
        return fallback

    def _navigation_icon_color(self) -> QColor:
        """Return icon color with contrast against the current button background."""
        return self.palette().color(QPalette.ButtonText)

    def _build_menu_navigation_icon(self, icon_size: QSize) -> QIcon:
        """Build a deterministic hamburger icon used when no themed icon exists."""
        icon_extent = max(16, min(icon_size.width(), icon_size.height()))
        pixmap = QPixmap(icon_extent, icon_extent)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self._navigation_icon_color())
        pen.setCapStyle(Qt.RoundCap)
        pen.setWidthF(max(1.6, icon_extent * 0.11))
        painter.setPen(pen)

        margin = icon_extent * 0.22
        for y_ratio in (0.30, 0.50, 0.70):
            y_pos = icon_extent * y_ratio
            painter.drawLine(
                QPointF(margin, y_pos), QPointF(icon_extent - margin, y_pos)
            )
        painter.end()
        return QIcon(pixmap)

    def _build_settings_navigation_icon(self, icon_size: QSize) -> QIcon:
        """Build a deterministic cog icon used when no themed icon exists."""
        icon_extent = max(16, min(icon_size.width(), icon_size.height()))
        pixmap = QPixmap(icon_extent, icon_extent)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self._navigation_icon_color())
        pen.setCapStyle(Qt.RoundCap)
        pen.setWidthF(max(1.4, icon_extent * 0.10))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        center = QPointF(icon_extent / 2.0, icon_extent / 2.0)
        outer_radius = icon_extent * 0.34
        inner_radius = icon_extent * 0.14
        tooth_inner = outer_radius * 0.73

        for angle_degrees in range(0, 360, 45):
            angle_radians = math.radians(angle_degrees)
            cos_angle = math.cos(angle_radians)
            sin_angle = math.sin(angle_radians)
            start_point = QPointF(
                center.x() + (tooth_inner * cos_angle),
                center.y() + (tooth_inner * sin_angle),
            )
            end_point = QPointF(
                center.x() + (outer_radius * cos_angle),
                center.y() + (outer_radius * sin_angle),
            )
            painter.drawLine(start_point, end_point)

        painter.drawEllipse(center, outer_radius * 0.62, outer_radius * 0.62)
        painter.drawEllipse(center, inner_radius, inner_radius)
        painter.end()
        return QIcon(pixmap)

    def _apply_sidebar_palette_styles(self) -> None:
        """Apply palette-aware sidebar frame and checkbox styles."""
        palette = self.sidebar.palette()
        border_color = self._blend_colors(
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
            "QListWidget {"
            " selection-background-color: palette(highlight);"
            " selection-color: palette(highlighted-text);"
            "}"
            "QListWidget::item {"
            " show-decoration-selected: 0;"
            "}"
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

    def switch_to_timer(self):
        """Switch to timer page."""
        self.stacked_widget.setCurrentWidget(self.timer_page)
        if not self.timer_page.is_running:
            self.sidebar_toggle_button.setVisible(True)

    def switch_to_management(self) -> None:
        """Switch to flashcard management page."""
        self.stacked_widget.setCurrentWidget(self.management_page)
        self.sidebar.setVisible(False)

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
        if (
            not is_running
            and self.timer_page.flashcard_question_label.isHidden()
            and self.timer_page.flashcard_answer_label.isHidden()
        ):
            self._cancel_flashcard_phase_timer()
            self._flashcard_sequence_paused = False

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
        self._flashcard_sequence_paused = paused
        if paused:
            if self._flashcard_phase_timer.isActive():
                self._flashcard_phase_remaining_ms = max(
                    0, self._flashcard_phase_timer.remainingTime()
                )
                self._flashcard_phase_timer.stop()
            self.timer_page.pause_flashcard_progress()
            return
        if self._pending_flashcard_phase_callback is None:
            return
        if self._flashcard_phase_remaining_ms <= 0:
            self._handle_flashcard_phase_timeout()
            return
        self.timer_page.resume_flashcard_progress(self._flashcard_phase_remaining_ms)
        self._flashcard_phase_timer.start(self._flashcard_phase_remaining_ms)

    def handle_timer_stop_requested(self) -> None:
        """Reset flashcard ordering when user clicks the Stop button."""
        self._reset_flashcard_sequence_order()

    def _start_flashcard_phase_timer(
        self, duration_milliseconds: int, callback: Callable[[], None]
    ) -> None:
        """Start single-shot phase timer used by flashcard question/answer flow.

        Args:
            duration_milliseconds: Delay before callback runs.
            callback: Action to run when delay completes.
        """
        self._flashcard_phase_timer.stop()
        self._pending_flashcard_phase_callback = callback
        self._flashcard_phase_remaining_ms = max(0, int(duration_milliseconds))
        if self._flashcard_phase_remaining_ms <= 0:
            self._handle_flashcard_phase_timeout()
            return
        self._flashcard_phase_timer.start(self._flashcard_phase_remaining_ms)

    def _handle_flashcard_phase_timeout(self) -> None:
        """Run pending flashcard phase callback when phase timer finishes."""
        callback = self._pending_flashcard_phase_callback
        self._pending_flashcard_phase_callback = None
        self._flashcard_phase_remaining_ms = 0
        if callback is not None:
            callback()

    def _cancel_flashcard_phase_timer(self) -> None:
        """Stop and clear pending flashcard phase callbacks."""
        self._flashcard_phase_timer.stop()
        self._pending_flashcard_phase_callback = None
        self._flashcard_phase_remaining_ms = 0

    def _reset_flashcard_sequence_order(self) -> None:
        """Reset sequential flashcard pointer to the first card."""
        self._next_flashcard_index = 0

    def handle_timer_cycle_completed(self) -> None:
        """Handle timer completion with probability-based flashcard triggering."""
        app_settings = load_app_settings()
        if random.randint(1, 100) > app_settings.flashcard_probability_percent:
            self.timer_page.restart_timer_cycle()
            return
        if not self.selected_folder_ids:
            QMessageBox.warning(
                self,
                "Timer",
                "No folders selected. Select at least one folder to show flashcards.",
            )
            self.timer_page.restart_timer_cycle()
            return
        if not self.loaded_flashcards:
            QMessageBox.warning(
                self,
                "Timer",
                "No flashcards are available in selected folders. Timer restarted.",
            )
            self.timer_page.restart_timer_cycle()
            return
        flashcard = self._next_flashcard_for_display(
            random_order=app_settings.flashcard_random_order_enabled
        )
        if flashcard is None:
            self.timer_page.restart_timer_cycle()
            return
        self.show_flashcard_requested.emit(flashcard)

    def _next_flashcard_for_display(self, *, random_order: bool) -> Flashcard | None:
        """Return next flashcard for current cycle and advance when sequential.

        Args:
            random_order: Whether to pick a random flashcard.

        Returns:
            Flashcard | None: Selected flashcard if available.
        """
        if not self.loaded_flashcards:
            return None
        if random_order:
            return random.choice(self.loaded_flashcards)
        flashcard = self.loaded_flashcards[
            self._next_flashcard_index % len(self.loaded_flashcards)
        ]
        self._next_flashcard_index = (self._next_flashcard_index + 1) % len(
            self.loaded_flashcards
        )
        return flashcard

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
            lambda: self._finish_flashcard_sequence(sequence_id),
        )

    def _finish_flashcard_sequence(self, sequence_id: int) -> None:
        """Clear flashcard content and restart timer after answer phase."""
        if (
            sequence_id != self._active_flashcard_sequence_id
            or self.timer_page.is_running
            or (
                self.timer_page.flashcard_question_label.isHidden()
                and self.timer_page.flashcard_answer_label.isHidden()
            )
        ):
            return
        self._cancel_flashcard_phase_timer()
        self._flashcard_sequence_paused = False
        self.timer_page.clear_flashcard_display()
        self.timer_page.restart_timer_cycle()

    def show_flashcard_popup(self, flashcard: object) -> None:
        """Show flashcard question/answer inside timer page.

        Args:
            flashcard: Flashcard payload emitted from timer completion.
        """
        if not isinstance(flashcard, Flashcard):
            return
        app_settings = load_app_settings()
        self._cancel_flashcard_phase_timer()
        self._flashcard_sequence_paused = False
        self._active_flashcard_sequence_id += 1
        sequence_id = self._active_flashcard_sequence_id
        self.switch_to_timer()
        self.set_navigation_visible(False)
        self.timer_page.show_flashcard_question(
            flashcard.question,
            app_settings.question_display_duration_seconds,
        )
        self._play_flashcard_notification_sound()
        self._start_flashcard_phase_timer(
            app_settings.question_display_duration_seconds * 1000,
            lambda: self._show_flashcard_answer(
                sequence_id,
                flashcard.answer,
                app_settings.answer_display_duration_seconds,
            ),
        )

    def toggle_sidebar(self):
        """Show or hide the left sidebar."""
        if self.sidebar.isHidden():
            self._position_sidebar()
            self.sidebar.setVisible(True)
            return
        self.sidebar.setVisible(False)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle keyboard shortcuts scoped to the main window.

        Args:
            event: Key event to process.
        """
        if (
            event.key() == Qt.Key_Space
            and self.stacked_widget.currentWidget() is self.timer_page
        ):
            if self.timer_page.start_button.isEnabled():
                self.timer_page.start_timer()
            elif self.timer_page.pause_button.isEnabled():
                self.timer_page.pause_timer()
            event.accept()
            return
        super().keyPressEvent(event)

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
            checked_folder_names.append(self._folder_item_name(item))
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
        self._reset_flashcard_sequence_order()
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
        if self._renaming_folder_id is not None:
            self.handle_management_data_changed(
                preferred_checked_ids=self._get_checked_folder_ids()
            )
        self._clear_rename_tracking()

    def handle_sidebar_folder_click(self, clicked_item: QListWidgetItem):
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
        self._renaming_original_name = self._folder_item_name(folder_item)
        folder_item.setText(self._renaming_original_name)
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
                self.open_management_for_folder(
                    folder_id, self._folder_item_name(folder_item)
                )
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
        folder_item = QListWidgetItem(
            self._format_sidebar_folder_label(folder_name, flashcard_count)
        )
        folder_item.setData(Qt.UserRole, folder_id)
        folder_item.setData(self.FOLDER_NAME_ROLE, folder_name)
        folder_item.setFlags(
            folder_item.flags()
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
        )
        folder_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._apply_sidebar_item_visual_state(folder_item)
        return folder_item

    def _apply_sidebar_item_visual_state(self, item: QListWidgetItem) -> None:
        """Apply visual cues that keep checked folders easy to identify."""
        if not self._is_folder_item(item):
            return
        is_checked = item.checkState() == Qt.Checked
        item_font = item.font()
        item_font.setBold(is_checked)
        item.setFont(item_font)
        item.setData(Qt.ForegroundRole, None)
        item.setData(Qt.BackgroundRole, None)

    @staticmethod
    def _blend_colors(base: QColor, overlay: QColor, overlay_ratio: float) -> QColor:
        """Return a deterministic blend between base and overlay colors."""
        clamped_ratio = max(0.0, min(1.0, overlay_ratio))
        base_ratio = 1.0 - clamped_ratio
        return QColor(
            int((base.red() * base_ratio) + (overlay.red() * clamped_ratio)),
            int((base.green() * base_ratio) + (overlay.green() * clamped_ratio)),
            int((base.blue() * base_ratio) + (overlay.blue() * clamped_ratio)),
        )

    def _refresh_sidebar_item_visual_states(self) -> None:
        """Recompute item visuals for current palette/theme values."""
        for index in range(self.sidebar_folder_list.count()):
            self._apply_sidebar_item_visual_state(self.sidebar_folder_list.item(index))

    def _folder_item_name(self, item: QListWidgetItem) -> str:
        """Return folder name without flashcard count suffix."""
        folder_name = item.data(self.FOLDER_NAME_ROLE)
        return folder_name if isinstance(folder_name, str) else item.text()

    def _format_sidebar_folder_label(
        self, folder_name: str, flashcard_count: int
    ) -> str:
        """Build sidebar folder label with card count."""
        card_word = "card" if flashcard_count == 1 else "cards"
        return f"{folder_name} ({flashcard_count} {card_word})"

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
                flashcard_count=len(folder_flashcards),
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
