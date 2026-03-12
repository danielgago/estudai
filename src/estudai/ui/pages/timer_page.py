"""Timer page."""

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
from PySide6.QtGui import QColor, QFont, QPalette, QTextDocument
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


class TimerPage(QWidget):
    """Timer page for study sessions."""

    timer_running_changed = Signal(bool)
    timer_cycle_completed = Signal()
    flashcard_pause_toggled = Signal(bool)
    flashcard_queue_shuffle_requested = Signal()
    flashcard_phase_skip_requested = Signal()
    flashcard_marked_correct = Signal()
    flashcard_marked_wrong = Signal()
    flashcard_edit_requested = Signal()
    flashcard_delete_requested = Signal()
    stop_requested = Signal()

    _FLASHCARD_QUESTION_BASE_POINT_SIZE = 40
    _FLASHCARD_ANSWER_BASE_POINT_SIZE = 34

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
        self.flashcard_actions_container = QWidget()
        actions_size_policy = self.flashcard_actions_container.sizePolicy()
        actions_size_policy.setRetainSizeWhenHidden(True)
        self.flashcard_actions_container.setSizePolicy(actions_size_policy)
        flashcard_actions_layout = QHBoxLayout(self.flashcard_actions_container)
        flashcard_actions_layout.setContentsMargins(0, 0, 0, 0)
        flashcard_actions_layout.setSpacing(14)
        flashcard_actions_layout.addStretch(1)
        self.correct_button = QPushButton("✓")
        self.correct_button.setToolTip("Mark correct")
        self.correct_button.setProperty("scoreAction", "correct")
        self.correct_button.setCheckable(True)
        self.correct_button.clicked.connect(self._handle_correct_button_clicked)
        self.correct_button.setMinimumWidth(84)
        self.correct_button.setFixedHeight(44)
        self.correct_button.setEnabled(False)
        self.wrong_button = QPushButton("✕")
        self.wrong_button.setToolTip("Mark wrong")
        self.wrong_button.setProperty("scoreAction", "wrong")
        self.wrong_button.setCheckable(True)
        self.wrong_button.clicked.connect(self._handle_wrong_button_clicked)
        self.wrong_button.setMinimumWidth(84)
        self.wrong_button.setFixedHeight(44)
        self.wrong_button.setEnabled(False)
        flashcard_actions_layout.addWidget(self.correct_button)
        flashcard_actions_layout.addWidget(self.wrong_button)
        flashcard_actions_layout.addStretch(1)
        self.flashcard_actions_container.setVisible(False)

        self.flashcard_pause_actions_container = QWidget()
        pause_actions_size_policy = self.flashcard_pause_actions_container.sizePolicy()
        pause_actions_size_policy.setRetainSizeWhenHidden(True)
        self.flashcard_pause_actions_container.setSizePolicy(pause_actions_size_policy)
        flashcard_pause_actions_layout = QHBoxLayout(
            self.flashcard_pause_actions_container
        )
        flashcard_pause_actions_layout.setContentsMargins(0, 0, 0, 0)
        flashcard_pause_actions_layout.setSpacing(10)
        flashcard_pause_actions_layout.addStretch(1)
        self.skip_phase_button = QPushButton("Skip")
        self.skip_phase_button.setToolTip("Advance the current flashcard phase")
        self.skip_phase_button.clicked.connect(self.flashcard_phase_skip_requested.emit)
        self.skip_phase_button.setMinimumWidth(130)
        self.skip_phase_button.setEnabled(False)
        flashcard_pause_actions_layout.addWidget(self.skip_phase_button)
        self.shuffle_queue_button = QPushButton("Shuffle Queue")
        self.shuffle_queue_button.setToolTip("Shuffle remaining queue")
        self.shuffle_queue_button.clicked.connect(
            self.flashcard_queue_shuffle_requested.emit
        )
        self.shuffle_queue_button.setMinimumWidth(140)
        self.shuffle_queue_button.setVisible(False)
        self.shuffle_queue_button.setEnabled(False)
        flashcard_pause_actions_layout.addWidget(self.shuffle_queue_button)
        self.edit_flashcard_button = QPushButton("Edit")
        self.edit_flashcard_button.setToolTip("Edit current flashcard")
        self.edit_flashcard_button.clicked.connect(self.flashcard_edit_requested.emit)
        self.edit_flashcard_button.setMinimumWidth(110)
        self.edit_flashcard_button.setEnabled(False)
        flashcard_pause_actions_layout.addWidget(self.edit_flashcard_button)
        self.delete_flashcard_button = QPushButton("Delete")
        self.delete_flashcard_button.setToolTip("Delete current flashcard")
        self.delete_flashcard_button.clicked.connect(
            self.flashcard_delete_requested.emit
        )
        self.delete_flashcard_button.setMinimumWidth(110)
        self.delete_flashcard_button.setEnabled(False)
        flashcard_pause_actions_layout.addWidget(self.delete_flashcard_button)
        flashcard_pause_actions_layout.addStretch(1)
        self.flashcard_pause_actions_container.setVisible(False)
        flashcard_layout.addWidget(self.flashcard_pause_actions_container)

        flashcard_layout.setAlignment(
            self.flashcard_pause_actions_container,
            Qt.AlignTop | Qt.AlignRight,
        )
        self.flashcard_content_widget = QWidget()
        self.flashcard_content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.flashcard_content_layout = QVBoxLayout(self.flashcard_content_widget)
        self.flashcard_content_layout.setContentsMargins(8, 0, 8, 0)
        self.flashcard_content_layout.setSpacing(12)
        self.flashcard_content_layout.addStretch(1)
        self.flashcard_question_label = QLabel("")
        self.flashcard_question_label.setAlignment(Qt.AlignCenter)
        self.flashcard_question_label.setWordWrap(True)
        self.flashcard_question_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.flashcard_question_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        question_font = QFont(self.flashcard_question_label.font())
        question_font.setPointSize(self._FLASHCARD_QUESTION_BASE_POINT_SIZE)
        question_font.setWeight(QFont.ExtraBold)
        self.flashcard_question_label.setFont(question_font)
        self.flashcard_question_label.setVisible(False)
        self.flashcard_content_layout.addWidget(self.flashcard_question_label)

        self.flashcard_answer_label = QLabel("")
        self.flashcard_answer_label.setAlignment(Qt.AlignCenter)
        self.flashcard_answer_label.setWordWrap(True)
        self.flashcard_answer_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.flashcard_answer_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        answer_font = QFont(self.flashcard_answer_label.font())
        answer_font.setPointSize(self._FLASHCARD_ANSWER_BASE_POINT_SIZE)
        answer_font.setWeight(QFont.DemiBold)
        self.flashcard_answer_label.setFont(answer_font)
        self.flashcard_answer_label.setVisible(False)
        self.flashcard_content_layout.addWidget(self.flashcard_answer_label)
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

        self.start_button = QPushButton("Start")
        self.start_button.setToolTip("Start")
        self.start_button.clicked.connect(self.start_timer)
        self.start_button.setMinimumWidth(110)
        controls_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setToolTip("Pause")
        self.pause_button.clicked.connect(self.pause_timer)
        self.pause_button.setEnabled(False)
        self.pause_button.setMinimumWidth(110)
        controls_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("Stop")
        self.stop_button.clicked.connect(self._handle_stop_button_clicked)
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumWidth(110)
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
        self, answer: str, display_duration_seconds: int = 0
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
        self._set_flashcard_label_text(self.flashcard_answer_label, answer)
        self.flashcard_answer_label.setVisible(True)
        self._update_flashcard_content_presentation()
        self._start_flashcard_progress(display_duration_seconds)

    def show_flashcard_question(
        self, question: str, display_duration_seconds: int = 0
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
        self.set_flashcard_scoring_actions_visible(False)
        self.set_flashcard_scoring_actions_enabled(False)
        self.flashcard_question_label.setVisible(True)
        self._set_flashcard_label_text(self.flashcard_question_label, question)
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)
        self._hide_copy_feedback()
        self._update_flashcard_content_presentation()
        self._start_flashcard_progress(display_duration_seconds)

    def clear_flashcard_display(self) -> None:
        """Hide flashcard question/answer and show timer display."""
        self._current_flashcard_question = ""
        self._current_flashcard_answer = ""
        self.flashcard_question_label.setText("")
        self.flashcard_question_label.setVisible(False)
        self.flashcard_answer_label.setText("")
        self.flashcard_answer_label.setVisible(False)
        self._hide_copy_feedback()
        self.content_stack.setCurrentIndex(0)
        self.set_flashcard_controls_active(False)
        self.clear_flashcard_score_selection()
        self.set_flashcard_scoring_actions_visible(False)
        self.set_flashcard_scoring_actions_enabled(False)
        self._stop_flashcard_progress()

    def update_displayed_flashcard(self, question: str, answer: str) -> None:
        """Refresh the currently shown flashcard text in place."""
        self._current_flashcard_question = question
        self._current_flashcard_answer = answer
        if not self.flashcard_question_label.isHidden():
            self._set_flashcard_label_text(self.flashcard_question_label, question)
        if not self.flashcard_answer_label.isHidden():
            self._set_flashcard_label_text(self.flashcard_answer_label, answer)
        self._update_flashcard_content_presentation()

    def _set_flashcard_label_text(self, label: QLabel, text: str) -> None:
        """Render flashcard text as plain text unless inline LaTeX needs rich text."""
        label.setTextFormat(Qt.RichText if has_inline_latex(text) else Qt.PlainText)
        label.setText(render_inline_latex_html(text))

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
        available_height = self._flashcard_content_available_height(
            visible_label_count=len(visible_label_specs)
        )
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

    def _set_flashcard_label_point_size(
        self, label: QLabel, point_size: int
    ) -> None:
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
            label: base_point_size
            for label, base_point_size in visible_label_specs
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
                label for label, _base_point_size in visible_label_specs
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
