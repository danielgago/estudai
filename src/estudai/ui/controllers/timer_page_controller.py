"""Timer-page and study-session workflow controller."""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QWidget

from estudai.services.csv_flashcards import Flashcard
from estudai.services.settings import (
    AppSettings,
    StudyOrderMode,
    get_default_notification_sound_path,
    load_app_settings,
)
from estudai.services.study_progress import (
    FlashcardProgressEntry,
    load_folder_progress,
    reviewed_progress,
    save_progress_entries,
)
from estudai.ui.application_state import StudyApplicationState
from estudai.ui.audio_playback import TimedAudioPlaybackController
from estudai.ui.flashcard_sequence import FlashcardSequenceController
from estudai.ui.pages import TimerPage
from estudai.ui.study_session import SessionCardCounters, StudySessionController

IterSidebarFolderItems = Callable[[], Iterable[QListWidgetItem]]
SetNavigationVisible = Callable[[bool], None]
PageSwitchCallback = Callable[[], None]
EmitFlashcardCallback = Callable[[Flashcard], None]
RefreshSidebarFolderProgressLabels = Callable[[set[str] | None], None]
PhaseTimerStarter = Callable[[int, object], None]
PhaseTimeoutHandler = Callable[[], None]
TimerCycleCompletionHandler = Callable[[], None]
AppSettingsLoader = Callable[[], AppSettings]
DefaultSoundPathGetter = Callable[[], str]


class TimerPageController:
    """Coordinate timer-page runtime state and study-session progression."""

    def __init__(
        self,
        *,
        parent: QWidget,
        timer_page: TimerPage,
        app_state: StudyApplicationState,
        flashcard_phase_timer: QTimer,
        flashcard_sound_player: object | None,
        iter_sidebar_folder_items: IterSidebarFolderItems,
        set_navigation_visible: SetNavigationVisible,
        switch_to_timer: PageSwitchCallback,
        emit_show_flashcard: EmitFlashcardCallback,
        refresh_sidebar_folder_progress_labels: RefreshSidebarFolderProgressLabels,
        start_flashcard_phase_timer: PhaseTimerStarter,
        handle_flashcard_phase_timeout: PhaseTimeoutHandler,
        handle_timer_cycle_completed: TimerCycleCompletionHandler,
        load_settings: AppSettingsLoader = load_app_settings,
        default_sound_path_getter: DefaultSoundPathGetter = (
            get_default_notification_sound_path
        ),
    ) -> None:
        """Initialize the controller.

        Args:
            parent: Parent widget used for timer-related dialogs.
            timer_page: Timer page widget controlled by this instance.
            app_state: Shared folder-selection application state.
            flashcard_phase_timer: Single-shot timer used for question/answer
                phase transitions.
            flashcard_sound_player: Media player used for phase sounds.
            iter_sidebar_folder_items: Returns persisted sidebar folder items.
            set_navigation_visible: Shows or hides top-level navigation.
            switch_to_timer: Navigates to the timer page.
            emit_show_flashcard: Emits the next flashcard for display.
            refresh_sidebar_folder_progress_labels: Refreshes sidebar progress
                labels for one or many folders.
            start_flashcard_phase_timer: Starts a timed flashcard phase using
                the host wrapper so tests can still patch that seam.
            handle_flashcard_phase_timeout: Handles phase timer completion using
                the host wrapper so pause logic keeps the same seam.
            handle_timer_cycle_completed: Re-enters timer-cycle completion using
                the host wrapper when instant mode chains flashcards.
            load_settings: Loads current application settings.
            default_sound_path_getter: Resolves the fallback sound path.
        """
        self._parent = parent
        self._timer_page = timer_page
        self._app_state = app_state
        self._iter_sidebar_folder_items = iter_sidebar_folder_items
        self._set_navigation_visible = set_navigation_visible
        self._switch_to_timer = switch_to_timer
        self._emit_show_flashcard = emit_show_flashcard
        self._refresh_sidebar_folder_progress_labels = (
            refresh_sidebar_folder_progress_labels
        )
        self._start_flashcard_phase_timer = start_flashcard_phase_timer
        self._handle_flashcard_phase_timeout = handle_flashcard_phase_timeout
        self._handle_timer_cycle_completed = handle_timer_cycle_completed
        self._load_settings = load_settings
        self._default_sound_path_getter = default_sound_path_getter
        self._study_session = StudySessionController()
        self._active_study_session_keys: list[tuple[str, str]] = []
        self._pending_flashcard_score: str | None = None
        self._visible_flashcard: Flashcard | None = None
        self._flashcard_sequence = FlashcardSequenceController(flashcard_phase_timer)
        self._flashcard_sound_controller = TimedAudioPlaybackController(
            parent,
            player=flashcard_sound_player,
        )

    @property
    def study_session(self) -> StudySessionController:
        """Return the runtime study-session controller."""
        return self._study_session

    @property
    def active_study_session_keys(self) -> list[tuple[str, str]]:
        """Return folder/card keys for the active session order."""
        return self._active_study_session_keys

    @active_study_session_keys.setter
    def active_study_session_keys(self, value: list[tuple[str, str]]) -> None:
        self._active_study_session_keys = value

    @property
    def pending_flashcard_score(self) -> str | None:
        """Return the score queued for the active flashcard."""
        return self._pending_flashcard_score

    @pending_flashcard_score.setter
    def pending_flashcard_score(self, value: str | None) -> None:
        self._pending_flashcard_score = value

    @property
    def visible_flashcard(self) -> Flashcard | None:
        """Return the flashcard currently visible on the timer page."""
        return self._visible_flashcard

    @visible_flashcard.setter
    def visible_flashcard(self, value: Flashcard | None) -> None:
        self._visible_flashcard = value

    @property
    def flashcard_sequence(self) -> FlashcardSequenceController:
        """Return the flashcard phase-sequencing controller."""
        return self._flashcard_sequence

    @property
    def flashcard_sound_controller(self) -> TimedAudioPlaybackController:
        """Return the timed flashcard audio controller."""
        return self._flashcard_sound_controller

    def handle_timer_running_changed(self, is_running: bool) -> None:
        """Hide editing/navigation controls while timer is active."""
        if is_running and not self._study_session.active:
            if not self.start_study_session():
                self._timer_page.stop_timer()
                return
        self._set_navigation_visible(not is_running)
        if not is_running and self._is_flashcard_display_hidden():
            self.cancel_flashcard_phase_timer()
            self._flashcard_sequence.sequence_paused = False

    def handle_flashcard_pause_toggled(self, paused: bool) -> None:
        """Pause or resume flashcard phase timing."""
        if self._is_flashcard_display_hidden():
            return
        self._apply_flashcard_pause_toggle(paused)

    def handle_flashcard_queue_shuffle_requested(self) -> None:
        """Shuffle the remaining queue for the active queue-based session."""
        if not self._study_session.shuffle_remaining_queue():
            return
        self.refresh_queue_shuffle_action()

    def handle_timer_stop_requested(self) -> None:
        """Abort the current runtime study session."""
        self.reset_study_session_state()

    def start_flashcard_phase_timer(self, duration_milliseconds: int, callback) -> None:
        """Start single-shot phase timer used by flashcard question/answer flow."""
        if not self._flashcard_sequence.start_phase_timer(
            duration_milliseconds,
            callback,
        ):
            self.handle_flashcard_phase_timeout()

    def handle_flashcard_phase_timeout(self) -> None:
        """Run the pending flashcard phase callback, if one exists."""
        callback = self._flashcard_sequence.handle_phase_timeout()
        if callback is not None:
            callback()

    def cancel_flashcard_phase_timer(self) -> None:
        """Stop and clear pending flashcard phase callbacks."""
        self._flashcard_sequence.cancel_phase_timer()
        self._flashcard_sound_controller.stop()

    def handle_flashcard_phase_skip_requested(self) -> None:
        """Advance the current flashcard phase immediately."""
        if self._is_flashcard_display_hidden():
            return
        was_paused = self._flashcard_sequence.sequence_paused
        callback = self._flashcard_sequence.skip_phase()
        if callback is None:
            return
        self._flashcard_sound_controller.stop()
        callback()
        if was_paused:
            self.reapply_paused_state_after_phase_skip()

    def reapply_paused_state_after_phase_skip(self) -> None:
        """Keep study flow paused after manually advancing a paused phase."""
        if not self._is_flashcard_display_hidden():
            if self._timer_pause_button_can_pause():
                self._timer_page.pause_timer()
                return
            self._apply_flashcard_pause_toggle(True)
            return
        if self._timer_page.is_running and self._timer_page.pause_button.isEnabled():
            self._timer_page.pause_timer()

    def _is_flashcard_display_hidden(self) -> bool:
        """Return whether both flashcard labels are currently hidden."""
        return (
            self._timer_page.flashcard_question_label.isHidden()
            and self._timer_page.flashcard_answer_label.isHidden()
        )

    def _apply_flashcard_pause_toggle(self, paused: bool) -> None:
        """Apply pause or resume state to the active flashcard sequence.

        Args:
            paused: Whether the flashcard sequence should be paused.
        """
        self._flashcard_sequence.handle_pause_toggle(
            paused,
            flashcard_visible=True,
            pause_progress=self._timer_page.pause_flashcard_progress,
            resume_progress=self._timer_page.resume_flashcard_progress,
            on_timeout=self._handle_flashcard_phase_timeout,
        )

    def _timer_pause_button_can_pause(self) -> bool:
        """Return whether the timer pause button can enter paused state."""
        return (
            self._timer_page.pause_button.isEnabled()
            and self._timer_page.pause_button.text() == "Pause"
        )

    def reset_flashcard_sequence_order(self) -> None:
        """Reset sequential flashcard pointer to the first card."""
        self._flashcard_sequence.reset_order()

    def handle_timer_cycle_completed(self) -> None:
        """Advance the study session when a timer cycle finishes."""
        app_settings = self._load_settings()
        if (
            app_settings.timer_duration_seconds > 0
            and not self._should_show_flashcard_this_cycle(
                app_settings.flashcard_probability_percent
            )
        ):
            self._timer_page.restart_timer_cycle()
            return
        flashcard = self.next_flashcard_for_display()
        if flashcard is None:
            self.complete_study_session()
            return
        self._emit_show_flashcard(flashcard)

    def next_flashcard_for_display(self) -> Flashcard | None:
        """Return the next active flashcard for the current study session."""
        return self._study_session.next_flashcard()

    def start_study_session(self) -> bool:
        """Create a runtime-only study session for the current flashcard scope."""
        if not self._app_state.selected_folder_ids:
            QMessageBox.warning(
                self._parent,
                "Timer",
                "No folders selected. Select at least one folder to start a study session.",
            )
            return False
        if not self._app_state.loaded_flashcards:
            QMessageBox.warning(
                self._parent,
                "Timer",
                "No flashcards are available in selected folders. Study session not started.",
            )
            return False
        self.cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self.reset_flashcard_sequence_order()
        self._pending_flashcard_score = None
        session_keys = self.selected_study_session_keys()
        app_settings = self._load_settings()
        if not self._study_session.start(
            self._app_state.loaded_flashcards,
            initial_counters=self.initial_study_session_counters(session_keys),
            study_order_mode=app_settings.flashcard_study_order_mode,
            queue_start_shuffled=app_settings.flashcard_queue_start_shuffled,
            wrong_answer_completion_mode=app_settings.wrong_answer_completion_mode,
            wrong_answer_reinsertion_mode=app_settings.wrong_answer_reinsertion_mode,
            wrong_answer_reinsert_after_count=app_settings.wrong_answer_reinsert_after_count,
            choice_func=random.choice,
        ):
            QMessageBox.information(
                self._parent,
                "Timer",
                "All selected flashcards are already completed.",
            )
            return False
        self._active_study_session_keys = session_keys
        self.update_study_session_progress()
        return True

    def selected_study_session_keys(self) -> list[tuple[str, str]]:
        """Return folder/card keys for the currently selected study scope."""
        session_keys: list[tuple[str, str]] = []
        for item in self._iter_sidebar_folder_items():
            folder_id = item.data(Qt.UserRole)
            if folder_id is None or item.checkState() != Qt.Checked:
                continue
            folder_flashcards = self._app_state.flashcards_by_folder.get(folder_id, [])
            selected_indexes = self._app_state.selected_flashcard_indexes_by_folder.get(
                folder_id,
                set(range(len(folder_flashcards))),
            )
            for flashcard_index, flashcard in enumerate(folder_flashcards):
                if flashcard_index not in selected_indexes or not flashcard.stable_id:
                    continue
                session_keys.append((folder_id, flashcard.stable_id))
        return session_keys

    def initial_study_session_counters(
        self,
        session_keys: list[tuple[str, str]],
    ) -> list[SessionCardCounters]:
        """Return persisted counters aligned with the selected session order."""
        progress_by_folder = {
            folder_id: load_folder_progress(folder_id)
            for folder_id in self._app_state.selected_folder_ids
        }
        counters: list[SessionCardCounters] = []
        for folder_id, flashcard_id in session_keys:
            flashcard_progress = progress_by_folder.get(folder_id, {}).get(flashcard_id)
            counters.append(
                SessionCardCounters(
                    wrong_count=(
                        flashcard_progress.wrong_count
                        if flashcard_progress is not None
                        else 0
                    ),
                    correct_count=(
                        flashcard_progress.correct_count
                        if flashcard_progress is not None
                        else 0
                    ),
                )
            )
        return counters

    def persist_active_study_session_progress(self, session_indexes: list[int]) -> None:
        """Persist counters for specific flashcards tracked in the session."""
        if not session_indexes or not self._active_study_session_keys:
            return
        if len(self._active_study_session_keys) != len(
            self._study_session.card_counters
        ):
            return
        progress_entries: list[FlashcardProgressEntry] = []
        updated_folder_ids: set[str] = set()
        for session_index in session_indexes:
            if not (0 <= session_index < len(self._active_study_session_keys)):
                continue
            folder_id, flashcard_id = self._active_study_session_keys[session_index]
            counters = self._study_session.card_counters[session_index]
            updated_folder_ids.add(folder_id)
            progress_entries.append(
                FlashcardProgressEntry(
                    folder_id=folder_id,
                    flashcard_id=flashcard_id,
                    progress=reviewed_progress(
                        counters.correct_count,
                        counters.wrong_count,
                    ),
                )
            )
        save_progress_entries(progress_entries)
        self._refresh_sidebar_folder_progress_labels(updated_folder_ids)

    def update_study_session_progress(self) -> None:
        """Refresh visible study progress for the timer page."""
        progress = self._study_session.progress()
        self._timer_page.set_session_progress(
            completed_count=progress.completed_count,
            remaining_count=progress.remaining_count,
            wrong_pending_count=progress.wrong_pending_count,
            total_count=progress.total_count,
        )
        self.refresh_queue_shuffle_action()

    def reset_study_session_state(self) -> None:
        """Clear all runtime-only study session state."""
        self.cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self.reset_flashcard_sequence_order()
        self._study_session.reset()
        self._active_study_session_keys = []
        self._pending_flashcard_score = None
        self._visible_flashcard = None
        self._timer_page.clear_session_progress()
        self.refresh_queue_shuffle_action()

    def complete_study_session(self) -> None:
        """Stop the timer UI after the active session is fully completed."""
        self.reset_study_session_state()
        self._timer_page.stop_timer()

    def play_flashcard_notification_sound(
        self,
        *,
        question_phase: bool,
        phase_duration_ms: int,
    ) -> None:
        """Play the configured flashcard sound for the current phase."""
        if not self._flashcard_sound_controller.is_available:
            return
        settings = self._load_settings()
        configured_sound_path = (
            settings.question_notification_sound_path
            if question_phase
            else settings.answer_notification_sound_path
        )
        sound_path_value = configured_sound_path or self._default_sound_path_getter()
        if not sound_path_value:
            return
        sound_path = Path(sound_path_value)
        if not sound_path.exists():
            return
        self._flashcard_sound_controller.play(
            sound_path,
            max_duration_ms=phase_duration_ms,
            context="question" if question_phase else "answer",
        )

    def show_current_flashcard_answer(
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
        self.show_flashcard_answer(
            sequence_id,
            current_flashcard.answer,
            current_flashcard.answer_image_path,
            answer_display_duration_seconds,
        )

    def show_flashcard_answer(
        self,
        sequence_id: int,
        answer: str,
        answer_image_path: str | None,
        answer_display_duration_seconds: int,
    ) -> None:
        """Show the answer phase for the active flashcard sequence."""
        if (
            sequence_id != self._flashcard_sequence.active_sequence_id
            or self._timer_page.is_running
            or self._timer_page.flashcard_question_label.isHidden()
        ):
            return
        self._timer_page.show_flashcard_answer(
            answer,
            self._resolved_flashcard_image_path(answer_image_path),
            answer_display_duration_seconds,
        )
        self.play_flashcard_notification_sound(
            question_phase=False,
            phase_duration_ms=answer_display_duration_seconds * 1000,
        )
        self._start_flashcard_phase_timer(
            answer_display_duration_seconds * 1000,
            lambda: self.finish_flashcard_answer_phase(sequence_id),
        )

    def finish_flashcard_answer_phase(self, sequence_id: int) -> None:
        """Apply the queued answer choice only after the answer timer finishes."""
        if (
            sequence_id != self._flashcard_sequence.active_sequence_id
            or self._timer_page.is_running
            or self._is_flashcard_display_hidden()
        ):
            return
        selected_score = self._pending_flashcard_score
        session_flashcard_index = self._study_session.current_flashcard_index
        self._study_session.apply_current_score(self._pending_flashcard_score)
        if (
            selected_score in {"correct", "wrong"}
            and session_flashcard_index is not None
        ):
            self.persist_active_study_session_progress([session_flashcard_index])
        self.advance_after_flashcard_score()

    def show_flashcard_popup(self, flashcard: object) -> None:
        """Show flashcard question/answer inside the timer page."""
        if not isinstance(flashcard, Flashcard):
            return
        app_settings = self._load_settings()
        self.cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self._pending_flashcard_score = None
        self._visible_flashcard = flashcard
        sequence_id = self._flashcard_sequence.begin_sequence()
        self._switch_to_timer()
        self._set_navigation_visible(False)
        self._timer_page.show_flashcard_question(
            flashcard.question,
            self._resolved_flashcard_image_path(flashcard.question_image_path),
            app_settings.question_display_duration_seconds,
        )
        self.refresh_queue_shuffle_action()
        self.play_flashcard_notification_sound(
            question_phase=True,
            phase_duration_ms=app_settings.question_display_duration_seconds * 1000,
        )
        self._start_flashcard_phase_timer(
            app_settings.question_display_duration_seconds * 1000,
            lambda: self.show_current_flashcard_answer(
                sequence_id,
                app_settings.answer_display_duration_seconds,
            ),
        )

    def _resolved_flashcard_image_path(self, image_path: str | None) -> str | None:
        """Return one absolute image path for timer-page rendering."""
        if image_path is None or self._visible_flashcard is None:
            return None
        candidate_path = Path(image_path)
        if candidate_path.is_absolute():
            return str(candidate_path)
        return str(self._visible_flashcard.source_file.parent / candidate_path)

    def advance_after_flashcard_score(self) -> None:
        """Continue or finish the session after scoring the current flashcard."""
        self.cancel_flashcard_phase_timer()
        self._flashcard_sequence.sequence_paused = False
        self._pending_flashcard_score = None
        self._visible_flashcard = None
        self.update_study_session_progress()
        if self._study_session.is_complete():
            self.complete_study_session()
            return
        if not self._timer_page.has_countdown_duration():
            self._handle_timer_cycle_completed()
            return
        self._timer_page.clear_flashcard_display()
        self._timer_page.restart_timer_cycle()

    def refresh_queue_shuffle_action(self) -> None:
        """Reflect queue-shuffle availability in the timer page."""
        self._timer_page.set_queue_shuffle_available(self.can_shuffle_remaining_queue())

    def can_shuffle_remaining_queue(self) -> bool:
        """Return whether the remaining session queue can be shuffled."""
        return (
            self._study_session.active
            and self._study_session.study_order_mode is StudyOrderMode.QUEUE
            and len(self._study_session.queued_flashcard_indexes()) > 1
        )

    def handle_flashcard_marked_correct(self) -> None:
        """Queue the selected Correct state until answer timeout."""
        self._queue_selected_flashcard_score()

    def handle_flashcard_marked_wrong(self) -> None:
        """Queue the selected Wrong state until answer timeout."""
        self._queue_selected_flashcard_score()

    def _queue_selected_flashcard_score(self) -> None:
        """Store the currently selected flashcard score for delayed apply."""
        if self._study_session.current_flashcard() is None:
            return
        self._pending_flashcard_score = self._timer_page.selected_flashcard_score()

    def refresh_active_study_session_after_progress_reset(
        self,
        folder_ids: set[str],
    ) -> None:
        """Rebuild the active study session when reset affects selected folders."""
        if not self._study_session.active:
            return
        session_folder_ids = {
            folder_id for folder_id, _flashcard_id in self._active_study_session_keys
        }
        if not folder_ids.intersection(session_folder_ids):
            return
        self.reset_study_session_state()
        if (
            not self._app_state.selected_folder_ids
            or not self._app_state.loaded_flashcards
        ):
            return
        self.start_study_session()

    def _should_show_flashcard_this_cycle(self, probability_percent: int) -> bool:
        """Return whether the current timer cycle should show a flashcard."""
        normalized_probability = max(0, min(100, int(probability_percent)))
        if normalized_probability <= 0:
            return False
        if normalized_probability >= 100:
            return True
        return random.randint(1, 100) <= normalized_probability
