"""Timer page."""

from collections.abc import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QTime,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPalette, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QGraphicsOpacityEffect,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from estudai.services.settings import MAX_TIMER_DURATION_SECONDS
from estudai.ui.utils import (
    blend_colors,
    format_card_count,
    has_inline_latex,
    render_inline_latex_html,
    set_muted_label_color,
)


class _ClickableLabel(QLabel):
    """QLabel variant that emits a signal when the user clicks it."""

    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Emit ``clicked`` on left-button release, then continue default handling.

        Args:
            event: Mouse event delivered by Qt.
        """
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class TimerPage(QWidget):
    """Timer page for study sessions."""

    timer_running_changed = Signal(bool)
    timer_cycle_completed = Signal()
    flashcard_pause_toggled = Signal(bool)
    flashcard_queue_shuffle_requested = Signal()
    flashcard_phase_skip_requested = Signal()
    flashcard_marked_correct = Signal()
    flashcard_marked_wrong = Signal()
    flashcard_origin_requested = Signal()
    flashcard_edit_requested = Signal()
    flashcard_delete_requested = Signal()
    stop_requested = Signal()

    _FLASHCARD_QUESTION_BASE_POINT_SIZE = 40
    _FLASHCARD_ANSWER_BASE_POINT_SIZE = 34
    _FLASHCARD_IMAGE_MAX_HEIGHT = 220
    _FLASHCARD_IMAGE_MIN_HEIGHT = 80
    _IMAGE_PATH_UNCHANGED = object()
    _PRIMARY_CONTROL_BUTTON_MIN_WIDTH = 110
    _SCORE_ACTION_BUTTON_MIN_WIDTH = 84
    _SCORE_ACTION_BUTTON_HEIGHT = 44

    def __init__(self, default_duration_seconds: int = 25 * 60):
        super().__init__()
        self._default_duration_seconds = max(
            0,
            min(MAX_TIMER_DURATION_SECONDS, int(default_duration_seconds)),
        )
        self.time = self._default_time()
        self.is_running = False
        self._flashcard_controls_active = False
        self._flashcard_paused = False
        self._flashcard_phase_animation: QPropertyAnimation | None = None
        self._flashcard_progress_active = False
        self._selected_flashcard_score: str | None = None
        self._current_flashcard_question: str = ""
        self._current_flashcard_answer: str = ""
        self._current_question_image_path: str | None = None
        self._current_answer_image_path: str | None = None
        self._current_flashcard_origin_path: str | None = None
        self._flashcard_origin_clickable = False
        self._folder_name: str = "No folders selected"
        self._card_count: int = 0
        self._session_progress_text: str = ""
        self._queue_shuffle_available = False
        self._copy_feedback_animation: QPropertyAnimation | None = None
        self._updating_flashcard_content_presentation = False
        self.init_ui()

    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.content_stack = QStackedWidget()
        self.content_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.content_stack.setMinimumHeight(260)

        timer_view = QWidget()
        timer_layout = QVBoxLayout(timer_view)
        timer_layout.setContentsMargins(0, 0, 0, 0)
        timer_layout.setSpacing(0)
        timer_layout.addStretch(1)
        self.timer_display = QLabel(self._idle_timer_display_text())
        timer_font = QFont(self.timer_display.font())
        timer_font.setPointSize(74)
        timer_font.setWeight(QFont.ExtraBold)
        self.timer_display.setFont(timer_font)
        self.timer_display.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.timer_display)
        timer_layout.addStretch(1)
        self.content_stack.addWidget(timer_view)

        flashcard_view = QWidget()
        self._flashcard_view = flashcard_view
        flashcard_layout = QVBoxLayout(flashcard_view)
        flashcard_layout.setContentsMargins(0, 0, 0, 0)
        flashcard_layout.setSpacing(10)
        self.flashcard_header_container = QWidget()
        flashcard_header_layout = QHBoxLayout(self.flashcard_header_container)
        flashcard_header_layout.setContentsMargins(0, 0, 0, 0)
        flashcard_header_layout.setSpacing(10)
        self.flashcard_origin_label = _ClickableLabel("")
        self.flashcard_origin_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.flashcard_origin_label.setWordWrap(True)
        self.flashcard_origin_label.setTextFormat(Qt.PlainText)
        self.flashcard_origin_label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.flashcard_origin_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.flashcard_origin_label.setVisible(False)
        self.flashcard_origin_label.clicked.connect(
            self._handle_flashcard_origin_clicked
        )
        origin_label_font = QFont(self.flashcard_origin_label.font())
        origin_label_font.setPointSize(11)
        self.flashcard_origin_label.setFont(origin_label_font)
        flashcard_header_layout.addWidget(self.flashcard_origin_label, 1)
        flashcard_header_layout.addStretch(1)
        self.flashcard_actions_container = QWidget()
        self._retain_size_when_hidden(self.flashcard_actions_container)
        flashcard_actions_layout = QHBoxLayout(self.flashcard_actions_container)
        flashcard_actions_layout.setContentsMargins(0, 0, 0, 0)
        flashcard_actions_layout.setSpacing(14)
        flashcard_actions_layout.addStretch(1)
        self.correct_button = self._create_score_action_button(
            "✓",
            tooltip="Mark correct",
            score_action="correct",
            clicked_handler=self._handle_correct_button_clicked,
        )
        self.wrong_button = self._create_score_action_button(
            "✕",
            tooltip="Mark wrong",
            score_action="wrong",
            clicked_handler=self._handle_wrong_button_clicked,
        )
        flashcard_actions_layout.addWidget(self.correct_button)
        flashcard_actions_layout.addWidget(self.wrong_button)
        flashcard_actions_layout.addStretch(1)
        self.flashcard_actions_container.setVisible(False)

        self.flashcard_pause_actions_container = QWidget()
        self._retain_size_when_hidden(self.flashcard_pause_actions_container)
        flashcard_pause_actions_layout = QHBoxLayout(
            self.flashcard_pause_actions_container
        )
        flashcard_pause_actions_layout.setContentsMargins(0, 0, 0, 0)
        flashcard_pause_actions_layout.setSpacing(10)
        flashcard_pause_actions_layout.addStretch(1)
        self.skip_phase_button = self._create_button(
            "Skip",
            tooltip="Advance the current flashcard phase",
            clicked_handler=self.flashcard_phase_skip_requested.emit,
            minimum_width=130,
            enabled=False,
        )
        flashcard_pause_actions_layout.addWidget(self.skip_phase_button)
        self.shuffle_queue_button = self._create_button(
            "Shuffle Queue",
            tooltip="Shuffle remaining queue",
            clicked_handler=self.flashcard_queue_shuffle_requested.emit,
            minimum_width=140,
            enabled=False,
            visible=False,
        )
        flashcard_pause_actions_layout.addWidget(self.shuffle_queue_button)
        self.edit_flashcard_button = self._create_button(
            "Edit",
            tooltip="Edit current flashcard",
            clicked_handler=self.flashcard_edit_requested.emit,
            minimum_width=self._PRIMARY_CONTROL_BUTTON_MIN_WIDTH,
            enabled=False,
        )
        flashcard_pause_actions_layout.addWidget(self.edit_flashcard_button)
        self.delete_flashcard_button = self._create_button(
            "Delete",
            tooltip="Delete current flashcard",
            clicked_handler=self.flashcard_delete_requested.emit,
            minimum_width=self._PRIMARY_CONTROL_BUTTON_MIN_WIDTH,
            enabled=False,
        )
        flashcard_pause_actions_layout.addWidget(self.delete_flashcard_button)
        flashcard_pause_actions_layout.addStretch(1)
        self.flashcard_pause_actions_container.setVisible(False)
        flashcard_header_layout.addWidget(self.flashcard_pause_actions_container)
        flashcard_layout.addWidget(self.flashcard_header_container)
        self.flashcard_content_widget = QWidget()
        self.flashcard_content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.flashcard_content_layout = QVBoxLayout(self.flashcard_content_widget)
        self.flashcard_content_layout.setContentsMargins(8, 0, 8, 0)
        self.flashcard_content_layout.setSpacing(12)
        self.flashcard_content_layout.addStretch(1)
        self.flashcard_question_label = self._create_flashcard_text_label(
            point_size=self._FLASHCARD_QUESTION_BASE_POINT_SIZE,
            weight=QFont.ExtraBold,
        )
        self.flashcard_content_layout.addWidget(self.flashcard_question_label)
        self.flashcard_question_image_label = QLabel("")
        self._configure_flashcard_image_label(self.flashcard_question_image_label)
        self.flashcard_content_layout.addWidget(self.flashcard_question_image_label)

        self.flashcard_answer_label = self._create_flashcard_text_label(
            point_size=self._FLASHCARD_ANSWER_BASE_POINT_SIZE,
            weight=QFont.DemiBold,
        )
        self.flashcard_content_layout.addWidget(self.flashcard_answer_label)
        self.flashcard_answer_image_label = QLabel("")
        self._configure_flashcard_image_label(self.flashcard_answer_image_label)
        self.flashcard_content_layout.addWidget(self.flashcard_answer_image_label)
        self.flashcard_content_layout.addStretch(1)
        flashcard_layout.addWidget(self.flashcard_content_widget, 1)

        self.copy_feedback_label = QLabel("Copied", self._flashcard_view)
        self.copy_feedback_label.setAlignment(Qt.AlignCenter)
        self.copy_feedback_label.setVisible(False)
        self.copy_feedback_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.copy_feedback_label.setStyleSheet(
            "QLabel {"
            " padding: 4px 10px;"
            " border-radius: 10px;"
            " background-color: rgba(60, 60, 60, 170);"
            " color: white;"
            " font-size: 12px;"
            " font-weight: 700;"
            "}"
        )
        self._copy_feedback_effect = QGraphicsOpacityEffect(self.copy_feedback_label)
        self._copy_feedback_effect.setOpacity(0.0)
        self.copy_feedback_label.setGraphicsEffect(self._copy_feedback_effect)
        self.copy_feedback_label.raise_()
        flashcard_layout.addWidget(self.flashcard_actions_container)

        self.content_stack.addWidget(flashcard_view)
        layout.addWidget(self.content_stack)

        self.folder_context_label = QLabel(
            f"Folder: {self._folder_name} ({format_card_count(self._card_count)})"
        )
        self.folder_context_label.setAlignment(Qt.AlignCenter)
        folder_context_font = QFont(self.folder_context_label.font())
        folder_context_font.setPointSize(14)
        self.folder_context_label.setFont(folder_context_font)
        set_muted_label_color(self.folder_context_label)
        layout.addWidget(self.folder_context_label)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        controls_layout.addStretch(1)

        self.start_button = self._create_button(
            "Start",
            tooltip="Start",
            clicked_handler=self.start_timer,
            minimum_width=self._PRIMARY_CONTROL_BUTTON_MIN_WIDTH,
        )
        controls_layout.addWidget(self.start_button)

        self.pause_button = self._create_button(
            "Pause",
            tooltip="Pause",
            clicked_handler=self.pause_timer,
            minimum_width=self._PRIMARY_CONTROL_BUTTON_MIN_WIDTH,
            enabled=False,
        )
        controls_layout.addWidget(self.pause_button)

        self.stop_button = self._create_button(
            "Stop",
            tooltip="Stop",
            clicked_handler=self._handle_stop_button_clicked,
            minimum_width=self._PRIMARY_CONTROL_BUTTON_MIN_WIDTH,
            enabled=False,
        )
        controls_layout.addWidget(self.stop_button)
        controls_layout.addStretch(1)
        layout.addLayout(controls_layout)

        self.flashcard_progress_bar = QProgressBar()
        self.flashcard_progress_bar.setRange(0, 1000)
        self.flashcard_progress_bar.setValue(0)
        self.flashcard_progress_bar.setTextVisible(False)
        self.flashcard_progress_bar.setFixedHeight(6)
        self.flashcard_progress_bar.setProperty("flashcardProgressActive", False)
        layout.addWidget(self.flashcard_progress_bar)

        self._apply_palette_styles()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Refresh palette-driven colors when theme/palette changes."""
        if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            set_muted_label_color(self.folder_context_label)
            self._apply_palette_styles()
        super().changeEvent(event)

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Keep overlay feedback aligned without moving the flashcard layout."""
        super().resizeEvent(event)
        self._update_flashcard_content_presentation()

    def _retain_size_when_hidden(self, widget: QWidget) -> None:
        """Keep a widget's layout footprint even while it is hidden.

        Args:
            widget: Widget whose size policy should retain hidden size.
        """
        size_policy = widget.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        widget.setSizePolicy(size_policy)

    def _create_button(
        self,
        text: str,
        *,
        tooltip: str,
        clicked_handler: Callable[[], object],
        minimum_width: int,
        enabled: bool = True,
        visible: bool = True,
        checkable: bool = False,
        fixed_height: int | None = None,
    ) -> QPushButton:
        """Create a timer-page button with shared presentation defaults.

        Args:
            text: Visible button text.
            tooltip: Tooltip text shown for the button.
            clicked_handler: Callable connected to the clicked signal.
            minimum_width: Minimum width applied to the button.
            enabled: Whether the button starts enabled.
            visible: Whether the button starts visible.
            checkable: Whether the button is toggleable.
            fixed_height: Optional fixed height for the button.

        Returns:
            Configured push button.
        """
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(clicked_handler)
        button.setMinimumWidth(minimum_width)
        if fixed_height is not None:
            button.setFixedHeight(fixed_height)
        button.setCheckable(checkable)
        button.setEnabled(enabled)
        button.setVisible(visible)
        return button

    def _create_score_action_button(
        self,
        text: str,
        *,
        tooltip: str,
        score_action: str,
        clicked_handler: Callable[[], object],
    ) -> QPushButton:
        """Create one flashcard score button with its shared configuration.

        Args:
            text: Visible button label.
            tooltip: Tooltip text shown for the button.
            score_action: Property value used to identify the score action.
            clicked_handler: Callable connected to the clicked signal.

        Returns:
            Configured score button.
        """
        button = self._create_button(
            text,
            tooltip=tooltip,
            clicked_handler=clicked_handler,
            minimum_width=self._SCORE_ACTION_BUTTON_MIN_WIDTH,
            enabled=False,
            checkable=True,
            fixed_height=self._SCORE_ACTION_BUTTON_HEIGHT,
        )
        button.setProperty("scoreAction", score_action)
        return button

    def _create_flashcard_text_label(self, *, point_size: int, weight: int) -> QLabel:
        """Create a flashcard text label with shared formatting defaults.

        Args:
            point_size: Base point size for the label font.
            weight: Font weight applied to the label.

        Returns:
            Configured flashcard text label.
        """
        label = QLabel("")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        label_font = QFont(label.font())
        label_font.setPointSize(point_size)
        label_font.setWeight(weight)
        label.setFont(label_font)
        label.setVisible(False)
        return label

    def _build_flashcard_progress_stylesheet(
        self,
        *,
        active_track: str,
        active_fill: str,
    ) -> str:
        """Return the palette-aware stylesheet for the flashcard progress bar.

        Args:
            active_track: Background color for the active track.
            active_fill: Fill color for the active chunk.

        Returns:
            Progress bar stylesheet.
        """
        return (
            "QProgressBar {"
            " border: none;"
            " border-radius: 3px;"
            " background: transparent;"
            "}"
            "QProgressBar::chunk {"
            " border-radius: 3px;"
            " background: transparent;"
            "}"
            "QProgressBar[flashcardProgressActive='true'] {"
            f" background: {active_track};"
            "}"
            "QProgressBar[flashcardProgressActive='true']::chunk {"
            f" background: {active_fill};"
            "}"
        )

    def _build_score_button_stylesheet(
        self,
        *,
        fill_color: QColor,
        text_tint: QColor,
        border_color: QColor,
        hover_color: QColor,
        checked_fill_color: QColor,
        checked_text_color: QColor,
        checked_border_color: QColor,
        disabled_fill_color: QColor,
        disabled_text_color: QColor,
        disabled_border_color: QColor,
    ) -> str:
        """Return the score-button stylesheet for one accent color variant.

        Args:
            fill_color: Default button background color.
            text_tint: Default button text color.
            border_color: Default border color.
            hover_color: Hover background color.
            checked_fill_color: Checked and pressed background color.
            checked_text_color: Checked and pressed text color.
            checked_border_color: Checked and pressed border color.
            disabled_fill_color: Disabled background color.
            disabled_text_color: Disabled text color.
            disabled_border_color: Disabled border color.

        Returns:
            Score button stylesheet.
        """
        return (
            "QPushButton {"
            f" background-color: {fill_color.name(QColor.HexRgb)};"
            f" color: {text_tint.name(QColor.HexRgb)};"
            f" border: 1px solid {border_color.name(QColor.HexRgb)};"
            " border-radius: 14px;"
            " padding: 6px 18px;"
            " font-size: 20px;"
            " font-weight: 700;"
            "}"
            "QPushButton:hover:!disabled {"
            f" background-color: {hover_color.name(QColor.HexRgb)};"
            "}"
            "QPushButton:pressed:!disabled, QPushButton:checked {"
            f" background-color: {checked_fill_color.name(QColor.HexRgb)};"
            f" color: {checked_text_color.name(QColor.HexRgb)};"
            f" border: 2px solid {checked_border_color.name(QColor.HexRgb)};"
            "}"
            "QPushButton:disabled {"
            f" background-color: {disabled_fill_color.name(QColor.HexRgb)};"
            f" color: {disabled_text_color.name(QColor.HexRgb)};"
            f" border: 1px solid {disabled_border_color.name(QColor.HexRgb)};"
            "}"
        )

    def _apply_palette_styles(self) -> None:
        """Apply palette-aware styles for non-native progress visuals."""
        palette = self.palette()
        active_track = blend_colors(
            palette.color(QPalette.Window),
            palette.color(QPalette.AlternateBase),
            overlay_ratio=0.65,
        ).name(QColor.HexRgb)
        active_fill = palette.color(QPalette.Highlight).name(QColor.HexRgb)
        self.flashcard_progress_bar.setStyleSheet(
            self._build_flashcard_progress_stylesheet(
                active_track=active_track,
                active_fill=active_fill,
            )
        )
        self._apply_score_button_styles()

    def _apply_score_button_styles(self) -> None:
        """Apply palette-aware styling for the correct and wrong buttons."""
        palette = self.palette()
        button_color = palette.color(QPalette.Button)
        text_color = palette.color(QPalette.ButtonText)
        window_color = palette.color(QPalette.Window)
        disabled_text_color = palette.color(QPalette.Disabled, QPalette.ButtonText)
        score_colors = (
            (self.correct_button, QColor(76, 175, 80)),
            (self.wrong_button, QColor(229, 83, 75)),
        )
        for button, accent_color in score_colors:
            fill_color = blend_colors(button_color, accent_color, overlay_ratio=0.22)
            hover_color = blend_colors(button_color, accent_color, overlay_ratio=0.34)
            checked_fill_color = blend_colors(
                button_color,
                accent_color,
                overlay_ratio=0.72,
            )
            border_color = blend_colors(button_color, accent_color, overlay_ratio=0.62)
            checked_border_color = blend_colors(
                checked_fill_color,
                accent_color,
                overlay_ratio=0.55,
            )
            text_tint = blend_colors(text_color, accent_color, overlay_ratio=0.48)
            checked_text_color = QColor("black")
            if checked_fill_color.lightness() < 150:
                checked_text_color = QColor("white")
            disabled_fill_color = blend_colors(
                button_color, window_color, overlay_ratio=0.55
            )
            disabled_border_color = blend_colors(
                disabled_fill_color,
                window_color,
                overlay_ratio=0.4,
            )
            button.setStyleSheet(
                self._build_score_button_stylesheet(
                    fill_color=fill_color,
                    text_tint=text_tint,
                    border_color=border_color,
                    hover_color=hover_color,
                    checked_fill_color=checked_fill_color,
                    checked_text_color=checked_text_color,
                    checked_border_color=checked_border_color,
                    disabled_fill_color=disabled_fill_color,
                    disabled_text_color=disabled_text_color,
                    disabled_border_color=disabled_border_color,
                )
            )

    def start_timer(self):
        """Start the timer."""
        if not self.is_running:
            self.clear_flashcard_display()
            if not self._has_countdown_duration():
                self.time = self._default_time()
            elif self._is_time_depleted():
                self.time = self._default_time()
                self.timer_display.setText(self.time.toString("mm:ss"))
            self.is_running = True
            self.start_button.setEnabled(False)
            self.pause_button.setText("Pause")
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.timer_running_changed.emit(True)
            if not self.is_running:
                return
            if not self._has_countdown_duration():
                self.is_running = False
                self.start_button.setEnabled(True)
                self.pause_button.setEnabled(False)
                self.stop_button.setEnabled(False)
                self.timer_display.setText(self._idle_timer_display_text())
                self.timer_running_changed.emit(False)
                self.timer_cycle_completed.emit()
                return
            self.timer.start(1000)

    def pause_timer(self):
        """Pause the timer without resetting remaining time."""
        if self.is_running:
            self.is_running = False
            self.timer.stop()
            self.start_button.setEnabled(False)
            self.pause_button.setText("Resume")
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            return
        if self._flashcard_controls_active:
            self._flashcard_paused = not self._flashcard_paused
            self.pause_button.setText("Resume" if self._flashcard_paused else "Pause")
            self._update_flashcard_pause_actions()
            self.flashcard_pause_toggled.emit(self._flashcard_paused)
            return
        if self.pause_button.text() == "Resume" and self.stop_button.isEnabled():
            self.start_timer()

    def stop_timer(self):
        """Stop and reset the timer to default duration."""
        if self.is_running:
            self.is_running = False
            self.timer.stop()
        self.clear_flashcard_display()
        self.time = self._default_time()
        self.timer_display.setText(self._idle_timer_display_text())
        self.start_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.timer_running_changed.emit(False)

    def _handle_stop_button_clicked(self) -> None:
        """Emit stop event and stop timer from stop button interaction."""
        self.stop_requested.emit()
        self.stop_timer()

    def reset_timer(self):
        """Reset the timer."""
        self.stop_timer()

    def restart_timer_cycle(self) -> None:
        """Reset the timer and immediately start a new countdown cycle."""
        self.clear_flashcard_display()
        self.time = self._default_time()
        self.timer_display.setText(self._idle_timer_display_text())
        self.start_timer()

    def prepare_next_timer_cycle_paused(self) -> None:
        """Reset the timer display while keeping the active session paused."""
        self.clear_flashcard_display()
        self.time = self._default_time()
        self.timer_display.setText(self._idle_timer_display_text())
        self.is_running = False
        self.start_button.setEnabled(False)
        self.pause_button.setText("Resume")
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)

    def update_timer(self):
        """Update timer display."""
        if not self.is_running:
            return
        self.time = self.time.addSecs(-1)
        self.timer_display.setText(self.time.toString("mm:ss"))

        if self._is_time_depleted():
            self.timer.stop()
            self.is_running = False
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.timer_running_changed.emit(False)
            self.timer_cycle_completed.emit()

    def show_flashcard_answer(
        self,
        answer: str,
        image_path: str | None = None,
        display_duration_seconds: int = 0,
    ) -> None:
        """Show flashcard answer under current question.

        Args:
            answer: Flashcard answer text.
            display_duration_seconds: Duration answer stays visible.
        """
        self.set_flashcard_controls_active(
            True,
            pause_enabled=display_duration_seconds > 0,
        )
        self.set_flashcard_scoring_actions_visible(True)
        self.set_flashcard_scoring_actions_enabled(True)
        self._current_flashcard_answer = answer
        self._current_answer_image_path = image_path
        self._set_flashcard_label_text(self.flashcard_answer_label, answer)
        self.flashcard_answer_label.setVisible(True)
        self._set_flashcard_image_visibility(
            self.flashcard_answer_image_label,
            image_path,
        )
        self._update_flashcard_content_presentation()
        self._start_flashcard_progress(display_duration_seconds)

    def show_flashcard_question(
        self,
        question: str,
        image_path: str | None = None,
        display_duration_seconds: int = 0,
    ) -> None:
        """Show flashcard question and hide timer display.

        Args:
            question: Flashcard question text.
            display_duration_seconds: Duration question stays visible.
        """
        self.content_stack.setCurrentIndex(1)
        self.clear_flashcard_score_selection()
        self.set_flashcard_controls_active(
            True,
            pause_enabled=display_duration_seconds > 0,
        )
        self._current_flashcard_question = question
        self._current_flashcard_answer = ""
        self._current_question_image_path = image_path
        self._current_answer_image_path = None
        self.set_flashcard_scoring_actions_visible(False)
        self.set_flashcard_scoring_actions_enabled(False)
        self.flashcard_question_label.setVisible(True)
        self._set_flashcard_label_text(self.flashcard_question_label, question)
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)
        self._set_flashcard_image_visibility(
            self.flashcard_question_image_label,
            image_path,
        )
        self.flashcard_answer_image_label.clear()
        self.flashcard_answer_image_label.setVisible(False)
        self._hide_copy_feedback()
        self._update_flashcard_content_presentation()
        self._start_flashcard_progress(display_duration_seconds)

    def set_flashcard_origin(
        self,
        origin_path: str | None,
        *,
        clickable: bool,
    ) -> None:
        """Show or hide the active flashcard origin path in the header.

        Args:
            origin_path: Full origin path for the visible flashcard, if known.
            clickable: Whether clicking the path should trigger in-app navigation.
        """
        self._current_flashcard_origin_path = origin_path
        self._flashcard_origin_clickable = clickable and bool(origin_path)
        if not origin_path:
            self.flashcard_origin_label.clear()
            self.flashcard_origin_label.setToolTip("")
            self.flashcard_origin_label.setCursor(Qt.ArrowCursor)
            self.flashcard_origin_label.setVisible(False)
            return
        self.flashcard_origin_label.setText(origin_path)
        self.flashcard_origin_label.setToolTip(origin_path)
        self.flashcard_origin_label.setCursor(
            Qt.PointingHandCursor if clickable else Qt.ArrowCursor
        )
        self.flashcard_origin_label.setVisible(True)

    def current_flashcard_origin_path(self) -> str | None:
        """Return the origin path shown for the current flashcard."""
        return self._current_flashcard_origin_path

    def clear_flashcard_display(self) -> None:
        """Hide flashcard question/answer and show timer display."""
        self._current_flashcard_question = ""
        self._current_flashcard_answer = ""
        self._current_question_image_path = None
        self._current_answer_image_path = None
        self._current_flashcard_origin_path = None
        self._flashcard_origin_clickable = False
        self.flashcard_question_label.setText("")
        self.flashcard_question_label.setVisible(False)
        self.flashcard_question_image_label.clear()
        self.flashcard_question_image_label.setVisible(False)
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)
        self.flashcard_answer_image_label.clear()
        self.flashcard_answer_image_label.setVisible(False)
        self.flashcard_origin_label.clear()
        self.flashcard_origin_label.setToolTip("")
        self.flashcard_origin_label.setCursor(Qt.ArrowCursor)
        self.flashcard_origin_label.setVisible(False)
        self._hide_copy_feedback()
        self.content_stack.setCurrentIndex(0)
        self.set_flashcard_controls_active(False)
        self.clear_flashcard_score_selection()
        self.set_flashcard_scoring_actions_visible(False)
        self.set_flashcard_scoring_actions_enabled(False)
        self._stop_flashcard_progress()

    def update_displayed_flashcard(
        self,
        question: str,
        answer: str,
        question_image_path: str | None | object = _IMAGE_PATH_UNCHANGED,
        answer_image_path: str | None | object = _IMAGE_PATH_UNCHANGED,
    ) -> None:
        """Refresh the currently shown flashcard text in place."""
        self._current_flashcard_question = question
        self._current_flashcard_answer = answer
        if question_image_path is not self._IMAGE_PATH_UNCHANGED:
            self._current_question_image_path = question_image_path
        if answer_image_path is not self._IMAGE_PATH_UNCHANGED:
            self._current_answer_image_path = answer_image_path
        if not self.flashcard_question_label.isHidden():
            self._set_flashcard_label_text(self.flashcard_question_label, question)
            self._set_flashcard_image_visibility(
                self.flashcard_question_image_label,
                self._current_question_image_path,
            )
        if not self.flashcard_answer_label.isHidden():
            self._set_flashcard_label_text(self.flashcard_answer_label, answer)
            self._set_flashcard_image_visibility(
                self.flashcard_answer_image_label,
                self._current_answer_image_path,
            )
        self._update_flashcard_content_presentation()

    def _set_flashcard_label_text(self, label: QLabel, text: str) -> None:
        """Render flashcard text as plain text unless inline LaTeX needs rich text."""
        label.setTextFormat(Qt.RichText if has_inline_latex(text) else Qt.PlainText)
        label.setText(render_inline_latex_html(text))

    def _configure_flashcard_image_label(self, label: QLabel) -> None:
        """Apply consistent presentation defaults for flashcard image widgets."""
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.NoTextInteraction)
        label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        label.setVisible(False)

    def _set_flashcard_image_visibility(
        self,
        label: QLabel,
        image_path: str | None,
    ) -> None:
        """Show or hide an image label based on whether a path is attached."""
        if image_path is None:
            label.clear()
            label.setVisible(False)
            return
        label.setVisible(True)

    def _update_flashcard_content_presentation(self) -> None:
        """Refresh flashcard typography and overlay placement for current bounds."""
        if self._updating_flashcard_content_presentation:
            return
        self._updating_flashcard_content_presentation = True
        flashcard_layout = self._flashcard_view.layout()
        try:
            if flashcard_layout is not None:
                flashcard_layout.activate()
            self.flashcard_content_layout.activate()
            self._apply_flashcard_content_fonts()
            self._refresh_flashcard_images()
            self._position_copy_feedback()
        finally:
            self._updating_flashcard_content_presentation = False

    def _apply_flashcard_content_fonts(self) -> None:
        """Fit visible flashcard text into the available content area."""
        label_specs = (
            (
                self.flashcard_question_label,
                self._FLASHCARD_QUESTION_BASE_POINT_SIZE,
            ),
            (
                self.flashcard_answer_label,
                self._FLASHCARD_ANSWER_BASE_POINT_SIZE,
            ),
        )
        if (
            self.flashcard_content_widget.width() <= 1
            or self.flashcard_content_widget.height() <= 1
        ):
            for label, base_point_size in label_specs:
                self._set_flashcard_label_point_size(label, base_point_size)
            return

        visible_label_specs = [
            (label, base_point_size)
            for label, base_point_size in label_specs
            if not label.isHidden() and bool(label.text())
        ]
        available_width = self._flashcard_content_available_width()
        visible_image_count = sum(
            not label.isHidden() and path is not None
            for label, path in (
                (
                    self.flashcard_question_image_label,
                    self._current_question_image_path,
                ),
                (
                    self.flashcard_answer_image_label,
                    self._current_answer_image_path,
                ),
            )
        )
        total_available_height = self._flashcard_content_available_height(
            visible_label_count=len(visible_label_specs) + visible_image_count
        )
        reserved_image_height = self._reserved_flashcard_image_height(
            total_available_height=total_available_height,
            visible_item_count=len(visible_label_specs) + visible_image_count,
            visible_image_count=visible_image_count,
        )
        available_height = max(1, total_available_height - reserved_image_height)
        resolved_point_sizes = self._resolve_flashcard_point_sizes(
            visible_label_specs,
            available_width=available_width,
            available_height=available_height,
        )

        for label, base_point_size in label_specs:
            self._set_flashcard_label_point_size(
                label,
                resolved_point_sizes.get(label, base_point_size),
            )

    def _reserved_flashcard_image_height(
        self,
        *,
        total_available_height: int,
        visible_item_count: int,
        visible_image_count: int,
    ) -> int:
        """Return the total height budget reserved for visible image attachments."""
        if visible_image_count <= 0:
            return 0
        max_height_per_image = min(
            self._FLASHCARD_IMAGE_MAX_HEIGHT,
            max(
                self._FLASHCARD_IMAGE_MIN_HEIGHT,
                total_available_height // max(1, visible_item_count),
            ),
        )
        return max_height_per_image * visible_image_count

    def _refresh_flashcard_images(self) -> None:
        """Scale visible flashcard images to fit the current content bounds."""
        available_width = self._flashcard_content_available_width()
        visible_image_count = sum(
            not label.isHidden() and path is not None
            for label, path in (
                (
                    self.flashcard_question_image_label,
                    self._current_question_image_path,
                ),
                (
                    self.flashcard_answer_image_label,
                    self._current_answer_image_path,
                ),
            )
        )
        if visible_image_count <= 0:
            return
        visible_text_count = sum(
            not label.isHidden() and bool(label.text())
            for label in (
                self.flashcard_question_label,
                self.flashcard_answer_label,
            )
        )
        total_available_height = self._flashcard_content_available_height(
            visible_label_count=visible_text_count + visible_image_count
        )
        max_height_per_image = min(
            self._FLASHCARD_IMAGE_MAX_HEIGHT,
            max(
                self._FLASHCARD_IMAGE_MIN_HEIGHT,
                total_available_height
                // max(1, visible_text_count + visible_image_count),
            ),
        )
        self._refresh_flashcard_image_label(
            self.flashcard_question_image_label,
            self._current_question_image_path,
            unavailable_text="Question image unavailable.",
            available_width=available_width,
            max_height=max_height_per_image,
        )
        self._refresh_flashcard_image_label(
            self.flashcard_answer_image_label,
            self._current_answer_image_path,
            unavailable_text="Answer image unavailable.",
            available_width=available_width,
            max_height=max_height_per_image,
        )

    def _refresh_flashcard_image_label(
        self,
        label: QLabel,
        image_path: str | None,
        *,
        unavailable_text: str,
        available_width: int,
        max_height: int,
    ) -> None:
        """Update one image label with a scaled pixmap or fallback text."""
        if image_path is None or label.isHidden():
            label.clear()
            return
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setTextFormat(Qt.PlainText)
            label.setText(unavailable_text)
            set_muted_label_color(label)
            return
        scaled_pixmap = pixmap.scaled(
            available_width,
            max_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        label.setText("")
        label.setPixmap(scaled_pixmap)

    def _set_flashcard_label_point_size(self, label: QLabel, point_size: int) -> None:
        """Apply one point size to a flashcard label."""
        font = QFont(label.font())
        if font.pointSize() == point_size:
            return
        font.setPointSize(point_size)
        label.setFont(font)

    def _flashcard_content_available_width(self) -> int:
        """Return the available text width inside the flashcard content area."""
        margins = self.flashcard_content_layout.contentsMargins()
        available_width = (
            self.flashcard_content_widget.width() - margins.left() - margins.right()
        )
        return max(120, available_width)

    def _flashcard_content_available_height(self, *, visible_label_count: int) -> int:
        """Return the total text height available inside the flashcard area."""
        margins = self.flashcard_content_layout.contentsMargins()
        available_height = (
            self.flashcard_content_widget.height() - margins.top() - margins.bottom()
        )
        spacing_height = self.flashcard_content_layout.spacing() * max(
            0, visible_label_count - 1
        )
        return max(1, available_height - spacing_height)

    def _resolve_flashcard_point_sizes(
        self,
        visible_label_specs: list[tuple[QLabel, int]],
        *,
        available_width: int,
        available_height: int,
    ) -> dict[QLabel, int]:
        """Shrink visible labels until their combined height fits the content area."""
        point_sizes = {
            label: base_point_size for label, base_point_size in visible_label_specs
        }
        if not point_sizes:
            return point_sizes

        while True:
            measured_heights = {
                label: self._measure_flashcard_text_height(
                    label,
                    rendered_text=label.text(),
                    point_size=point_sizes[label],
                    available_width=available_width,
                )
                for label, _base_point_size in visible_label_specs
            }
            if sum(measured_heights.values()) <= available_height:
                return point_sizes

            shrinkable_labels = [
                label
                for label, _base_point_size in visible_label_specs
                if point_sizes[label] > 1
            ]
            if not shrinkable_labels:
                return point_sizes

            label_to_shrink = max(
                shrinkable_labels,
                key=lambda current_label: (
                    measured_heights[current_label],
                    point_sizes[current_label],
                ),
            )
            point_sizes[label_to_shrink] -= 1

    def _measure_flashcard_text_height(
        self,
        label: QLabel,
        *,
        rendered_text: str,
        point_size: int,
        available_width: int,
    ) -> float:
        """Measure the rendered text height for a candidate flashcard font size."""
        candidate_font = QFont(label.font())
        candidate_font.setPointSize(point_size)
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(candidate_font)
        if label.textFormat() == Qt.RichText:
            document.setHtml(rendered_text)
        else:
            document.setPlainText(rendered_text)
        document.setTextWidth(max(1, available_width))
        return document.size().height()

    def current_flashcard_question_text(self) -> str:
        """Return the raw question text for the currently visible flashcard."""
        return self._current_flashcard_question

    def set_flashcard_context(self, folder_name: str, card_count: int) -> None:
        """Update selected folder summary shown on the timer page.

        Args:
            folder_name: Selected folder display name.
            card_count: Number of loaded flashcards in scope.
        """
        self._folder_name = folder_name
        self._card_count = card_count
        self._recompose_folder_label()

    def set_timer_duration_seconds(self, duration_seconds: int) -> None:
        """Set the default timer duration used by reset and idle display.

        Args:
            duration_seconds: New default countdown duration in seconds.
        """
        self._default_duration_seconds = max(
            0,
            min(MAX_TIMER_DURATION_SECONDS, int(duration_seconds)),
        )
        if not self.is_running:
            self.time = self._default_time()
            self.timer_display.setText(self._idle_timer_display_text())

    def _default_time(self) -> QTime:
        """Return the idle/default countdown time object."""
        return QTime(0, 0, 0).addSecs(self._default_duration_seconds)

    def _has_countdown_duration(self) -> bool:
        """Return whether the timer should run a countdown before flashcards."""
        return self._default_duration_seconds > 0

    def has_countdown_duration(self) -> bool:
        """Return whether study cycles should return through the timer countdown."""
        return self._has_countdown_duration()

    def _idle_timer_display_text(self) -> str:
        """Return the idle timer label for the current mode."""
        if not self._has_countdown_duration():
            return "Ready?"
        return self.time.toString("mm:ss")

    def _is_time_depleted(self) -> bool:
        """Return whether the countdown has reached zero."""
        return self.time.minute() == 0 and self.time.second() == 0

    def set_session_progress(
        self,
        *,
        completed_count: int,
        remaining_count: int,
        wrong_pending_count: int,
        total_count: int,
    ) -> None:
        """Update scored-session progress summary."""
        if total_count <= 0:
            self._session_progress_text = ""
        else:
            self._session_progress_text = (
                "Session: "
                f"{completed_count}/{total_count} completed | "
                f"{remaining_count} remaining | "
                f"{wrong_pending_count} pending review"
            )
        self._recompose_folder_label()

    def clear_session_progress(self) -> None:
        """Hide session progress outside an active study session."""
        self._session_progress_text = ""
        self._recompose_folder_label()

    def _recompose_folder_label(self) -> None:
        """Rebuild folder context label from stored folder and session state."""
        if self._session_progress_text:
            self.folder_context_label.setText(self._session_progress_text)
        else:
            self.folder_context_label.setText(
                f"Folder: {self._folder_name} ({format_card_count(self._card_count)})"
            )

    def set_flashcard_controls_active(
        self,
        active: bool,
        *,
        pause_enabled: bool = True,
    ) -> None:
        """Configure control buttons for flashcard phase interactions.

        Args:
            active: Whether flashcard controls should be active.
            pause_enabled: Whether pause/resume should be available right now.
        """
        was_paused = self._flashcard_paused
        self._flashcard_controls_active = active
        if active:
            self.start_button.setEnabled(False)
            self.pause_button.setEnabled(pause_enabled)
            if not pause_enabled:
                self._flashcard_paused = False
            self.stop_button.setEnabled(True)
            if not self._flashcard_paused:
                self.pause_button.setText("Pause")
            self._update_flashcard_pause_actions()
            return
        self._flashcard_paused = False
        self.pause_button.setText("Pause")
        self._update_flashcard_pause_actions()
        if was_paused:
            self.flashcard_pause_toggled.emit(False)

    def set_flashcard_scoring_actions_enabled(self, enabled: bool) -> None:
        """Enable or disable scored-session actions without moving the layout."""
        self.correct_button.setEnabled(enabled)
        self.wrong_button.setEnabled(enabled)

    def set_flashcard_scoring_actions_visible(self, visible: bool) -> None:
        """Show or hide score actions while preserving their layout footprint."""
        self.flashcard_actions_container.setVisible(visible)

    def _update_flashcard_pause_actions(self) -> None:
        """Refresh paused-session actions for the current flashcard visibility state."""
        actions_visible = self._flashcard_controls_active
        paused_actions_visible = actions_visible and self._flashcard_paused
        self.flashcard_pause_actions_container.setVisible(actions_visible)
        self.skip_phase_button.setVisible(actions_visible)
        self.skip_phase_button.setEnabled(actions_visible)
        self.shuffle_queue_button.setVisible(
            paused_actions_visible and self._queue_shuffle_available
        )
        self.shuffle_queue_button.setEnabled(
            paused_actions_visible and self._queue_shuffle_available
        )
        self.edit_flashcard_button.setVisible(paused_actions_visible)
        self.edit_flashcard_button.setEnabled(paused_actions_visible)
        self.delete_flashcard_button.setVisible(paused_actions_visible)
        self.delete_flashcard_button.setEnabled(paused_actions_visible)

    def set_queue_shuffle_available(self, available: bool) -> None:
        """Show the queue-shuffle action only when it is meaningful."""
        self._queue_shuffle_available = available
        self._update_flashcard_pause_actions()

    def is_flashcard_progress_active(self) -> bool:
        """Return whether the flashcard progress bar is visually active."""
        return self._flashcard_progress_active

    def selected_flashcard_score(self) -> str | None:
        """Return the currently selected score action, if any."""
        return self._selected_flashcard_score

    def clear_flashcard_score_selection(self) -> None:
        """Clear any pending score choice for the current flashcard."""
        self._selected_flashcard_score = None
        self.correct_button.setChecked(False)
        self.wrong_button.setChecked(False)

    def _handle_correct_button_clicked(self) -> None:
        """Toggle Correct selection and keep the choices visually exclusive."""
        self._selected_flashcard_score = (
            "correct" if self.correct_button.isChecked() else None
        )
        if self.correct_button.isChecked():
            self.wrong_button.setChecked(False)
        self.flashcard_marked_correct.emit()

    def _handle_wrong_button_clicked(self) -> None:
        """Toggle Wrong selection and keep the choices visually exclusive."""
        self._selected_flashcard_score = (
            "wrong" if self.wrong_button.isChecked() else None
        )
        if self.wrong_button.isChecked():
            self.correct_button.setChecked(False)
        self.flashcard_marked_wrong.emit()

    def _handle_flashcard_origin_clicked(self) -> None:
        """Emit the flashcard-origin navigation request."""
        if self._flashcard_origin_clickable:
            self.flashcard_origin_requested.emit()

    def _start_flashcard_progress(self, duration_seconds: int) -> None:
        """Animate progress bar for flashcard phase durations.

        Args:
            duration_seconds: Duration in seconds for the current phase.
        """
        self._stop_flashcard_progress()
        if duration_seconds <= 0:
            return
        self._set_flashcard_progress_active(True)
        self.flashcard_progress_bar.setValue(0)
        self._animate_flashcard_progress(0, duration_seconds * 1000)

    def pause_flashcard_progress(self) -> None:
        """Pause progress animation without resetting current progress."""
        if self._flashcard_phase_animation is not None:
            self._flashcard_phase_animation.stop()

    def resume_flashcard_progress(self, remaining_milliseconds: int) -> None:
        """Resume progress animation from current value.

        Args:
            remaining_milliseconds: Remaining phase duration.
        """
        if not self._flashcard_progress_active or remaining_milliseconds <= 0:
            return
        self._animate_flashcard_progress(
            self.flashcard_progress_bar.value(), remaining_milliseconds
        )

    def _animate_flashcard_progress(
        self, start_value: int, duration_milliseconds: int
    ) -> None:
        """Animate progress bar between values.

        Args:
            start_value: Initial progress value.
            duration_milliseconds: Duration in milliseconds.
        """
        if self._flashcard_phase_animation is not None:
            self._flashcard_phase_animation.stop()
            self._flashcard_phase_animation.deleteLater()
            self._flashcard_phase_animation = None
        self.flashcard_progress_bar.setValue(start_value)
        animation = QPropertyAnimation(self.flashcard_progress_bar, b"value", self)
        animation.setStartValue(start_value)
        animation.setEndValue(1000)
        animation.setDuration(duration_milliseconds)
        animation.setEasingCurve(QEasingCurve.Type.Linear)
        animation.start()
        self._flashcard_phase_animation = animation

    def _stop_flashcard_progress(self) -> None:
        """Stop and reset the flashcard progress animation."""
        if self._flashcard_phase_animation is not None:
            self._flashcard_phase_animation.stop()
            self._flashcard_phase_animation.deleteLater()
            self._flashcard_phase_animation = None
        self.flashcard_progress_bar.setValue(0)
        self._set_flashcard_progress_active(False)

    def _set_flashcard_progress_active(self, active: bool) -> None:
        """Toggle the flashcard progress bar between active and invisible states."""
        self._flashcard_progress_active = active
        self.flashcard_progress_bar.setProperty("flashcardProgressActive", active)
        self.flashcard_progress_bar.style().unpolish(self.flashcard_progress_bar)
        self.flashcard_progress_bar.style().polish(self.flashcard_progress_bar)
        self.flashcard_progress_bar.update()

    def show_copy_feedback(self) -> None:
        """Show a small fade animation that confirms question copy."""
        if (
            not self._current_flashcard_question
            or self.flashcard_question_label.isHidden()
        ):
            return
        if self._copy_feedback_animation is not None:
            self._copy_feedback_animation.stop()
            self._copy_feedback_animation.deleteLater()
            self._copy_feedback_animation = None
        self._position_copy_feedback()
        self.copy_feedback_label.setVisible(True)
        self._copy_feedback_effect.setOpacity(0.0)
        animation = QPropertyAnimation(self._copy_feedback_effect, b"opacity", self)
        animation.setDuration(700)
        animation.setStartValue(0.0)
        animation.setKeyValueAt(0.2, 1.0)
        animation.setKeyValueAt(0.7, 1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        animation.finished.connect(self._hide_copy_feedback)
        animation.start()
        self._copy_feedback_animation = animation

    def _hide_copy_feedback(self) -> None:
        """Hide and reset the copied badge state."""
        if self._copy_feedback_animation is not None:
            self._copy_feedback_animation.stop()
            self._copy_feedback_animation.deleteLater()
            self._copy_feedback_animation = None
        self.copy_feedback_label.setVisible(False)
        self._copy_feedback_effect.setOpacity(0.0)

    def _position_copy_feedback(self) -> None:
        """Anchor the copy feedback above the question without affecting layout."""
        flashcard_layout = self._flashcard_view.layout()
        if flashcard_layout is not None:
            flashcard_layout.activate()
        self.copy_feedback_label.adjustSize()
        badge_size = self.copy_feedback_label.sizeHint()
        question_top_left = self.flashcard_question_label.mapTo(
            self._flashcard_view, QPoint(0, 0)
        )
        x_position = max(
            0,
            (self._flashcard_view.width() - badge_size.width()) // 2,
        )
        y_position = max(
            8,
            question_top_left.y() - badge_size.height() - 8,
        )
        maximum_y = max(8, self._flashcard_view.height() - badge_size.height() - 8)
        self.copy_feedback_label.move(x_position, min(y_position, maximum_y))
