"""Flashcard sequence state and timer helpers."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer

from estudai.services.csv_flashcards import Flashcard

__all__ = ["FlashcardSequenceController"]


class FlashcardSequenceController:
    """Encapsulate flashcard ordering and phase-timer state."""

    def __init__(self, phase_timer: QTimer) -> None:
        """Initialize the sequence controller."""
        self.phase_timer = phase_timer
        self.active_sequence_id = 0
        self.next_flashcard_index = 0
        self.pending_phase_callback: Callable[[], None] | None = None
        self.phase_remaining_ms = 0
        self.sequence_paused = False

    def reset_order(self) -> None:
        """Reset sequential flashcard pointer to the first card."""
        self.next_flashcard_index = 0

    def next_flashcard(
        self,
        flashcards: list[Flashcard],
        *,
        random_order: bool,
        choice_func: Callable[[list[Flashcard]], Flashcard],
    ) -> Flashcard | None:
        """Return the next flashcard for the current selection."""
        if not flashcards:
            return None
        if random_order:
            return choice_func(flashcards)
        flashcard = flashcards[self.next_flashcard_index % len(flashcards)]
        self.next_flashcard_index = (self.next_flashcard_index + 1) % len(flashcards)
        return flashcard

    def next_flashcard_index_for_session(
        self,
        active_indexes: list[int],
        total_flashcards: int,
        *,
        random_order: bool,
        choice_func: Callable[[list[int]], int],
    ) -> int | None:
        """Return the next active flashcard index for the current session."""
        if not active_indexes or total_flashcards <= 0:
            return None
        if random_order:
            return choice_func(active_indexes)
        active_index_set = set(active_indexes)
        start_index = self.next_flashcard_index % total_flashcards
        for offset in range(total_flashcards):
            flashcard_index = (start_index + offset) % total_flashcards
            if flashcard_index not in active_index_set:
                continue
            self.next_flashcard_index = (flashcard_index + 1) % total_flashcards
            return flashcard_index
        return None

    def begin_sequence(self) -> int:
        """Start a new flashcard sequence and return its id."""
        self.active_sequence_id += 1
        return self.active_sequence_id

    def start_phase_timer(
        self,
        duration_milliseconds: int,
        callback: Callable[[], None],
    ) -> bool:
        """Start a single-shot phase timer.

        Returns:
            bool: True when the timer was started, False when callback should run now.
        """
        self.phase_timer.stop()
        self.pending_phase_callback = callback
        self.phase_remaining_ms = max(0, int(duration_milliseconds))
        if self.phase_remaining_ms <= 0:
            return False
        self.phase_timer.start(self.phase_remaining_ms)
        return True

    def handle_phase_timeout(self) -> Callable[[], None] | None:
        """Return and clear the pending phase callback."""
        callback = self.pending_phase_callback
        self.pending_phase_callback = None
        self.phase_remaining_ms = 0
        return callback

    def cancel_phase_timer(self) -> None:
        """Stop and clear pending phase state."""
        self.phase_timer.stop()
        self.pending_phase_callback = None
        self.phase_remaining_ms = 0

    def skip_phase(self) -> Callable[[], None] | None:
        """Return the pending phase callback after cancelling the active timer."""
        callback = self.pending_phase_callback
        self.cancel_phase_timer()
        return callback

    def handle_pause_toggle(
        self,
        paused: bool,
        *,
        flashcard_visible: bool,
        pause_progress: Callable[[], None],
        resume_progress: Callable[[int], None],
        on_timeout: Callable[[], None],
    ) -> None:
        """Pause or resume flashcard phase timing."""
        if not flashcard_visible:
            return
        self.sequence_paused = paused
        if paused:
            if self.phase_timer.isActive():
                self.phase_remaining_ms = max(0, self.phase_timer.remainingTime())
                self.phase_timer.stop()
            pause_progress()
            return
        if self.pending_phase_callback is None:
            return
        if self.phase_remaining_ms <= 0:
            on_timeout()
            return
        resume_progress(self.phase_remaining_ms)
        self.phase_timer.start(self.phase_remaining_ms)
